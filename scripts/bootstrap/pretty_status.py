import pathlib, subprocess, sys, textwrap

ROOT = pathlib.Path.cwd()
BIN  = ROOT / "bin"
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

# ── helper script that pretty-prints daemon status ──
helper = BE / "scripts" / "daemon_status.py"
helper.write_text(textwrap.dedent('''
    """Pretty printer for aidaemon status."""
    import json, urllib.request, sys, pathlib

    def main():
        try:
            with urllib.request.urlopen("http://127.0.0.1:7700/", timeout=2) as r:
                data = json.loads(r.read())
        except Exception:
            print("aidaemon  ●  not running")
            print("           start with: aidaemon start")
            return 0

        print("aidaemon  ●  running")
        print()
        print(f"  {'PROVIDER':<10} {'PORT':<6} {'BROWSER':<10} {'ATTACHED':<10}")
        print("  " + "-" * 40)
        for name, cfg in data["providers"].items():
            browser = "alive" if cfg["chrome_alive"] else "off"
            attached = "yes" if cfg["attached"] else "no"
            print(f"  {name:<10} {cfg['port']:<6} {browser:<10} {attached:<10}")
        print()
        print("  Browser launches on first use. Login once with:")
        print("     daemon login <provider>")
        print()
        print("  Chat:  deepseek  |  claude  |  chatgpt  |  aigemini")
        return 0

    sys.exit(main())
'''), encoding="utf-8", newline="\n")
print(f"  [OK] {helper.relative_to(ROOT)}")

# ── rewrite aidaemon.cmd with proper usage + pretty status ──
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
    "if \"%1\"==\"-h\" goto help\r\n"
    "if \"%1\"==\"--help\" goto help\r\n"
    "echo Unknown command: %1\r\n"
    "goto help\r\n"
    "\r\n"
    ":start\r\n"
    "echo Starting aidaemon...\r\n"
    f'start \"\" /b \"{PY.replace("python.exe","pythonw.exe")}\" -m scripts.aidaemon\r\n'
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
    "echo   aidaemon help        Show this message\r\n"
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
print("  [OK] bin/aidaemon.cmd rewritten")

# syntax check
import ast
try:
    ast.parse(helper.read_text(encoding="utf-8"))
except SyntaxError as e:
    print("[FAIL]", e); sys.exit(1)
print("  [OK] syntax valid")

# commit
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "feat(cli): readable aidaemon status + proper help output"])
print(r.stdout.strip() or r.stderr.strip())

print()
print("=" * 60)
print("Try now:")
print("  aidaemon status")
print("  aidaemon help")
print("=" * 60)
