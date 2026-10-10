import pathlib, subprocess, sys, ast

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend" / "app"

# ═══════════════════════════════════════════════════════════════
# 1. Write new path_b.py — 90-line adapter
# ═══════════════════════════════════════════════════════════════
NEW_PATH_B = '''"""Path B — browser-based transport, delegated to provider runtimes.

This module does NOT implement CDP capture itself. It delegates to the
provider runtime classes (ChatGPTRuntime, ClaudeRuntime, GeminiRuntime,
DeepSeekRuntime, etc.) defined in app/interception/<provider>.py.

Those classes use the proven CDP pattern:
    Network.enable(maxTotalBufferSize=50MB)
    + Network.streamResourceContent
    + Network.dataReceived

That is the same pattern that already drives the working CLI. This
adapter simply calls it from the daemon's dispatcher.

Interface is unchanged from the caller's view:

    async def stream_b(provider, page, prompt) -> AsyncIterator[str]

`page` is accepted for signature compatibility with dispatcher.py and
is not used — the runtime attaches to Chrome itself via cdp_url.
"""
from __future__ import annotations
import importlib
import time
from typing import Any, AsyncIterator


CDP_URL = "http://127.0.0.1:9222"


class PathBError(Exception):
    """Raised when path B cannot complete."""


def _find_runtime_class(provider: str):
    """Return the *Runtime class defined in the provider's module."""
    try:
        mod = importlib.import_module(f"app.interception.{provider}")
    except Exception as e:
        raise PathBError(f"{provider}: cannot import module: {e}")

    candidates = []
    for name, obj in vars(mod).items():
        if not isinstance(obj, type):
            continue
        if obj.__module__ != mod.__name__:
            continue
        if name.endswith("Runtime"):
            candidates.append((name, obj))

    if not candidates:
        raise PathBError(f"{provider}: no *Runtime class found in app.interception.{provider}")

    # Prefer the most specific name (ChatGPTRuntime over Runtime)
    candidates.sort(key=lambda x: len(x[0]), reverse=True)
    return candidates[0][1]


async def stream_b(provider: str, page: Any, prompt: str) -> AsyncIterator[str]:
    """Submit prompt via the provider's runtime; yield text deltas."""
    runtime_cls = _find_runtime_class(provider)

    # Try to attach to the daemon-owned Chrome; fall back if the class
    # constructor does not accept cdp_url.
    try:
        rt = runtime_cls(cdp_url=CDP_URL)
    except TypeError:
        try:
            rt = runtime_cls()
        except Exception as e:
            raise PathBError(f"{provider}: cannot instantiate {runtime_cls.__name__}: {e}")

    await rt.start()
    try:
        from app.interception.contracts import ProviderExecutionRequest
        request = ProviderExecutionRequest(
            provider=provider,
            request_id=f"daemon-{int(time.time() * 1000)}",
            messages=[{"role": "user", "content": prompt}],
        )
        async for event in rt.execute(request):
            delta = getattr(event, "delta", None)
            if delta:
                yield delta
    finally:
        try:
            await rt.close()
        except Exception:
            pass
'''

(BE / "runtime" / "path_b.py").write_text(NEW_PATH_B, encoding="utf-8", newline="\n")
print("  [OK] path_b.py replaced with 90-line adapter")

# ═══════════════════════════════════════════════════════════════
# 2. Remove JS init-script injection from browser_supervisor.py
# ═══════════════════════════════════════════════════════════════
BS = BE / "runtime" / "browser_supervisor.py"
bs = BS.read_text(encoding="utf-8")

old_open_tab = '''        page = await self.state.context.new_page()
        # install the network-tap wrapper BEFORE navigation so it runs
        # before any site JS captures a reference to fetch/XHR/EventSource
        try:
            from app.runtime.path_b import _WRAPPER_JS
            await page.add_init_script(_WRAPPER_JS)
            self.log(f"init script installed for {provider}")
        except Exception as e:
            self.log(f"init script failed for {provider}: {e}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)'''

new_open_tab = '''        page = await self.state.context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)'''

