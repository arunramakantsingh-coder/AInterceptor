"""Chrome process helpers for the browser supervisor."""
from __future__ import annotations
import pathlib
import socket
import subprocess
import sys


def find_chrome() -> str | None:
    for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
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
    if not sys.platform.startswith("win"):
        return
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


def kill_our_chromes() -> int:
    """Kill Chrome processes whose command line mentions our profile path.
    Never touches the user's normal Chrome windows.
    """
    if not sys.platform.startswith("win"):
        return 0
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
