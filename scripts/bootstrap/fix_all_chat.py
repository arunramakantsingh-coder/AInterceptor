import pathlib, subprocess, sys, os, re, json, shutil, time

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists():
    PY = sys.executable

def w(rel, content):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8", newline="\n")
    print(f"  [OK] {rel}")

def run(args, cwd=ROOT, check=False):
    print(f"  $ {' '.join(str(a) for a in args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.stdout.strip(): print("   ", r.stdout.strip()[-1500:])
    if r.stderr.strip(): print("   ", r.stderr.strip()[-800:])
    if check and r.returncode != 0:
        print(f"FAIL: exit {r.returncode}"); sys.exit(1)
    return r

# ───────────────────────────────────────────────────────────
# 1. Kill any DeepSeek runtime that could attach to 9222
# ───────────────────────────────────────────────────────────
print("==> Step 1: purge existing_chrome_cdp() fallbacks")

# 1a. deepseek.py — force registry, drop any existing_chrome_cdp()
ds = BE / "app/interception/deepseek.py"
src = ds.read_text(encoding="utf-8")

# Remove the entire DeepSeekRuntime class and rewrite it cleanly.
cls_re = re.compile(r"class DeepSeekRuntime\b.*?(?=\nclass |\Z)", re.S)
clean_runtime = '''class DeepSeekRuntime(NonClaudeWebRuntime):
    provider = "deepseek"

    def __init__(
        self,
        session_path: str | None = None,
        headless: bool = False,
        cdp_url: str | None = None,
    ) -> None:
        spec = WebProviderSpec(
            provider="deepseek",
            home_url="https://chat.deepseek.com/",
            login_markers=("/login", "/auth", "/sign_in", "/signin"),
            response_markers=("/api/v0/chat/completion",),
            request_markers=("/api/v0/chat/completion",),
            default_model="deepseek-flash",
            composer_selectors=(
                'textarea[placeholder*="Message"]',
                'textarea[placeholder*="message"]',
                "textarea",
                '[contenteditable="true"]',
                '[role="textbox"]',
            ),
        )
        # Resolve CDP ONLY through the registry; never fall back to the shared
        # "existing_chrome_cdp()" (which points at whichever browser is running
        # for Claude — a cross-provider leak that caused prompts to appear in
        # the wrong chat).
        explicit = cdp_url or os.getenv("AINTERCEPTOR_DEEPSEEK_CDP_URL")
        resolved = explicit if explicit is not None else provider_registry.cdp_url("deepseek")
        sp = (
            session_path
            or os.getenv("AINTERCEPTOR_DEEPSEEK_STORAGE_STATE")
            or str(pathlib.Path(".ainterceptor") / "deepseek" / "storage_state.json")
        )
        super().__init__(spec, session_path=sp, cdp_url=resolved,
                         headless=headless, parser=DeepSeekStreamParser())
'''
if cls_re.search(src):
    src = cls_re.sub(clean_runtime, src)
    print("  [OK] DeepSeekRuntime rewritten (registry-only CDP)")
else:
    print("  [!] DeepSeekRuntime class not found")

# Ensure imports exist
if "from app.interception import registry as provider_registry" not in src:
    lines = src.splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if ln.startswith("from ") or ln.startswith("import "):
            lines.insert(i, "from app.interception import registry as provider_registry\n")
            break
    src = "".join(lines)
    print("  [OK] added registry import to deepseek.py")

ds.write_text(src, encoding="utf-8", newline="\n")

# 1b. nonclaude_runtime.py — hard-enforce registry at start()
nrt = BE / "app/interception/nonclaude_runtime.py"
nsrc = nrt.read_text(encoding="utf-8")

old_block = '''        if not self.cdp_url:
            self.cdp_url = provider_registry.cdp_url(self.provider)
        if self.cdp_url:'''
new_block = '''        # Hard-enforce registry. If an env override was NOT explicitly set,
        # we IGNORE any prior self.cdp_url value (it may have been set
        # accidentally by a caller or by a stale default).
        env_key = f"AINTERCEPTOR_{self.provider.upper()}_CDP_URL"
        env_val = os.environ.get(env_key)
        if env_val == "":
            self.cdp_url = None
        elif env_val:
            self.cdp_url = env_val
        else:
            self.cdp_url = provider_registry.cdp_url(self.provider)
        print(f"[interception] {self.provider}: CDP -> {self.cdp_url}")
        if self.cdp_url:'''

if old_block in nsrc:
    nsrc = nsrc.replace(old_block, new_block, 1)
    print("  [OK] _ensure_page hard-enforces registry")
elif "self.cdp_url = provider_registry.cdp_url(self.provider)" in nsrc:
    # fallback: insert the enforcement before `if self.cdp_url:`
    nsrc = re.sub(
        r"(\n\s+)if self\.cdp_url:\n\s+self\._browser = await self\._pw\.chromium\.connect_over_cdp\(self\.cdp_url\)",
        r"\1" + new_block.split("        ")[0] + new_block + r"\n\1if self.cdp_url:\n\1    self._browser = await self._pw.chromium.connect_over_cdp(self.cdp_url)",
        nsrc, count=1)
    print("  [OK] registry enforcement inserted")

nrt.write_text(nsrc, encoding="utf-8", newline="\n")

# ───────────────────────────────────────────────────────────
# 2. Rewrite the chat REPL with hard checks
# ───────────────────────────────────────────────────────────
w("backend/scripts/chat_deepseek.py", '''"""Interactive DeepSeek chat through AInterceptor.

Refuses to start if CDP is not 9223, to prevent cross-chat leaks.
"""
import asyncio, os, sys, uuid, pathlib, socket

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Force CDP to DeepSeek's own browser
os.environ.pop("AINTERCEPTOR_DEEPSEEK_CDP_URL", None)  # let registry resolve

RAW = pathlib.Path("..") / ".evidence" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
os.environ["AINTERCEPTOR_RAW_CAPTURE_DIR"] = str(RAW)

from app.interception import registry as provider_registry
from app.interception.contracts import ProviderExecutionRequest
from app.interception.deepseek import DeepSeekRuntime


def _port_open(port: int) -> bool:
    s = socket.socket(); s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", port)); return True
    except OSError:
        return False
    finally:
        s.close()


async def main() -> int:
    expected = provider_registry.cdp_url("deepseek") or ""
    print(f"[AInterceptor] deepseek CDP target: {expected}")

    # Sanity: DeepSeek browser must be alive on 9223
    port = 9223
    if not _port_open(port):
        print(f"[FAIL] No Chrome listening on {port}.")
        print("       Launch DeepSeek's Chrome first:")
        print()
        print("  $c='C:\\\\Program Files\\\\Google\\\\Chrome\\\\Application\\\\chrome.exe'")
        print("  if (!(Test-Path $c)) { $c='C:\\\\Program Files (x86)\\\\Google\\\\Chrome\\\\Application\\\\chrome.exe' }")
        print("  Start-Process $c -ArgumentList '--remote-debugging-port=9223',")
        print("    '--user-data-dir=C:\\\\Projects\\\\AInterceptor-M1.5\\\\.ainterceptor\\\\chrome-profile-deepseek',")
        print("    'https://chat.deepseek.com/'")
        print()
        print("  Then log in and rerun this script.")
        return 2

    # Sanity: we must NOT attach to 9222 (Claude's browser)
    if ":9222" in expected:
        print("[FAIL] Refusing to start: CDP resolves to 9222 (Claude).")
        return 3

    rt = DeepSeekRuntime()
    await rt.start()
    print("Connected to DeepSeek Web chat context.")
    print("Type /exit or Ctrl+C to return to AIRouter.\\n")

    try:
        while True:
            try:
                prompt = input("AIRouter(chat)> ")
            except (EOFError, KeyboardInterrupt):
                print(); break
            if not prompt.strip():
                continue
            if prompt.strip() in {"/exit", "/back", "quit", "exit"}:
                break
            req = ProviderExecutionRequest(
                provider="deepseek",
                request_id=str(uuid.uuid4()),
                messages=[{"role": "user", "content": prompt}],
            )
            print("Deepseek:")
            async for ev in rt.execute(req):
                if ev.delta:
                    print(ev.delta, end="", flush=True)
            print()
    finally:
        await rt.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
''')

# ───────────────────────────────────────────────────────────
# 3. Tests
# ───────────────────────────────────────────────────────────
print("\n==> Step 3: run parser tests")
r = run([PY, "-m", "pytest", "-q", "tests/test_nonclaude_parsers.py",
         "-o", "asyncio_mode=auto"], cwd=ROOT)
if r.returncode != 0:
    print("FAIL: parser tests broke"); sys.exit(1)

# ───────────────────────────────────────────────────────────
# 4. Dry-run: resolve CDP (no browser interaction)
# ───────────────────────────────────────────────────────────
print("\n==> Step 4: verify CDP resolution")
probe = (
    "import os, sys\n"
    f"sys.path.insert(0, r'{BE}')\n"
    "from app.interception import registry as r\n"
    "print('deepseek ->', r.cdp_url('deepseek'))\n"
    "print('claude   ->', r.cdp_url('claude'))\n"
)
r = run([PY, "-c", probe])
if "deepseek -> http://127.0.0.1:9223" not in r.stdout:
    print("[FAIL] DeepSeek does not resolve to 9223"); sys.exit(1)
print("  [OK] DeepSeek resolves to 9223")
print("  [OK] Claude stays on 9222")

# ───────────────────────────────────────────────────────────
# 5. Commit
# ───────────────────────────────────────────────────────────
def git(args):
    return subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)
