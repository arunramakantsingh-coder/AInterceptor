import pathlib, subprocess, sys, textwrap, re

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists():
    PY = sys.executable

nrt = BE / "app/interception/nonclaude_runtime.py"
src = nrt.read_text(encoding="utf-8")

# Isolate the NonClaudeNetworkCapture class body
cls_start = src.index("class NonClaudeNetworkCapture")
# find next top-level class or EOF
next_cls = src.find("\nclass ", cls_start + 10)
cls_body = src[cls_start: next_cls if next_cls != -1 else len(src)]

has_def = "async def __aenter__" in cls_body

if has_def:
    print("  [OK] __aenter__ already defined in NonClaudeNetworkCapture")
else:
    # Insert the two methods right before 'async def events(' inside the class
    anchor = "    async def events("
    if anchor not in src:
        print("  [FAIL] cannot find 'async def events(' anchor")
        sys.exit(1)

    methods = textwrap.dedent('''
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

    ''').lstrip("\n")

    src = src.replace(anchor, methods + anchor, 1)
    nrt.write_text(src, encoding="utf-8", newline="\n")
    print("  [OK] __aenter__ / __aexit__ inserted")

# Sanity: compile the file
r = subprocess.run([PY, "-c",
                    f"import ast, pathlib; ast.parse(pathlib.Path(r'{nrt}').read_text(encoding='utf-8'))"],
                   capture_output=True, text=True)
if r.returncode != 0:
    print("  [FAIL] syntax error after patch:")
    print(r.stderr)
    sys.exit(1)
print("  [OK] syntax valid")

# Run tests to confirm nothing broke
def run(args, cwd=ROOT):
    print(f"\n$ {' '.join(args)}  (cwd={cwd})")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if r.stdout: print(r.stdout)
    if r.stderr.strip(): print("STDERR:", r.stderr)
    return r.returncode

rc1 = run([PY, "-m", "pytest", "-q", "tests/test_nonclaude_parsers.py",
           "-o", "asyncio_mode=auto"], cwd=ROOT)
rc2 = run([PY, "-m", "pytest", "-q", "tests/",
           "-o", "asyncio_mode=auto"], cwd=BE)

if rc1 != 0 or rc2 != 0:
    print("\nRESULT: FAIL — tests broken, nothing committed.")
    sys.exit(1)

# Commit
def git(args):
    return subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)

git(["add", "-A"])
msg = "fix(deepseek): actually add __aenter__/__aexit__ to NonClaudeNetworkCapture"
r = git(["commit", "-m", msg])
print(r.stdout.strip() or r.stderr.strip())

sha = git(["rev-parse", "HEAD"]).stdout.strip()
print("=" * 60)
print("RESULT: PASS")
print("COMMIT:", sha)
print("NEXT:")
print(f"  cd backend")
print(f"  {PY} -u -m scripts.repro_deepseek_capture \"hi how are you\"")
print("=" * 60)
