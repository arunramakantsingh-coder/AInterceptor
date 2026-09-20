"""Chrome process helpers for the browser supervisor (cross-platform)."""
from __future__ import annotations
import os
import pathlib
import socket
import subprocess
import sys


def find_chrome() -> str | None:
    if sys.platform.startswith("win"):
        for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
            if pathlib.Path(c).exists():
                return c
    else:
        for c in ("/usr/bin/google-chrome",
                  "/usr/bin/google-chrome-stable",
                  "/usr/bin/chromium",
                  "/usr/bin/chromium-browser",
                  "/opt/google/chrome/chrome"):
            if pathlib.Path(c).exists():
                return c
    return None


def port_open(port: int) -> bool:
    s = socket.socket()
    s.settimeout(0.4)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def cdp_alive(port: int) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version",
                                    timeout=1.0) as r:
            return "Browser" in r.read().decode("utf-8", "replace")
    except Exception:
        return False


def kill_port(port: int) -> None:
    if sys.platform.startswith("win"):
        cmd = (
            "Get-NetTCPConnection -LocalPort " + str(port) +
            " -State Listen -EA SilentlyContinue | "
            "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }"
        )
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                           capture_output=True, timeout=10)
        except Exception:
            pass
        return
    # Linux/macOS: try fuser, then pkill by debug-port marker
    for tool in (("fuser", "-k", f"{port}/tcp"),
                 ("pkill", "-f", f"remote-debugging-port={port}")):
        try:
            subprocess.run(list(tool), capture_output=True, timeout=10)
            return
        except FileNotFoundError:
            continue
        except Exception:
            return


def kill_our_chromes() -> int:
    """Kill Chrome processes whose command line mentions our profile path.
    Never touches the user's normal Chrome windows.
    """
    patterns = ("ainterceptor", "chrome-profile", "ainterceptor-chrome")
    if sys.platform.startswith("win"):
        cmd = (
            "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
            "Where-Object { $_.CommandLine -like '*ainterceptor*' -or "
            "$_.CommandLine -like '*chrome-profile*' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue; "
            "Write-Output $_.ProcessId }"
        )
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                               capture_output=True, text=True, timeout=15)
            ids = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
            return len(ids)
        except Exception:
            return 0
    # Linux/macOS
    try:
        r = subprocess.run(["pgrep", "-af", "chrome"],
                           capture_output=True, text=True, timeout=10)
    except Exception:
        return 0
    pids: list[str] = []
    for line in (r.stdout or "").splitlines():
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        pid, cmdline = parts
        if any(p in cmdline for p in patterns):
            pids.append(pid)
    killed = 0
    for pid in pids:
        try:
            os.kill(int(pid), 9)
            killed += 1
        except Exception:
            pass
    return killed
