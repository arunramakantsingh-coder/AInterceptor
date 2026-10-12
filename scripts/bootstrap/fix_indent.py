import pathlib, subprocess, sys, re

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists():
    PY = sys.executable

nrt = BE / "app/interception/nonclaude_runtime.py"
text = nrt.read_text(encoding="utf-8")
lines = text.splitlines()

# ── Show lines 190..220 with visible indent ──
print("==> Lines 190..220 (· = space)")
for i in range(189, min(220, len(lines))):
    print(f"  {i+1:4d}  {lines[i].replace(' ', '·')}")

# ── Find and replace the malformed block ──
# The bad block looks like:
#      <no-indent> if self.cdp_url:
#          self._browser = ...
# We want to rebuild the `_ensure_page`'s CDP selection section as a
# canonical, well-indented block.

# Locate `_ensure_page` method
start = None
for i, ln in enumerate(lines):
    if ln.lstrip().startswith("async def _ensure_page"):
        start = i
        break
if start is None:
    print("[FAIL] _ensure_page not found"); sys.exit(1)

# Find where `_ensure_page` ends (next `    async def ` or `    def `)
end = None
for i in range(start + 1, len(lines)):
    if lines[i].startswith("    async def ") or lines[i].startswith("    def "):
        end = i
        break
if end is None:
    end = len(lines)

print(f"\n==> _ensure_page spans lines {start+1}..{end}")

# Canonical replacement for the entire method
canonical = '''    async def _ensure_page(self, interactive: bool = False) -> None:
        if async_playwright is None:
            raise WebProviderSessionError("playwright is not installed")
        if self._pw is None:
            self._pw = await async_playwright().start()

        # CDP resolution: registry-first, env override honored, never fall
        # back to a shared "existing_chrome_cdp()" that could attach us to
        # another provider's browser.
        env_key = f"AINTERCEPTOR_{self.provider.upper()}_CDP_URL"
        env_val = os.environ.get(env_key)
        if env_val == "":
            self.cdp_url = None
        elif env_val:
            self.cdp_url = env_val
        else:
            self.cdp_url = provider_registry.cdp_url(self.provider)
        print(f"[interception] {self.provider}: CDP -> {self.cdp_url}")

        if self.cdp_url:
            self._browser = await self._pw.chromium.connect_over_cdp(self.cdp_url)
            contexts = self._browser.contexts
            if not contexts:
                raise WebProviderSessionError("CDP browser has no context")
            self._context = contexts[0]
            self._owns_browser = self._owns_context = False
            host = urlparse(self.spec.home_url).netloc
            pages = [p for p in self._context.pages
                     if host == urlparse(p.url or "").netloc]
            self._page = pages[-1] if pages else await self._context.new_page()
        elif self.session_path and pathlib.Path(self.session_path).exists():
            self._browser = await self._pw.chromium.launch(headless=self.headless)
            self._context = await self._browser.new_context(storage_state=self.session_path)
            self._owns_browser = self._owns_context = True
            self._page = await self._context.new_page()
        else:
            profile = pathlib.Path(".ainterceptor") / "profiles" / self.provider
            profile.mkdir(parents=True, exist_ok=True)
            self._context = await self._pw.chromium.launch_persistent_context(
                str(profile), headless=False if interactive else self.headless)
            self._owns_context = True
            pages = list(self._context.pages)
            self._page = pages[-1] if pages else await self._context.new_page()

        if urlparse(self._page.url or "").netloc != urlparse(self.spec.home_url).netloc:
            await self._page.goto(self.spec.home_url, wait_until="domcontentloaded",
                                  timeout=30_000)
'''

new_lines = lines[:start] + canonical.splitlines() + lines[end:]
nrt.write_text("\n".join(new_lines) + "\n", encoding="utf-8", newline="\n")
print("  [OK] _ensure_page rewritten cleanly")

# ── Syntax check ──
r = subprocess.run([PY, "-c",
    f"import ast, pathlib; ast.parse(pathlib.Path(r'{nrt}').read_text(encoding='utf-8'))"],
    capture_output=True, text=True)
if r.returncode != 0:
    print("[FAIL] syntax:"); print(r.stderr); sys.exit(1)
print("  [OK] syntax valid")

# ── Import check ──
probe = (
    "import sys, pathlib\n"
    f"sys.path.insert(0, r'{BE}')\n"
    "from app.interception.deepseek import DeepSeekRuntime\n"
    "from app.interception import registry as r\n"
    "print('registry deepseek ->', r.cdp_url('deepseek'))\n"
    "print('registry claude   ->', r.cdp_url('claude'))\n"
    "print('OK')\n"
)
r = subprocess.run([PY, "-c", probe], capture_output=True, text=True)
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr)
if "OK" not in r.stdout:
    print("[FAIL] import failed"); sys.exit(1)

# ── Run parser tests ──
print("\n==> Parser tests")
r = subprocess.run([PY, "-m", "pytest", "-q", "tests/test_nonclaude_parsers.py",
                    "-o", "asyncio_mode=auto"],
                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr)
if r.returncode != 0:
    print("FAIL: tests broke"); sys.exit(1)

# ── Commit ──
def git(args):
    return subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)
git(["add", "-A"])
r = git(["commit", "-m", "fix(nonclaude): canonical _ensure_page CDP resolution"])
print(r.stdout.strip() or r.stderr.strip())

sha = git(["rev-parse", "HEAD"]).stdout.strip()
print("=" * 60)
print("RESULT: PASS")
print("COMMIT:", sha)
print()
print("NEXT — start the DeepSeek chat REPL:")
print("  cd backend")
print('  $env:PYTHONUTF8="1"')
print(f"  {PY} -u -m scripts.chat_deepseek")
print("=" * 60)
