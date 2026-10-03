"""discover_layout.py — read-only. Tells us the real branch layout."""
import subprocess, pathlib, sys, os

ROOT = pathlib.Path.cwd()
if not (ROOT / ".git").exists():
    print(f"[FAIL] no .git in {ROOT}"); sys.exit(1)

def run(args):
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, shell=True)
    return (r.stdout or "").strip(), (r.stderr or "").strip(), r.returncode

def hr(title):
    print()
    print("=" * 64)
    print(title)
    print("=" * 64)

hr("REPO ROOT")
print(ROOT)

hr("BRANCHES")
out, _, _ = run(["git", "branch", "-a"])
print(out or "(none)")

hr("CURRENT HEAD")
out, _, _ = run(["git", "rev-parse", "HEAD"])
print(out)
out, _, _ = run(["git", "log", "--oneline", "-10"])
print(out)

hr("TAGS")
out, _, _ = run(["git", "tag", "--list"])
print(out or "(none)")

hr("REMOTES")
out, _, _ = run(["git", "remote", "-v"])
print(out or "(none)")

hr("STATUS")
out, _, _ = run(["git", "status", "--short"])
print(out or "(clean)")

hr("TRACKED FILES (all)")
out, _, _ = run(["git", "ls-files"])
files = [f for f in out.split("\n") if f]
print(f"total tracked: {len(files)}")

hr("FILES CONTAINING 'deepseek'")
for f in files:
    if "deepseek" in f.lower():
        print(" ", f)

hr("FILES CONTAINING 'provider'")
for f in files:
    if "provider" in f.lower():
        print(" ", f)

hr("FILES CONTAINING 'intercept' OR 'runtime' OR 'cdp'")
for f in files:
    if any(k in f.lower() for k in ("intercept","runtime","cdp")):
        print(" ", f)

hr("FILES CONTAINING 'cli' OR 'airouter'")
for f in files:
    if "cli" in f.lower() or "airouter" in f.lower():
        print(" ", f)

hr("TOP-LEVEL LAYOUT (depth <= 3, excluding .git/node_modules/.venv)")
for p in sorted(ROOT.rglob("*")):
    if any(part in (".git","node_modules",".venv","__pycache__",".next",".evidence",".bak")
           for part in p.parts):
        continue
    try:
        rel = p.relative_to(ROOT)
    except ValueError:
        continue
    depth = len(rel.parts)
    if depth <= 3:
        indent = "  " * (depth - 1)
        suffix = "/" if p.is_dir() else ""
        print(f"{indent}{p.name}{suffix}")

hr("AIRouter ENTRYPOINT")
for candidate in ["airouter.py","airouter","pyproject.toml","setup.py","setup.cfg"]:
    p = ROOT / candidate
    if p.exists():
        print(f"  FOUND: {candidate}")

hr("PYTHON PACKAGES (dirs with __init__.py)")
pkg_dirs = set()
for p in ROOT.rglob("__init__.py"):
    if ".git" in p.parts or ".venv" in p.parts or "node_modules" in p.parts:
        continue
    pkg_dirs.add(p.parent.relative_to(ROOT))
for d in sorted(pkg_dirs):
    print(" ", d)

hr("RESULT")
print("RESULT: PASS")
print("Copy the entire output above and paste it back.")
