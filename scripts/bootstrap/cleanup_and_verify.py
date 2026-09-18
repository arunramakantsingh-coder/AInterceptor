import pathlib, subprocess

ROOT = pathlib.Path.cwd()

gi = ROOT / ".gitignore"
g = gi.read_text(encoding="utf-8")
for line in [".env.test", "*.egg-info/", "agent/airouter_agent.egg-info/"]:
    if line not in g:
        g = g.rstrip() + "\n" + line + "\n"
gi.write_text(g, encoding="utf-8", newline="\n")
print("  [OK] .gitignore updated")

for path in [".env.test", "agent/airouter_agent.egg-info"]:
    subprocess.run(["git","rm","-r","--cached","--ignore-unmatch", path],
                   cwd=ROOT, capture_output=True)
    print(f"  [OK] untracked {path}")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","chore: untrack .env.test and egg-info (key leak prevention)"])
print((r.stdout.strip() or r.stderr.strip())[:300])

# Verify session uploaded
import json, urllib.request
token = None
for line in (ROOT / ".env.test").read_text().splitlines():
    if line.startswith("TOKEN="):
        token = line[6:]
        break
req = urllib.request.Request("http://localhost:8000/api/sessions",
                              headers={"Authorization": f"Bearer {token}"})
with urllib.request.urlopen(req, timeout=5) as resp:
    sessions = json.loads(resp.read())
print(f"\n==> Sessions on server: {len(sessions)}")
for s in sessions:
    print(f"   {s['provider']:<10} {s['alias']:<10} {s['status']}")
