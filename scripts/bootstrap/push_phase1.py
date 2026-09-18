import pathlib, subprocess

ROOT = pathlib.Path.cwd()

# Untrack body.json + extend gitignore
gi = ROOT / ".gitignore"
g = gi.read_text(encoding="utf-8")
for line in ["body.json", "test_input.txt"]:
    if line not in g:
        g = g.rstrip() + "\n" + line + "\n"
gi.write_text(g, encoding="utf-8", newline="\n")

subprocess.run(["git","rm","--cached","--ignore-unmatch","body.json"],
               cwd=ROOT, capture_output=True)

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)

git(["add","-A"])
r = git(["commit","-m","chore: untrack body.json"])
print((r.stdout.strip() or r.stderr.strip())[:300])

# Push branch + tag
branch = git(["rev-parse","--abbrev-ref","HEAD"]).stdout.strip()
print(f"\n==> Pushing {branch} and v0.2.0-phase1-api")
r = git(["push","origin",branch])
print((r.stdout.strip() or r.stderr.strip())[:500])
r = git(["push","origin","v0.2.0-phase1-api"])
print((r.stdout.strip() or r.stderr.strip())[:500])

sha = git(["rev-parse","HEAD"]).stdout.strip()
ls = git(["ls-remote","origin",f"refs/heads/{branch}"]).stdout
tag_ls = git(["ls-remote","origin","refs/tags/v0.2.0-phase1-api"]).stdout

print()
print("=" * 60)
print("RESULT:", "PASS" if sha in ls and tag_ls.strip() else "REVIEW")
print("  HEAD:", sha[:10])
print("  Remote branch:", branch, "✓" if sha in ls else "✗")
print("  Remote tag:", "✓" if tag_ls.strip() else "✗")
print("=" * 60)
