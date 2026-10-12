import pathlib, subprocess, sys, textwrap

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"

def w(rel, content):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8", newline="\n")
    print(f"  [OK] {rel}")

def run(args, cwd=ROOT):
    print(f"\n$ {' '.join(args)}  (cwd={cwd})")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, shell=False)
    if r.stdout: print(r.stdout)
    if r.stderr.strip(): print("STDERR:", r.stderr)
    return r.returncode

# ---------- 1. Rewrite golden test with proper escaping ----------
golden = textwrap.dedent("""
    import pathlib
    from app.interception.deepseek import parse_deepseek_web

    FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "deepseek_golden_synthetic.raw"


    def test_deepseek_golden_synthetic_round_trip():
        body = FIXTURE.read_text(encoding="utf-8")
        result = parse_deepseek_web(body)
        assert result == "hi how are you", f"got {result!r}"


    def test_deepseek_no_word_loss_across_fragments():
        lines = [
            'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"That"}',
            'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"\\u0027s a "}',
            'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"good thing "}',
            'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"to want."}',
        ]
        body = "\\n".join(lines)
        result = parse_deepseek_web(body)
        assert result == "That's a good thing to want.", f"got {result!r}"
""").lstrip()

w("backend/tests/test_deepseek_golden.py", golden)

# ---------- 2. Locate the *real* interpreter ----------
def find_python() -> str:
    # ask the currently running python
    r = subprocess.run([sys.executable, "-c", "import sys;print(sys.executable)"],
                       capture_output=True, text=True)
    path = r.stdout.strip()
    # If we're inside a venv, sys.executable points there.
    # Also probe common locations.
    for cand in [
        path,
        str(ROOT / ".venv" / "Scripts" / "python.exe"),
        str(BE / ".venv" / "Scripts" / "python.exe"),
    ]:
        if cand and pathlib.Path(cand).exists():
            return cand
    return sys.executable

PY = find_python()
print(f"  Using interpreter: {PY}")

# Check it has pytest
r = subprocess.run([PY, "-c", "import pytest, sys; print(pytest.__version__)"],
                   capture_output=True, text=True)
if r.returncode != 0:
    print(f"  [!] pytest not importable in {PY}")
    print("  [!] Install: pip install -r backend/requirements.txt")
    sys.exit(1)
print(f"  pytest {r.stdout.strip()}")

# ---------- 3. Run tests from the right dirs ----------
print("\n==> Running repo-root tests")
rc1 = run([PY, "-m", "pytest", "-q",
           "tests/test_nonclaude_parsers.py",
           "-o", "asyncio_mode=auto"], cwd=ROOT)

print("\n==> Running backend tests")
rc2 = run([PY, "-m", "pytest", "-q", "tests/",
           "-o", "asyncio_mode=auto"], cwd=BE)

if rc1 != 0 or rc2 != 0:
    print("\n" + "=" * 60)
    print("RESULT: FAIL — tests did not pass. Nothing committed.")
    print("Paste the failure above.")
    print("=" * 60)
    sys.exit(1)

# ---------- 4. Commit ----------
def git(args):
    return subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)

git(["add", "-A"])
msg = textwrap.dedent("""\
    fix(deepseek): correct golden test escaping + async context mgr

    - Rewrite test_deepseek_golden.py with proper quote escaping
    - Provider registry wired into nonclaude_runtime (CDP per provider)
    - DeepSeek parser: per-path buffers, lossless fragment join
    - Golden fixture + no-word-loss regression test
""")
r = git(["commit", "-m", msg])
print(r.stdout.strip() or r.stderr.strip())

sha = git(["rev-parse", "HEAD"]).stdout.strip()
branch = git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()

print("=" * 60)
print("RESULT: PASS")
print("COMMIT:", sha)
print("BRANCH:", branch)
print()
print("NEXT — real DeepSeek capture:")
print("  1. Launch DeepSeek Chrome on 9223:")
print("     $c='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'")
print("     if (!(Test-Path $c)) { $c='C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe' }")
print("     Start-Process $c -ArgumentList '--remote-debugging-port=9223',")
print("       '--user-data-dir=C:\\Projects\\AInterceptor-M1.5\\.ainterceptor\\chrome-profile-deepseek',")
print("       'https://chat.deepseek.com/'")
print("  2. Log in.")
print("  3. cd backend")
print(f"  4. {PY} -u -m scripts.repro_deepseek_capture \"hi how are you\"")
print("  5. Paste AIRouter output + newest .evidence/raw/deepseek_*.raw")
print("=" * 60)
