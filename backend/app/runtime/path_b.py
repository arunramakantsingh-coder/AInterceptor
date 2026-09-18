"""Path B — headless Chromium inside the container.

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
