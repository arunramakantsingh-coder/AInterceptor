import pathlib, subprocess, sys, textwrap, socket, time, ast, urllib.request, json

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
STATE = ROOT / ".ainterceptor"
STATE.mkdir(exist_ok=True)
PROFILE = STATE / "chrome-profile-shared"
PROFILE.mkdir(parents=True, exist_ok=True)
PY = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

# ─────────────────────────────────────────────────────────────
# 0. Kill Chrome, clean lock files, verify CDP is truly offline
# ─────────────────────────────────────────────────────────────
print("==> Cleaning Chrome state")
subprocess.run(["powershell","-NoProfile","-Command",
    "Get-NetTCPConnection -LocalPort 9222 -State Listen -EA SilentlyContinue | "
    "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }"],
    capture_output=True, shell=True)
time.sleep(2)

for name in ("SingletonLock","SingletonCookie","SingletonSocket","lockfile"):
    p = PROFILE / name
    if p.exists():
        try: p.unlink()
        except Exception: pass

print("  [OK] lock files removed")

# ─────────────────────────────────────────────────────────────
# 1. Robust shared-Chrome launcher (verifies CDP via /json/version)
# ─────────────────────────────────────────────────────────────
launcher = BE / "scripts" / "shared_chrome.py"
launcher.write_text(textwrap.dedent('''
    """Robust shared-Chrome launcher."""
    import json, pathlib, socket, subprocess, sys, time, urllib.request

    ROOT = pathlib.Path(__file__).resolve().parents[2]
    STATE = ROOT / ".ainterceptor"
    PROFILE = STATE / "chrome-profile-shared"
    PORT = 9222
    URLS = {
        "chatgpt":  "https://chatgpt.com/",
        "claude":   "https://claude.ai/",
        "gemini":   "https://gemini.google.com/",
        "deepseek": "https://chat.deepseek.com/",
    }


    def find_chrome():
        for c in (r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                  r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"):
            if pathlib.Path(c).exists(): return c
        return None


    def cdp_ready() -> bool:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1.0) as r:
                data = json.loads(r.read())
                return "Browser" in data
        except Exception:
            return False


    def kill_chrome():
        subprocess.run(["powershell","-NoProfile","-Command",
            f"Get-NetTCPConnection -LocalPort {PORT} -State Listen -EA SilentlyContinue | "
            "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }"],
            capture_output=True, shell=True)


    def launch(off_screen=True, open_tabs=True) -> bool:
        chrome = find_chrome()
        if not chrome:
            print("[FAIL] chrome.exe not found"); return False
        PROFILE.mkdir(parents=True, exist_ok=True)
        pos = "-32000,-32000" if off_screen else "80,80"
        args = [chrome,
                f"--remote-debugging-port={PORT}",
                f"--user-data-dir={PROFILE}",
                "--no-first-run", "--no-default-browser-check",
                "--disable-features=ChromeWhatsNewUI",
                f"--window-position={pos}", "--window-size=1400,900"]
        if open_tabs:
            args.extend(URLS.values())
        else:
            args.append("about:blank")
        subprocess.Popen(args)
        for _ in range(40):     # 20s
            time.sleep(0.5)
            if cdp_ready(): return True
        return False


    def main():
        action = sys.argv[1] if len(sys.argv) > 1 else "start"
        if action in {"stop","kill"}:
            kill_chrome(); print("stopped"); return 0
        if action == "restart":
            kill_chrome(); time.sleep(2)
            ok = launch(off_screen=True)
            print("restarted" if ok else "failed")
            return 0 if ok else 1
        if action == "status":
            print(f"CDP 9222: {'ready' if cdp_ready() else 'off'}")
            return 0
        # default start
        ok = launch(off_screen=True)
        print("started" if ok else "failed")
        return 0 if ok else 1


    if __name__ == "__main__":
        sys.exit(main())
'''), encoding="utf-8", newline="\n")
print(f"  [OK] {launcher.relative_to(ROOT)}")

