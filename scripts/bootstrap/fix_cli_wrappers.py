import subprocess, pathlib, os

ROOT = pathlib.Path.cwd()
BIN  = ROOT / "bin"

print("==> Current bin/ contents")
if BIN.exists():
    for f in sorted(BIN.iterdir()):
        print(f"  {f.name}")
else:
    print("  [FAIL] bin/ does not exist")

print("\n==> What 'gemini' currently resolves to")
r = subprocess.run(["where.exe", "gemini"], capture_output=True, text=True, shell=True)
print(r.stdout.strip() or "(not found)")

print("\n==> What 'chatgpt' currently resolves to")
r = subprocess.run(["where.exe", "chatgpt"], capture_output=True, text=True, shell=True)
print(r.stdout.strip() or "(not found)")

print("\n==> What 'deepseek' currently resolves to")
r = subprocess.run(["where.exe", "deepseek"], capture_output=True, text=True, shell=True)
print(r.stdout.strip() or "(not found)")

# Rename our gemini.cmd to aigemini.cmd to avoid Google CLI collision
gemini_cmd = BIN / "gemini.cmd"
if gemini_cmd.exists():
    gemini_cmd.rename(BIN / "aigemini.cmd")
    print("\n  [OK] renamed gemini.cmd -> aigemini.cmd")

# Ensure ALL our .cmd wrappers exist
PY = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
BE = ROOT / "backend"
for name in ["deepseek", "claude", "chatgpt", "aigemini", "ai"]:
    p = BIN / f"{name}.cmd"
    content = (
        "@echo off\r\n"
        "set PYTHONUTF8=1\r\n"
        f"cd /d \"{BE}\"\r\n"
        f"\"{PY}\" -u -m scripts.chat_any {name if name != 'ai' else '%*'}\r\n"
    )
    p.write_text(content, encoding="utf-8", newline="")
    print(f"  [OK] wrote bin/{name}.cmd")

# Append bin/ to USER PATH (permanent)
ps = f'''
$bin = "{BIN}"
$p = [Environment]::GetEnvironmentVariable("Path", "User")
if ($p -notlike "*$bin*") {{
    [Environment]::SetEnvironmentVariable("Path", $p + ";" + $bin, "User")
    Write-Host "added to USER PATH"
}} else {{
    Write-Host "already on USER PATH"
}}
'''
r = subprocess.run(["powershell","-NoProfile","-Command", ps],
                   capture_output=True, text=True, shell=True)
print("\n  " + (r.stdout.strip() or r.stderr.strip()))

# Commit
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","chore(cli): rename gemini->aigemini; ensure all wrappers exist"])
print(r.stdout.strip() or r.stderr.strip())

print()
print("=" * 60)
print("OPEN A BRAND NEW POWERSHELL WINDOW, THEN USE:")
print("  deepseek")
print("  claude")
print("  chatgpt")
print("  aigemini    <-- Gemini (NOT `gemini`, that is Google's own CLI)")
print("=" * 60)
