import pathlib, subprocess

ROOT = pathlib.Path.cwd()
req = ROOT / "backend" / "requirements.txt"
txt = req.read_text(encoding="utf-8")
if "email-validator" not in txt:
    txt = txt.rstrip() + "\nemail-validator==2.2.0\n"
    req.write_text(txt, encoding="utf-8", newline="\n")
    print("  [OK] added email-validator")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(phase-1): add email-validator for pydantic EmailStr"])
print((r.stdout.strip() or r.stderr.strip())[:300])
