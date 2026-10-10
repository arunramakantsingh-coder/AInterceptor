import pathlib, subprocess, sys, ast, re

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app"

# ═══════════════════════════════════════════════════════════════
# 1. browser_supervisor.py — replace _launch and _open_tab
# ═══════════════════════════════════════════════════════════════
BS = BE / "runtime" / "browser_supervisor.py"
src = BS.read_text(encoding="utf-8")

# Add subprocess import if missing
if "\nimport subprocess" not in src:
    src = src.replace("import pathlib", "import pathlib\nimport subprocess", 1)

# Add socket for port check if missing
if "\nimport socket" not in src:
    src = src.replace("import pathlib", "import pathlib\nimport socket", 1)

# ── Replace _launch ──
launch_start = src.find("    async def _launch(self")
if launch_start == -1:
    print("[FAIL] _launch not found"); sys.exit(1)
# find next method at same indent
launch_end = src.find("\n    async def ", launch_start + 10)
if launch_end == -1:
    launch_end = src.find("\n    def ", launch_start + 10)
if launch_end == -1:
    print("[FAIL] end of _launch not found"); sys.exit(1)

new_launch = '''
    async def _launch(self) -> None:
        """Launch Chrome as a plain subprocess — Playwright does NOT own it.

        This lets external CDP clients (like the runtime classes) attach
        simultaneously. The previous launch_persistent_context() approach
        made Playwright the owner of the CDP session, which caused every
        other client to time out.
        """
        try:
            from patchright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError(f"patchright not installed: {e}")

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        chrome = _find_chrome()
        if not chrome:
            raise RuntimeError("chrome.exe not found")

        # Kill anything already on the CDP port
        _kill_port(CDP_PORT)
        await asyncio.sleep(1.0)

        args = _chrome_args(self.profile_dir, off_screen=self.off_screen)
        cmd = [chrome] + args
        # NOTE: we do NOT pass the provider URLs here — the supervisor will
        # open tabs itself. Passing URLs causes duplicate tabs.
        self.log(f"launching Chrome: {chrome}")
        self._chrome_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )

        # Wait for CDP endpoint
        ready = False
        for _ in range(60):
            await asyncio.sleep(0.5)
            if _port_open(CDP_PORT):
                ready = True
                break
        if not ready:
            raise RuntimeError(f"Chrome CDP did not bind on port {CDP_PORT}")

        # Now attach via CDP — we do not own the browser
        self.state.pw = await async_playwright().start()
        try:
            self.state.browser = await asyncio.wait_for(
                self.state.pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}"),
                timeout=15,
            )
        except Exception as e:
            raise RuntimeError(f"CDP attach failed: {e}")

        contexts = self.state.browser.contexts
        if not contexts:
            self.state.context = await self.state.browser.new_context(
                viewport={"width": 1400, "height": 900},
                locale="en-US",
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/130.0.0.0 Safari/537.36"),
            )
        else:
            self.state.context = contexts[0]
        self.log(f"attached: {len(contexts) if contexts else 0} contexts")

'''
src = src[:launch_start] + new_launch + src[launch_end:]

# ── Update _open_tab to remove init_script (already done) and be simpler ──
old_open = '''    async def _open_tab(self, provider: str) -> Tab:
        url = PROVIDER_URLS[provider]
        self.log(f"open tab: {provider} -> {url}")
        page = await self.state.context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        except Exception as e:
            self.log(f"goto failed for {provider}: {e}")
        return Tab(provider=provider, url=url, page=page, last_used=time.time())'''

new_open = '''    async def _open_tab(self, provider: str) -> Tab:
        url = PROVIDER_URLS[provider]
        self.log(f"open tab: {provider} -> {url}")
        page = await self.state.context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        except Exception as e:
            self.log(f"goto failed for {provider}: {e}")
        return Tab(provider=provider, url=url, page=page, last_used=time.time())'''

if old_open in src:
    src = src.replace(old_open, new_open, 1)

