import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

# Fix _load_runtime in chat_any.py to discover any *Runtime class
p = BE / "scripts" / "chat_any.py"
src = p.read_text(encoding="utf-8")

old = '''    def _load_runtime(provider: str):
        module = importlib.import_module(f"app.interception.{provider}")
        for name in (provider.capitalize() + "Runtime",
                     provider.title() + "Runtime",
                     "Runtime"):
            cls = getattr(module, name, None)
            if cls is not None:
                return cls
        raise RuntimeError(f"no runtime class found in app.interception.{provider}")'''

new = '''    def _load_runtime(provider: str):
        module = importlib.import_module(f"app.interception.{provider}")
        # First try well-known names (case-insensitive)
        wanted = {provider.lower() + "runtime", "runtime"}
        for name, obj in vars(module).items():
            if name.lower() in wanted and isinstance(obj, type):
                return obj
        # Fall back: any class whose name ends with "Runtime" and is a type
        for name, obj in vars(module).items():
            if isinstance(obj, type) and name.endswith("Runtime") and obj.__module__ == module.__name__:
                return obj
        raise RuntimeError(f"no runtime class found in app.interception.{provider}")'''

if old in src:
    src = src.replace(old, new, 1)
    p.write_text(src, encoding="utf-8", newline="\n")
    print("  [OK] _load_runtime: case-insensitive + suffix discovery")
else:
    print("  [!] pattern not matched")

# syntax
r = subprocess.run([PY, "-c",
    f"import ast, pathlib; ast.parse(pathlib.Path(r'{p}').read_text(encoding='utf-8'))"],
    capture_output=True, text=True)
if r.returncode != 0:
    print("[FAIL] syntax:", r.stderr); sys.exit(1)
print("  [OK] syntax valid")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(cli): robust runtime class discovery in chat_any"])
print(r.stdout.strip() or r.stderr.strip())
