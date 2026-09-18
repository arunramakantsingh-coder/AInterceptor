"""AInterceptor chat — direct attach to shared Chrome."""
import asyncio, importlib, os, sys, uuid, pathlib, subprocess, time, socket

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

def port_open(port):
    s = socket.socket(); s.settimeout(0.4)
    try: s.connect(("127.0.0.1", port)); return True
    except OSError: return False
    finally: s.close()

def find_chrome():
    for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if pathlib.Path(c).exists(): return c
    return None

def launch_shared_chrome(off_screen=True):
    chrome = find_chrome()
    if not chrome:
        print("[FAIL] chrome.exe not found"); return False
    SHARED_PROFILE.mkdir(parents=True, exist_ok=True)
    pos = "-32000,-32000" if off_screen else "100,100"
    args = [chrome,
            f"--remote-debugging-port={SHARED_PORT}",
            f"--user-data-dir={SHARED_PROFILE}",
            "--no-first-run", "--no-default-browser-check",
            f"--window-position={pos}",
            "--window-size=1400,900"]
    args.extend(URLS.values())
    subprocess.Popen(args)
    for _ in range(30):
        time.sleep(0.5)
        if port_open(SHARED_PORT): return True
    return False

def load_runtime(provider):
    module = importlib.import_module(f"app.interception.{provider}")
    target = provider.replace("-", "").lower()
    for name, obj in vars(module).items():
        if isinstance(obj, type) and obj.__module__ == module.__name__:
            if name.lower() == f"{target}runtime":
                return obj
    for name, obj in vars(module).items():
        if isinstance(obj, type) and obj.__module__ == module.__name__ and name.endswith("Runtime"):
            return obj
    raise RuntimeError(f"no Runtime class for {provider}")

async def do_chat(provider):
    if not port_open(SHARED_PORT):
        print(f"[..] shared Chrome not running — launching off-screen on {SHARED_PORT}")
        if not launch_shared_chrome(off_screen=True):
            print("[FAIL] could not launch shared Chrome"); return 2
    cls = load_runtime(provider)
    rt = cls()
    await rt.start()
    print(f"Connected to {provider}. /exit or Ctrl+C to leave.\n")
    try:
        while True:
            try:
                line = input(f"{provider}> ")
            except (EOFError, KeyboardInterrupt):
                print(); break
            if not line.strip(): continue
            if line.strip() in {"/exit","/back","exit","quit"}: break
            req = ProviderExecutionRequest(
                provider=provider,
                request_id=str(uuid.uuid4()),
                messages=[{"role":"user","content":line}],
            )
            print()
            async for ev in rt.execute(req):
                if ev.delta:
                    print(ev.delta, end="", flush=True)
            print()
    finally:
        await rt.close()
    return 0

def do_login(provider):
    """Bring the shared Chrome on-screen so the user can log into `provider`."""
    if not port_open(SHARED_PORT):
        print(f"[..] launching shared Chrome with all providers as tabs")
        if not launch_shared_chrome(off_screen=False):
            print("[FAIL] launch failed"); return 2
    # Move the window on-screen
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, lp):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n+1)
                user32.GetWindowTextW(hwnd, buf, n+1)
                if "Chrome" in buf.value or "chatgpt" in buf.value.lower() or \
                   "claude" in buf.value.lower() or "gemini" in buf.value.lower() or \
                   "deepseek" in buf.value.lower():
                    user32.MoveWindow(hwnd, 80, 80, 1400, 900, True)
            return True
        user32.EnumWindows(WNDENUMPROC(cb), 0)
    except Exception as e:
        print(f"[WARN] could not move window: {e}")
    print()
    print(f"Log in to {provider} in the Chrome window.")
    print(f"Then run:  daemon hide {provider}   (or just close this and run {provider})")
    return 0

def do_hide(provider=None):
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, lp):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n+1)
                user32.GetWindowTextW(hwnd, buf, n+1)
                if "Chrome" in buf.value:
                    user32.MoveWindow(hwnd, -32000, -32000, 1400, 900, True)
            return True
        user32.EnumWindows(WNDENUMPROC(cb), 0)
    except Exception as e:
        print(f"[WARN] {e}")
    print("Chrome pushed off-screen.")
    return 0

def do_status():
    alive = port_open(SHARED_PORT)
    print("AInterceptor shared browser")
    print(f"  port    : {SHARED_PORT}")
    print(f"  profile : {SHARED_PROFILE}")
    print(f"  status  : {'alive' if alive else 'off'}")
    return 0

def main():
    if len(sys.argv) < 2:
        print("usage: <provider> [login|hide|status]")
        return 1
    a0 = sys.argv[0+1].lower()
    if a0 == "status": return do_status()
    if a0 == "hide":   return do_hide()
    if a0 == "login":
        if len(sys.argv) < 3: print("usage: login <provider>"); return 1
        return do_login(sys.argv[2].lower())
    provider = a0
    if len(sys.argv) > 2:
        sub = sys.argv[2].lower()
        if sub == "login": return do_login(provider)
        if sub == "hide":  return do_hide(provider)
        if sub == "status":return do_status()
    return asyncio.run(do_chat(provider))

if __name__ == "__main__":
    sys.exit(main())
