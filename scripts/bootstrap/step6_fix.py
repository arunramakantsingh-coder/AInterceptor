import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()

# conftest.py at repo root: adds both paths so `app.*` and `backend.app.*`
# are both importable from any test.
(ROOT / "conftest.py").write_text('''"""pytest configuration.

Adds repo root AND repo root's backend/ to sys.path so both import styles
work:
    from app.runtime import ...          (as the app does internally)
    from backend.app.runtime import ...  (as some tests do)
"""
import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
BACKEND = ROOT / "backend"

for p in (str(ROOT), str(BACKEND)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Set test-safe env vars early
os.environ.setdefault("MASTER_KEY", __import__("base64").b64encode(os.urandom(32)).decode())
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
''', encoding="utf-8", newline="\n")
print("  [OK] conftest.py at repo root")

# Fix the test to use the canonical import (app.*) matching internal code
T = ROOT / "tests" / "test_dispatcher_routing.py"
src = T.read_text(encoding="utf-8")
src = src.replace(
    "from backend.app.runtime import dispatcher, supervisor_registry",
    "from app.runtime import dispatcher, supervisor_registry",
)
src = src.replace(
    "from backend.app.runtime.circuit_breaker import CircuitRegistry",
    "from app.runtime.circuit_breaker import CircuitRegistry",
)
src = src.replace(
    "from backend.app.runtime.circuit_breaker import CircuitState",
    "from app.runtime.circuit_breaker import CircuitState",
)
T.write_text(src, encoding="utf-8", newline="\n")
print("  [OK] test_dispatcher_routing.py updated")

# Also fix any other tests still using backend.app
for t in (ROOT / "tests").glob("test_*.py"):
    txt = t.read_text(encoding="utf-8")
    new = txt.replace("from backend.app.runtime", "from app.runtime")
    new = new.replace("from backend.app.", "from app.")
    if new != txt:
        t.write_text(new, encoding="utf-8", newline="\n")
        print(f"  [OK] {t.name} updated")

# syntax
import ast
for f in ["conftest.py", "tests/test_dispatcher_routing.py"]:
    try: ast.parse((ROOT / f).read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {f}: {e}"); sys.exit(1)
print("  [OK] syntax valid")

PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable

print("\n==> re-running all runtime tests")
r = subprocess.run([str(PY), "-m", "pytest", "-q",
                    "tests/", "-o", "asyncio_mode=auto",
                    "--ignore=tests/test_auth.py",   # needs argon2 in venv
                    ],
                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
print(r.stdout[-2500:] if r.stdout else "")
if r.stderr.strip(): print("STDERR:", r.stderr[-400:])

if r.returncode != 0:
    print("[FAIL] tests did not pass"); sys.exit(1)

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(tests): conftest adds repo + backend to sys.path; unify imports (Step 6 fix)"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("=" * 60)
print("STEP 6 COMPLETE — dispatcher tests passing with shared conftest")
print("=" * 60)
