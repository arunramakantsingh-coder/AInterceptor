import pathlib, subprocess

ROOT = pathlib.Path.cwd()

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)

# Verify the doc exists
P = ROOT / "PROJECT" / "ARCHITECTURE_v2.md"
if not P.exists():
    print("[FAIL] PROJECT/ARCHITECTURE_v2.md not found — run arch_v2_doc.py first")
    raise SystemExit(1)

# Commit
git(["add", "PROJECT/ARCHITECTURE_v2.md"])
r = git(["commit", "-m",
         "docs: Architecture v2 approved (daemon, Patchright, CDP capture, circuit breakers, session export)"])
print((r.stdout.strip() or r.stderr.strip())[:300])

# Tag as approved design baseline
git(["tag", "-a", "arch-v2-approved",
     "-m", "Architecture v2 approved by owner"])
print("[OK] tagged arch-v2-approved")

sha = git(["rev-parse", "HEAD"]).stdout.strip()
print(f"\n  Commit: {sha[:10]}")
print(f"  Tag:    arch-v2-approved")
