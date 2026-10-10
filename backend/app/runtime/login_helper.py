"""Bring daemon-owned Chrome on-screen so user can log into a provider.

Flow:
  1. Find the provider tab in the running supervisor
  2. Move Chrome window on-screen (100, 100)
  3. Bring the tab to front
  4. Navigate to provider home if the tab is stale
  5. Poll login markers every 2s until login detected (or timeout)
  6. Capture storage_state + IndexedDB
  7. Save to <export_dir>/<provider>.json
  8. Move Chrome back off-screen
  9. Return {ok, saved_path, took_s}
"""
from __future__ import annotations
import asyncio
import json
import pathlib
import time
from typing import Any


# login markers per provider — URL fragments indicating "not logged in"
LOGIN_MARKERS: dict[str, tuple[str, ...]] = {
    # Original 10
    "claude":      ("/login", "/auth", "/signin", "claude.ai/login"),
    "chatgpt":     ("/auth/login", "/auth/0", "/login"),
    "gemini":      ("/accounts/", "signin", "accounts.google.com"),
    "deepseek":    ("/login", "/auth", "/sign_in", "/signin"),
    "mistral":     ("/login", "/auth", "/signin", "/sign-in"),
    "qwen":        ("/login", "/auth", "/signin"),
    "huggingchat": ("/login", "/auth", "signin"),
    "perplexity":  ("/login", "/auth"),
    "grok":        ("/login", "/auth", "/signin"),
    "poe":         ("/login", "/auth", "/signin"),
    # New 10 (Tier A)
    "kimi":        ("/login", "/auth", "/signin"),
    "yi":          ("/login", "/signin", "/auth"),
    "lechat":      ("/login", "/auth", "/signin"),
    "glm":         ("/login", "/auth", "/signin"),
    "you":         ("/login", "/signin"),
    "phind":       ("/login", "/signin"),
    "doubao":      ("/login", "/signin", "/auth"),
    # New 3 (Tier B)
    "copilot":     ("/login", "/signin", "login.live.com"),
    "meta":        ("/login", "/signin", "facebook.com/login", "instagram.com/accounts/login"),
    "character":   ("/login", "/signin", "plus.character.ai"),
}

# how long to wait for login (seconds)
LOGIN_TIMEOUT_S = 300     # 5 min


def _is_login_page(provider: str, url: str) -> bool:
    markers = LOGIN_MARKERS.get(provider, ("/login", "/auth"))
    u = (url or "").lower()
    return any(m.lower() in u for m in markers)


async def begin_login(provider: str, supervisor: Any, export_dir: pathlib.Path,
                      logger=None) -> dict:
    log = logger or (lambda m: print(f"[login] {m}", flush=True))

    # ── 1. Validate provider + get tab ──
    if provider not in LOGIN_MARKERS:
        return {"ok": False, "error": f"unknown provider: {provider}"}

    tab = await supervisor.get_tab(provider)
    if tab.page is None or tab.page.is_closed():
        return {"ok": False, "error": f"{provider} tab is not available"}

    # ── 2. Bring Chrome on-screen ──
    log(f"bringing Chrome on-screen for {provider}")
    from app.runtime.browser_supervisor import push_chrome_off_screen  # keep import path stable
    _move_chrome(100, 100)

    # ── 3. Focus the tab + reload home ──
    try:
        await tab.page.bring_to_front()
    except Exception:
        pass
    try:
        # only reload if the tab is not on the provider's host
        from app.runtime.browser_supervisor import PROVIDER_URLS
        home = PROVIDER_URLS.get(provider)
        if home and home not in (tab.page.url or ""):
            log(f"navigating {provider} tab to {home}")
            await tab.page.goto(home, wait_until="domcontentloaded", timeout=45_000)
    except Exception as e:
        log(f"navigate failed (continuing): {e}")

    log(f"USER ACTION: log in to {provider} in the Chrome window")
    log(f"waiting up to {LOGIN_TIMEOUT_S}s for login to complete")

    # ── 4. Poll for login success ──
    t0 = time.monotonic()
    logged_in = False
    while time.monotonic() - t0 < LOGIN_TIMEOUT_S:
        await asyncio.sleep(2.0)
        try:
            url = tab.page.url or ""
        except Exception:
            continue
        if not _is_login_page(provider, url):
            # double-check after 2s to avoid catching transient navigation
            await asyncio.sleep(2.0)
            try:
                url2 = tab.page.url or ""
            except Exception:
                url2 = url
            if not _is_login_page(provider, url2):
                logged_in = True
                break

    took = int(time.monotonic() - t0)

    if not logged_in:
        _move_chrome(-32000, -32000)
        return {"ok": False, "error": f"login not detected in {LOGIN_TIMEOUT_S}s", "took_s": took}

    log(f"login detected after {took}s — capturing state")

    # ── 5. Capture storage_state + IDB ──
    try:
        state = await supervisor.state.context.storage_state()
    except Exception as e:
        _move_chrome(-32000, -32000)
        return {"ok": False, "error": f"storage_state failed: {e}"}

    try:
        from app.runtime.session_exporter import IDB_DUMP_JS
        idb = await tab.page.evaluate(IDB_DUMP_JS)
        if idb:
            state["_ainterceptor_idb"] = idb
    except Exception as e:
        log(f"idb dump skipped: {e}")

    # ── 6. Save to export dir ──
    export_dir = pathlib.Path(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    target = export_dir / f"{provider}.json"
    tmp = target.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(target)
    except Exception as e:
        _move_chrome(-32000, -32000)
        return {"ok": False, "error": f"save failed: {e}"}

    # ── 7. Hide Chrome again ──
    _move_chrome(-32000, -32000)

    return {"ok": True, "provider": provider, "saved_path": str(target),
            "cookies": len(state.get("cookies", [])),
            "idb_databases": list((state.get("_ainterceptor_idb") or {}).keys()),
            "took_s": took}


def _move_chrome(x: int, y: int) -> None:
    """Move every Chrome window to (x, y)."""
    import sys
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, lp):
            try:
                n = u.GetWindowTextLengthW(hwnd)
                if not n:
                    return True
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                if "chrome" in buf.value.lower() or any(
                    k in buf.value.lower() for k in
                    ("claude", "chatgpt", "gemini", "deepseek", "mistral",
                     "qwen", "perplexity", "grok", "poe", "hugging")
                ):
                    u.MoveWindow(hwnd, x, y, 1400, 900, True)
            except Exception:
                pass
            return True
        u.EnumWindows(CB(cb), 0)
    except Exception:
        pass
