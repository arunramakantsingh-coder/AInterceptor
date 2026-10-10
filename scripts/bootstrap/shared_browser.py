import pathlib, subprocess, sys, textwrap, os, socket, time

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
BIN  = ROOT / "bin"
STATE = ROOT / ".ainterceptor"
STATE.mkdir(exist_ok=True)
PY = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists(): PY = sys.executable

SHARED_PROFILE = STATE / "chrome-profile-shared"
SHARED_PORT = 9222
SHARED_URLS = [
    "https://chatgpt.com/",
    "https://claude.ai/",
    "https://gemini.google.com/",
    "https://chat.deepseek.com/",
]

# ─────────────────────────────────────────────────────────
# 1. Kill every Chrome bound to our ports (clean slate)
# ─────────────────────────────────────────────────────────
print("==> Stopping existing AInterceptor Chromes")
for p in [9222,9223,9224,9225]:
    subprocess.run(["powershell","-NoProfile","-Command",
        f"Get-NetTCPConnection -LocalPort {p} -State Listen -EA SilentlyContinue | "
        f"ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }}"],
        capture_output=True, shell=True)

# ─────────────────────────────────────────────────────────
# 2. Rewrite registry — one port, per-provider tab URLs
# ─────────────────────────────────────────────────────────
reg = BE / "app/interception/registry.py"
reg.write_text(textwrap.dedent('''
    """AInterceptor provider registry.

    All providers share ONE Chrome instance on CDP port 9222 (shared
    profile). Each provider owns a tab URL. The runtime selects the tab
    matching the provider's home_url.
    """
    from __future__ import annotations
    import os, pathlib
    from dataclasses import dataclass

    SHARED_PORT = 9222
    SHARED_PROFILE = pathlib.Path(".ainterceptor") / "chrome-profile-shared"


    @dataclass(frozen=True)
    class ProviderEntry:
        name: str
        home_url: str
        tab_url_prefix: str
        transport: str = "cdp"
        default_model: str = ""
        composer_selectors: tuple[str, ...] = ()
        login_markers: tuple[str, ...] = ()
        response_markers: tuple[str, ...] = ()
        request_markers: tuple[str, ...] = ()


    REGISTRY: dict[str, ProviderEntry] = {
        "chatgpt": ProviderEntry(
            name="chatgpt",
            home_url="https://chatgpt.com/",
            tab_url_prefix="chatgpt.com",
            default_model="chatgpt-web",
            composer_selectors=("#prompt-textarea", 'div[contenteditable="true"]', "textarea"),
            login_markers=("/auth/login",),
            response_markers=("/backend-api/conversation",),
            request_markers=("/backend-api/conversation",),
        ),
        "claude": ProviderEntry(
            name="claude",
            home_url="https://claude.ai/",
            tab_url_prefix="claude.ai",
            default_model="claude-web",
            composer_selectors=('div[contenteditable="true"]', "textarea"),
            login_markers=("/login", "/auth", "/signin"),
            response_markers=("/api/organizations/", "/completion"),
            request_markers=("/api/organizations/", "/completion"),
        ),
        "gemini": ProviderEntry(
            name="gemini",
            home_url="https://gemini.google.com/",
            tab_url_prefix="gemini.google.com",
            default_model="gemini-web",
            composer_selectors=('div[contenteditable="true"]', "textarea"),
            login_markers=("/accounts/", "signin"),
            response_markers=("StreamGenerate", "/assistant.lamda"),
            request_markers=("StreamGenerate",),
        ),
        "deepseek": ProviderEntry(
            name="deepseek",
            home_url="https://chat.deepseek.com/",
            tab_url_prefix="chat.deepseek.com",
            default_model="deepseek-flash",
            composer_selectors=(
                'textarea[placeholder*="Message"]',
                'textarea[placeholder*="message"]',
                "textarea",
                '[contenteditable="true"]',
                '[role="textbox"]',
            ),
            login_markers=("/login", "/auth", "/sign_in", "/signin"),
            response_markers=("/api/v0/chat/completion",),
            request_markers=("/api/v0/chat/completion",),
        ),
    }


    def get(provider: str) -> ProviderEntry:
        p = provider.lower()
        if p not in REGISTRY:
            raise KeyError(f"unknown provider: {provider}; known: {list(REGISTRY)}")
        return REGISTRY[p]


    def cdp_url(provider: str) -> str | None:
        """Return the shared CDP URL. Env override respected."""
        env = os.environ.get(f"AINTERCEPTOR_{provider.upper()}_CDP_URL")
        if env == "":
            return None
        if env:
            return env
        return f"http://127.0.0.1:{SHARED_PORT}"


    def session_path(provider: str) -> pathlib.Path:
        env = os.environ.get(f"AINTERCEPTOR_{provider.upper()}_STORAGE_STATE")
        if env:
            return pathlib.Path(env)
        return SHARED_PROFILE / "storage_state.json"


    def all_providers() -> list[str]:
        return list(REGISTRY)
'''), encoding="utf-8", newline="\n")
print("  [OK] registry.py rewritten (single shared port 9222)")

