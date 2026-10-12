import pathlib, subprocess, sys, textwrap, os

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
BIN  = ROOT / "bin"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
PYW  = r"C:\Projects\Atlas\.venv\Scripts\pythonw.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

# ============================================================
# 1. Daemon
# ============================================================
daemon = textwrap.dedent('''\
    """aidaemon — resident session manager for AInterceptor.

    Owns all four provider browsers, keeps them off-screen, exposes them
    via HTTP on 127.0.0.1:7700. CLI clients connect to this daemon.
    """
    from __future__ import annotations
    import asyncio, ctypes, importlib, json, os, pathlib, socket, subprocess, sys, time
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel

    ROOT = pathlib.Path(__file__).resolve().parents[2]
    BACKEND = ROOT / "backend"
    STATE_DIR = ROOT / ".ainterceptor"
    STATE_DIR.mkdir(exist_ok=True)

    PROVIDERS = {
        "claude":   {"port": 9222, "url": "https://claude.ai/",          "profile": "chrome-profile-claude"},
        "deepseek": {"port": 9223, "url": "https://chat.deepseek.com/",  "profile": "chrome-profile-deepseek"},
        "chatgpt":  {"port": 9224, "url": "https://chatgpt.com/",        "profile": "chrome-profile-chatgpt"},
        "gemini":   {"port": 9225, "url": "https://gemini.google.com/",  "profile": "chrome-profile-gemini"},
    }
    TITLE_MATCH = {
        "claude":   ["claude"],
        "deepseek": ["deepseek"],
        "chatgpt":  ["chatgpt"],
        "gemini":   ["gemini"],
    }

    # ── helpers ──
    def find_chrome():
        for c in (r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                  r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"):
            if pathlib.Path(c).exists(): return c
        return None

    def port_open(port):
        s = socket.socket(); s.settimeout(0.4)
        try: s.connect(("127.0.0.1", port)); return True
        except OSError: return False
        finally: s.close()

    def launch_chrome(provider, off_screen=True):
        cfg = PROVIDERS[provider]
        chrome = find_chrome()
        if not chrome: raise RuntimeError("chrome.exe not found")
        profile = STATE_DIR / cfg["profile"]
        profile.mkdir(parents=True, exist_ok=True)
        pos = "-32000,-32000" if off_screen else "100,100"
        args = [chrome,
                f"--remote-debugging-port={cfg['port']}",
                f"--user-data-dir={profile}",
                "--no-first-run", "--no-default-browser-check",
                f"--window-position={pos}",
                "--window-size=1280,900",
                cfg["url"]]
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(args, creationflags=flags)
        for _ in range(30):
            time.sleep(0.5)
            if port_open(cfg["port"]): return
        raise RuntimeError(f"{provider} chrome did not bind port {cfg['port']}")

    # ── window manipulation ──
    _enum_windows = ctypes.windll.user32.EnumWindows
    _get_text = ctypes.windll.user32.GetWindowTextW
    _get_text_len = ctypes.windll.user32.GetWindowTextLengthW
    _is_visible = ctypes.windll.user32.IsWindowVisible
    _move = ctypes.windll.user32.MoveWindow
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _windows():
        out = []
        def cb(hwnd, lp):
            n = _get_text_len(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n+1)
                _get_text(hwnd, buf, n+1)
                if _is_visible(hwnd):
                    out.append((hwnd, buf.value))
            return True
        _enum_windows(WNDENUMPROC(cb), 0)
        return out

    def move_provider_window(provider, x, y):
        keys = TITLE_MATCH.get(provider, [provider])
        moved = 0
        for hwnd, title in _windows():
            tl = title.lower()
            if any(k in tl for k in keys):
                _move(hwnd, x, y, 1280, 900, True)
                moved += 1
        return moved

    # ── runtime loading ──
    sys.path.insert(0, str(BACKEND))
    from app.interception.contracts import ProviderExecutionRequest

    def load_runtime_class(provider):
        module = importlib.import_module(f"app.interception.{provider}")
        target = provider.replace("-","").lower()
        for name, obj in vars(module).items():
            if isinstance(obj, type) and obj.__module__ == module.__name__:
                if name.lower() == f"{target}runtime": return obj
        for name, obj in vars(module).items():
            if isinstance(obj, type) and obj.__module__ == module.__name__ and name.endswith("Runtime"):
                return obj
        raise RuntimeError(f"no Runtime for {provider}")

    # ── state ──
    LOCK = asyncio.Lock()
    RUNTIMES = {}

    async def ensure(provider):
        cfg = PROVIDERS[provider]
        async with LOCK:
            if not port_open(cfg["port"]):
                print(f"[daemon] launching {provider} chrome off-screen", flush=True)
                launch_chrome(provider, off_screen=True)
            if provider not in RUNTIMES:
                cls = load_runtime_class(provider)
                rt = cls()
                await rt.start()
                RUNTIMES[provider] = rt
                print(f"[daemon] {provider} attached", flush=True)
            return RUNTIMES[provider]

    # ── API ──
    app = FastAPI(title="aidaemon")

    class ChatBody(BaseModel):
        prompt: str

    @app.get("/")
    def status():
        out = {"daemon": "running", "providers": {}}
        for name, cfg in PROVIDERS.items():
            out["providers"][name] = {
                "port": cfg["port"],
                "chrome_alive": port_open(cfg["port"]),
                "attached": name in RUNTIMES,
            }
        return out

    @app.post("/ensure/{provider}")
    async def api_ensure(provider: str):
        if provider not in PROVIDERS: raise HTTPException(404)
        await ensure(provider)
        return {"ok": True}

    @app.post("/chat/{provider}")
    async def api_chat(provider: str, body: ChatBody):
        if provider not in PROVIDERS: raise HTTPException(404)
        rt = await ensure(provider)
        req = ProviderExecutionRequest(
            provider=provider,
            request_id=os.urandom(8).hex(),
            messages=[{"role":"user","content":body.prompt}],
        )
        async def gen():
            try:
                async for ev in rt.execute(req):
                    if ev.delta:
                        yield f"data: {json.dumps({'delta': ev.delta})}\\n\\n"
                yield "data: [DONE]\\n\\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\\n\\n"
                yield "data: [DONE]\\n\\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/login/{provider}")
    async def api_login(provider: str):
        if provider not in PROVIDERS: raise HTTPException(404)
        if not port_open(PROVIDERS[provider]["port"]):
            launch_chrome(provider, off_screen=False)
        else:
            move_provider_window(provider, 100, 100)
        return {"ok": True, "message": f"Log into {provider} in the window, then run: daemon hide {provider}"}

    @app.post("/show/{provider}")
    async def api_show(provider: str):
        n = move_provider_window(provider, 100, 100)
        return {"moved": n}

    @app.post("/hide/{provider}")
    async def api_hide(provider: str):
        n = move_provider_window(provider, -32000, -32000)
        return {"moved": n}

    @app.post("/shutdown")
    async def api_shutdown():
        async def later():
            await asyncio.sleep(0.3)
            os._exit(0)
        asyncio.create_task(later())
        return {"ok": True}

    if __name__ == "__main__":
        uvicorn.run(app, host="127.0.0.1", port=7700, log_level="warning")
''')

