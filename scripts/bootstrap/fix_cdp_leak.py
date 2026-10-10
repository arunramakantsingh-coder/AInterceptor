import pathlib, subprocess, sys, os

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists():
    PY = sys.executable

# ── 1. Fix DeepSeekRuntime constructor: no existing_chrome_cdp() fallback ──
ds = BE / "app/interception/deepseek.py"
src = ds.read_text(encoding="utf-8")

# Show current constructor
import re
m = re.search(r"class DeepSeekRuntime.*?(?=\nclass |\Z)", src, re.S)
if m:
    print("==> Current DeepSeekRuntime body:")
    print(m.group(0)[:1500])
    print("----")

# Replace existing_chrome_cdp() with registry resolution
old_init_patterns = [
    # variant A
    'cdp_url=cdp_url or os.getenv("AINTERCEPTOR_DEEPSEEK_CDP_URL") or existing_chrome_cdp()',
    # variant B with different spacing
    'cdp_url=cdp_url or os.getenv("AINTERCEPTOR_DEEPSEEK_CDP_URL")\n                or existing_chrome_cdp()',
]

new_init = 'cdp_url=cdp_url or os.getenv("AINTERCEPTOR_DEEPSEEK_CDP_URL") or provider_registry.cdp_url("deepseek")'

patched = False
for old in old_init_patterns:
    if old in src:
        src = src.replace(old, new_init, 1)
        patched = True
        print(f"  [OK] replaced constructor fallback")
        break

if not patched:
    # fallback: brute-force replace any existing_chrome_cdp() in DeepSeekRuntime
    # with the registry call
    if "existing_chrome_cdp()" in src:
        src = src.replace("existing_chrome_cdp()",
                          'provider_registry.cdp_url("deepseek")')
        patched = True
        print("  [OK] brute-force replaced existing_chrome_cdp()")

# Ensure registry import exists
if "from app.interception import registry as provider_registry" not in src:
    if "from app.interception.registry import" in src:
        pass  # some other import style
    else:
        # add after first import
        lines = src.splitlines(keepends=True)
        for i, ln in enumerate(lines):
            if ln.startswith("from ") or ln.startswith("import "):
                lines.insert(i, "from app.interception import registry as provider_registry\n")
                break
        src = "".join(lines)
        print("  [OK] added registry import")

ds.write_text(src, encoding="utf-8", newline="\n")

# ── 2. Harden _ensure_page: always prefer registry unless env override ──
nrt = BE / "app/interception/nonclaude_runtime.py"
nsrc = nrt.read_text(encoding="utf-8")

old_ensure = '''        if not self.cdp_url:
            self.cdp_url = provider_registry.cdp_url(self.provider)'''

new_ensure = '''        # Always resolve CDP via registry unless an explicit env override exists.
        # This prevents accidental attachment to another provider's browser.
        env_key = f"AINTERCEPTOR_{self.provider.upper()}_CDP_URL"
        env_val = os.environ.get(env_key)
        if env_val == "":
            self.cdp_url = None
        elif env_val:
            self.cdp_url = env_val
        else:
            self.cdp_url = provider_registry.cdp_url(self.provider)
        print(f"[interception] {self.provider}: CDP -> {self.cdp_url}")'''

if old_ensure in nsrc:
    nsrc = nsrc.replace(old_ensure, new_ensure, 1)
    print("  [OK] _ensure_page: always resolve via registry")
else:
    # insert before `if self.cdp_url:`
    anchor = "        if self.cdp_url:\n            self._browser = await self._pw.chromium.connect_over_cdp(self.cdp_url)"
    if anchor in nsrc:
        nsrc = nsrc.replace(anchor, new_ensure + "\n" + anchor, 1)
        print("  [OK] inserted CDP resolution before connect")

nrt.write_text(nsrc, encoding="utf-8", newline="\n")

# ── 3. Print confirmation and test ──
print("\n==> Verifying constructor in deepseek.py")
new_src = ds.read_text(encoding="utf-8")
for ln in new_src.splitlines():
    if "cdp_url=" in ln and "AINTERCEPTOR_DEEPSEEK" in ln:
        print(f"  {ln.strip()}")
    if "existing_chrome_cdp" in ln:
        print(f"  [!] WARNING: still contains existing_chrome_cdp: {ln.strip()}")

# Tests
def run(args, cwd=ROOT):
    print(f"\n$ {' '.join(args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if r.stdout: print(r.stdout)
    if r.stderr.strip(): print("STDERR:", r.stderr)
    return r.returncode

rc = run([PY, "-m", "pytest", "-q", "tests/test_nonclaude_parsers.py",
          "-o", "asyncio_mode=auto"], cwd=ROOT)
if rc != 0:
    print("RESULT: FAIL — tests broken, not committing"); sys.exit(1)

# ── 4. Live repro with a UNIQUE prompt we can trace ──
env = os.environ.copy()
env["PYTHONUTF8"] = "1"; env["PYTHONIOENCODING"] = "utf-8"
print("\n==> Live repro with unique prompt 'ping-42-deepseek'")
r = subprocess.run(
    [PY, "-X", "utf8", "-u", "-m", "scripts.repro_deepseek_capture", "ping-42-deepseek"],
    cwd=BE, capture_output=True, text=True, encoding="utf-8", env=env,
)
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr)

# ── 5. Commit ──
def git(args):
    return subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)
git(["add", "-A"])
r = git(["commit", "-m",
         "fix(deepseek): resolve CDP via registry, never fall back to existing_chrome_cdp"])
print("\n" + (r.stdout.strip() or r.stderr.strip()))

print("=" * 60)
print("RESULT: REVIEW output above")
print("Key check: 'ping-42-deepseek' should appear ONLY in DeepSeek, not in Claude")
print("=" * 60)
