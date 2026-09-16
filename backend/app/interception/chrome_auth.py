"""Launch and discover the real Chrome browser used for provider authentication.

Google OAuth is intentionally performed in a normal Chrome instance rather than
inside a Playwright-launched Chromium context. The browser uses an isolated
AInterceptor profile and localhost-only CDP so provider runtimes can attach to
the authenticated session without handling Google credentials.
"""
from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_PORT = 9222


def _port() -> int:
    raw = os.getenv("AINTERCEPTOR_CHROME_CDP_PORT", str(DEFAULT_PORT))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("AINTERCEPTOR_CHROME_CDP_PORT must be an integer") from exc
    if not 1024 <= value <= 65535:
        raise RuntimeError("AINTERCEPTOR_CHROME_CDP_PORT must be between 1024 and 65535")
    return value


def _profile_dir() -> Path:
    return Path(
        os.getenv("AINTERCEPTOR_CHROME_USER_DATA_DIR")
        or str(Path(".ainterceptor") / "chrome-profile")
    ).expanduser()


def _endpoint_file() -> Path:
    return _profile_dir() / "cdp_endpoint.txt"


def _chrome_executable() -> str:
    configured = os.getenv("AINTERCEPTOR_CHROME_PATH")
    if configured:
        path = Path(configured).expanduser()
        if path.exists():
            return str(path)
        raise RuntimeError(f"AINTERCEPTOR_CHROME_PATH does not exist: {path}")

    candidates: list[Path] = []
    system = platform.system()
    if system == "Windows":
        for root in (os.getenv("PROGRAMFILES"), os.getenv("PROGRAMFILES(X86)"), os.getenv("LOCALAPPDATA")):
            if root:
                candidates.append(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe")
    elif system == "Darwin":
        candidates.append(Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
    else:
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            found = shutil.which(name)
            if found:
                return found

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise RuntimeError(
        "Google Chrome was not found. Set AINTERCEPTOR_CHROME_PATH to the Chrome executable."
    )


def chrome_cdp_url() -> str:
    configured = os.getenv("AINTERCEPTOR_CHROME_CDP_URL")
    if configured:
        return configured
    endpoint_file = _endpoint_file()
    try:
        saved = endpoint_file.read_text(encoding="utf-8").strip()
    except OSError:
        saved = ""
    return saved or f"http://127.0.0.1:{_port()}"


def _cdp_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/json/version", timeout=1.0) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _free_port(start: int) -> int:
    for port in range(start, min(start + 50, 65536)):
        if _port_in_use(port):
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free localhost CDP port found starting at {start}")


def _launch(executable: str, profile: Path, port: int) -> None:
    profile.mkdir(parents=True, exist_ok=True)
    log_path = profile / "chrome_launch.log"
    log_handle = log_path.open("a", encoding="utf-8")
    args = [
        executable,
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=*",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
    ]
    subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    # The child owns the duplicated file descriptor after Popen returns.
    log_handle.close()


def ensure_chrome_cdp() -> str:
    """Return a localhost CDP endpoint, starting isolated system Chrome if needed."""
    configured = os.getenv("AINTERCEPTOR_CHROME_CDP_URL")
    if configured and _cdp_ready(configured):
        return configured

    profile = _profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    executable = _chrome_executable()
    requested_port = _port()

    # The first choice is the persistent AInterceptor authentication profile.
    # If it is locked by another Chrome instance, or the requested port belongs
    # to another process, use a fresh isolated profile instead of allowing
    # Chrome to hand the launch to an unrelated existing browser.
    candidates: list[tuple[Path, int]] = []
    stable_port = requested_port
    stable_locked = (profile / "SingletonLock").exists()
    stable_port_busy = _port_in_use(stable_port) and not _cdp_ready(
        f"http://127.0.0.1:{stable_port}"
    )

    if not stable_locked and not stable_port_busy:
        candidates.append((profile, stable_port))

    fallback_profile = profile.parent / f"chrome-profile-{int(time.time())}"
    candidates.append((fallback_profile, _free_port(requested_port)))

    last_url = f"http://127.0.0.1:{requested_port}"
    for launch_profile, port in candidates:
        candidate = f"http://127.0.0.1:{port}"
        last_url = candidate
        if _cdp_ready(candidate):
            return candidate

        try:
            _launch(executable, launch_profile, port)
        except OSError as exc:
            continue

        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if _cdp_ready(candidate):
                try:
                    _endpoint_file().parent.mkdir(parents=True, exist_ok=True)
                    _endpoint_file().write_text(candidate, encoding="utf-8")
                except OSError:
                    pass
                return candidate
            time.sleep(0.25)

    raise RuntimeError(
        f"Chrome authentication browser did not expose CDP: {last_url}. "
        "AInterceptor requires a separate visible Chrome window with a dedicated user-data directory. "
        "If Chrome closes immediately, inspect .ainterceptor\\chrome-profile\\chrome_launch.log."
    )


def existing_chrome_cdp() -> str | None:
    """Return an already-running configured CDP endpoint without starting Chrome."""
    url = chrome_cdp_url()
    return url if _cdp_ready(url) else None