# ─────────────────────────────────────────────────────────────
# 2. Rewrite chat_any.py: full subcommands, uses shared_chrome
# ─────────────────────────────────────────────────────────────
chat = textwrap.dedent('''\
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


    def find_chrome():
        for c in (r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                  r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"):
            if pathlib.Path(c).exists(): return c
        return None


    def launch_chrome(off_screen=True):
        chrome = find_chrome()
        if not chrome:
            print("[FAIL] chrome.exe not found"); return False
        SHARED_PROFILE.mkdir(parents=True, exist_ok=True)
        pos = "-32000,-32000" if off_screen else "80,80"
        args = [chrome,
                f"--remote-debugging-port={SHARED_PORT}",
                f"--user-data-dir={SHARED_PROFILE}",
                "--no-first-run", "--no-default-browser-check",
                "--disable-features=ChromeWhatsNewUI",
                f"--window-position={pos}", "--window-size=1400,900"]
        args.extend(URLS.values())
        subprocess.Popen(args)
        for _ in range(40):
            time.sleep(0.5)
            if cdp_ready(): return True
        return False


    def kill_chrome():
        subprocess.run(["powershell","-NoProfile","-Command",
            f"Get-NetTCPConnection -LocalPort {SHARED_PORT} -State Listen -EA SilentlyContinue | "
            "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }"],
            capture_output=True, shell=True)


    def load_runtime(provider):
        module = importlib.import_module(f"app.interception.{provider}")
        target = provider.replace("-", "").lower()
        for name, obj in vars(module).items():
            if isinstance(obj, type) and obj.__module__ == module.__name__ \\
               and name.lower() == f"{target}runtime":
                return obj
        for name, obj in vars(module).items():
            if isinstance(obj, type) and obj.__module__ == module.__name__ \\
               and name.endswith("Runtime"):
                return obj
        raise RuntimeError(f"no Runtime class for {provider}")


    async def do_chat(provider):
        if not cdp_ready():
            print(f"[..] launching shared Chrome off-screen on {SHARED_PORT}")
            if not launch_chrome(off_screen=True):
                print("[FAIL] Chrome did not become CDP-ready in 20s")
                print("       Try:  aid restart")
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
            print("       Try:  aid restart")
            return 4
        except Exception as e:
            print(f"[FAIL] attach: {e}")
            return 5

        print(f"Connected to {provider}. /exit to leave.\\n")
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
                    print(f"\\n[FAIL] {e}")
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
''')
(BE / "scripts" / "chat_any.py").write_text(chat, encoding="utf-8", newline="\n")
ast.parse(chat)
print("  [OK] chat_any.py rewritten (with restart + kill)")

# ─────────────────────────────────────────────────────────────
# 3. Add `aid` and `airouter` wrappers
# ─────────────────────────────────────────────────────────────
BIN = ROOT / "bin"
BIN.mkdir(exist_ok=True)
for name in ["aid","airouter","hide","status","login","restart"]:
    sub = "" if name in {"aid","airouter"} else name
    tail = sub + " %*" if sub else "%*"
    (BIN / f"{name}.cmd").write_text(
        f"@echo off\r\nset PYTHONUTF8=1\r\ncd /d \"{BE}\"\r\n"
        f'"{PY}" -u -m scripts.chat_any {tail}\r\n',
        encoding="utf-8", newline="")
    print(f"  [OK] bin/{name}.cmd")

# ─────────────────────────────────────────────────────────────
# 4. Launch Chrome, verify CDP ready
# ─────────────────────────────────────────────────────────────
print("\n==> launching Chrome")
if launch_chrome(off_screen=True):
    print("  [OK] CDP 9222 ready")
else:
    print("  [FAIL] Chrome did not bind CDP within 20s")

# ─────────────────────────────────────────────────────────────
# 5. Commit
# ─────────────────────────────────────────────────────────────
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(cli): CDP-readiness check, restart/kill subcommands, robust Chrome launcher"])
print((r.stdout.strip() or r.stderr.strip())[:300])

print()
print("=" * 66)
print("Try:")
print("  aid restart     # ensures Chrome is fresh")
print("  deepseek        # should attach within 15s")
print("  chatgpt")
print("  claude")
print("  aigemini")
print()
print("If any provider hangs, run: aid restart  then retry")
print("=" * 66)
