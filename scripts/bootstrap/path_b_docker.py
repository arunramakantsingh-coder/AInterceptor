import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend" / "app"
(BE / "runtime").mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# path_b.py — headless Chromium inside the container
# ═══════════════════════════════════════════════════════════════
(BE / "runtime" / "path_b.py").write_text('''"""Path B — headless Chromium inside the container.

Loads the user's storage_state into a Playwright context, navigates to
the provider home, submits the prompt, and reads the reply from the DOM.

Runs entirely inside the container. No display, no Xvfb, no VNC.
"""
from __future__ import annotations
import asyncio, os, sys
from typing import AsyncIterator


class PathBError(Exception):
    pass


DEBUG = os.environ.get("AINTERCEPTOR_PATH_B_DEBUG") == "1"

def _dbg(*a):
    if DEBUG:
        print("[path_b]", *a, file=sys.stderr, flush=True)


# Home URLs and login markers per provider
PROVIDERS = {
    "deepseek": {
        "url": "https://chat.deepseek.com/",
        "login_markers": ("/login", "/auth", "/sign_in", "/signin"),
        "composer": [
            'textarea[placeholder*="Message"]',
            'textarea[placeholder*="message"]',
            "textarea",
            '[contenteditable="true"]',
            '[role="textbox"]',
        ],
        "reply": [".ds-markdown", ".ds-markdown--block", '[class*="ds-markdown"]'],
    },
    "chatgpt": {
        "url": "https://chatgpt.com/",
        "login_markers": ("/auth/login",),
        "composer": ["#prompt-textarea", 'div[contenteditable="true"]', "textarea"],
        "reply": ['[data-message-author-role="assistant"]', ".markdown", ".prose"],
    },
    "gemini": {
        "url": "https://gemini.google.com/",
        "login_markers": ("/accounts/", "signin"),
        "composer": ['div[contenteditable="true"]', "textarea", "rich-textarea"],
        "reply": ["message-content", ".model-response-text", ".response-container"],
    },
    "claude": {
        "url": "https://claude.ai/",
        "login_markers": ("/login", "/auth", "/signin"),
        "composer": ['div[contenteditable="true"]', "textarea"],
        "reply": ['[data-testid*="assistant"]', ".font-claude-message",
                  'div[class*="progressive"]', ".whitespace-pre-wrap"],
    },
}


async def _find_composer(page, selectors):
    for sel in selectors:
        try:
            loc = page.locator(sel)
            n = await loc.count()
            for i in range(n - 1, -1, -1):
                cand = loc.nth(i)
                if await cand.is_visible() and await cand.is_editable():
                    return cand
        except Exception:
            continue
    return None


async def _read_last_reply(page, selectors):
    """Read the newest assistant reply from the DOM."""
    for sel in selectors:
        try:
            loc = page.locator(sel)
            n = await loc.count()
            if n == 0:
                continue
            txt = (await loc.nth(n - 1).inner_text()).strip()
            if txt:
                return txt
        except Exception:
            continue
    return ""


async def _submit_and_wait(page, cfg, prompt, deadline_s: float = 120.0,
                            stable_for_s: float = 2.5) -> str:
    import time
    composer = await _find_composer(page, cfg["composer"])
    if composer is None:
        raise PathBError("composer not found")
    await composer.click()
    try:
        await composer.fill(prompt)
    except Exception:
        # contenteditable sometimes needs type instead of fill
        await composer.type(prompt, delay=5)
    await composer.press("Enter")

    # Wait for reply text to appear and stabilize
    t0 = time.monotonic()
    last = ""
    last_change = t0
    seen = False
    while time.monotonic() - t0 < deadline_s:
        await asyncio.sleep(0.4)
        cur = await _read_last_reply(page, cfg["reply"])
        if not cur:
            continue
        seen = True
        if cur != last:
            last = cur
            last_change = time.monotonic()
            continue
        if time.monotonic() - last_change >= stable_for_s:
            return cur
    if last:
        return last
    raise PathBError("no reply observed")


async def stream_b(provider: str, session_state: dict, prompt: str) -> AsyncIterator[str]:
    """Drive provider web UI in a headless Chromium; yield the final text once."""
    if provider not in PROVIDERS:
        raise PathBError(f"provider {provider} not in path B registry")
    cfg = PROVIDERS[provider]
    _dbg(f"starting headless Chromium for {provider}")
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise PathBError("playwright not installed in container")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
            ],
        )
        try:
            ctx = await browser.new_context(
                storage_state=session_state,
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/130.0.0.0 Safari/537.36"),
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            page = await ctx.new_page()
            _dbg(f"navigating to {cfg['url']}")
            await page.goto(cfg["url"], wait_until="domcontentloaded", timeout=45_000)
            await asyncio.sleep(2.0)
            url = (page.url or "").lower()
            if any(m.lower() in url for m in cfg["login_markers"]):
                raise PathBError(f"{provider} session expired — re-run agent login")

            _dbg(f"submitting prompt ({len(prompt)} chars)")
            reply = await _submit_and_wait(page, cfg, prompt)
            _dbg(f"got reply ({len(reply)} chars)")
            yield reply
        finally:
            await browser.close()
''', encoding="utf-8", newline="\n")
print("  [OK] path_b.py — 4 providers wired")

