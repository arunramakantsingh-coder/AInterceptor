import pathlib, subprocess, sys, ast

ROOT = pathlib.Path.cwd()
BS = ROOT / "backend" / "app" / "runtime" / "browser_supervisor.py"
src = BS.read_text(encoding="utf-8")

# Find the _launch method and replace the kill+spawn preamble with:
#   - if 9222 already answering /json/version -> just attach
#   - else kill + launch new
old = '''        self.profile_dir.mkdir(parents=True, exist_ok=True)
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
            raise RuntimeError(f"Chrome CDP did not bind on port {CDP_PORT}")'''

new = '''        self.profile_dir.mkdir(parents=True, exist_ok=True)

        def _cdp_alive(port: int) -> bool:
            import urllib.request as _u
            try:
                with _u.urlopen(f"http://127.0.0.1:{port}/json/version",
                                timeout=1.0) as r:
                    return "Browser" in r.read().decode("utf-8", "replace")
            except Exception:
                return False

        if _cdp_alive(CDP_PORT):
            # Reuse the existing Chrome — do not launch a second one.
            self.log(f"reusing existing Chrome on port {CDP_PORT}")
            self._chrome_proc = None
            ready = True
        else:
            # Kill any zombie listener (port open but not answering CDP)
            if _port_open(CDP_PORT):
                self.log(f"port {CDP_PORT} held by non-CDP process — killing")
                _kill_port(CDP_PORT)
                await asyncio.sleep(2.0)

            chrome = _find_chrome()
            if not chrome:
                raise RuntimeError("chrome.exe not found")

            args = _chrome_args(self.profile_dir, off_screen=self.off_screen)
            cmd = [chrome] + args
            self.log(f"launching Chrome: {chrome}")
            self._chrome_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )

            ready = False
            for _ in range(60):
                await asyncio.sleep(0.5)
                if _cdp_alive(CDP_PORT):
                    ready = True
                    break
            if not ready:
                raise RuntimeError(f"Chrome CDP did not bind on port {CDP_PORT}")'''

if old in src:
    src = src.replace(old, new, 1)
    BS.write_text(src, encoding="utf-8", newline="\n")
    print("  [OK] _launch: reuse existing Chrome if CDP is already answering")
else:
    print("  [!] _launch pattern not found — inspecting")
    # show region
    idx = src.find("def _launch")
    print(src[idx:idx+1200])
    sys.exit(1)

# Verify close() does not kill a Chrome we didn't launch
if "_chrome_proc is not None" not in src:
    src = src.replace(
        '''            try:
                proc = getattr(self, "_chrome_proc", None)
                if proc is not None:
                    proc.terminate()
            except Exception:
                pass''',
        '''            try:
                proc = getattr(self, "_chrome_proc", None)
                if proc is not None and proc.poll() is None:
                    # Only kill the Chrome if WE launched it
                    proc.terminate()
            except Exception:
                pass''',
        1,
    )
    BS.write_text(src, encoding="utf-8", newline="\n")
    print("  [OK] close() only kills Chrome we launched")

try:
    ast.parse(BS.read_text(encoding="utf-8"))
    print("  [OK] syntax valid")
except SyntaxError as e:
    print(f"[FAIL] {e}"); sys.exit(1)

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(supervisor): reuse running Chrome on 9222; only launch if none"])
print((r.stdout.strip() or r.stderr.strip())[:250])

print()
print("=" * 60)
print("Now:")
print("  1. Do NOT kill Chrome. Leave the one you see running.")
print("  2. In the daemon window: Ctrl+C")
print("  3. .\\run-windows.ps1")
print()
print("The daemon should now say:")
print("  [browser] reusing existing Chrome on port 9222")
print("  [browser] attached: N contexts")
print("  [browser] open tab: chatgpt -> ...")
print("=" * 60)
