import subprocess, pathlib, sys, re, datetime
ROOT = pathlib.Path(__file__).resolve().parent
MILESTONE = "M0"

def run(args, check=True):
    print(f"  $ {' '.join(args)}")
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if r.stdout.strip(): print("   ", r.stdout.strip())
    if r.stderr.strip(): print("   ", r.stderr.strip())
    if check and r.returncode != 0:
        print(f"FAIL: exit {r.returncode}"); sys.exit(1)
    return r

print("==> Validation")
r = subprocess.run(["python","scripts/validate_phase.py","--milestone",MILESTONE],
                   cwd=ROOT, capture_output=True, text=True)
print(r.stdout)
if "RESULT: PASS" not in r.stdout:
    print("BLOCKED: validation"); sys.exit(1)

print("==> Secret scan")
run(["git","add","-N","."], check=False)
diff = subprocess.run(["git","diff","--cached","-U0"],
                      cwd=ROOT, capture_output=True, text=True).stdout
for p in [r"sk-[A-Za-z0-9]{20,}", r"Bearer\s+[A-Za-z0-9._\-]{20,}",
          r"-----BEGIN [A-Z ]+PRIVATE KEY-----", r"SECURE_1PSID"]:
    if re.search(p, diff):
        print(f"BLOCKED: secret match {p}"); sys.exit(1)

print("==> Staging")
for p in ["PROJECT","TEST",".ai","docs","scripts","backend","dashboard",
          "README.md","AGENTS.md","BLUEPRINT.md","KICKOFF_PROMPT.txt",
          "PROJECT_GOVERNANCE_STANDARD_v1.1.md",".gitignore",
          "bootstrap.py","git_init.py","patch_datetime.py","first_commit.py"]:
    if (ROOT / p).exists():
        run(["git","add","--",p], check=False)

stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
log = f".evidence/M0_{stamp}.log"
pathlib.Path(ROOT / log).write_text(r.stdout or "PASS", encoding="utf-8")

print("==> Commit")
msg = (f"feat({MILESTONE}): milestone checkpoint\n\n"
       f"Milestone: {MILESTONE}\nValidation: PASS\nEvidence: {log}")
run(["git","commit","-m",msg])

print("==> Push")
run(["git","push","-u","origin","main"])

print("==> Verify remote")
sha = subprocess.run(["git","rev-parse","HEAD"],
                     cwd=ROOT, capture_output=True, text=True).stdout.strip()
ls = subprocess.run(["git","ls-remote","origin","refs/heads/main"],
                    cwd=ROOT, capture_output=True, text=True).stdout
if sha not in ls:
    print("BLOCKED: remote verify"); sys.exit(1)

print("="*44); print(f"MILESTONE: {MILESTONE}")
print("RESULT: PASS"); print(f"COMMIT: {sha}"); print("BRANCH: main")
print("="*44)
