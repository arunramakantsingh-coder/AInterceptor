import pathlib, subprocess, sys, textwrap

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
BIN  = ROOT / "bin"
BIN.mkdir(exist_ok=True)
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

# ───────────────────────────────────────────────────────────
# 1. Rewrite chat_any.py: handles `login` subcommand + friendly errors
# ───────────────────────────────────────────────────────────
chat_any = textwrap.dedent('''\
    """AInterceptor chat launcher.

    Usage:
        <provider>              open chat (attaches to running browser)
        <provider> login        open the provider's login window
    """
    import asyncio, importlib, os, sys, uuid, pathlib, inspect, subprocess, socket, time

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    RAW = pathlib.Path("..") / ".evidence" / "raw"
    RAW.mkdir(parents=True, exist_ok=True)
    os.environ["AINTERCEPTOR_RAW_CAPTURE_DIR"] = str(RAW)

    from app.interception.contracts import ProviderExecutionRequest
    from app.interception import registry as provider_registry

    PORTS = {"claude": 9222, "deepseek": 9223, "chatgpt": 9224, "gemini": 9225}
    URLS  = {
        "claude":   "https://claude.ai/",
        "deepseek": "https://chat.deepseek.com/",
        "chatgpt":  "https://chatgpt.com/",
        "gemini":   "https://gemini.google.com/",
    }
    PROFILES = {
        "claude":   "chrome-profile-claude",
        "deepseek": "chrome-profile-deepseek",
        "chatgpt":  "chrome-profile-chatgpt",
        "gemini":   "chrome-profile-gemini",
    }


    def _port_open(port: int) -> bool:
        s = socket.socket(); s.settimeout(0.4)
        try: s.connect(("127.0.0.1", port)); return True
        except OSError: return False
        finally: s.close()


    def _find_chrome() -> str | None:
        for c in (r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                  r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"):
            if pathlib.Path(c).exists(): return c
        return None


    def open_login_window(provider: str) -> int:
        chrome = _find_chrome()
        if not chrome:
            print("[FAIL] chrome.exe not found"); return 2
        port = PORTS[provider]
        profile = pathlib.Path(r"C:\\Projects\\AInterceptor-M1.5\\.ainterceptor") / PROFILES[provider]
        profile.mkdir(parents=True, exist_ok=True)

        if _port_open(port):
            print(f"[OK] {provider} browser already running on {port}")
            print("     Bring it on-screen to log in, or run the chat now.")
            return 0

        print(f"[..] Opening {provider} login window on {port}")
        args = [
            chrome,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1280,900",
            URLS[provider],
        ]
        subprocess.Popen(args)
        for _ in range(20):
            time.sleep(0.5)
            if _port_open(port):
                print(f"[OK] {provider} browser ready. Log in, then run: {provider}")
                return 0
        print("[WARN] Chrome did not come up in 10s — check for a popup or error")
        return 1


    def _load_runtime(provider: str):
        module = importlib.import_module(f"app.interception.{provider}")
        target = provider.replace("-", "").lower()
        candidates = []
        for name, obj in vars(module).items():
            if not isinstance(obj, type): continue
            if obj.__module__ != module.__name__: continue
            lname = name.lower()
            if lname == f"{target}runtime": return obj
            if lname.endswith("runtime"): candidates.append(obj)
        if candidates: return candidates[0]
        raise RuntimeError(f"no Runtime class in app.interception.{provider}")


    def _instantiate(cls, provider):
        sig = inspect.signature(cls.__init__)
        kwargs = {}
        for p in list(sig.parameters.values())[1:]:
            if p.name == "provider": kwargs["provider"] = provider
        try: return cls(**kwargs)
        except TypeError: return cls()


    async def _chat(provider: str) -> int:
        port = PORTS.get(provider, 0)
        if port and not _port_open(port):
            print(f"[FAIL] {provider} browser is not running on port {port}.")
            print(f"       Run this first:")
            print(f"           {provider} login")
            return 2

        try:
            RuntimeClass = _load_runtime(provider)
        except Exception as e:
            print(f"[FAIL] {e}"); return 3

        try:
            rt = _instantiate(RuntimeClass, provider)
        except Exception as e:
            print(f"[FAIL] cannot instantiate {RuntimeClass.__name__}: {e}"); return 3

        try:
            await rt.start()
        except Exception as e:
            msg = str(e)
            if "login" in msg.lower() or "not authenticated" in msg.lower() or "session" in msg.lower():
                print(f"[FAIL] {provider} is not logged in.")
                print(f"       Run: {provider} login")
                return 4
            print(f"[FAIL] start: {msg}")
            return 5

        print(f"Connected to {provider}. /exit or Ctrl+C to leave.\\n")
        prefix = f"{provider}> "
        try:
            while True:
                try:
                    line = input(prefix)
                except (EOFError, KeyboardInterrupt):
                    print(); break
                if not line.strip(): continue
                if line.strip() in {"/exit", "/back", "exit", "quit"}: break
                req = ProviderExecutionRequest(
                    provider=provider,
                    request_id=str(uuid.uuid4()),
                    messages=[{"role": "user", "content": line}],
                )
                print()
                got_reply = False
                async for ev in rt.execute(req):
                    if ev.delta:
                        print(ev.delta, end="", flush=True)
                        got_reply = True
                print()
                if not got_reply:
                    print(f"[WARN] no reply received. If you are logged out, run: {provider} login")
        finally:
            await rt.close()
        return 0


    async def main() -> int:
        if len(sys.argv) < 2:
            print("usage: chat_any <provider> [login]")
            return 1
        provider = sys.argv[1].lower()
        sub = sys.argv[2].lower() if len(sys.argv) > 2 else ""

        if sub == "login":
            return open_login_window(provider)
        return await _chat(provider)


    if __name__ == "__main__":
        sys.exit(asyncio.run(main()))
''')