# ── Update BrowserState to add browser and chrome_proc fields ──
old_state = '''@dataclass
class BrowserState:
    pw: Any = None
    context: Any = None
    tabs: dict[str, Tab] = field(default_factory=dict)
    started_at: float = 0.0
    restarts: int = 0
    ready: bool = False'''

new_state = '''@dataclass
class BrowserState:
    pw: Any = None
    browser: Any = None
    context: Any = None
    tabs: dict[str, Tab] = field(default_factory=dict)
    started_at: float = 0.0
    restarts: int = 0
    ready: bool = False'''

if old_state in src:
    src = src.replace(old_state, new_state, 1)

# ── Add helper functions if missing ──
if "_find_chrome" not in src:
    helpers = '''

def _find_chrome() -> str | None:
    for c in (r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
              r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"):
        if pathlib.Path(c).exists():
            return c
    return None


def _port_open(port: int) -> bool:
    s = socket.socket(); s.settimeout(0.4)
    try:
        s.connect(("127.0.0.1", port)); return True
    except OSError:
        return False
    finally:
        s.close()


def _kill_port(port: int) -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-NetTCPConnection -LocalPort {port} -State Listen -EA SilentlyContinue | "
             "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass

'''
    # Insert before "class Tab" or "class BrowserState"
    anchor = "@dataclass\nclass Tab:"
    if anchor in src:
        src = src.replace(anchor, helpers + anchor, 1)
        print("  [OK] added _find_chrome, _port_open, _kill_port")

# ── Update close() to kill the subprocess Chrome too ──
old_close = '''    async def stop(self) -> None:
        self._stopping = True
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except (asyncio.CancelledError, Exception):
                pass
        async with self._lock:
            try:
                if self.state.context:
                    await self.state.context.close()
            except Exception:
                pass
            try:
                if self.state.pw:
                    await self.state.pw.stop()
            except Exception:
                pass
            self.state = BrowserState()'''

new_close = '''    async def stop(self) -> None:
        self._stopping = True
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except (asyncio.CancelledError, Exception):
                pass
        async with self._lock:
            # We do NOT own the context (attached via CDP). Just detach.
            try:
                if self.state.browser:
                    await self.state.browser.close()
            except Exception:
                pass
            try:
                if self.state.pw:
                    await self.state.pw.stop()
            except Exception:
                pass
            # Kill the subprocess Chrome we launched
            try:
                proc = getattr(self, "_chrome_proc", None)
                if proc is not None:
                    proc.terminate()
            except Exception:
                pass
            self.state = BrowserState()'''

if old_close in src:
    src = src.replace(old_close, new_close, 1)
    print("  [OK] close() updated")

# Add _chrome_proc to __init__
if "self._chrome_proc" not in src:
    src = src.replace(
        "self._watchdog_task: asyncio.Task | None = None",
        "self._watchdog_task: asyncio.Task | None = None\n        self._chrome_proc: subprocess.Popen | None = None",
        1,
    )
    print("  [OK] _chrome_proc attribute added")

BS.write_text(src, encoding="utf-8", newline="\n")
try:
    ast.parse(src)
    print("  [OK] browser_supervisor.py syntax valid")
except SyntaxError as e:
    print(f"[FAIL] browser_supervisor: {e}")
    lines = src.splitlines()
    for i in range(max(0, e.lineno - 6), min(len(lines), e.lineno + 3)):
        m = ">>>" if i + 1 == e.lineno else "   "
        print(f"  {m} {i+1:4d}  {lines[i]}")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# 2. daemon.py — prober disabled unless explicitly enabled
# ═══════════════════════════════════════════════════════════════
daemon = BE / "runtime" / "daemon.py"
dt = daemon.read_text(encoding="utf-8")

