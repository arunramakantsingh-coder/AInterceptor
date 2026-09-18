import pathlib, subprocess, sys, textwrap, os

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
BIN  = ROOT / "bin"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

# ══════════════════════════════════════════════════════════════
# 1. Make daemon log to a file so we can see crashes
# ══════════════════════════════════════════════════════════════
daemon_path = BE / "scripts" / "aidaemon.py"
src = daemon_path.read_text(encoding="utf-8")

if "LOGFILE" not in src:
    # Insert file logging near the top
    src = src.replace(
        "import asyncio, ctypes, importlib, json, os, pathlib, socket, subprocess, sys, time",
        "import asyncio, ctypes, importlib, json, os, pathlib, socket, subprocess, sys, time, traceback\n"
    )
    # Add log dir + file redirect right after STATE_DIR
    src = src.replace(
        '    STATE_DIR = ROOT / ".ainterceptor"\n    STATE_DIR.mkdir(exist_ok=True)',
        '    STATE_DIR = ROOT / ".ainterceptor"\n'
        '    STATE_DIR.mkdir(exist_ok=True)\n'
        '    LOGFILE = STATE_DIR / "daemon.log"\n'
        '    _log = open(LOGFILE, "a", encoding="utf-8", buffering=1)\n'
        '    def log(*a):\n'
        '        msg = " ".join(str(x) for x in a)\n'
        '        print(msg, file=_log)\n'
        '        print(msg, file=sys.stderr, flush=True)\n'
    )
    daemon_path.write_text(src, encoding="utf-8", newline="\n")
    print("  [OK] daemon now writes .ainterceptor/daemon.log")

# ══════════════════════════════════════════════════════════════
# 2. Fix chat_any.py: login/show/hide/status BEFORE treating arg as provider
# ══════════════════════════════════════════════════════════════
chat_path = BE / "scripts" / "chat_any.py"
src = chat_path.read_text(encoding="utf-8")

# Find the main() dispatch and replace it
old_main = '''    async def main():
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
        return await chat_local(provider)'''

new_main = '''    SUBCOMMANDS = {"login", "show", "hide", "status"}

    async def main():
        args = sys.argv[1:]
        if not args:
            print("usage: chat_any <provider> [login|show|hide|status]")
            return 1

        # Verb-first form:  daemon login deepseek
        if args[0].lower() in SUBCOMMANDS:
            if len(args) < 2:
                print(f"usage: chat_any {args[0].lower()} <provider>")
                return 1
            sub = args[0].lower()
            provider = args[1].lower()
            if sub == "status":
                if not daemon_alive():
                    print("aidaemon  ●  not running"); return 0
                print(daemon_call("GET", "/")); return 0
            if not daemon_alive():
                print("[FAIL] daemon not running. Start it with: aidaemon start")
                return 2
            try:
                print(daemon_call("POST", f"/{sub}/{provider}"))
            except Exception as e:
                print(f"[FAIL] {e}")
            return 0

        # Provider-first form:  <provider> [sub]
        provider = args[0].lower()
        sub = args[1].lower() if len(args) > 1 and args[1].lower() in SUBCOMMANDS else ""
        if sub:
            if not daemon_alive():
                print("[FAIL] daemon not running. Start it with: aidaemon start")
                return 2
            try:
                print(daemon_call("POST", f"/{sub}/{provider}"))
            except Exception as e:
                print(f"[FAIL] {e}")
            return 0

        if daemon_alive():
            return await chat_via_daemon(provider)
        print("[WARN] daemon not running — falling back to local (browser will appear)")
        print("       To use the daemon: aidaemon start")
        return await chat_local(provider)'''

if old_main in src:
    src = src.replace(old_main, new_main, 1)
    chat_path.write_text(src, encoding="utf-8", newline="\n")
    print("  [OK] chat_any.py: verb-first subcommand dispatch")
else:
    print("  [!] main() pattern not matched")