(BE / "scripts" / "chat_any.py").write_text(chat_any, encoding="utf-8", newline="\n")
print("  [OK] chat_any.py rewritten (login subcommand + friendly errors)")

# ───────────────────────────────────────────────────────────
# 2. Rewrite all bin/*.cmd wrappers to pass through arguments
# ───────────────────────────────────────────────────────────
for name, provider in [("deepseek","deepseek"), ("claude","claude"),
                       ("chatgpt","chatgpt"), ("aigemini","gemini")]:
    cmd = (
        "@echo off\r\n"
        "set PYTHONUTF8=1\r\n"
        f'cd /d "{BE}"\r\n'
        f'"{PY}" -u -m scripts.chat_any {provider} %*\r\n'
    )
    (BIN / f"{name}.cmd").write_text(cmd, encoding="utf-8", newline="")
    print(f"  [OK] bin/{name}.cmd (passes %*)")

(BIN / "ai.cmd").write_text(
    "@echo off\r\n"
    "set PYTHONUTF8=1\r\n"
    f'cd /d "{BE}"\r\n'
    f'"{PY}" -u -m scripts.chat_any %*\r\n',
    encoding="utf-8", newline="",
)
print("  [OK] bin/ai.cmd")

# ───────────────────────────────────────────────────────────
# 3. Syntax + tests
# ───────────────────────────────────────────────────────────
def run(args, cwd=ROOT):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if r.stdout: print(r.stdout)
    if r.stderr.strip(): print(r.stderr)
    return r.returncode

r = subprocess.run([PY, "-c",
    f"import ast, pathlib; ast.parse(pathlib.Path(r'{BE / 'scripts' / 'chat_any.py'}').read_text(encoding='utf-8'))"],
    capture_output=True, text=True)
if r.returncode != 0:
    print("[FAIL] syntax:", r.stderr); sys.exit(1)
print("  [OK] syntax valid")

run([PY, "-m", "pytest", "-q",
     "tests/test_nonclaude_parsers.py",
     "tests/test_deepseek_think_response.py",
     "-o", "asyncio_mode=auto"], cwd=ROOT)

# ───────────────────────────────────────────────────────────
# 4. Commit
# ───────────────────────────────────────────────────────────
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "feat(cli): <provider> login subcommand + friendly not-running/not-logged-in errors"])
print(r.stdout.strip() or r.stderr.strip())

print()
print("=" * 60)
print("HOW IT WORKS NOW:")
print()
print("  chatgpt login     -> opens a visible Chrome for login")
print("  chatgpt           -> if browser missing: tells you to run login")
print("                       if logged in: replies normally")
print("                       if logged out: tells you to run login")
print()
print("  Same for deepseek, claude, aigemini")
print("=" * 60)
