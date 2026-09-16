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


def _free_port(start: int) -> int:
    for port in range(start, min(start + 50, 65536)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free localhost CDP port found starting at {start}")


def _launch(executable: str, profile: Path, port: int) -> None:
    args = [
        executable,
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=*",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def ensure_chrome_cdp() -> str:
    """Return a localhost CDP endpoint, starting isolated system Chrome if needed."""
    url = chrome_cdp_url()
    if _cdp_ready(url):
        return url

    profile = _profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    executable = _chrome_executable()
    requested_port = _port()

    # A previous Chrome can leave the default port unavailable, or a Chrome
    # process can already own the profile without exposing CDP. Prefer the
    # configured port, then recover with a fresh localhost port and isolated
    # profile rather than reporting a generic startup failure.
    profiles = [profile]
    if (profile / "SingletonLock").exists():
        profiles.append(profile.parent / f"chrome-profile-{int(time.time())}")

    last_url = url
    for launch_profile in profiles:
        port = requested_port if launch_profile == profile else _free_port(requested_port)
        if not _cdp_ready(f"http://127.0.0.1:{port}"):
            _launch(executable, launch_profile, port)
        candidate = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if _cdp_ready(candidate):
                try:
                    _endpoint_file().parent.mkdir(parents=True, exist_ok=True)
                    _endpoint_file().write_text(candidate, encoding="utf-8")
                except OSError:
                    pass
                return candidate
            time.sleep(0.25)
        last_url = candidate

    raise RuntimeError(
        f"Chrome started but CDP endpoint did not become ready: {last_url}. "
        "Check whether Chrome is already using the AInterceptor profile or an enterprise policy blocks remote debugging."
    )


def existing_chrome_cdp() -> str | None:
    """Return an already-running configured CDP endpoint without starting Chrome."""
    url = chrome_cdp_url()
    return url if _cdp_ready(url) else None
