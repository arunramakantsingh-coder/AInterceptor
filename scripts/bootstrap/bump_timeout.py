import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
p = BE / "scripts" / "chat_any.py"
src = p.read_text(encoding="utf-8")

src = src.replace(
    '''    def daemon_alive():
        try:
            http_get("/", timeout=1.0)
            return True
        except Exception:
            return False''',
    '''    def daemon_alive():
        try:
            http_get("/", timeout=4.0)
            return True
        except Exception:
            return False''',
    1,
)
p.write_text(src, encoding="utf-8", newline="\n")
print("  [OK] daemon_alive timeout: 1s -> 4s")

import ast
try: ast.parse(src)
except SyntaxError as e:
    print("[FAIL]", e); sys.exit(1)
print("  [OK] syntax valid")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(cli): daemon_alive timeout 1s -> 4s"])
print(r.stdout.strip() or r.stderr.strip())

print()
print("NOW TRY:")
print("  deepseek login")
print("  deepseek")
