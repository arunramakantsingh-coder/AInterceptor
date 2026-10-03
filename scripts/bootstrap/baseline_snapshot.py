import pathlib, subprocess, hashlib

ROOT = pathlib.Path.cwd()

def run(a):
    r = subprocess.run(a, cwd=ROOT, capture_output=True, text=True, shell=True)
    return r.stdout.strip(), r.stderr.strip()

print("="*66)
print("CLAUDE FILES — current SHA256 (so we can prove they don't change)")
print("="*66)
targets = [
    "backend/app/interception/claude.py",
    "backend/app/interception/claude_transport.py",
    "backend/app/interception/runtime.py",
    "backend/app/interception/web_runtime.py",
]
for t in targets:
    p = ROOT / t
    if p.exists():
        h = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        print(f"  {h}  {t}")
    else:
        print(f"  (missing)  {t}")

print()
print("="*66)
print("CURRENT BRANCH + HEAD")
print("="*66)
for cmd in ["git rev-parse --abbrev-ref HEAD", "git rev-parse HEAD",
            "git status --short", "git branch -a", "git tag --list"]:
    out, err = run(cmd.split())
    print(f"$ {cmd}")
    print(out or err)
    print()

print("="*66)
print("CLI LAUNCH SANITY (non-interactive, just import)")
print("="*66)
out, err = run(["python", "-c", "from cli.shell import AIRouterShell; s = AIRouterShell(); print('Shell loaded OK'); print('Modes:', [m.value for m in s.state.mode.__class__])"])
print(out or err)

print()
print("="*66)
print("TEST SUITE COUNTS")
print("="*66)
for cwd, t in [(str(ROOT), "tests/"), (str(ROOT/"backend"), "tests/")]:
    p = ROOT / cwd / t if (ROOT/cwd).exists() else None
    if p and p.exists():
        out, _ = run(["python", "-m", "pytest", "-q", str(p), "-o", "asyncio_mode=auto"])
        print(f"[{cwd}] {out.splitlines()[-1] if out else '(no output)'}")
