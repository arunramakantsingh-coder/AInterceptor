import pathlib, subprocess, sys, re, ast

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists():
    PY = sys.executable

ds = BE / "app/interception/deepseek.py"
src = ds.read_text(encoding="utf-8")
lines = src.splitlines()

# ── Find the misplaced future import and the offending line before it ──
future_idx = None
for i, ln in enumerate(lines):
    if ln.strip() == "from __future__ import annotations":
        future_idx = i
        break

if future_idx is None:
    print("  [FAIL] 'from __future__ import annotations' not found")
    sys.exit(1)

print(f"  future import at line {future_idx+1}")
print(f"  lines BEFORE future import:")
for i in range(future_idx):
    print(f"    {i+1}: {lines[i]!r}")

# ── Identify what's before it that shouldn't be ──
# Allowed before: empty lines, comments (#), docstring (triple quote)
def is_allowed_before(line: str) -> bool:
    s = line.strip()
    return s == "" or s.startswith("#")

offenders = [(i, lines[i]) for i in range(future_idx) if not is_allowed_before(lines[i])]
print(f"  offenders: {len(offenders)}")
for i, ln in offenders:
    print(f"    line {i+1}: {ln}")

# ── Move offenders to AFTER the future import + its sibling imports ──
if offenders:
    # Remove them from their current positions (reverse order to keep indices)
    offender_indices = sorted([i for i, _ in offenders], reverse=True)
    offender_lines = []
    for i in sorted([i for i, _ in offenders]):
        offender_lines.append(lines[i])
    for i in offender_indices:
        del lines[i]

    # Now find the new position of the future import
    new_future_idx = next(
        i for i, ln in enumerate(lines)
        if ln.strip() == "from __future__ import annotations"
    )
    # Skip past any subsequent `from`/`import` lines that come right after
    insert_at = new_future_idx + 1
    while insert_at < len(lines) and (
        lines[insert_at].startswith("import ") or
        lines[insert_at].startswith("from ") or
        lines[insert_at].strip() == ""
    ):
        insert_at += 1

    # Insert the offenders there
    lines[insert_at:insert_at] = offender_lines
    print(f"  [OK] moved {len(offender_lines)} line(s) to position {insert_at+1}")

    ds.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
else:
    print("  [OK] nothing to move")

# ── Syntax-check the file ──
try:
    ast.parse(ds.read_text(encoding="utf-8"))
    print("  [OK] syntax valid")
except SyntaxError as e:
    print(f"  [FAIL] syntax still broken: {e}")
    sys.exit(1)

# ── Verify all critical modules import ──
probe = (
    "import sys, pathlib\n"
    "sys.path.insert(0, r'" + str(BE) + "')\n"
    "import app.interception.deepseek as d\n"
    "import app.interception.nonclaude_runtime as n\n"
    "from app.interception.registry import cdp_url\n"
    "print('deepseek:', d.DeepSeekRuntime.__name__)\n"
    "print('nonclaude:', n.NonClaudeNetworkCapture.__name__)\n"
    "print('deepseek CDP:', cdp_url('deepseek'))\n"
    "print('claude   CDP:', cdp_url('claude'))\n"
)
r = subprocess.run([PY, "-c", probe], capture_output=True, text=True)
print("\n==> Module import probe")
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr)
if r.returncode != 0:
    print("  [FAIL] imports still broken")
    sys.exit(1)

# ── Verify the CLI imports too ──
probe2 = (
    "import sys\n"
    "sys.path.insert(0, r'" + str(ROOT) + "')\n"
    "sys.path.insert(0, r'" + str(BE) + "')\n"
    "import cli.main\n"
    "import cli.shell\n"
    "print('CLI imports OK')\n"
)
r = subprocess.run([PY, "-c", probe2], capture_output=True, text=True)
print("\n==> CLI import probe")
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr)
if r.returncode != 0:
    print("  [FAIL] CLI still can't import")
    sys.exit(1)

# ── Commit ──
def git(args):
    return subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)
git(["add", "-A"])
r = git(["commit", "-m",
         "fix(deepseek): move registry import after __future__ to restore CLI boot"])
print("\n" + (r.stdout.strip() or r.stderr.strip()))

# ── Reinstall CLI (entry points pick up new code automatically, but be safe) ──
print("\n==> Reinstalling CLI entry points")
r = subprocess.run([PY, "-m", "pip", "install", "-q", "-e", str(ROOT)],
                   capture_output=True, text=True)
print(r.stdout or r.stderr)

print("=" * 60)
print("RESULT: PASS")
print("NEXT — try the CLI again:")
print("  bootai")
print("  (or) airouter")
print("=" * 60)
