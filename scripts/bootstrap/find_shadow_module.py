import pathlib, subprocess, sys, shutil

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists():
    PY = sys.executable

# 1. Find every nonclaude_runtime.py on disk under the project
print("==> Every nonclaude_runtime.py on disk")
hits = list(ROOT.rglob("nonclaude_runtime.py"))
for h in hits:
    size = h.stat().st_size
    has_aenter = "__aenter__" in h.read_text(encoding="utf-8", errors="replace")
    print(f"  {size:>7} bytes  aenter={has_aenter}  {h}")

# 2. Ask Python where it imports the module from
probe = r'''
import sys
sys.path.insert(0, str(__import__("pathlib").Path(r"C:\Projects\AInterceptor-M1.5\backend")))
import app.interception.nonclaude_runtime as m
print("MODULE FILE:", m.__file__)
print("sys.path (first 8):")
for p in sys.path[:8]:
    print("   ", p)
'''
r = subprocess.run([PY, "-c", probe], capture_output=True, text=True)
print("\n==> Python's import resolution")
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr)

# 3. Locate the stale module and its file
import re
m = re.search(r"MODULE FILE:\s*(.+)", r.stdout)
if m:
    imported = pathlib.Path(m.group(1).strip())
    expected = BE / "app" / "interception" / "nonclaude_runtime.py"
    print(f"\n  expected: {expected}")
    print(f"  imported: {imported}")
    if imported.resolve() != expected.resolve():
        print("  [!!] STALE SHADOW FOUND — Python imported a different file")
        # Rename the shadow so it can never load again
        backup = imported.with_suffix(".py.disabled")
        try:
            imported.rename(backup)
            print(f"  [OK] renamed shadow -> {backup}")
        except Exception as e:
            print(f"  [!!] could not rename: {e}")
            sys.exit(1)
    else:
        print("  [OK] import points at the correct file — cache was the issue")

# 4. Purge all __pycache__ again after rename
for pyc in ROOT.rglob("__pycache__"):
    shutil.rmtree(pyc, ignore_errors=True)
print("  [OK] cleared __pycache__")

# 5. Re-probe
r = subprocess.run([PY, "-c", probe], capture_output=True, text=True)
print("\n==> Re-import after cleanup")
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr)

# 6. Protocol check
proto = r'''
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(r"C:\Projects\AInterceptor-M1.5\backend")))
from app.interception.nonclaude_runtime import NonClaudeNetworkCapture
print("aenter:", hasattr(NonClaudeNetworkCapture, "__aenter__"))
print("aexit :", hasattr(NonClaudeNetworkCapture, "__aexit__"))
'''
r = subprocess.run([PY, "-c", proto], capture_output=True, text=True)
print("\n==> Protocol check")
print(r.stdout)
if "aenter: True" not in r.stdout:
    print("  [FAIL] still no protocol. Paste the FULL output above.")
    sys.exit(1)
print("  [OK] protocol present")

# 7. Run the repro
print("\n==> Running repro")
r = subprocess.run([PY, "-u", "-m", "scripts.repro_deepseek_capture", "hi how are you"],
                   cwd=BE, capture_output=True, text=True)
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr)

print("=" * 60)
print("RESULT:", "PASS" if r.returncode == 0 else "FAIL")
print("=" * 60)