(BE / "scripts" / "aidaemon.py").write_text(daemon, encoding="utf-8", newline="\n")
print("  [OK] backend/scripts/aidaemon.py")

# ============================================================
# 2. Rewrite chat_any.py — prefer daemon, fall back to local
# ============================================================
client = textwrap.dedent('''\
    """Chat CLI — prefers aidaemon, falls back to local runtime."""
    import asyncio, json, os, sys, uuid, pathlib, urllib.request, urllib.error

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    DAEMON = "http://127.0.0.1:7700"

    def daemon_alive():
        try:
            with urllib.request.urlopen(f"{DAEMON}/", timeout=0.8) as r:
                return r.status == 200
        except Exception:
            return False

    def daemon_call(method, path):
        req = urllib.request.Request(f"{DAEMON}{path}", method=method)
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")

    async def chat_via_daemon(provider):
        print(f"Connected to {provider} (daemon). /exit or Ctrl+C to leave.\\n")
        prefix = f"{provider}> "
        while True:
            try:
                line = input(prefix)
            except (EOFError, KeyboardInterrupt):
                print(); break
            if not line.strip(): continue
            if line.strip() in {"/exit","/back","exit","quit"}: break
            body = json.dumps({"prompt": line}).encode()
            req = urllib.request.Request(
                f"{DAEMON}/chat/{provider}",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            print()
            try:
                with urllib.request.urlopen(req, timeout=240) as resp:
                    buf = b""
                    for chunk in resp:
                        buf += chunk
                        while b"\\n\\n" in buf:
                            ev, buf = buf.split(b"\\n\\n", 1)
                            for ln in ev.split(b"\\n"):
                                if not ln.startswith(b"data: "): continue
                                payload = ln[6:].decode("utf-8","replace")
                                if payload == "[DONE]": break
                                try:
                                    j = json.loads(payload)
                                    if "delta" in j:
                                        print(j["delta"], end="", flush=True)
                                    elif "error" in j:
                                        print(f"\\n[ERROR] {j['error']}")
                                except Exception:
                                    pass
            except Exception as e:
                print(f"[FAIL] {e}")
            print()
        return 0

    # ── local fallback (identical to previous behavior) ──
    async def chat_local(provider):
        import importlib, inspect
        RAW = pathlib.Path("..") / ".evidence" / "raw"
        RAW.mkdir(parents=True, exist_ok=True)
        os.environ["AINTERCEPTOR_RAW_CAPTURE_DIR"] = str(RAW)
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
        from app.interception.contracts import ProviderExecutionRequest
        module = importlib.import_module(f"app.interception.{provider}")
        target = provider.replace("-","").lower()
        cls = None
        for name, obj in vars(module).items():
            if isinstance(obj, type) and obj.__module__ == module.__name__:
                if name.lower() == f"{target}runtime": cls = obj; break
        if cls is None:
            for name, obj in vars(module).items():
                if isinstance(obj, type) and obj.__module__ == module.__name__ and name.endswith("Runtime"):
                    cls = obj; break
        if cls is None: print("[FAIL] no runtime"); return 3
        rt = cls()
        await rt.start()
        print(f"Connected to {provider} (local). /exit or Ctrl+C to leave.\\n")
        while True:
            try:
                line = input(f"{provider}> ")
            except (EOFError, KeyboardInterrupt):
                print(); break
            if not line.strip(): continue
            if line.strip() in {"/exit","/back","exit","quit"}: break
            req = ProviderExecutionRequest(provider=provider,
                request_id=str(uuid.uuid4()),
                messages=[{"role":"user","content":line}])
            print()
            async for ev in rt.execute(req):
                if ev.delta: print(ev.delta, end="", flush=True)
            print()
        await rt.close()
        return 0

    async def main():
        args = sys.argv[1:]
        if not args:
            print("usage: chat_any <provider> [login|show|hide|status]")
            return 1
        provider = args[0].lower()
        sub = args[1].lower() if len(args) > 1 else ""
        if sub in {"login","show","hide"}:
            if not daemon_alive():
                print("[FAIL] daemon not running. Start it with: aidaemon start")
                return 2
            try:
                print(daemon_call("POST", f"/{sub}/{provider}"))
            except Exception as e:
                print(f"[FAIL] {e}")
            return 0
        if sub == "status":
            if not daemon_alive():
                print("daemon: not running"); return 0
            print(daemon_call("GET", "/")); return 0
        if daemon_alive():
            return await chat_via_daemon(provider)
        print("[WARN] daemon not running — falling back to local (browser will appear)")
        print("       To use the daemon: aidaemon start")
        return await chat_local(provider)

    if __name__ == "__main__":
        sys.exit(asyncio.run(main()))
''')

