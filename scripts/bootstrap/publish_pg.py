import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
dc = ROOT / "docker-compose.yml"
txt = dc.read_text(encoding="utf-8")

# Publish postgres 5432 to the host so native uvicorn can reach it
if '"5432:5432"' not in txt:
    # Find the db service's ports block, or add one
    if "  db:\n" in txt:
        # insert ports under db if missing
        old = '    healthcheck:\n      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-airouter}"]'
        new = '    ports:\n      - "5432:5432"\n    healthcheck:\n      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-airouter}"]'
        if old in txt:
            txt = txt.replace(old, new, 1)
            dc.write_text(txt, encoding="utf-8", newline="\n")
            print("  [OK] docker-compose.yml: postgres 5432 published")
        else:
            print("  [!] pattern not matched — inspect docker-compose.yml")
    else:
        print("  [!] no db: section found")
else:
    print("  [OK] 5432 already published")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(compose): publish postgres 5432 for native API access"])
print((r.stdout.strip() or r.stderr.strip())[:200])
