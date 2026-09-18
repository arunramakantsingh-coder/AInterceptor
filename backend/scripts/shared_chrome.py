
"""Robust shared-Chrome launcher."""
import json, pathlib, socket, subprocess, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / ".ainterceptor"
PROFILE = STATE / "chrome-profile-shared"
PORT = 9222
URLS = {
    "chatgpt":  "https://chatgpt.com/",
    "claude":   "https://claude.ai/",
    "gemini":   "https://gemini.google.com/",
    "deepseek": "https://chat.deepseek.com/",
}


def find_chrome():
    for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if pathlib.Path(c).exists(): return c
    return None


def cdp_ready() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1.0) as r:
            data = json.loads(r.read())
            return "Browser" in data
    except Exception:
        return False


def kill_chrome():
    subprocess.run(["powershell","-NoProfile","-Command",
        f"Get-NetTCPConnection -LocalPort {PORT} -State Listen -EA SilentlyContinue | "
        "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }"],
        capture_output=True, shell=True)


def launch(off_screen=True, open_tabs=True) -> bool:
    chrome = find_chrome()
    if not chrome:
        print("[FAIL] chrome.exe not found"); return False
    PROFILE.mkdir(parents=True, exist_ok=True)
    pos = "-32000,-32000" if off_screen else "80,80"
    args = [chrome,
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={PROFILE}",
            "--no-first-run", "--no-default-browser-check",
            "--disable-features=ChromeWhatsNewUI",
            f"--window-position={pos}", "--window-size=1400,900"]
    if open_tabs:
        args.extend(URLS.values())
    else:
        args.append("about:blank")
    subprocess.Popen(args)
    for _ in range(40):     # 20s
        time.sleep(0.5)
        if cdp_ready(): return True
    return False


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "start"
    if action in {"stop","kill"}:
        kill_chrome(); print("stopped"); return 0
    if action == "restart":
        kill_chrome(); time.sleep(2)
        ok = launch(off_screen=True)
        print("restarted" if ok else "failed")
        return 0 if ok else 1
    if action == "status":
        print(f"CDP 9222: {'ready' if cdp_ready() else 'off'}")
        return 0
    # default start
    ok = launch(off_screen=True)
    print("started" if ok else "failed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
