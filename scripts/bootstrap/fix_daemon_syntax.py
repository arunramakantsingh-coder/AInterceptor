import pathlib, subprocess, sys, ast, re

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app"
D = BE / "runtime" / "daemon.py"
src = D.read_text(encoding="utf-8")

print("==> Current syntax status")
try:
    ast.parse(src)
    print("  [OK] valid")
    sys.exit(0)
except SyntaxError as e:
    print(f"  [FAIL] line {e.lineno}: {e.msg}")

lines = src.splitlines()
print(f"\n==> Context around line {e.lineno}")
for i in range(max(0, e.lineno - 12), min(len(lines), e.lineno + 8)):
    m = ">>>" if i + 1 == e.lineno else "   "
    print(f"  {m} {i+1:4d}  {lines[i]}")

# Repair: find orphan `else:` that has no matching `if:` above it
# Common symptom: leftover `else:` after we removed `if prober is not None:`
print("\n==> Looking for orphan else blocks")
fixed = False

# Pattern: blank line, then "    else:" with no if above in the same block
for i, ln in enumerate(lines):
    stripped = ln.strip()
    if stripped == "else:":
        # Look back up to 30 lines for a matching `if` at same indent
        indent = len(ln) - len(ln.lstrip())
        has_match = False
        for j in range(i - 1, max(0, i - 40), -1):
            prev = lines[j]
            prev_indent = len(prev) - len(prev.lstrip())
            if prev.strip().startswith("if ") and prev_indent == indent:
                has_match = True
                break
            # stop if we hit a def/class at lower indent
            if prev.strip().startswith(("def ", "class ")) and prev_indent < indent:
                break
        if not has_match:
            print(f"  found orphan else at line {i+1}: {ln!r}")
            # Remove the else and everything indented under it
            end = i + 1
            while end < len(lines):
                next_line = lines[end]
                if next_line.strip() == "":
                    end += 1
                    continue
                next_indent = len(next_line) - len(next_line.lstrip())
                if next_indent > indent:
                    end += 1
                    continue
                break
            # Delete lines i..end-1
            del lines[i:end]
            fixed = True
            break

if fixed:
    new_src = "\n".join(lines) + "\n"
    try:
        ast.parse(new_src)
        D.write_text(new_src, encoding="utf-8", newline="\n")
        print("  [OK] orphan else block removed, syntax now valid")
    except SyntaxError as e2:
        print(f"  [FAIL] still broken: line {e2.lineno}: {e2.msg}")
        for i in range(max(0, e2.lineno - 10), min(len(lines), e2.lineno + 5)):
            m = ">>>" if i + 1 == e2.lineno else "   "
            print(f"  {m} {i+1:4d}  {lines[i]}")
        sys.exit(1)
else:
    print("  [i] no orphan else found — manual inspection needed")
    sys.exit(1)

# Test import
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
if r.stderr.strip(): print("STDERR:", r.stderr[-400:])

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add", "-A"])
r = git(["commit", "-m", "fix(daemon): remove orphan else from prober patch"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("NEXT: .\\run-windows.ps1")
