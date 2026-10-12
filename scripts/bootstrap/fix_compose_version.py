import pathlib, subprocess

ROOT = pathlib.Path.cwd()
dc = ROOT / "docker-compose.yml"
txt = dc.read_text(encoding="utf-8")
if txt.startswith('version: "3.9"'):
    txt = txt.replace('version: "3.9"\n\n', '', 1)
    dc.write_text(txt, encoding="utf-8", newline="\n")
    print("  [OK] removed obsolete version tag")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","chore: remove obsolete compose version tag"])
print((r.stdout.strip() or r.stderr.strip())[:300])
