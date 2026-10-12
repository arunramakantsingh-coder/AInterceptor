import pathlib, subprocess, sys, socket, time, json, urllib.request

ROOT = pathlib.Path.cwd()
STATE = ROOT / ".ainterceptor"
PROFILE = STATE / "chrome-profile-shared"
PROFILE.mkdir(parents=True, exist_ok=True)
PORT = 9222

# ── 1. Kill any Chrome on 9222 ──
print("==> killing Chrome on 9222")
subprocess.run(["powershell","-NoProfile","-Command",
    f"Get-NetTCPConnection -LocalPort {PORT} -State Listen -EA SilentlyContinue | "
    "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }"],
    capture_output=True, shell=True)
time.sleep(2)

# Clean locks
for n in ("SingletonLock","SingletonCookie","SingletonSocket","lockfile"):
    p = PROFILE / n
    if p.exists():
        try: p.unlink()
        except Exception: pass

# ── 2. Launch Chrome with the CDP-friendly flags ──
chrome = None
for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
          r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
    if pathlib.Path(c).exists():
        chrome = c; break

if not chrome:
    print("[FAIL] chrome.exe not found"); sys.exit(1)

print(f"==> launching {chrome}")
args = [
    chrome,
    f"--remote-debugging-port={PORT}",
    f"--user-data-dir={PROFILE}",
    "--no-first-run",
    "--no-default-browser-check",
    "--remote-allow-origins=*",                 # ← THE FIX for Playwright
    "--disable-features=ChromeWhatsNewUI",
    "--window-position=-32000,-32000",
    "--window-size=1400,900",
    "https://chatgpt.com/",
    "https://claude.ai/",
    "https://gemini.google.com/",
    "https://chat.deepseek.com/",
]
subprocess.Popen(args)

# ── 3. Wait for CDP to be reachable ──
def cdp_ok():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1.0) as r:
            return json.loads(r.read())
    except Exception:
        return None

info = None
for _ in range(40):
    time.sleep(0.5)
    info = cdp_ok()
    if info: break

if not info:
    print("[FAIL] Chrome CDP never came up"); sys.exit(1)

print(f"  [OK] CDP ready: {info.get('Browser')}")
print(f"       WS URL:   {info.get('webSocketDebuggerUrl')}")

# ── 4. Direct Playwright test ──
print("\n==> testing Playwright connect_over_cdp")
PY = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
test = '''
import asyncio, sys
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        try:
            browser = await asyncio.wait_for(
                pw.chromium.connect_over_cdp("http://127.0.0.1:9222"),
                timeout=15)
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            pages = ctx.pages
            print(f"OK: connected. {len(pages)} tabs")
            for p in pages[:5]:
                print(f"   - {p.url[:80]}")
            await browser.close()
            return 0
        except Exception as e:
            print(f"FAIL: {type(e).__name__}: {e}")
            return 1

sys.exit(asyncio.run(main()))
'''
r = subprocess.run([PY, "-u", "-c", test],
                   capture_output=True, text=True, encoding="utf-8")
print(r.stdout)
if r.stderr.strip(): print(r.stderr[-800:])

# ── 5. Commit ──
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(browser): add --remote-allow-origins=* for Playwright CDP handshake"])
print((r.stdout.strip() or r.stderr.strip())[:300])

print()
print("=" * 66)
print("If the Playwright test printed 'OK:', run:")
print("  deepseek")
print("=" * 66)
