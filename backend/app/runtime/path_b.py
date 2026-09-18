"""Path B — drive a real Chrome.

Two modes:
  1. HOST CDP (default in Docker): connect to a Chrome running on the
     host (Windows dev) or sibling container via CDP. Uses the real
     logged-in session and real Chrome fingerprint — Cloudflare-trusted.
  2. IN-CONTAINER HEADLESS: fallback when no host CDP is reachable.
     Works for lenient providers (DeepSeek); blocked by Cloudflare on
     Claude and ChatGPT.
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


# Where to reach the host from inside a container. Override with env.
def _cdp_hosts():
    env = os.environ.get("AINTERCEPTOR_HOST_CDP_BASE")
    if env:
        return [env]
    return ["127.0.0.1", "host.docker.internal"]

HOST_CDP_BASE = _cdp_hosts()[0]  # legacy compat


PROVIDERS = {
    "deepseek": {
        "url": "https://chat.deepseek.com/",
        "cdp_port": 9223,
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
    "claude": {
        "url": "https://claude.ai/",
        "cdp_port": 9222,
        "login_markers": ("/login", "/auth", "/signin"),
        "composer": [
            'div[contenteditable="true"]',
            "textarea",
            '[role="textbox"]',
        ],
        "reply": [
            '[data-testid*="assistant"]',
            ".font-claude-message",
            "div.progressive-markdown",
            ".whitespace-pre-wrap",
        ],
    },
    "chatgpt": {
        "url": "https://chatgpt.com/",
        "cdp_port": 9224,
        "login_markers": ("/auth/login", "/auth/0"),
        "composer": [
            "#prompt-textarea",
            'div[contenteditable="true"]',
            "textarea",
        ],
        "reply": [
            '[data-message-author-role="assistant"]',
            ".markdown",
            ".prose",
        ],
    },
    "gemini": {
        "url": "https://gemini.google.com/",
        "cdp_port": 9225,
        "login_markers": ("/accounts/", "signin"),
        "composer": [
            "rich-textarea div[contenteditable='true']",
            "rich-textarea [contenteditable='true']",
            'div[contenteditable="true"]',
            "textarea",
        ],
        "reply": [
            "message-content",
            ".model-response-text",
            ".response-container",
            "model-response",
        ],
    },
}


async def _find_composer(page, selectors):
    """Find an editable composer, walking shadow DOM if needed."""
    for sel in selectors:
        try:
            loc = page.locator(sel)
            n = await loc.count()
            for i in range(n - 1, -1, -1):
                cand = loc.nth(i)
                try:
                    if await cand.is_visible() and await cand.is_editable():
                        return cand
                except Exception:
                    pass
        except Exception:
            continue
    # Shadow DOM traversal via JS
    try:
        handle = await page.evaluate_handle("""
            () => {
                const sels = ['rich-textarea [contenteditable="true"]',
                              'div[contenteditable="true"]',
                              'textarea',
                              '[role="textbox"]'];
                function walk(root) {
                    for (const s of sels) {
                        const el = root.querySelector(s);
                        if (el && el.offsetParent) return el;
                    }
                    const all = root.querySelectorAll('*');
                    for (const el of all) {
                        if (el.shadowRoot) {
                            const found = walk(el.shadowRoot);
                            if (found) return found;
                        }
                    }
                    return null;
                }
                return walk(document);
            }
        """)
        if handle:
            el = handle.as_element()
            if el is not None:
                return el
    except Exception as e:
        _dbg(f"shadow DOM traversal failed: {e}")
    return None


async def _read_last_reply(page, selectors):
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
    # Shadow DOM fallback
    try:
        txt = await page.evaluate("""
            () => {
                const sels = ['message-content', '.model-response-text',
                              '.response-container', 'model-response'];
                function walk(root) {
                    for (const s of sels) {
                        const els = root.querySelectorAll(s);
                        if (els.length) {
                            const t = (els[els.length-1].innerText||'').trim();
                            if (t) return t;
                        }
                    }
                    for (const el of root.querySelectorAll('*')) {
                        if (el.shadowRoot) {
                            const r = walk(el.shadowRoot);
                            if (r) return r;
                        }
                    }
                    return '';
                }
                return walk(document);
            }
        """)
        if txt:
            return txt.strip()
    except Exception:
        pass
    return ""


async def _submit_and_wait(page, cfg, prompt, deadline_s=120.0, stable_for_s=2.5):
    import time
    composer = await _find_composer(page, cfg["composer"])
    if composer is None:
        raise PathBError("composer not found")
    await composer.click()
    try:
        await composer.fill(prompt)
    except Exception:
        await composer.type(prompt, delay=5)
    await composer.press("Enter")

    t0 = time.monotonic()
    last = ""
    last_change = t0
    while time.monotonic() - t0 < deadline_s:
        await asyncio.sleep(0.4)
        cur = await _read_last_reply(page, cfg["reply"])
        if not cur:
            continue
        if cur != last:
            last = cur
            last_change = time.monotonic()
            continue
        if time.monotonic() - last_change >= stable_for_s:
            return cur
    if last:
        return last
    raise PathBError("no reply observed")


async def _via_host_cdp(provider: str, cfg: dict, prompt: str) -> str:
    """Attach to a Chrome running on the host; drive the right tab."""
    from playwright.async_api import async_playwright
    url = f"http://{HOST_CDP_BASE}:{cfg['cdp_port']}"
    _dbg(f"connecting to host CDP {url}")
    async with async_playwright() as pw:
        try:
            browser = await asyncio.wait_for(
                pw.chromium.connect_over_cdp(url), timeout=10)
        except Exception as e:
            raise PathBError(f"host CDP unreachable at {url}: {e}")

        contexts = browser.contexts
        if not contexts:
            raise PathBError("host CDP has no context")
        ctx = contexts[0]
        # Find a tab on the provider's host
        host = cfg["url"].split("://")[-1].split("/")[0]
        page = None
        for p in ctx.pages:
            try:
                if host in (p.url or ""):
                    page = p
                    break
            except Exception:
                continue
        if page is None:
            _dbg(f"no tab for {host}; opening a new one")
            page = await ctx.new_page()
            await page.goto(cfg["url"], wait_until="domcontentloaded", timeout=30000)

        await asyncio.sleep(1.0)
        url_now = (page.url or "").lower()
        if any(m.lower() in url_now for m in cfg["login_markers"]):
            raise PathBError(f"{provider}: host tab is on login page")
        # If a Cloudflare challenge is up, bail
        title = (await page.title() or "").lower()
        if "just a moment" in title or "attention required" in title:
            raise PathBError(f"{provider}: Cloudflare challenge on host tab")

        _dbg(f"submitting to {host} tab")
        return await _submit_and_wait(page, cfg, prompt)


async def _via_in_container(provider: str, cfg: dict, session_state: dict,
                             prompt: str) -> str:
    """Fallback: headless Chromium inside the container. Lenient providers only."""
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-gpu",
        ])
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
            await page.goto(cfg["url"], wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2.0)
            title = (await page.title() or "").lower()
            if "just a moment" in title:
                raise PathBError(f"{provider}: Cloudflare challenge (in-container headless)")
            if any(m.lower() in (page.url or "").lower() for m in cfg["login_markers"]):
                raise PathBError(f"{provider}: session expired in headless mode")
            return await _submit_and_wait(page, cfg, prompt)
        finally:
            await browser.close()


async def stream_b(provider: str, session_state: dict, prompt: str) -> AsyncIterator[str]:
    if provider not in PROVIDERS:
        raise PathBError(f"provider {provider} not in path B registry")
    cfg = PROVIDERS[provider]

    # Prefer host CDP (real Chrome, Cloudflare-trusted)
    errors = []
    try:
        text = await _via_host_cdp(provider, cfg, prompt)
        yield text
        return
    except PathBError as e:
        errors.append(f"host: {e}")
        _dbg(f"host CDP failed: {e}")

    # Fall back to in-container headless
    try:
        text = await _via_in_container(provider, cfg, session_state, prompt)
        yield text
        return
    except PathBError as e:
        errors.append(f"headless: {e}")

    raise PathBError(" | ".join(errors))
