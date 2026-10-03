import pathlib, subprocess, sys, textwrap

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists():
    PY = sys.executable

nrt = BE / "app/interception/nonclaude_runtime.py"
src = nrt.read_text(encoding="utf-8")
lines = src.splitlines()

# --- show class layout ---
print("==> Classes and methods in nonclaude_runtime.py")
for i, line in enumerate(lines, 1):
    if line.startswith("class "):
        print(f"  {i:4d}  {line}")
    elif line.startswith("    async def ") or line.startswith("    def "):
        print(f"  {i:4d}      {line.strip()}")

# Find NonClaudeNetworkCapture class block
cls_start = None
cls_end = None
for i, line in enumerate(lines):
    if line.startswith("class NonClaudeNetworkCapture"):
        cls_start = i
    elif cls_start is not None and line.startswith("class ") and i > cls_start:
        cls_end = i
        break
if cls_end is None:
    cls_end = len(lines)

print(f"\n  NonClaudeNetworkCapture: lines {cls_start+1}..{cls_end}")
has_aenter = any("async def __aenter__" in ln for ln in lines[cls_start:cls_end])
print(f"  has __aenter__: {has_aenter}")

if has_aenter:
    print("  [OK] nothing to patch")
    sys.exit(0)

# --- insert methods before the first `async def events(` inside the class ---
insert_at = None
for i in range(cls_start, cls_end):
    if lines[i].startswith("    async def events("):
        insert_at = i
        break

if insert_at is None:
    print("  [FAIL] cannot find 'async def events(' inside NonClaudeNetworkCapture")
    sys.exit(1)

methods = [
    '    async def __aenter__(self) -> "NonClaudeNetworkCapture":',
    '        self._cdp = await self.page.context.new_cdp_session(self.page)',
    '        try:',
    '            await self._cdp.send("Network.enable", {',
    '                "maxTotalBufferSize": 50 * 1024 * 1024,',
    '                "maxResourceBufferSize": 10 * 1024 * 1024,',
    '            })',
    '        except Exception:',
    '            pass',
    '        try:',
    '            await self._cdp.send("Network.setBypassServiceWorker", {"bypass": True})',
    '        except Exception:',
    '            pass',
    '        self._cdp.on("Network.requestWillBeSent", self._on_request)',
    '        self._cdp.on("Network.responseReceived", self._on_response)',
    '        self._cdp.on("Network.dataReceived", self._on_data)',
    '        self._cdp.on("Network.loadingFinished", self._on_finished)',
    '        self._cdp.on("Network.loadingFailed", self._on_failed)',
    '        return self',
    '',
    '    async def __aexit__(self, *exc: Any) -> None:',
    '        if self._cdp is not None:',
    '            try:',
    '                await self._cdp.send("Network.disable")',
    '            except Exception:',
    '                pass',
    '            try:',
    '                await self._cdp.detach()',
    '            except Exception:',
    '                pass',
    '            self._cdp = None',
    '',
]

new_lines = lines[:insert_at] + methods + lines[insert_at:]
nrt.write_text("\n".join(new_lines) + "\n", encoding="utf-8", newline="\n")
print(f"  [OK] inserted __aenter__/__aexit__ at line {insert_at+1}")

# --- syntax check ---
r = subprocess.run([PY, "-c",
    "import ast, pathlib; ast.parse(pathlib.Path(r'" + str(nrt) + "').read_text(encoding='utf-8'))"],
    capture_output=True, text=True)
if r.returncode != 0:
    print("  [FAIL] syntax error:"); print(r.stderr); sys.exit(1)
print("  [OK] syntax valid")

# --- tests ---
def run(args, cwd=ROOT):
    print(f"\n$ {' '.join(args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if r.stdout: print(r.stdout)
    if r.stderr.strip(): print("STDERR:", r.stderr)
    return r.returncode

rc1 = run([PY, "-m", "pytest", "-q", "tests/test_nonclaude_parsers.py",
           "-o", "asyncio_mode=auto"], cwd=ROOT)
rc2 = run([PY, "-m", "pytest", "-q", "tests/",
           "-o", "asyncio_mode=auto"], cwd=BE)

if rc1 != 0 or rc2 != 0:
    print("\nRESULT: FAIL — nothing committed."); sys.exit(1)

# --- commit ---
def git(args):
    return subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)

git(["add", "-A"])
r = git(["commit", "-m",
         "fix(nonclaude): add missing __aenter__/__aexit__ to NonClaudeNetworkCapture"])
print(r.stdout.strip() or r.stderr.strip())

print("=" * 60)
print("RESULT: PASS")
print("COMMIT:", git(["rev-parse", "HEAD"]).stdout.strip())
print("NEXT:")
print("  cd backend")
print(f'  {PY} -u -m scripts.repro_deepseek_capture "hi how are you"')
print("=" * 60)