# ═══════════════════════════════════════════════════════════════
# Dispatcher — try A, fall back to B
# ═══════════════════════════════════════════════════════════════
(BE / "runtime" / "dispatcher.py").write_text('''"""Path A vs Path B selection per provider.

A = direct HTTPS with cookies  (fast, ~0.5 s, ~1 MB)
B = headless Chromium          (universal, ~3-8 s, ~100 MB)

Try A first for providers that support it. On any Path A failure, fall
back to B automatically. Providers marked B-only skip A entirely.
"""
from __future__ import annotations
from typing import AsyncIterator
from app.runtime import path_a, path_b
from app.providers_list import ALL_PROVIDERS, PATH_A_SUPPORTED, PATH_B_REQUIRED


class ProviderUnavailable(Exception):
    pass


async def stream_reply(provider: str, session_state: dict,
                       prompt: str) -> AsyncIterator[str]:
    if provider not in ALL_PROVIDERS:
        raise ProviderUnavailable(f"unknown provider: {provider}")

    a_ok = provider in PATH_A_SUPPORTED

    if a_ok:
        emitted = 0
        a_failed = None
        try:
            async for delta in path_a.stream(provider, session_state, prompt):
                if delta:
                    emitted += 1
                    yield delta
            if emitted > 0:
                return
            a_failed = "path A returned no text"
        except path_a.PathAError as e:
            a_failed = f"path A: {e}"
        except Exception as e:
            a_failed = f"path A error: {e}"
        # Fall through to B

    # Path B (headless Chromium)
    try:
        async for delta in path_b.stream_b(provider, session_state, prompt):
            if delta:
                yield delta
        return
    except path_b.PathBError as e:
        # If A was tried and failed, surface both
        if a_ok:
            raise ProviderUnavailable(
                f"{provider}: A failed ({a_failed}); B failed ({e})")
        raise ProviderUnavailable(f"{provider} path B: {e}")
    except Exception as e:
        raise ProviderUnavailable(f"{provider} path B error: {e}")
''', encoding="utf-8", newline="\n")
print("  [OK] dispatcher.py — A→B fallback")

# ═══════════════════════════════════════════════════════════════
# Syntax + commit
# ═══════════════════════════════════════════════════════════════
import ast
for f in ["runtime/path_a.py", "runtime/path_b.py", "runtime/dispatcher.py"]:
    try:
        ast.parse((BE / f).read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {f}: {e}"); sys.exit(1)
print("  [OK] syntax valid")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "feat(phase-2): Path B (headless Chromium in container) + A→B fallback dispatcher"])
print((r.stdout.strip() or r.stderr.strip())[:300])
print()
print("Next: rebuild container, test DeepSeek live.")