(BE / "scripts" / "chat_any.py").write_text(client, encoding="utf-8", newline="\n")
print("  [OK] backend/scripts/chat_any.py")

# ============================================================
# 3. bin wrappers
# ============================================================
BIN.mkdir(exist_ok=True)

# aidaemon.cmd — daemon control
(BIN / "aidaemon.cmd").write_text(
    "@echo off\r\n"
    "set PYTHONUTF8=1\r\n"
    f'cd /d "{BE}"\r\n'
    "if \"%1\"==\"\" goto start\r\n"
    "if \"%1\"==\"start\" goto start\r\n"
    "if \"%1\"==\"stop\" goto stop\r\n"
    "if \"%1\"==\"status\" goto status\r\n"
    "if \"%1\"==\"restart\" goto restart\r\n"
    "goto start\r\n"
    ":start\r\n"
    f'start \"\" /b \"{PYW}\" -m scripts.aidaemon\r\n'
    "echo daemon starting (wait 3s)...\r\n"
    "timeout /t 3 /nobreak >nul\r\n"
    "goto status\r\n"
    ":stop\r\n"
    f'\"{PY}\" -c \"import urllib.request; urllib.request.urlopen(urllib.request.Request(\\\"http://127.0.0.1:7700/shutdown\\\", method=\\\"POST\\\"), timeout=5)\"\r\n'
    "echo daemon stopped\r\n"
    "goto :eof\r\n"
    ":status\r\n"
    f'\"{PY}\" -c \"import urllib.request,json; print(json.dumps(json.loads(urllib.request.urlopen(\\\"http://127.0.0.1:7700/\\\",timeout=3).read()),indent=2))\"\r\n'
    "goto :eof\r\n"
    ":restart\r\n"
    "call \"%~f0\" stop\r\n"
    "timeout /t 2 /nobreak >nul\r\n"
    "call \"%~f0\" start\r\n"
    "goto :eof\r\n",
    encoding="utf-8", newline="",
)
print("  [OK] bin/aidaemon.cmd")