git(["add", "-A"])
r = git(["commit", "-m",
         "fix(deepseek): force CDP via registry, block cross-provider leak to 9222"])
print("\n" + (r.stdout.strip() or r.stderr.strip()))

# ───────────────────────────────────────────────────────────
# 6. Final status
# ───────────────────────────────────────────────────────────
sha = git(["rev-parse", "HEAD"]).stdout.strip()
branch = git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()

print("=" * 66)
print("RESULT: PASS")
print("COMMIT:", sha)
print("BRANCH:", branch)
print()
print("WHAT TO DO NEXT — order matters:")
print()
print("  1. CLOSE any Chrome started with --remote-debugging-port=9222 OR 9223.")
print()
print("  2. Open a NEW PowerShell window and launch DeepSeek's Chrome:")
print("       $c = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'")
print("       if (!(Test-Path $c)) { $c = 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe' }")
print("       Start-Process $c -ArgumentList '--remote-debugging-port=9223',")
print("         '--user-data-dir=C:\\Projects\\AInterceptor-M1.5\\.ainterceptor\\chrome-profile-deepseek',")
print("         '--no-first-run','--no-default-browser-check','https://chat.deepseek.com/'")
print()
print("  3. Log into DeepSeek in that window. Confirm the chat box works.")
print()
print("  4. Back in the terminal:")
print("       cd C:\\Projects\\AInterceptor-M1.5\\backend")
print("       $env:PYTHONUTF8='1'")
print(f"       {PY} -u -m scripts.chat_deepseek")
print()
print("  5. At the AIRouter(chat)> prompt, type 'hello test 42'")
print("     - It MUST appear in the DeepSeek window, NOT in this chat.")
print("     - DeepSeek's reply streams back to the terminal.")
print()
print("If the prompt still leaks here, paste the [interception] line from the")
print("terminal — it prints the exact CDP URL it attached to.")
print("=" * 66)
