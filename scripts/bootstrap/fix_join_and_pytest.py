import pathlib, subprocess, sys, textwrap

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"   # known from last run
if not pathlib.Path(PY).exists():
    PY = sys.executable

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

# ---------- 1. Install pytest-asyncio ----------
print("==> Installing pytest-asyncio")
run([PY, "-m", "pip", "install", "-q", "pytest-asyncio"])

# ---------- 2. Fix _join_response_parts: paragraph separator only for DISTINCT fragments ----------
ds_path = BE / "app/interception/deepseek.py"
ds = ds_path.read_text(encoding="utf-8")

old = '''    @classmethod
    def _join_response_parts(cls, parts: list[str]) -> str:
        """Join distinct DeepSeek response fragments without losing any text.

        Rules:
        - Consecutive fragments are joined literally (no dropped middle).
        - A fragment that is a strict cumulative extension of the accumulated
          text replaces it (this is DeepSeek replaying the growing body).
        - Any other fragment is appended as a new paragraph.
        Never discards text.
        """
        assembled = ""
        for raw_part in parts:
            part = raw_part
            if not part:
                continue
            if not assembled:
                assembled = part
                continue
            # Cumulative replay: new fragment strictly extends what we have
            if part.startswith(assembled):
                assembled = part
                continue
            # Exact duplicate: skip
            if part == assembled:
                continue
            # Literal append (fragments are sequential pieces of the SAME run)
            # Only treat as separate paragraph if there's clear paragraph signal.
            # DeepSeek uses explicit paragraph markers in `content`; here we
            # join literally and let the runtime compute deltas.
            assembled = assembled + part
        return assembled'''

new = '''    @classmethod
    def _join_response_parts(cls, parts: list[str]) -> str:
        """Join fragments from a snapshot's `fragments` array.

        Semantics:
        - Each entry in the array is a DISTINCT fragment of the final answer.
        - A later entry that cumulatively extends an earlier one is the SAME
          fragment, replayed with more text — replace, don't duplicate.
        - Distinct fragments are separated by a paragraph break (\\n\\n).
        Never discards text.
        """
        assembled = ""
        for part in parts:
            if part is None:
                continue
            if not assembled:
                assembled = part
                continue
            if part == assembled:
                continue
            if part.startswith(assembled):
                assembled = part
                continue
            if assembled.startswith(part):
                continue
            assembled = f"{assembled}\\n\\n{part}"
        return assembled'''

if old in ds:
    ds = ds.replace(old, new, 1)
    ds_path.write_text(ds, encoding="utf-8", newline="\n")
    print("  [OK] _join_response_parts restored paragraph separator")
else:
    print("  [!] pattern not found — checking for already-fixed variant")
    if 'assembled = f"{assembled}\\n\\n{part}"' in ds:
        print("  [OK] already restored")

# ---------- 3. pytest config so asyncio_mode is honored ----------
w("pytest.ini", "[pytest]\nasyncio_mode = auto\ntestpaths = tests backend/tests\n")

# ---------- 4. Run all tests ----------
print("\n==> Root parser tests")
rc1 = run([PY, "-m", "pytest", "-q", "tests/test_nonclaude_parsers.py",
           "-o", "asyncio_mode=auto"], cwd=ROOT)

print("\n==> Backend tests")
rc2 = run([PY, "-m", "pytest", "-q", "tests/",
           "-o", "asyncio_mode=auto"], cwd=BE)

if rc1 != 0 or rc2 != 0:
    print("\n" + "=" * 60)
    print("RESULT: FAIL — tests still failing. Nothing committed.")
    print("Paste the failure above.")
    print("=" * 60)
    sys.exit(1)

# ---------- 5. Commit ----------
def git(args):
    return subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)

git(["add", "-A"])
msg = textwrap.dedent("""\
    fix(deepseek): restore paragraph separator + pytest asyncio mode

    - _join_response_parts: distinct snapshot fragments joined by \\n\\n,
      cumulative replays replace (no duplication, no word loss)
    - add pytest.ini at repo root so asyncio_mode=auto is honored
    - install pytest-asyncio in project venv
    - provider registry + per-path buffers retained
""")
r = git(["commit", "-m", msg])
print(r.stdout.strip() or r.stderr.strip())

sha = git(["rev-parse", "HEAD"]).stdout.strip()
branch = git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()

print("=" * 60)
print("RESULT: PASS")
print("COMMIT:", sha)
print("BRANCH:", branch)
print("=" * 60)
print()
print("NEXT — real DeepSeek capture:")
print("  1. Launch DeepSeek Chrome on 9223:")
print("     $c='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'")
print("     if (!(Test-Path $c)) { $c='C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe' }")
print("     Start-Process $c -ArgumentList '--remote-debugging-port=9223',")
print("       '--user-data-dir=C:\\Projects\\AInterceptor-M1.5\\.ainterceptor\\chrome-profile-deepseek',")
print("       'https://chat.deepseek.com/'")
print("  2. Log in to DeepSeek in that window.")
print("  3. cd backend")
print(f"  4. {PY} -u -m scripts.repro_deepseek_capture \"hi how are you\"")
print("  5. Paste AIRouter output + newest .evidence/raw/deepseek_*.raw")
print("=" * 60)
