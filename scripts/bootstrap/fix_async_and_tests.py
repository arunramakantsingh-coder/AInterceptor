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
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, shell=True)
    print(r.stdout)
    if r.stderr.strip():
        print("STDERR:", r.stderr)
    return r.returncode

# ---------- 1. Add missing async context manager to NonClaudeNetworkCapture ----------
nrt = BE / "app/interception/nonclaude_runtime.py"
src = nrt.read_text(encoding="utf-8")

if "__aenter__" not in src.split("class NonClaudeNetworkCapture")[1][:4000]:
    # Insert __aenter__/__aexit__ right before `async def events(`
    aenter_block = textwrap.dedent('''
        async def __aenter__(self) -> "NonClaudeNetworkCapture":
            self._cdp = await self.page.context.new_cdp_session(self.page)
            try:
                await self._cdp.send("Network.enable", {
                    "maxTotalBufferSize": 50 * 1024 * 1024,
                    "maxResourceBufferSize": 10 * 1024 * 1024,
                })
            except Exception:
                pass
            try:
                await self._cdp.send("Network.setBypassServiceWorker", {"bypass": True})
            except Exception:
                pass
            self._cdp.on("Network.requestWillBeSent", self._on_request)
            self._cdp.on("Network.responseReceived", self._on_response)
            self._cdp.on("Network.dataReceived", self._on_data)
            self._cdp.on("Network.loadingFinished", self._on_finished)
            self._cdp.on("Network.loadingFailed", self._on_failed)
            return self

        async def __aexit__(self, *exc: Any) -> None:
            if self._cdp is not None:
                try:
                    await self._cdp.send("Network.disable")
                except Exception:
                    pass
                try:
                    await self._cdp.detach()
                except Exception:
                    pass
                self._cdp = None

    ''').rstrip() + "\n\n"
    anchor = "    async def events("
    if anchor in src:
        src = src.replace(anchor, aenter_block + anchor, 1)
        nrt.write_text(src, encoding="utf-8", newline="\n")
        print("  [OK] nonclaude_runtime: added __aenter__/__aexit__")
    else:
        print("  [!] could not find 'async def events(' anchor")
else:
    print("  [OK] __aenter__ already present")

# ---------- 2. Fix pytest.ini to live where pytest is invoked ----------
# Ensure backend/pytest.ini has asyncio_mode = auto AND testpaths includes repo-root tests
w("backend/pytest.ini", "[pytest]\nasyncio_mode = auto\n")

# ---------- 3. Fix pyproject if it lacks asyncio config ----------
pp = ROOT / "pyproject.toml"
if pp.exists():
    text = pp.read_text(encoding="utf-8")
    if "asyncio_mode" not in text:
        print("  [info] pyproject.toml exists, leaving as-is (backend/pytest.ini covers it)")

# ---------- 4. Run tests with the CORRECT interpreter ----------
# The .venv at repo root has a python. Use it explicitly. Do NOT rely on PATH.
ROOT_PY = ROOT / ".venv" / "Scripts" / "python.exe"
if not ROOT_PY.exists():
    # try backend/.venv
    ROOT_PY = BE / ".venv" / "Scripts" / "python.exe"
if not ROOT_PY.exists():
    print("  [!] no project venv found; falling back to 'python' from PATH")
    ROOT_PY = "python"

print(f"  Using interpreter: {ROOT_PY}")

# Run parser tests from REPO ROOT (where tests/ lives), pointing pytest at both test dirs
rc1 = run([str(ROOT_PY), "-m", "pytest", "-q",
           "tests/test_nonclaude_parsers.py",
           "tests/test_deepseek_golden.py",
           "-o", "asyncio_mode=auto"], cwd=ROOT)

# Golden test also exists under backend/tests? run if present
rc2 = 0
be_tests = BE / "tests"
if (be_tests / "test_deepseek_golden.py").exists() or (be_tests / "test_fake_provider.py").exists():
    rc2 = run([str(ROOT_PY), "-m", "pytest", "-q", "tests/", "-o", "asyncio_mode=auto"], cwd=BE)

if rc1 != 0 or rc2 != 0:
    print("\n" + "=" * 60)
    print("RESULT: FAIL — tests did not pass. Nothing committed.")
    print("Paste the failure above.")
    print("=" * 60)
    sys.exit(1)

# ---------- 5. Commit ----------
def git(args):
    r = subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)
    return r

git(["add", "-A"])
msg = textwrap.dedent("""\
    fix(deepseek): async context manager + correct test invocation

    - Add __aenter__/__aexit__ to NonClaudeNetworkCapture
    - Fix pytest invocation to use repo-root venv and repo-root tests/
    - Provider registry wired into nonclaude_runtime (CDP per provider)
    - DeepSeek parser: per-path buffers, lossless fragment join
    - Golden fixture (synthetic) + no-word-loss regression test
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
print("     Start-Process 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' `")
print("       -ArgumentList '--remote-debugging-port=9223',")
print("       '--user-data-dir=C:\\Projects\\AInterceptor-M1.5\\.ainterceptor\\chrome-profile-deepseek',")
print("       'https://chat.deepseek.com/'")
print("  2. Log in.")
print("  3. cd C:\\Projects\\AInterceptor-M1.5\\backend")
print("  4. C:\\Projects\\AInterceptor-M1.5\\.venv\\Scripts\\python.exe -u -m scripts.repro_deepseek_capture \"hi how are you\"")
print("  5. Paste output + .evidence/raw/deepseek_*.raw")
print("=" * 60)
