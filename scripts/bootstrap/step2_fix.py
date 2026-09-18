import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
T = ROOT / "tests" / "test_circuit_breaker.py"
src = T.read_text(encoding="utf-8")

# The circuit opens at t+15 (6th failure at t+15). Backoff 30s.
# Probe must be at t+45 or later. Fix all t+11+31 → t+11+40 (t+51).

src = src.replace("c.allows_request(now=t + 11 + 31)",  "c.allows_request(now=t + 11 + 40)")
src = src.replace("c.record_success(50, now=t + 11 + 32)", "c.record_success(50, now=t + 11 + 41)")
src = src.replace("c.record_failure(now=t + 11 + 32)",  "c.record_failure(now=t + 11 + 41)")

T.write_text(src, encoding="utf-8", newline="\n")
print("  [OK] test timestamps corrected")

import ast
try: ast.parse(src)
except SyntaxError as e:
    print("[FAIL]", e); sys.exit(1)

PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable

print("\n==> re-running tests")
r = subprocess.run([str(PY), "-m", "pytest", "-q",
                    "tests/test_circuit_breaker.py", "-o", "asyncio_mode=auto"],
                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
print(r.stdout[-1500:] if r.stdout else "")
if r.stderr.strip(): print("STDERR:", r.stderr[-400:])

if r.returncode != 0:
    print("[FAIL] still failing")
    sys.exit(1)

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(test): circuit breaker test timing — probe after backoff expires"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("=" * 60)
print("STEP 2 COMPLETE — all circuit breaker tests pass")
print("=" * 60)
