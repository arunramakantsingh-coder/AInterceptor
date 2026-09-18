import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
BIN  = ROOT / "bin"
BIN.mkdir(exist_ok=True)
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

wrappers = {
    "login":    "login",
    "hide":     "hide",
    "status":   "status",
    "aid":      None,   # passes args through
}

for name, sub in wrappers.items():
    if sub:
        body = (
            "@echo off\r\n"
            "set PYTHONUTF8=1\r\n"
            f'cd /d "{BE}"\r\n'
            f'"{PY}" -u -m scripts.chat_any {sub} %*\r\n'
        )
    else:
        body = (
            "@echo off\r\n"
            "set PYTHONUTF8=1\r\n"
            f'cd /d "{BE}"\r\n'
            f'"{PY}" -u -m scripts.chat_any %*\r\n'
        )
    (BIN / f"{name}.cmd").write_text(body, encoding="utf-8", newline="")
    print(f"  [OK] bin/{name}.cmd")

# Ensure USER PATH contains bin/
ps = f'''
$bin = "{BIN}"
$p = [Environment]::GetEnvironmentVariable("Path", "User")
if ($p -notlike "*$bin*") {{
    [Environment]::SetEnvironmentVariable("Path", "$p;$bin", "User")
    Write-Host "added to USER PATH"
}} else {{
    Write-Host "already on USER PATH"
}}
'''
r = subprocess.run(["powershell","-NoProfile","-Command", ps],
                   capture_output=True, text=True, shell=True)
print("  " + (r.stdout.strip() or r.stderr.strip()))

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","feat(cli): login/hide/status wrappers"])
print(r.stdout.strip() or r.stderr.strip())

print()
print("=" * 60)
print("OPEN A NEW POWERSHELL WINDOW, THEN:")
print("  login chatgpt")
print("  login claude")
print("  login gemini")
print("  login deepseek")
print("  hide")
print("  deepseek")
print("=" * 60)