# daemon.cmd — per-provider ops
(BIN / "daemon.cmd").write_text(
    "@echo off\r\n"
    "set PYTHONUTF8=1\r\n"
    f'cd /d "{BE}"\r\n'
    f'\"{PY}\" -u -m scripts.chat_any %*\r\n',
    encoding="utf-8", newline="",
)
print("  [OK] bin/daemon.cmd")

# refresh provider wrappers
for name, provider in [("deepseek","deepseek"),("claude","claude"),
                       ("chatgpt","chatgpt"),("aigemini","gemini")]:
    (BIN / f"{name}.cmd").write_text(
        "@echo off\r\n"
        "set PYTHONUTF8=1\r\n"
        f'cd /d "{BE}"\r\n'
        f'\"{PY}\" -u -m scripts.chat_any {provider} %*\r\n',
        encoding="utf-8", newline="",
    )
print("  [OK] refreshed provider wrappers")

# ============================================================
# 4. Syntax check
# ============================================================
import ast
for f in ["aidaemon.py", "chat_any.py"]:
    p = BE / "scripts" / f
    try:
        ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {f}: {e}"); sys.exit(1)
print("  [OK] syntax valid")

# ============================================================
# 5. Commit
# ============================================================
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "feat(daemon): aidaemon — persistent session manager owns all browsers invisibly"])
print(r.stdout.strip() or r.stderr.strip())

# ============================================================
# 6. Kill any stray Chromes bound to our ports, then start daemon
# ============================================================
for port in [9222, 9223, 9224, 9225]:
    r = subprocess.run(["powershell","-NoProfile","-Command",
        f"Get-NetTCPConnection -LocalPort {port} -State Listen -EA SilentlyContinue | "
        f"ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }}"],
        capture_output=True, text=True, shell=True)

print("\n==> Starting daemon")
subprocess.Popen(
    [PY, "-u", "-m", "scripts.aidaemon"],
    cwd=BE,
    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
)
import time as _t
for _ in range(20):
    _t.sleep(0.5)
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:7700/", timeout=0.8) as r:
            print("  [OK] daemon alive")
            print(r.read().decode())
            break
    except Exception:
        continue
else:
    print("  [!] daemon did not come up — check .ainterceptor/daemon.log")

print()
print("=" * 66)
print("PERMANENT SETUP READY")
print()
print("  Now:      deepseek       (no browser window appears)")
print("            claude")
print("            chatgpt")
print("            aigemini")
print()
print("  Login:    daemon login claude")
print("            daemon login chatgpt")
print("            daemon login deepseek")
print("            daemon login gemini")
print("  Hide:     daemon hide <provider>     (after login)")
print()
print("  Daemon:   aidaemon status")
print("            aidaemon stop")
print("            aidaemon start")
print()
print("  Open a NEW terminal once, then use the above commands.")
print("=" * 66)
