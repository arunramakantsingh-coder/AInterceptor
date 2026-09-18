import pathlib, subprocess

ROOT = pathlib.Path.cwd()
PROFILE = ROOT / ".ainterceptor" / "chrome-profile-chatgpt"
PROFILE.mkdir(parents=True, exist_ok=True)

# Already listening?
r = subprocess.run(["powershell","-NoProfile","-Command",
    "(Get-NetTCPConnection -LocalPort 9224 -State Listen -EA SilentlyContinue) -ne $null"],
    capture_output=True, text=True, shell=True)
if "True" in r.stdout:
    print("  [OK] chatgpt Chrome already on 9224")
else:
    cmd = (
        f'$c="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"; '
        f'if (!(Test-Path $c)) {{ $c="C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe" }}; '
        f'Start-Process $c -ArgumentList "--remote-debugging-port=9224",'
        f'"--user-data-dir={PROFILE}","--no-first-run","--no-default-browser-check",'
        f'"--window-position=-32000,-32000","https://chatgpt.com/"'
    )
    r = subprocess.run(["powershell","-NoProfile","-Command", cmd],
                       capture_output=True, text=True, shell=True)
    print("  [OK] launched chatgpt Chrome off-screen on 9224")

import time
time.sleep(4)

r = subprocess.run(["powershell","-NoProfile","-Command",
    "(Get-NetTCPConnection -LocalPort 9224 -State Listen -EA SilentlyContinue) -ne $null"],
    capture_output=True, text=True, shell=True)
print("  9224 alive:", "True" in r.stdout)

print()
print("=" * 60)
print("NEXT:")
print("  1. Bring ChatGPT's window on-screen to log in once.")
print("     Taskbar -> Chrome icon -> right-click ChatGPT -> Move -> arrow key")
print("  2. Log in with your ChatGPT account.")
print("  3. Then from PowerShell:")
print("       chatgpt")
print("=" * 60)
