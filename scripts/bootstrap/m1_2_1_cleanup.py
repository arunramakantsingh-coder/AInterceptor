import pathlib, subprocess, sys, shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent  # scripts/bootstrap -> root
# Fallback: if __file__ layout differs, force to project root
if not (ROOT / ".git").exists():
    ROOT = pathlib.Path(r"C:\Projects\AInterceptor")

def run(args, cwd=ROOT, check=True):
    print(f"  $ {' '.join(args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, shell=True)
    if r.stdout.strip(): print("   ", r.stdout.strip()[-1500:])
    if r.stderr.strip(): print("   ", r.stderr.strip()[-500:])
    if check and r.returncode != 0:
        print(f"FAIL: {r.returncode}"); sys.exit(1)
    return r

# 1. .gitignore
gi = ROOT / ".gitignore"
g = gi.read_text(encoding="utf-8")
if ".evidence/*.json" not in g:
    g = g.replace(".evidence/*.log", ".evidence/*.log\n.evidence/*.json")
    gi.write_text(g, encoding="utf-8")
    print("[OK] .gitignore: .evidence/*.json")

# 2. Untrack evidence
subprocess.run(["git","reset","HEAD",".evidence"], cwd=ROOT, capture_output=True)
print("[OK] unstaged .evidence/")

# 3. Move bootstrap scripts
boot = ROOT / "scripts" / "bootstrap"
boot.mkdir(parents=True, exist_ok=True)
for name in ["bootstrap.py","git_init.py","patch_datetime.py","first_commit.py",
             "patch_m0_1.py","phase_1_1.py","phase_1_2.py"]:
    src = ROOT / name
    if src.exists():
        shutil.move(str(src), str(boot / name))
        print(f"[OK] moved {name}")

# 4. Bootstrap README
(boot / "README.md").write_text("""# scripts/bootstrap/
Historical bootstrap scripts. Never delete; history is evidence.
- bootstrap.py, git_init.py, patch_datetime.py, first_commit.py,
  patch_m0_1.py, phase_1_1.py, phase_1_2.py
""", encoding="utf-8")
print("[OK] scripts/bootstrap/README.md")

# 5. Commit
subprocess.run(["git","add","--",".gitignore","scripts/bootstrap"], cwd=ROOT, capture_output=True)
subprocess.run(["git","rm","--cached","-r",".evidence"], cwd=ROOT, capture_output=True)

msg = "chore(M1.2.1): tidy evidence + relocate bootstrap scripts"
r = subprocess.run(["git","commit","-m",msg], cwd=ROOT, capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip())

subprocess.run(["git","push","origin","main"], cwd=ROOT, capture_output=True)

sha = subprocess.run(["git","rev-parse","HEAD"], cwd=ROOT,
                     capture_output=True, text=True).stdout.strip()
ls = subprocess.run(["git","ls-remote","origin","refs/heads/main"],
                    cwd=ROOT, capture_output=True, text=True).stdout

print("="*44)
print("MILESTONE: M1.2.1")
print("RESULT:", "PASS" if sha in ls else "BLOCKED")
print("COMMIT:", sha)
print("BRANCH: main")
print("="*44)

print("==> M1.2 remote content check")
tree = subprocess.run(["git","ls-tree","-r","--name-only","origin/main"],
                      cwd=ROOT, capture_output=True, text=True).stdout
for f in ["backend/app/orchestrator/__init__.py",
          "backend/app/orchestrator/README.md",
          "backend/app/gateway/__init__.py",
          "backend/app/gateway/README.md",
          "PROJECT_GOVERNANCE_STANDARD_v1.1.md"]:
    print(f"  [{'PASS' if f in tree else 'FAIL'}] {f}")
