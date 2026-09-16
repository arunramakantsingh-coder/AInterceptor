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
    return os.getenv("AINTERCEPTOR_CHROME_CDP_URL") or f"http://127.0.0.1:{_port()}"


def _cdp_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/json/version", timeout=1.0) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def ensure_chrome_cdp() -> str:
    """Return a localhost CDP endpoint, starting isolated system Chrome if needed."""
    url = chrome_cdp_url()
    if _cdp_ready(url):
        return url

    profile = _profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    executable = _chrome_executable()
    port = _port()
    args = [
        executable,
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
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

    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if _cdp_ready(url):
            return url
        time.sleep(0.25)
    raise RuntimeError(
        f"Chrome started but CDP endpoint did not become ready: {url}. "
        "Check whether Chrome or an enterprise policy blocks remote debugging."
    )


def existing_chrome_cdp() -> str | None:
    """Return an already-running configured CDP endpoint without starting Chrome."""
    url = chrome_cdp_url()
    return url if _cdp_ready(url) else None
