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

    # Use the user's real Chrome (not Playwright's bundled Chromium) so that
    # Google OAuth trusts the browser. Also keep a persistent profile so
    # Google remembers the device after the first successful login.
    profile_dir = pathlib.Path.home() / ".airouter" / "chrome-profile" / provider
    profile_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel="chrome",                 # real Chrome, not Chromium
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(LOGIN_URLS[provider])
        try:
            await _wait_until_logged_in(page, provider)
        except TimeoutError as e:
            print(f"error: {e}")
            await ctx.close()
            return 1

        state = await ctx.storage_state()

        # ── Capture IndexedDB (Playwright's storage_state does not include it) ──
        try:
            idb = await page.evaluate("""async () => {
    if (!indexedDB.databases) return {};
    const dbs = await indexedDB.databases();
    const out = {};
    for (const info of dbs) {
        if (!info.name) continue;
        try {
            const db = await new Promise((resolve, reject) => {
                const req = indexedDB.open(info.name);
                req.onsuccess = () => resolve(req.result);
                req.onerror = () => reject(req.error);
            });
            const stores = Array.from(db.objectStoreNames);
            out[info.name] = {};
            for (const sn of stores) {
                try {
                    const tx = db.transaction(sn, 'readonly');
                    const store = tx.objectStore(sn);
                    const all = await new Promise((resolve, reject) => {
                        const req = store.getAll();
                        req.onsuccess = () => resolve(req.result);
                        req.onerror = () => reject(req.error);
                    });
                    // JSON-stringify each value; IDB values may be Maps/objects
                    out[info.name][sn] = all.map(v => {
                        try { return JSON.parse(JSON.stringify(v)); }
                        catch { return String(v); }
                    });
                } catch (e) { out[info.name][sn] = []; }
            }
            db.close();
        } catch (e) {}
    }
    return out;
}""")
            if idb:
                state["_ainterceptor_idb"] = idb
                print(f"[agent] captured IndexedDB: {list(idb.keys())}")
            else:
                print("[agent] no IndexedDB captured")
        except Exception as e:
            print(f"[agent] IndexedDB read failed: {e}")

        await ctx.close()

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