# ─────────────────────────────────────────────────────────
# 3. Patch runtime: choose the right TAB, not the right port
# ─────────────────────────────────────────────────────────
rt = BE / "app/interception/nonclaude_runtime.py"
src = rt.read_text(encoding="utf-8")

# Replace page-selection logic to pick the provider's tab by URL prefix
old_page_pick = '''            self._context = contexts[0]
            self._owns_browser = self._owns_context = False
            host = urlparse(self.spec.home_url).netloc
            pages = [p for p in self._context.pages
                     if host == urlparse(p.url or "").netloc]
            self._page = pages[-1] if pages else await self._context.new_page()'''

new_page_pick = '''            self._context = contexts[0]
            self._owns_browser = self._owns_context = False
            # Find the tab whose URL matches this provider's home host.
            # If none exists, open a new tab to the provider home.
            host = urlparse(self.spec.home_url).netloc
            matching = [p for p in self._context.pages
                        if host in (p.url or "")]
            if matching:
                self._page = matching[-1]
            else:
                self._page = await self._context.new_page()
                try:
                    await self._page.goto(self.spec.home_url,
                                          wait_until="domcontentloaded",
                                          timeout=30_000)
                except Exception:
                    pass'''

if old_page_pick in src:
    src = src.replace(old_page_pick, new_page_pick, 1)
    print("  [OK] runtime: tab selection by URL prefix")
else:
    print("  [!] page-pick block not matched")

# Remove stale-cache guard: always re-resolve CDP via registry
old_resolve = '''        if env_val == "":
            self.cdp_url = None
        elif env_val:
            self.cdp_url = env_val
        else:
            self.cdp_url = provider_registry.cdp_url(self.provider)'''
new_resolve = '''        if env_val == "":
            self.cdp_url = None
        elif env_val:
            self.cdp_url = env_val
        else:
            self.cdp_url = provider_registry.cdp_url(self.provider)'''
# no change needed but keep for clarity

rt.write_text(src, encoding="utf-8", newline="\n")

# syntax
import ast
try: ast.parse(src)
except SyntaxError as e:
    print("[FAIL] nonclaude_runtime:", e); sys.exit(1)
print("  [OK] syntax valid (runtime)")