# ══════════════════════════════════════════════════════════════
# 3. Rewrite aidaemon.cmd: capture log, don't use pythonw
# ══════════════════════════════════════════════════════════════
(BIN / "aidaemon.cmd").write_text(
    "@echo off\r\n"
    "set PYTHONUTF8=1\r\n"
    f'cd /d "{BE}"\r\n'
    "if \"%1\"==\"\" goto help\r\n"
    "if \"%1\"==\"start\" goto start\r\n"
    "if \"%1\"==\"stop\" goto stop\r\n"
    "if \"%1\"==\"status\" goto status\r\n"
    "if \"%1\"==\"restart\" goto restart\r\n"
    "if \"%1\"==\"help\" goto help\r\n"
    "if \"%1\"==\"log\" goto log\r\n"
    "echo Unknown command: %1\r\n"
    "goto help\r\n"
    "\r\n"
    ":start\r\n"
    "echo Starting aidaemon...\r\n"
    f'start \"aidaemon\" /min \"{PY}\" -u -m scripts.aidaemon\r\n'
    "timeout /t 3 /nobreak >nul\r\n"
    "goto status\r\n"
    "\r\n"
    ":stop\r\n"
    f'\"{PY}\" -c \"import urllib.request; urllib.request.urlopen(urllib.request.Request(\\\"http://127.0.0.1:7700/shutdown\\\", method=\\\"POST\\\"), timeout=5)\" 2>nul\r\n'
    "echo aidaemon stopped\r\n"
    "goto :eof\r\n"
    "\r\n"
    ":status\r\n"
    f'\"{PY}\" -u scripts\\\\daemon_status.py\r\n'
    "goto :eof\r\n"
    "\r\n"
    ":log\r\n"
    f'type \"{ROOT}\\.ainterceptor\\daemon.log\"\r\n'
    "goto :eof\r\n"
    "\r\n"
    ":restart\r\n"
    "call \"%~f0\" stop\r\n"
    "timeout /t 2 /nobreak >nul\r\n"
    "call \"%~f0\" start\r\n"
    "goto :eof\r\n"
    "\r\n"
    ":help\r\n"
    "echo.\r\n"
    "echo AIDAEMON - AInterceptor session manager\r\n"
    "echo.\r\n"
    "echo USAGE:\r\n"
    "echo   aidaemon start       Start the background daemon\r\n"
    "echo   aidaemon stop        Stop the daemon and all browsers\r\n"
    "echo   aidaemon status      Show provider status\r\n"
    "echo   aidaemon restart     Restart the daemon\r\n"
    "echo   aidaemon log         Show daemon log\r\n"
    "echo.\r\n"
    "echo CHAT:\r\n"
    "echo   deepseek             Open DeepSeek chat\r\n"
    "echo   claude               Open Claude chat\r\n"
    "echo   chatgpt              Open ChatGPT chat\r\n"
    "echo   aigemini             Open Gemini chat\r\n"
    "echo.\r\n"
    "echo LOGIN:\r\n"
    "echo   daemon login ^<provider^>    Open browser for login\r\n"
    "echo   daemon hide  ^<provider^>    Hide the browser again\r\n"
    "echo   daemon show  ^<provider^>    Bring browser on-screen\r\n"
    "echo.\r\n"
    "goto :eof\r\n",
    encoding="utf-8", newline="",
)
print("  [OK] bin/aidaemon.cmd rewritten (log + python, not pythonw)")

# ══════════════════════════════════════════════════════════════
# 4. Ensure bin/ is on USER PATH (permanent)
# ══════════════════════════════════════════════════════════════
ps = f'''
$bin = "{BIN}"
$p = [Environment]::GetEnvironmentVariable("Path", "User")
if ($p -notlike "*$bin*") {{
    [Environment]::SetEnvironmentVariable("Path", "$p;$bin", "User")
    Write-Host "added $bin to USER PATH"
}} else {{
    Write-Host "$bin already on USER PATH"
}}
'''
r = subprocess.run(["powershell","-NoProfile","-Command", ps],
                   capture_output=True, text=True, shell=True)
print("  " + (r.stdout.strip() or r.stderr.strip()))

# ══════════════════════════════════════════════════════════════
# 5. Syntax check
# ══════════════════════════════════════════════════════════════
import ast
for f in ["aidaemon.py", "chat_any.py"]:
    try:
        ast.parse((BE/"scripts"/f).read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {f}: {e}"); sys.exit(1)
print("  [OK] syntax valid")

# ══════════════════════════════════════════════════════════════
# 6. Kill stale daemon, restart with logging
# ══════════════════════════════════════════════════════════════
subprocess.run(["powershell","-NoProfile","-Command",
    "Get-Process python -EA SilentlyContinue | "
    "Where-Object { $_.Path -like '*Atlas*' } | "
    "Stop-Process -Force -EA SilentlyContinue"],
    capture_output=True, shell=True)

log = ROOT / ".ainterceptor" / "daemon.log"
if log.exists():
    log.unlink()

print("\n==> Starting daemon (visible window, logs to .ainterceptor/daemon.log)")
subprocess.Popen(
    [PY, "-u", "-m", "scripts.aidaemon"],
    cwd=BE,
    creationflags=subprocess.CREATE_NEW_CONSOLE,
)

import time as _t
for _ in range(20):
    _t.sleep(0.5)
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:7700/", timeout=0.8) as r:
            print("  [OK] daemon alive")
            break
    except Exception:
        continue
else:
    print("  [FAIL] daemon crashed — see log below")
    if log.exists():
        print(log.read_text(encoding="utf-8", errors="replace"))

# ══════════════════════════════════════════════════════════════
# 7. Commit
# ══════════════════════════════════════════════════════════════
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(daemon): verb-first subcommands + log to file + visible launcher"])
print(r.stdout.strip() or r.stderr.strip())

print()
print("=" * 66)
print("OPEN A NEW POWERSHELL WINDOW. Then:")
print()
print("  aidaemon status             -> readable table")
print("  deepseek login              -> visible window to log in")
print("  deepseek                    -> chat, no window")
print()
print("If aidaemon says 'daemon not running':")
print("  aidaemon start")
print("  aidaemon log                -> shows why if it crashes")
print("=" * 66)
