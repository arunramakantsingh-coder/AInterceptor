import subprocess, pathlib, sys

ROOT = pathlib.Path.cwd()

def run(args):
    print(f"$ {' '.join(args)}")
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, shell=True)
    print(r.stdout.strip() or r.stderr.strip())
    print()
    return r.returncode

print("==> Restoring corrupted files to last commit")
run(["git", "checkout", "--",
     "backend/app/interception/deepseek.py",
     "backend/app/interception/nonclaude_runtime.py"])

print("==> Status after restore")
run(["git", "status", "--short"])

print("==> Syntax check")
rc = run(["python", "-c",
          "import ast, pathlib; ast.parse(pathlib.Path('backend/app/interception/deepseek.py').read_text(encoding='utf-8')); print('deepseek.py OK')"])
rc2 = run(["python", "-c",
           "import ast, pathlib; ast.parse(pathlib.Path('backend/app/interception/nonclaude_runtime.py').read_text(encoding='utf-8')); print('nonclaude_runtime.py OK')"])

if rc != 0 or rc2 != 0:
    print("STILL BROKEN — do not proceed")
    sys.exit(1)

print("==> CLI import sanity")
run(["python", "-c", "from cli.shell import AIRouterShell; AIRouterShell(); print('CLI OK')"])

print("==> Test suite")
rc = run(["python", "-m", "pytest", "-q", "tests/test_nonclaude_parsers.py",
          "-o", "asyncio_mode=auto"])
print("RESULT:", "PASS" if rc == 0 else "FAIL")
