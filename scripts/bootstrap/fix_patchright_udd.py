import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BS = ROOT / "backend" / "app" / "runtime" / "browser_supervisor.py"
src = BS.read_text(encoding="utf-8")

# Drop --user-data-dir from args (Patchright handles it via parameter)
old = '''    return [
        f"--user-data-dir={profile_dir}",
        f"--remote-debugging-port={CDP_PORT}",'''
new = '''    return [
        f"--remote-debugging-port={CDP_PORT}",'''

if old in src:
    src = src.replace(old, new, 1)
    print("  [OK] removed --user-data-dir from args")

BS.write_text(src, encoding="utf-8", newline="\n")

import ast
try: ast.parse(BS.read_text(encoding="utf-8"))
except SyntaxError as e:
    print("[FAIL]", e); sys.exit(1)
print("  [OK] syntax valid")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(supervisor): Patchright forbids --user-data-dir in args; use parameter instead"])
print((r.stdout.strip() or r.stderr.strip())[:200])