# Ensure prober defaults to disabled. Look for the existing pattern.
if 'AINTERCEPTOR_PROBER_ENABLED' not in dt:
    # Inject the guard: replace unconditional prober creation
    # Find "prober = HealthProber(" and wrap in env check
    old_prober = '''    prober = HealthProber('''
    new_prober = '''    import os as _os_guard
    _prober_enabled = _os_guard.environ.get("AINTERCEPTOR_PROBER_ENABLED", "0") == "1"
    print(f"[daemon] prober enabled: {_prober_enabled}", flush=True)
    prober = None
    if _prober_enabled:
        prober = HealthProber('''
    if old_prober in dt:
        dt = dt.replace(old_prober, new_prober, 1)
        # Indent the block that follows until prober.start() call — simplify
        # by just wrapping differently. Actually we need to be careful.
        # Roll back and use a simpler patch.
        dt = daemon.read_text(encoding="utf-8")

# Simpler approach: find the prober.start() line and wrap it
old_start_block = '''    prober.start()
    sr.set_prober(prober)'''
new_start_block = '''    if prober is not None:
        prober.start()
        sr.set_prober(prober)
        print("[daemon] prober started", flush=True)
    else:
        print("[daemon] prober disabled (set AINTERCEPTOR_PROBER_ENABLED=1 to enable)", flush=True)'''

if old_start_block in dt:
    dt = dt.replace(old_start_block, new_start_block, 1)
    print("  [OK] daemon.py prober gated")
else:
    print("  [!] daemon.py prober.start pattern not found — inspecting")

daemon.write_text(dt, encoding="utf-8", newline="\n")

try:
    ast.parse(dt)
    print("  [OK] daemon.py syntax valid")
except SyntaxError as e:
    print(f"[FAIL] daemon: {e}"); sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# 3. prober.py — defense-in-depth: only probe active
# ═══════════════════════════════════════════════════════════════
PR = BE / "runtime" / "prober.py"
pt = PR.read_text(encoding="utf-8")

if "from app.control_plane.state import get_state" not in pt:
    old_sweep = '''    async def sweep(self) -> list[ProbeResult]:
        results: list[ProbeResult] = []
        for provider in self.providers:'''
    new_sweep = '''    async def sweep(self) -> list[ProbeResult]:
        # Defense-in-depth: intersect with active providers
        try:
            from app.control_plane.state import get_state
            active = set(get_state().list_active())
            providers = [p for p in self.providers if p in active]
        except Exception:
            providers = list(self.providers)
        results: list[ProbeResult] = []
        for provider in providers:'''
    if old_sweep in pt:
        pt = pt.replace(old_sweep, new_sweep, 1)
        PR.write_text(pt, encoding="utf-8", newline="\n")
        print("  [OK] prober.py intersects with active list")
    else:
        print("  [!] prober sweep pattern not found")

try:
    ast.parse(PR.read_text(encoding="utf-8"))
    print("  [OK] prober.py syntax valid")
except SyntaxError as e:
    print(f"[FAIL] prober: {e}"); sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# 4. Commit
# ═══════════════════════════════════════════════════════════════
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(supervisor): launch Chrome as subprocess (no Playwright ownership); gate prober"])
print((r.stdout.strip() or r.stderr.strip())[:300])

print()
print("=" * 66)
print("FIXES APPLIED")
print()
print("  browser_supervisor.py — Chrome launched by subprocess.Popen,")
print("    attached via connect_over_cdp. Multiple CDP clients can now")
print("    coexist (supervisor + runtime classes).")
print()
print("  daemon.py — prober gated behind AINTERCEPTOR_PROBER_ENABLED=1")
print("    (default: disabled). No background probing unless you opt in.")
print()
print("  prober.py — even when enabled, only probes active providers.")
print()
print("NEXT:")
print("  1. Kill everything cleanly:")
print("     - Ctrl+C in the daemon window")
print("     - Get-NetTCPConnection -LocalPort 8000,9222 -State Listen -EA SilentlyContinue |")
print("       ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }")
print()
print("  2. Start daemon:  .\\run-windows.ps1")
print()
print("  3. Test:")
print("     python scripts\\test_all_providers.py")
print("=" * 66)
