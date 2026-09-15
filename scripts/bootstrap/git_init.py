# git_init.py — initialize git repo, wire remote, set identity
import subprocess, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent
REMOTE = "https://github.com/arunramakantsingh-coder/AInterceptor.git"
EMAIL = "arunramakantsingh@gmail.com"
NAME  = "Arun Ramakantsingh"

def run(args, check=True):
    print(f"  $ {' '.join(args)}")
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if r.stdout.strip(): print("   ", r.stdout.strip())
    if r.stderr.strip(): print("   ", r.stderr.strip())
    if check and r.returncode != 0:
        print(f"FAIL: exit {r.returncode}")
        sys.exit(1)
    return r

print("==> Initializing git")
if not (ROOT / ".git").exists():
    run(["git", "init", "-b", "main"])
else:
    print("    .git already exists")

run(["git", "config", "user.email", EMAIL])
run(["git", "config", "user.name", NAME])

print("==> Configuring remote")
r = subprocess.run(["git", "remote", "get-url", "origin"],
                   cwd=ROOT, capture_output=True, text=True)
if r.returncode != 0:
    run(["git", "remote", "add", "origin", REMOTE])
else:
    run(["git", "remote", "set-url", "origin", REMOTE])

print("=" * 44)
print("SCRIPT: git_init.py")
print("RESULT: PASS")
print("NEXT: powershell -ExecutionPolicy Bypass -File scripts\\milestone_commit.ps1 -Milestone M0")
print("=" * 44)