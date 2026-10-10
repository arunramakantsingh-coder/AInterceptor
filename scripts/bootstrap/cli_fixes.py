import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BIN  = ROOT / "bin"

# Rename gemini.cmd -> aigemini.cmd to avoid collision with Google's CLI
old = BIN / "gemini.cmd"
new = BIN / "aigemini.cmd"
if old.exists():
    txt = old.read_text(encoding="utf-8")
    new.write_text(txt, encoding="utf-8", newline="")
    old.unlink()
    print("  [OK] renamed gemini.cmd -> aigemini.cmd")

# Add an `ai` universal launcher for any provider
(BIN / "ai.cmd").write_text(
    "@echo off\r\n"
    "set PYTHONUTF8=1\r\n"
    f'cd /d "{ROOT / "backend"}"\r\n'
    f'"C:\\Projects\\Atlas\\.venv\\Scripts\\python.exe" -u -m scripts.chat_any %*\r\n',
    encoding="utf-8", newline="",
)
print("  [OK] bin/ai.cmd")

# Start both missing Chromes off-screen
def run(args):
    return subprocess.run(args, capture_output=True, text=True, shell=True)

for prov, port, url, prof in [
    ("chatgpt", 9224, "https://chatgpt.com/", "chrome-profile-chatgpt"),
    ("gemini", 9225, "https://gemini.google.com/", "chrome-profile-gemini"),
]:
    listen = run(['powershell','-Command',
        f'(Get-NetTCPConnection -LocalPort {port} -State Listen -EA SilentlyContinue) -ne $null'])
    if "True" in listen.stdout:
        print(f"  [OK] {prov} already on {port}")
        continue
    profile_dir = ROOT / ".ainterceptor" / prof
    profile_dir.mkdir(parents=True, exist_ok=True)
    cmd = (
        f'$c="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"; '
        f'if (!(Test-Path $c)) {{ $c="C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe" }}; '
        f'Start-Process $c -ArgumentList "--remote-debugging-port={port}",'
        f'"--user-data-dir={profile_dir}","--no-first-run","--no-default-browser-check",'
        f'"--window-position=-32000,-32000","{url}"'
    )
    run(["powershell","-Command", cmd])
    print(f"  [OK] launching {prov} off-screen on {port}")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "chore(cli): rename gemini->aigemini (avoid Google CLI collision); add ai wrapper"])
print(r.stdout.strip() or r.stderr.strip())

print()
print("=" * 60)
print("NOW USE:")
print("  deepseek     -> DeepSeek REPL")
print("  claude       -> Claude REPL")
print("  chatgpt      -> ChatGPT REPL")
print("  aigemini     -> Gemini REPL (our launcher)")
print("  ai <provider> -> generic form")
print()
print("Log into the newly-launched ChatGPT / Gemini windows once.")
print("=" * 60)