if old_open_tab in bs:
    bs = bs.replace(old_open_tab, new_open_tab, 1)
    BS.write_text(bs, encoding="utf-8", newline="\n")
    print("  [OK] browser_supervisor.py: init-script injection removed")
else:
    print("  [!] _open_tab pattern not matched — inspecting")
    # try a smaller remove
    old2 = '''        try:
            from app.runtime.path_b import _WRAPPER_JS
            await page.add_init_script(_WRAPPER_JS)
            self.log(f"init script installed for {provider}")
        except Exception as e:
            self.log(f"init script failed for {provider}: {e}")
'''
    if old2 in bs:
        bs = bs.replace(old2, "", 1)
        BS.write_text(bs, encoding="utf-8", newline="\n")
        print("  [OK] browser_supervisor.py: init-script block removed (short form)")

# ═══════════════════════════════════════════════════════════════
# 3. Delete obsolete test
# ═══════════════════════════════════════════════════════════════
old_test = ROOT / "tests" / "test_path_b_parser_adapters.py"
if old_test.exists():
    old_test.unlink()
    print("  [OK] deleted tests/test_path_b_parser_adapters.py")

# ═══════════════════════════════════════════════════════════════
# 4. Syntax check
# ═══════════════════════════════════════════════════════════════
for f in ["backend/app/runtime/path_b.py",
          "backend/app/runtime/browser_supervisor.py"]:
    try:
        ast.parse((ROOT / f).read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {f}: {e}"); sys.exit(1)
print("  [OK] syntax valid")

# ═══════════════════════════════════════════════════════════════
# 5. Import test — confirm the adapter can find runtime classes
# ═══════════════════════════════════════════════════════════════
PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable

probe = (
    "import sys, pathlib\n"
    "sys.path.insert(0, r'" + str(BE) + "')\n"
    "from app.runtime.path_b import _find_runtime_class\n"
    "for p in ['chatgpt','claude','gemini','deepseek']:\n"
    "    try:\n"
    "        cls = _find_runtime_class(p)\n"
    "        print(f'{p}: {cls.__name__}')\n"
    "    except Exception as e:\n"
    "        print(f'{p}: MISSING ({e})')\n"
)
r = subprocess.run([str(PY), "-c", probe],
                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
print()
print("==> Runtime class discovery")
print(r.stdout)
if r.stderr.strip():
    print("STDERR:", r.stderr[-400:])

# ═══════════════════════════════════════════════════════════════
# 6. Run remaining tests
# ═══════════════════════════════════════════════════════════════
print("==> running tests")
r = subprocess.run([str(PY), "-m", "pytest", "-q", "tests/",
                    "-o", "asyncio_mode=auto",
                    "--ignore=tests/test_auth.py"],
                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
# print tail only
lines = (r.stdout or "").splitlines()
for ln in lines[-15:]:
    print("   ", ln)
if r.returncode != 0:
    print("[FAIL] tests failed — see above")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# 7. Commit
# ═══════════════════════════════════════════════════════════════
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(path_b): replace rewrite with adapter to proven runtime classes"])
print((r.stdout.strip() or r.stderr.strip())[:250])

print()
print("=" * 66)
print("SWAP COMPLETE")
print()
print("NEXT:")
print("  1. In the daemon window: Ctrl+C")
print("  2. .\\run-windows.ps1")
print("     (tabs will open — NO 'init script installed' lines this time)")
print()
print("  3. In a new window:")
print('     $envFile = Get-Content .\\.env.test')
print('     $APIKEY = ($envFile | Where-Object { $_ -like "API_KEY=*" }) -replace "^API_KEY=", ""')
print("     $json = '{\"model\":\"chatgpt\",\"messages\":[{\"role\":\"user\",\"content\":\"say hi in one word\"}],\"stream\":true}'")
print('     Set-Content .\\body.json $json -Encoding ascii -NoNewline')
print("     curl.exe -s -N -X POST http://localhost:8000/v1/chat/completions `")
print('         -H "Authorization: Bearer $APIKEY" `')
print('         -H "Content-Type: application/json" `')
print('         --data-binary "@body.json"')
print()
print("  4. Repeat for claude, gemini, deepseek.")
print("=" * 66)