# ─────────────────────────────────────────────────────────
# 4. Rewrite chat_any.py — no daemon, direct local attach
# ─────────────────────────────────────────────────────────
chat = textwrap.dedent('''\
    """AInterceptor chat — direct attach to shared Chrome."""
    import asyncio, importlib, os, sys, uuid, pathlib, subprocess, time, socket

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ROOT = pathlib.Path(__file__).resolve().parents[2]
    BACKEND = ROOT / "backend"
    STATE = ROOT / ".ainterceptor"
    STATE.mkdir(exist_ok=True)
    SHARED_PROFILE = STATE / "chrome-profile-shared"
    SHARED_PORT = 9222

    URLS = {
        "chatgpt":  "https://chatgpt.com/",
        "claude":   "https://claude.ai/",
        "gemini":   "https://gemini.google.com/",
        "deepseek": "https://chat.deepseek.com/",
    }

    sys.path.insert(0, str(BACKEND))
    from app.interception.contracts import ProviderExecutionRequest

    def port_open(port):
        s = socket.socket(); s.settimeout(0.4)
        try: s.connect(("127.0.0.1", port)); return True
        except OSError: return False
        finally: s.close()

    def find_chrome():
        for c in (r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                  r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"):
            if pathlib.Path(c).exists(): return c
        return None

    def launch_shared_chrome(off_screen=True):
        chrome = find_chrome()
        if not chrome:
            print("[FAIL] chrome.exe not found"); return False
        SHARED_PROFILE.mkdir(parents=True, exist_ok=True)
        pos = "-32000,-32000" if off_screen else "100,100"
        args = [chrome,
                f"--remote-debugging-port={SHARED_PORT}",
                f"--user-data-dir={SHARED_PROFILE}",
                "--no-first-run", "--no-default-browser-check",
                f"--window-position={pos}",
                "--window-size=1400,900"]
        args.extend(URLS.values())
        subprocess.Popen(args)
        for _ in range(30):
            time.sleep(0.5)
            if port_open(SHARED_PORT): return True
        return False

    def load_runtime(provider):
        module = importlib.import_module(f"app.interception.{provider}")
        target = provider.replace("-", "").lower()
        for name, obj in vars(module).items():
            if isinstance(obj, type) and obj.__module__ == module.__name__:
                if name.lower() == f"{target}runtime":
                    return obj
        for name, obj in vars(module).items():
            if isinstance(obj, type) and obj.__module__ == module.__name__ and name.endswith("Runtime"):
                return obj
        raise RuntimeError(f"no Runtime class for {provider}")

    async def do_chat(provider):
        if not port_open(SHARED_PORT):
            print(f"[..] shared Chrome not running — launching off-screen on {SHARED_PORT}")
            if not launch_shared_chrome(off_screen=True):
                print("[FAIL] could not launch shared Chrome"); return 2
        cls = load_runtime(provider)
        rt = cls()
        await rt.start()
        print(f"Connected to {provider}. /exit or Ctrl+C to leave.\\n")
        try:
            while True:
                try:
                    line = input(f"{provider}> ")
                except (EOFError, KeyboardInterrupt):
                    print(); break
                if not line.strip(): continue
                if line.strip() in {"/exit","/back","exit","quit"}: break
                req = ProviderExecutionRequest(
                    provider=provider,
                    request_id=str(uuid.uuid4()),
                    messages=[{"role":"user","content":line}],
                )
                print()
                async for ev in rt.execute(req):
                    if ev.delta:
                        print(ev.delta, end="", flush=True)
                print()
        finally:
            await rt.close()
        return 0

    def do_login(provider):
        """Bring the shared Chrome on-screen so the user can log into `provider`."""
        if not port_open(SHARED_PORT):
            print(f"[..] launching shared Chrome with all providers as tabs")
            if not launch_shared_chrome(off_screen=False):
                print("[FAIL] launch failed"); return 2
        # Move the window on-screen
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            def cb(hwnd, lp):
                n = user32.GetWindowTextLengthW(hwnd)
                if n:
                    buf = ctypes.create_unicode_buffer(n+1)
                    user32.GetWindowTextW(hwnd, buf, n+1)
                    if "Chrome" in buf.value or "chatgpt" in buf.value.lower() or \\
                       "claude" in buf.value.lower() or "gemini" in buf.value.lower() or \\
                       "deepseek" in buf.value.lower():
                        user32.MoveWindow(hwnd, 80, 80, 1400, 900, True)
                return True
            user32.EnumWindows(WNDENUMPROC(cb), 0)
        except Exception as e:
            print(f"[WARN] could not move window: {e}")
        print()
        print(f"Log in to {provider} in the Chrome window.")
        print(f"Then run:  daemon hide {provider}   (or just close this and run {provider})")
        return 0

    def do_hide(provider=None):
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            def cb(hwnd, lp):
                n = user32.GetWindowTextLengthW(hwnd)
                if n:
                    buf = ctypes.create_unicode_buffer(n+1)
                    user32.GetWindowTextW(hwnd, buf, n+1)
                    if "Chrome" in buf.value:
                        user32.MoveWindow(hwnd, -32000, -32000, 1400, 900, True)
                return True
            user32.EnumWindows(WNDENUMPROC(cb), 0)
        except Exception as e:
            print(f"[WARN] {e}")
        print("Chrome pushed off-screen.")
        return 0

    def do_status():
        alive = port_open(SHARED_PORT)
        print("AInterceptor shared browser")
        print(f"  port    : {SHARED_PORT}")
        print(f"  profile : {SHARED_PROFILE}")
        print(f"  status  : {'alive' if alive else 'off'}")
        return 0

    def main():
        if len(sys.argv) < 2:
            print("usage: <provider> [login|hide|status]")
            return 1
        a0 = sys.argv[0+1].lower()
        if a0 == "status": return do_status()
        if a0 == "hide":   return do_hide()
        if a0 == "login":
            if len(sys.argv) < 3: print("usage: login <provider>"); return 1
            return do_login(sys.argv[2].lower())
        provider = a0
        if len(sys.argv) > 2:
            sub = sys.argv[2].lower()
            if sub == "login": return do_login(provider)
            if sub == "hide":  return do_hide(provider)
            if sub == "status":return do_status()
        return asyncio.run(do_chat(provider))

    if __name__ == "__main__":
        sys.exit(main())
''')

(BE / "scripts" / "chat_any.py").write_text(chat, encoding="utf-8", newline="\n")
print("  [OK] chat_any.py rewritten (shared browser, no daemon)")

# syntax
try: ast.parse(chat)
except SyntaxError as e:
    print("[FAIL] chat_any:", e); sys.exit(1)
print("  [OK] syntax valid (chat_any)")

