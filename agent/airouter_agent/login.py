"""Provider login flow: opens a real Chrome, waits for login, uploads state."""
from __future__ import annotations
import asyncio, json, pathlib, sys, tempfile
import httpx

LOGIN_URLS = {
    "claude":   "https://claude.ai/",
    "chatgpt":  "https://chatgpt.com/",
    "gemini":   "https://gemini.google.com/",
    "deepseek": "https://chat.deepseek.com/",
}
LOGIN_MARKERS = {
    "claude":   ("/login", "/auth", "/signin"),
    "chatgpt":  ("/auth/login", "/auth/0"),
    "gemini":   ("/accounts/", "signin"),
    "deepseek": ("/login", "/auth", "/sign_in", "/signin"),
}


async def _wait_until_logged_in(page, provider: str, timeout: int = 600) -> None:
    markers = LOGIN_MARKERS[provider]
    import time
    t0 = time.monotonic()
    print("Waiting for you to log in (up to 10 minutes)…")
    while time.monotonic() - t0 < timeout:
        await asyncio.sleep(2)
        url = (page.url or "").lower()
        if not any(m.lower() in url for m in markers):
            await asyncio.sleep(2)
            if not any(m.lower() in (page.url or "").lower() for m in markers):
                print("Login detected.")
                return
    raise TimeoutError("login did not complete in time")


async def run_login(provider: str, server: str, token: str) -> int:
    if provider not in LOGIN_URLS:
        print(f"unknown provider: {provider}")
        return 1
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("playwright not installed. Run:")
        print("  pip install playwright")
        print("  python -m playwright install chromium")
        return 1

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(LOGIN_URLS[provider])
        try:
            await _wait_until_logged_in(page, provider)
        except TimeoutError as e:
            print(f"error: {e}")
            await browser.close()
            return 1

        state = await ctx.storage_state()
        await browser.close()

    tmp = pathlib.Path(tempfile.mkstemp(suffix=".json")[1])
    tmp.write_text(json.dumps(state), encoding="utf-8")

    print(f"Uploading {provider} session to {server}…")
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            with open(tmp, "rb") as fh:
                files = {"file": ("storage_state.json", fh, "application/json")}
                data = {"provider": provider, "alias": "default"}
                r = await c.post(f"{server.rstrip('/')}/api/sessions/upload",
                                 headers={"Authorization": f"Bearer {token}"},
                                 files=files, data=data)
        if r.status_code != 200:
            print(f"upload failed: {r.status_code} {r.text}")
            return 1
        print(f"Session for {provider} uploaded successfully.")
        return 0
    finally:
        try: tmp.unlink()
        except Exception: pass


def login_sync(provider: str, server: str, token: str) -> int:
    return asyncio.run(run_login(provider, server, token))
