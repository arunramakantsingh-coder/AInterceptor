import pathlib, subprocess, sys, ast, re

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app"
D = BE / "runtime" / "daemon.py"
src = D.read_text(encoding="utf-8")

print("==> Current syntax status")
syntax_err = None
try:
    ast.parse(src)
    print("  [OK] valid — nothing to fix")
    sys.exit(0)
except SyntaxError as err:
    syntax_err = err
    print(f"  [FAIL] line {err.lineno}: {err.msg}")

lines = src.splitlines()
lineno = syntax_err.lineno or 1

print(f"\n==> Context around line {lineno}")
for i in range(max(0, lineno - 15), min(len(lines), lineno + 10)):
    m = ">>>" if i + 1 == lineno else "   "
    print(f"  {m} {i+1:4d}  {lines[i]}")

# Repair: find orphan else blocks (an else: with no matching if: above it)
print("\n==> Looking for orphan else blocks")
fixed = False
for i, ln in enumerate(lines):
    stripped = ln.strip()
    if stripped == "else:":
        indent = len(ln) - len(ln.lstrip())
        has_match = False
        for j in range(i - 1, max(0, i - 40), -1):
            prev = lines[j]
            prev_indent = len(prev) - len(prev.lstrip())
            if prev.strip().startswith("if ") and prev_indent == indent:
                has_match = True
                break
            if prev.strip().startswith(("def ", "class ")) and prev_indent < indent:
                break
            # also match `elif` at same indent as the else
            if prev.strip().startswith("elif ") and prev_indent == indent:
                has_match = True
                break
        if not has_match:
            print(f"  orphan else at line {i+1}: {ln!r}")
            # Remove the else: and the block below it
            end = i + 1
            while end < len(lines):
                nxt = lines[end]
                if nxt.strip() == "":
                    end += 1
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip())
                if nxt_indent > indent:
                    end += 1
                    continue
                break
            del lines[i:end]
            fixed = True
            break

if not fixed:
    print("  [i] no orphan else found — manual inspection needed")
    sys.exit(1)

new_src = "\n".join(lines) + "\n"
print("\n==> Verifying new source")
try:
    ast.parse(new_src)
    print("  [OK] syntax now valid")
except SyntaxError as e2:
    print(f"  [FAIL] still broken: line {e2.lineno}: {e2.msg}")
    for i in range(max(0, e2.lineno - 10), min(len(lines), e2.lineno + 5)):
        m = ">>>" if i + 1 == e2.lineno else "   "
        print(f"  {m} {i+1:4d}  {lines[i]}")
    sys.exit(1)

D.write_text(new_src, encoding="utf-8", newline="\n")
print("  [OK] file written")

# Import test
PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable
probe = (
    "import sys\n"
    f"sys.path.insert(0, r'{ROOT / 'backend'}')\n"
    "import app.runtime.daemon\n"
    "print('daemon module import OK')\n"
)
r = subprocess.run([str(PY), "-c", probe], cwd=str(ROOT / "backend"),
                   capture_output=True, text=True, encoding="utf-8")
print("\n==> Import test")
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr[-500:])

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add", "-A"])
r = git(["commit", "-m", "fix(daemon): remove orphan else block"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("NEXT: .\\run-windows.ps1")
