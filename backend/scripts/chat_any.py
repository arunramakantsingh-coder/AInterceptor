"""AInterceptor CLI — attach to shared Chrome on 9222."""
import asyncio, importlib, os, sys, uuid, pathlib, subprocess, socket, time, json, urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
STATE = ROOT / ".ainterceptor"
STATE.mkdir(exist_ok=True)
SHARED_PROFILE = STATE / "chrome-profile-shared"
SHARED_PORT = 9222
URLS = {
    "chatgpt":  "https://chatgpt.com/",
    "claude":   "https://claude.ai/",
    "gemini":   "https://gemini.google.com/",
    "deepseek": "https://chat.deepseek.com/",
}
sys.path.insert(0, str(BACKEND))
from app.interception.contracts import ProviderExecutionRequest


def cdp_ready() -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{SHARED_PORT}/json/version", timeout=1.0) as r:
            return "Browser" in json.loads(r.read())
    except Exception:
        return False


def cdp_alive(port=None):
    """True if Chrome's CDP is speaking on 127.0.0.1:<port>."""
    import urllib.request
    if port is None:
        port = SHARED_PORT
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.5) as r:
            return b"Browser" in r.read()
    except Exception:
        return False


def require_cdp():
    """Fail fast with a useful hint if the daemon isn't up."""
    if cdp_alive():
        return True
    print()
    print("=" * 60)
    print(f" VM Chrome is not running (CDP :{SHARED_PORT})")
    print("=" * 60)
    print("  Start the daemon:")
    print("     arestart")
    print()
    print("  Check state:")
    print("     astatus")
    print("=" * 60)
    return False


async def do_chat(provider):
    if not require_cdp():
        return 2
    try:
        cls = load_runtime(provider)
    except Exception as e:
        print(f"[FAIL] {e}"); return 3
    rt = cls()
    try:
        await asyncio.wait_for(rt.start(), timeout=20)
    except asyncio.TimeoutError:
        print(f"[FAIL] timeout attaching to Chrome on {SHARED_PORT}")
        print("       Try:  arestart")
        return 4
    except Exception as e:
        print(f"[FAIL] attach: {e}")
        return 5

    print(f"Connected to {provider}. /exit to leave.\n")
    try:
        while True:
            try:
                line = input(f"{provider}> ")
            except (EOFError, KeyboardInterrupt):
                print(); break
            if not line.strip(): continue
            if line.strip() in {"/exit","/back","exit","quit"}: break
            req = ProviderExecutionRequest(
                provider=provider, request_id=str(uuid.uuid4()),
                messages=[{"role":"user","content":line}],
            )
            print()
            got = False
            need_login = False
            try:
                async for ev in rt.execute(req):
                    if ev.delta:
                        print(ev.delta, end="", flush=True)
                        got = True
                    et = getattr(ev.event_type, "value", str(ev.event_type))
                    if et in ("SESSION_EXPIRED", "SESSION_RECOVERY_REQUIRED"):
                        need_login = True
            except Exception as e:
                print(f"\n[FAIL] {e}")
            print()
            if need_login:
                print(f"This provider needs a login.")
                print(f"  login {provider}    # Chrome appears, log in")
                print(f"  hide               # push back off-screen")
            elif not got:
                print("(no reply)")
    finally:
        try: await rt.close()
        except Exception: pass
    return 0


def move_windows(x, y):
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, lp):
            n = u.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n+1)
                u.GetWindowTextW(hwnd, buf, n+1)
                if "Chrome" in buf.value:
                    u.MoveWindow(hwnd, x, y, 1400, 900, True)
            return True
        u.EnumWindows(CB(cb), 0)
    except Exception as e:
        print(f"[WARN] {e}")


def do_login(provider):
    if not cdp_ready():
        if not launch_chrome(off_screen=False):
            print("[FAIL] launch failed"); return 2
    move_windows(80, 80)
    print(f"Chrome is on-screen. Log into {provider}, then run:  hide")
    return 0


def do_hide():
    move_windows(-32000, -32000)
    print("Chrome off-screen.")
    return 0


def do_status():
    print(f"shared Chrome : {'ready' if cdp_ready() else 'off'} (port {SHARED_PORT})")
    print(f"profile       : {SHARED_PROFILE}")
    return 0


def do_restart():
    kill_chrome()
    time.sleep(2)
    ok = launch_chrome(off_screen=True)
    print("restarted" if ok else "failed")
    return 0 if ok else 1


def main():
    args = sys.argv[1:]
    if not args:
        print("usage:  <provider> | login <provider> | hide | status | restart | kill")
        return 1
    a0 = args[0].lower()
    if a0 == "status":  return do_status()
    if a0 == "hide":    return do_hide()
    if a0 == "restart": return do_restart()
    if a0 == "kill":
        kill_chrome(); print("killed"); return 0
    if a0 == "login":
        if len(args) < 2: print("usage: login <provider>"); return 1
        return do_login(args[1].lower())
    provider = a0
    if len(args) > 1:
        sub = args[1].lower()
        if sub == "login":  return do_login(provider)
        if sub == "hide":   return do_hide()
        if sub == "status": return do_status()
    return asyncio.run(do_chat(provider))


if __name__ == "__main__":
    sys.exit(main())
