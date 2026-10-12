import pathlib, subprocess, sys, zipfile

ROOT = pathlib.Path.cwd()

def run(args):
    print(f"$ {' '.join(args)}")
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, shell=True)
    print(r.stdout.strip() or r.stderr.strip())
    print()
    return r.returncode

print("==> Committing clean state")
run(["git", "add", "scripts/bootstrap/"])
run(["git", "commit", "-m",
     "chore(bootstrap): add diagnostic scripts; restore clean source state"])

print("==> Verifying claude files unchanged")
CLAUDE = [
    "backend/app/interception/claude.py",
    "backend/app/interception/claude_transport.py",
    "backend/app/interception/runtime.py",
    "backend/app/interception/web_runtime.py",
]
import hashlib
for f in CLAUDE:
    p = ROOT / f
    h = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    print(f"  {h}  {f}")

print("\n==> Building _bundle.zip")

BUNDLE_FILES = [
    # backend interceptor
    "backend/app/interception/deepseek.py",
    "backend/app/interception/nonclaude_runtime.py",
    "backend/app/interception/registry.py",
    "backend/app/interception/contracts.py",
    "backend/app/interception/runtime.py",
    "backend/app/interception/web_runtime.py",
    "backend/app/interception/__init__.py",
    # backend providers
    "backend/app/providers/base.py",
    "backend/app/providers/__init__.py",
    # backend api / orchestrator / gateway stubs
    "backend/app/api/main.py",
    # CLI frontend
    "cli/__init__.py",
    "cli/main.py",
    "cli/shell.py",
    "cli/nos.py",
    "cli/renderer.py",
    "cli/config_store.py",
    "cli/chat.py",
    "cli/registry.py",
    # project governance
    "PROJECT_GOVERNANCE_STANDARD_v1.1.md",
    "PROJECT/ROADMAP.md",
    "PROJECT/ARCHITECTURE.md",
    "AGENTS.md",
    ".ai/CURRENT_TASK.md",
    ".ai/SESSION.md",
    "pyproject.toml",
    # tests
    "tests/test_nonclaude_parsers.py",
]

bundle = ROOT / "_bundle.zip"
with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
    for rel in BUNDLE_FILES:
        p = ROOT / rel
        if p.exists():
            z.write(p, rel)
            print(f"  + {rel}")
        else:
            print(f"  (missing) {rel}")

size = bundle.stat().st_size
print(f"\nBundle written: {bundle}  ({size} bytes, {len(BUNDLE_FILES)} files)")

print("\n" + "="*66)
print("NEXT STEP — attach this file to your next chat message:")
print(f"  {bundle}")
print("="*66)
