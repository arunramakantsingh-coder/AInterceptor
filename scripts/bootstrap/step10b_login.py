import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend" / "app"
(ROOT / "scripts").mkdir(exist_ok=True)

(BE / "runtime" / "login_helper.py").write_text('''"""Bring daemon-owned Chrome on-screen so user can log into a provider.

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
    "claude":     ("/login", "/auth", "/signin", "claude.ai/login"),
    "chatgpt":    ("/auth/login", "/auth/0", "/login"),
    "gemini":     ("/accounts/", "signin", "accounts.google.com"),
    "deepseek":   ("/login", "/auth", "/sign_in", "/signin"),
    "mistral":    ("/login", "/auth"),
    "qwen":       ("/login", "/auth"),
    "huggingchat":("/login", "/auth"),
    "perplexity": ("/login", "/auth"),
    "grok":       ("/login", "/auth"),
    "poe":        ("/login", "/auth"),
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
''', encoding="utf-8", newline="\n")
print("  [OK] backend/app/runtime/login_helper.py")

# ── /api/login route ──
(BE / "api" / "login_routes.py").write_text('''"""Login endpoints — bring Chrome on-screen for user login."""
from __future__ import annotations
import pathlib
import os
from fastapi import APIRouter, Depends, HTTPException
from app.deps import current_user
from app.db.models import User
from app.runtime import supervisor_registry
from app.runtime.login_helper import begin_login

router = APIRouter(prefix="/api/login", tags=["login"])


@router.post("/{provider}")
async def login(provider: str, user: User = Depends(current_user)):
    sup = supervisor_registry.get_supervisor()
    if sup is None:
        raise HTTPException(503, "browser supervisor not running")
    export_dir = pathlib.Path(os.environ.get(
        "AINTERCEPTOR_EXPORT_DIR",
        str(pathlib.Path.cwd() / ".ainterceptor" / "exports")))
    result = await begin_login(provider, sup, export_dir)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "login failed"))
    return result
''', encoding="utf-8", newline="\n")
print("  [OK] backend/app/api/login_routes.py")

# ── wire route into main ──
main = BE / "main.py"
m = main.read_text(encoding="utf-8")
if "login_routes" not in m:
    m = m.replace(
        "from app.api import auth_routes, keys_routes, health_routes, sessions_routes, chat_routes",
        "from app.api import auth_routes, keys_routes, health_routes, sessions_routes, chat_routes, login_routes",
    )
    m = m.replace(
        "app.include_router(chat_routes.router)",
        "app.include_router(chat_routes.router)\napp.include_router(login_routes.router)",
    )
    main.write_text(m, encoding="utf-8", newline="\n")
    print("  [OK] main.py: login_routes registered")

# ── CLI helper ──
(ROOT / "scripts" / "login.py").write_text('''"""CLI helper: python scripts/login.py <provider>

Calls the running daemon's /api/login/<provider> endpoint, which brings
the daemon's Chrome on-screen. Log in to the provider in the browser,
the daemon detects success and saves the session.
"""
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request


def _token() -> str:
    env_file = pathlib.Path(".env.test")
    if not env_file.exists():
        print("[FAIL] .env.test not found — run the signup script first")
        sys.exit(1)
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("TOKEN="):
            return line[6:].strip()
    print("[FAIL] TOKEN not found in .env.test")
    sys.exit(1)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/login.py <provider>")
        print("providers: claude chatgpt gemini deepseek mistral qwen huggingchat perplexity grok poe")
        return 1
    provider = sys.argv[1].lower()
    base = os.environ.get("AINTERCEPTOR_BASE", "http://127.0.0.1:8000")
    token = _token()

    print(f"[..] requesting login for {provider}")
    print(f"     the daemon's Chrome will appear on screen shortly")
    print(f"     log in normally, then wait for confirmation")
    print()

    req = urllib.request.Request(
        f"{base}/api/login/{provider}",
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=360) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"[FAIL] HTTP {e.code}: {e.read().decode('utf-8','replace')[:400]}")
        return 1
    except Exception as e:
        print(f"[FAIL] {e}")
        return 1

    if not body.get("ok"):
        print(f"[FAIL] {body.get('error')}")
        return 1

    print()
    print(f"[OK] {provider} session saved")
    print(f"     cookies         : {body.get('cookies')}")
    print(f"     indexeddb dbs   : {body.get('idb_databases')}")
    print(f"     took            : {body.get('took_s')}s")
    print(f"     saved at        : {body.get('saved_path')}")
    print()
    print("Chrome is now off-screen again. Log in to other providers with:")
    print(f"  python scripts/login.py <provider>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
''', encoding="utf-8", newline="\n")
print("  [OK] scripts/login.py")

import ast
for f in ["backend/app/runtime/login_helper.py",
          "backend/app/api/login_routes.py",
          "backend/app/main.py",
          "scripts/login.py"]:
    try: ast.parse((ROOT / f).read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {f}: {e}"); sys.exit(1)
print("  [OK] syntax valid")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","feat(login): on-demand login flow (bring Chrome on-screen, capture, save)"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("=" * 60)
print("STEP 10b COMPLETE")
print()
print("NEXT:")
print("  1. Restart the daemon:")
print("       .\\run-windows.ps1")
print()
print("  2. In a new terminal, log in to a provider:")
print("       python scripts\\login.py chatgpt")
print()
print("  Watch Chrome appear on your screen, log in normally,")
print("  then wait — Chrome will hide itself and print confirmation.")
print()
print("  Repeat for: claude, gemini, deepseek")
print("=" * 60)
