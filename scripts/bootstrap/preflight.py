import pathlib, subprocess

ROOT = pathlib.Path.cwd()

# 1. backend/__init__.py — makes backend a proper package
(BE := ROOT / "backend" / "__init__.py").write_text(
    '"""AInterceptor backend package."""\n', encoding="utf-8")
print("  [OK] backend/__init__.py")

# 2. Dockerfile — use --app-dir so `app.main` resolves cleanly
df = ROOT / "docker" / "Dockerfile"
txt = df.read_text(encoding="utf-8")
old = 'CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]'
new = 'CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]'
if old in txt:
    txt = txt.replace(old, new)
    df.write_text(txt, encoding="utf-8", newline="\n")
    print("  [OK] Dockerfile CMD updated")

# 3. docker-compose.yml — match
dc = ROOT / "docker-compose.yml"
txt = dc.read_text(encoding="utf-8")
old = 'uvicorn backend.app.main:app --host 0.0.0.0 --port 8000'
new = 'uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000'
if old in txt:
    txt = txt.replace(old, new)
    dc.write_text(txt, encoding="utf-8", newline="\n")
    print("  [OK] docker-compose updated")

# 4. alembic env.py — both /app and /app/backend on sys.path
env_py = ROOT / "alembic" / "env.py"
txt = env_py.read_text(encoding="utf-8")
old = 'sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))'
new = ('_here = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))\n'
       'sys.path.insert(0, _here)\n'
       'sys.path.insert(0, os.path.join(_here, "backend"))')
if old in txt:
    txt = txt.replace(old, new)
    env_py.write_text(txt, encoding="utf-8", newline="\n")
    print("  [OK] alembic env.py path updated")

# 5. .dockerignore — exclude .env from the image
di = ROOT / ".dockerignore"
txt = di.read_text(encoding="utf-8")
if "\n.env\n" not in "\n" + txt:
    txt = txt.replace(".git\n", ".git\n.env\n", 1)
    di.write_text(txt, encoding="utf-8", newline="\n")
    print("  [OK] .dockerignore excludes .env")

# 6. config.py — read env vars only (no .env file inside container)
cfg = ROOT / "backend" / "app" / "config.py"
txt = cfg.read_text(encoding="utf-8")
old = 'model_config = SettingsConfigDict(env_file=".env", extra="ignore")'
new = 'model_config = SettingsConfigDict(env_file=None, extra="ignore")'
if old in txt:
    txt = txt.replace(old, new)
    cfg.write_text(txt, encoding="utf-8", newline="\n")
    print("  [OK] config.py reads env vars only")

# 7. .gitignore — untrack .env if accidentally added
gi = ROOT / ".gitignore"
txt = gi.read_text(encoding="utf-8")
if ".env" not in txt.split("\n"):
    txt = txt.rstrip() + "\n.env\n"
    gi.write_text(txt, encoding="utf-8", newline="\n")
    print("  [OK] .gitignore has .env")

subprocess.run(["git","rm","--cached","--ignore-unmatch",".env"],
               cwd=ROOT, capture_output=True)

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(phase-1): docker import paths, .env safety, package init"])
print((r.stdout.strip() or r.stderr.strip())[:300])

print()
print("=" * 60)
print("PRE-FLIGHT DONE. Now build the stack:")
print()
print("  docker compose up -d --build")
print()
print("First build takes 3-6 min (installs python deps + playwright).")
print("Paste the build output next.")
print("=" * 60)