# ─────────────────────────────────────────────────────────
# 5. bin wrappers
# ─────────────────────────────────────────────────────────
BIN.mkdir(exist_ok=True)
for name, provider in [("deepseek","deepseek"), ("claude","claude"),
                       ("chatgpt","chatgpt"), ("aigemini","gemini")]:
    (BIN / f"{name}.cmd").write_text(
        "@echo off\r\nset PYTHONUTF8=1\r\n"
        f'cd /d "{BE}"\r\n'
        f'"{PY}" -u -m scripts.chat_any {provider} %*\r\n',
        encoding="utf-8", newline="",
    )
    print(f"  [OK] bin/{name}.cmd")

(BIN / "daemon.cmd").write_text(
    "@echo off\r\nset PYTHONUTF8=1\r\n"
    f'cd /d "{BE}"\r\n'
    f'"{PY}" -u -m scripts.chat_any %*\r\n',
    encoding="utf-8", newline="",
)
print("  [OK] bin/daemon.cmd")

(BIN / "aid.cmd").write_text(
    "@echo off\r\nset PYTHONUTF8=1\r\n"
    f'cd /d "{BE}"\r\n'
    f'"{PY}" -u -m scripts.chat_any %*\r\n',
    encoding="utf-8", newline="",
)
print("  [OK] bin/aid.cmd")

# Also keep old aidaemon.cmd but make it delegate
(BIN / "aidaemon.cmd").write_text(
    "@echo off\r\n"
    "echo AInterceptor uses a shared Chrome (no daemon needed).\r\n"
    "echo.\r\n"
    "echo   login ^<provider^>    open Chrome for one-time login\r\n"
    "echo   hide                 push Chrome off-screen\r\n"
    "echo   status               show browser status\r\n"
    "echo   ^<provider^>          chat (deepseek/claude/chatgpt/aigemini)\r\n"
    "goto :eof\r\n",
    encoding="utf-8", newline="",
)
print("  [OK] bin/aidaemon.cmd (informational)")

# ─────────────────────────────────────────────────────────
# 6. Kill daemon remnants
# ─────────────────────────────────────────────────────────
subprocess.run(["powershell","-NoProfile","-Command",
    "Get-Process python,pythonw -EA SilentlyContinue | "
    "Where-Object { $_.Path -like '*Atlas*' } | "
    "Stop-Process -Force -EA SilentlyContinue"],
    capture_output=True, shell=True)

# ─────────────────────────────────────────────────────────
# 7. Launch the shared Chrome off-screen, open all four tabs
# ─────────────────────────────────────────────────────────
print("\n==> Launching shared Chrome off-screen on 9222")
subprocess.Popen(
    [PY, "-c",
     "import sys, pathlib, subprocess, time, socket\n"
     f"chrome = r'{find_chrome() or ''}'\n"
     "if not chrome:\n"
     "    print('FAIL: chrome.exe not found'); sys.exit(1)\n"
     f"profile = r'{SHARED_PROFILE}'\n"
     "args = [chrome, '--remote-debugging-port=9222',\n"
     f"        '--user-data-dir={{profile}}'.format(profile=profile),\n"
     "        '--no-first-run','--no-default-browser-check',\n"
     "        '--window-position=-32000,-32000','--window-size=1400,900',\n"
     "        'https://chatgpt.com/','https://claude.ai/','https://gemini.google.com/','https://chat.deepseek.com/']\n"
     "subprocess.Popen(args)\n"
     "for _ in range(30):\n"
     "    time.sleep(0.5)\n"
     "    s = socket.socket(); s.settimeout(0.4)\n"
     "    try:\n"
     "        s.connect(('127.0.0.1',9222)); print('OK: shared Chrome on 9222'); break\n"
     "    except OSError: pass\n"
     "    finally: s.close()\n"
     ],
    cwd=ROOT,
)

time.sleep(8)

# ─────────────────────────────────────────────────────────
# 8. Verify + instructions
# ─────────────────────────────────────────────────────────
s = socket.socket(); s.settimeout(0.4)
try:
    s.connect(("127.0.0.1", 9222)); alive = True
except OSError:
    alive = False
finally:
    s.close()

print()
print("=" * 66)
print("SHARED BROWSER READY — 9222" if alive else "SHARED BROWSER FAILED TO START")
print()
print("NEXT (open a new PowerShell window):")
print()
print("  1. Bring the shared Chrome on-screen once to log in:")
print("         login chatgpt")
print("         login claude")
print("         login gemini")
print("         login deepseek")
print("     (or just bring Chrome to front from the taskbar and log into all four tabs)")
print()
print("  2. Push it off-screen again:")
print("         hide")
print()
print("  3. Chat — no browser window:")
print("         deepseek")
print("         claude")
print("         chatgpt")
print("         aigemini")
print()
print("  Check status:")
print("         status")
print("=" * 66)

# Commit
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "feat(browser): shared Chrome profile for all providers; single CDP port 9222; tab-based routing"])
print((r.stdout.strip() or r.stderr.strip())[:500])
