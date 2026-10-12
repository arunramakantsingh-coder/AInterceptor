import pathlib, subprocess, sys, socket, time

ROOT = pathlib.Path.cwd()
STATE = ROOT / ".ainterceptor"
STATE.mkdir(exist_ok=True)
PROFILE = STATE / "chrome-profile-shared"
PROFILE.mkdir(parents=True, exist_ok=True)

chrome = None
for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
          r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
    if pathlib.Path(c).exists():
        chrome = c
        break

if not chrome:
    print("[FAIL] chrome.exe not found"); sys.exit(1)

# Kill anything already on 9222
subprocess.run(["powershell","-NoProfile","-Command",
    "Get-NetTCPConnection -LocalPort 9222 -State Listen -EA SilentlyContinue | "
    "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }"],
    capture_output=True, shell=True)
time.sleep(1)

print(f"launching: {chrome}")
print(f"profile:   {PROFILE}")

subprocess.Popen([
    chrome,
    "--remote-debugging-port=9222",
    f"--user-data-dir={PROFILE}",
    "--no-first-run",
    "--no-default-browser-check",
    "--window-position=-32000,-32000",
    "--window-size=1400,900",
    "https://chatgpt.com/",
    "https://claude.ai/",
    "https://gemini.google.com/",
    "https://chat.deepseek.com/",
])

ok = False
for _ in range(30):
    time.sleep(0.5)
    s = socket.socket(); s.settimeout(0.4)
    try:
        s.connect(("127.0.0.1", 9222)); ok = True; break
    except OSError:
        pass
    finally:
        s.close()

if ok:
    print("PASS: shared Chrome alive on 9222 (off-screen)")
    print()
    print("NEXT (open a new PowerShell window):")
    print("  login chatgpt      <- brings Chrome on-screen")
    print("  login claude")
    print("  login gemini")
    print("  login deepseek")
    print("  hide               <- push it back off-screen")
    print("  deepseek           <- chat, no window")
else:
    print("FAIL: 9222 did not come up")
    sys.exit(1)

# commit
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "chore(browser): fix shared Chrome launcher (chrome path resolution)"])
print(r.stdout.strip() or r.stderr.strip())
