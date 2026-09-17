import pathlib, subprocess, sys, shutil

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists():
    PY = sys.executable

nrt = BE / "app/interception/nonclaude_runtime.py"
lines = nrt.read_text(encoding="utf-8").splitlines()

print("==> Raw lines 110..150 (indent visible with ·)")
for i in range(110, min(151, len(lines))):
    line = lines[i]
    visible = line.replace(" ", "·")
    print(f"  {i+1:4d}  {visible}")

# Verify: for each method name in the class, check the exact indentation
print("\n==> Indentation audit")
targets = ["async def __aenter__", "async def events", "async def __aexit__"]
for i, line in enumerate(lines, 1):
    for t in targets:
        if line.lstrip().startswith(t):
            indent = len(line) - len(line.lstrip())
            marker = "OK  " if indent == 4 else "BAD "
            print(f"  {marker} line {i}: indent={indent}  {t}")

# Clear __pycache__ in both repos to kill stale bytecode
for p in [ROOT / "backend", ROOT / "backend" / "app", ROOT / "backend" / "app" / "interception"]:
    for pyc in p.rglob("__pycache__"):
        shutil.rmtree(pyc, ignore_errors=True)
        print(f"  [OK] removed {pyc}")

# Verify syntax
r = subprocess.run([PY, "-c",
    f"import ast, pathlib; ast.parse(pathlib.Path(r'{nrt}').read_text(encoding='utf-8'))"],
    capture_output=True, text=True)
if r.returncode != 0:
    print("  [FAIL] syntax:"); print(r.stderr); sys.exit(1)
print("  [OK] syntax valid")

# Import the class fresh in a subprocess and confirm it implements the protocol
probe = r'''
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(r"C:\Projects\AInterceptor-M1.5\backend")))
from app.interception.nonclaude_runtime import NonClaudeNetworkCapture
ok_aenter = hasattr(NonClaudeNetworkCapture, "__aenter__")
ok_aexit  = hasattr(NonClaudeNetworkCapture, "__aexit__")
print(f"__aenter__: {ok_aenter}  __aexit__: {ok_aexit}")
if not (ok_aenter and ok_aexit):
    import inspect
    src = inspect.getsource(NonClaudeNetworkCapture)
    print(src)
    sys.exit(1)
'''
r = subprocess.run([PY, "-c", probe], capture_output=True, text=True)
print("\n==> Runtime protocol check")
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr)
if r.returncode != 0:
    print("  [FAIL] class still lacks the async context manager protocol")
    sys.exit(1)

print("  [OK] NonClaudeNetworkCapture has __aenter__ and __aexit__")

# Now run the repro
print("\n==> Running repro")
r = subprocess.run(
    [PY, "-u", "-m", "scripts.repro_deepseek_capture", "hi how are you"],
    cwd=BE, capture_output=True, text=True)
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr)

print("=" * 60)
print("RESULT:", "PASS" if r.returncode == 0 else "FAIL")
print("=" * 60)
