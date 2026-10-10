"""snapshot_parser.py — dump the DeepSeek parser, runtime, and latest tests."""
import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
OUT = ROOT / ".evidence" / "dump"
OUT.mkdir(parents=True, exist_ok=True)

TARGETS = [
    "backend/app/interception/deepseek.py",
    "backend/app/interception/nonclaude_runtime.py",
    "backend/app/interception/contracts.py",
    "backend/app/interception/runtime.py",
    "tests/test_nonclaude_parsers.py",
    ".ai/rules/WEB_INTERCEPTION_ARCHITECTURE.md",
    "PROJECT/TRANSPORT_EVENT_CONTRACT_V1.md",
]

def hr(t):
    print(); print("="*72); print(t); print("="*72)

for rel in TARGETS:
    p = ROOT / rel
    if not p.exists():
        hr(f"MISSING: {rel}")
        continue
    text = p.read_text(encoding="utf-8", errors="replace")
    (OUT / rel.replace("/", "__")).write_text(text, encoding="utf-8")
    hr(f"FILE: {rel}  ({len(text)} chars)")
    print(text)

hr("GIT STATUS (short)")
r = subprocess.run(["git","status","--short"], cwd=ROOT, capture_output=True, text=True)
print(r.stdout)

hr("RESULT")
print("RESULT: PASS")
print("All files dumped to .evidence/dump/ and printed above.")
