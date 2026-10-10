import pathlib, subprocess, sys, os, textwrap

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists():
    PY = sys.executable

# ── 1. Move test to repo-root tests/ where pytest actually looks
src_be = BE / "tests" / "test_deepseek_think_response.py"
dst    = ROOT / "tests" / "test_deepseek_think_response.py"
dst.parent.mkdir(parents=True, exist_ok=True)
if src_be.exists():
    dst.write_text(src_be.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    src_be.unlink()
    print(f"  [OK] moved test to {dst.relative_to(ROOT)}")
elif dst.exists():
    print(f"  [OK] test already at {dst.relative_to(ROOT)}")
else:
    print("  [!] test file missing — writing fresh")
    dst.write_text(textwrap.dedent('''
        from app.interception.deepseek import parse_deepseek_web


        def test_response_fragment_keeps_snapshot_prefix():
            body = "\\n".join([
                'data: {"v":{"response":{"fragments":[{"id":1,"type":"RESPONSE","content":"Hello"}]}}}',
                'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"!"}',
                'data: {"v":" How"}',
                'data: {"v":" can"}',
                'data: {"v":" I"}',
                'data: {"v":" help"}',
                'data: {"v":"?"}',
            ])
            assert parse_deepseek_web(body) == "Hello! How can I help?"


        def test_think_then_response_isolated():
            body = "\\n".join([
                'data: {"v":{"response":{"fragments":[{"id":2,"type":"THINK","content":"We"}]}}}',
                'data: {"p":"response/fragments/-1/content","o":"APPEND","v":" need"}',
                'data: {"p":"response/fragments","o":"APPEND","v":[{"id":3,"type":"RESPONSE","content":"zz"}]}',
                'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"-m"}',
                'data: {"v":"arker"}',
                'data: {"v":"-"}',
                'data: {"v":"7"}',
                'data: {"v":" acknowledged"}',
                'data: {"v":"."}',
            ])
            assert parse_deepseek_web(body) == "zz-marker-7 acknowledged."
    ''').lstrip(), encoding="utf-8", newline="\n")

# ── 2. Tests
def run(args, cwd=ROOT, check=False):
    print(f"\n$ {' '.join(str(a) for a in args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if r.stdout: print(r.stdout)
    if r.stderr.strip(): print("STDERR:", r.stderr)
    if check and r.returncode != 0:
        print(f"FAIL exit {r.returncode}"); sys.exit(1)
    return r

r = run([PY, "-m", "pytest", "-q",
         "tests/test_nonclaude_parsers.py",
         "tests/test_deepseek_think_response.py",
         "-o", "asyncio_mode=auto"], cwd=ROOT)
if r.returncode != 0:
    print("FAIL: tests broke — nothing committed"); sys.exit(1)

# ── 3. Commit
def git(args):
    return subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)
git(["add", "-A"])
r = git(["commit", "-m",
         "fix(deepseek): APPEND uses fragment content; golden tests for THINK/RESPONSE"])
print(r.stdout.strip() or r.stderr.strip())

# ── 4. Live DeepSeek REPL test with auto-fed prompt
print("\n==> Live DeepSeek test")
env = os.environ.copy()
env["PYTHONUTF8"] = "1"
r = subprocess.run(
    [PY, "-u", "-m", "scripts.chat_deepseek"],
    cwd=BE, input="hello there 42\n/exit\n", capture_output=True, text=True,
    encoding="utf-8", env=env,
)
print("--- stdout ---")
print(r.stdout)
if r.stderr.strip():
    print("--- stderr ---"); print(r.stderr)

print("=" * 60)
print("RESULT: PASS")
print("Check the 'Deepseek:' line above — it must begin with a real DeepSeek reply.")
print("=" * 60)
