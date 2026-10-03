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


def load_runtime(provider):
    """Resolve the *Runtime class for a provider module.

    Restored from c149dd8; it was deleted by 69fbb8f while its call
    site in do_chat() remained, which broke every CLI chat command.
    """
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
    if not require_cdp():
        return 2
    try:
        cls = load_runtime(provider)
    except Exception as e:
        print(f"[FAIL] {e}"); return 3
    rt = cls()
    # 20s was too short to be meaningful. A raw Playwright connect_over_cdp to
    # this browser succeeds in well under a second, so this budget is not about
    # the transport: each provider runtime's start() must locate its tab, drive
    # it and wait for load state, which legitimately takes longer - especially
    # just after `arestart` when the tabs are still settling. Measured overruns
    # sat in the 24-40s range, so allow real headroom while keeping a distinct
    # message for a genuinely unreachable browser.
    START_TIMEOUT_S = float(os.environ.get("AINTERCEPTOR_CLI_START_TIMEOUT", "120"))
    try:
        await asyncio.wait_for(rt.start(), timeout=START_TIMEOUT_S)
    except asyncio.TimeoutError:
        print(f"[FAIL] timeout attaching to Chrome on {SHARED_PORT} "
              f"(runtime start exceeded {START_TIMEOUT_S:.0f}s)")
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


def _chrome_windows():
    """Window ids of the real Chrome browser window(s) on :99.

    Filters out Chrome's own 10x10 helper window (the class-owner window
    has no WM_CLASS and a tiny geometry), which a naive
    `xdotool search --class google-chrome` would match.
    """
    ids = []
    try:
        out = subprocess.run(["xdotool", "search", "--name", "Chrome"],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return ids
    for wid in out.split():
        try:
            geo = subprocess.run(["xdotool", "getwindowgeometry", wid],
                                 capture_output=True, text=True, timeout=5).stdout
        except Exception:
            continue
        dims = [ln.split(":")[1].strip() for ln in geo.splitlines()
                if "Geometry" in ln]
        if not dims:
            continue
        try:
            w, h = (int(v) for v in dims[0].lower().split("x"))
        except Exception:
            continue
        if w >= 400 and h >= 300:
            ids.append(wid)
    return ids


def move_windows(x, y):
    """Move the Chrome window(s) to (x, y).

    Linux/xdotool implementation. The previous ctypes.windll.user32
    version was Windows-only and could never work in the VM.
    """
    ids = _chrome_windows()
    if not ids:
        print("[WARN] no Chrome window found (is the daemon up? try: astart)")
        return
    for wid in ids:
        try:
            subprocess.run(["xdotool", "windowmove", wid, str(x), str(y)],
                           capture_output=True, timeout=5)
            subprocess.run(["xdotool", "windowactivate", wid],
                           capture_output=True, timeout=5)
        except Exception as e:
            print(f"[WARN] move {wid} failed: {e}")


PROVIDER_HOSTS = {
    "claude": "claude.ai",
    "chatgpt": "chatgpt.com",
    "gemini": "gemini.google.com",
    "deepseek": "chat.deepseek.com",
}


def activate_provider_tab(provider):
    """Bring `provider`'s Chrome tab to the front over CDP.

    do_login used to move the window without selecting a tab, so whichever
    tab happened to be active came forward (observed: Grok when logging in
    to Claude). Returns the activated tab title, or None.
    """
    needle = PROVIDER_HOSTS.get(provider.lower(), provider.lower())
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{SHARED_PORT}/json/list", timeout=5) as r:
            tabs = json.loads(r.read().decode())
    except Exception as e:
        print(f"[WARN] could not list tabs: {e}")
        return None

    target = None
    for t in tabs:
        if t.get("type") != "page":
            continue
        if needle in (t.get("url") or ""):
            target = t
            break
    if target is None:
        print(f"[WARN] no open tab matching {needle} — open it first, or run: astart")
        return None
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{SHARED_PORT}/json/activate/{target['id']}",
                timeout=5) as r:
            r.read()
    except Exception:
        pass  # CDP returns an empty body; a read error here is not fatal
    return target.get("title") or needle


def do_login(provider):
    """Bring the daemon's Chrome on-screen so the user can log in."""
    if not cdp_ready():
        print("[..] daemon/Chrome not running Ã¢â‚¬â€ starting it")
        try:
            from scripts import ops_sys as S
            if S.astart() != 0:
                print("[FAIL] could not start the daemon")
                return 2
        except Exception as e:
            print(f"[FAIL] start: {e}")
            return 2
    move_windows(80, 80)
    title = activate_provider_tab(provider)
    print()
    if title:
        print(f"Chrome is on-screen showing: {title}")
    else:
        print("Chrome is on-screen. Select the tab yourself.")
    print(f"Log in to {provider}, then run:  hide")
    print(f"  VNC if you cannot see the desktop:"
          f"  x11vnc -display :99 -rfbport 5900")
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
    """Restart the daemon (which owns Chrome).

    kill_chrome()/launch_chrome() were removed by 69fbb8f when browser
    ownership moved to the daemon. Delegate to the daemon's own control
    path instead of launching Chrome from the client.
    """
    from scripts import ops_sys as S
    return S.arestart()


def do_kill():
    """Stop the daemon and the Chrome it owns."""
    from scripts import ops_sys as S
    return S.astop()


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
        return do_kill()
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
