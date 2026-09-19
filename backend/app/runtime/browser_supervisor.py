"""Patchright-based browser supervisor.

Owns exactly one Chrome process. Opens one tab per provider. Keeps
everything off-screen. Detects crashes and re-launches from the
persistent profile. Exposes an async API used by the daemon.
"""
from __future__ import annotations
import asyncio
import os
import pathlib
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any


def _find_chrome() -> str | None:
    for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if pathlib.Path(c).exists():
            return c
    return None


def _port_open(port: int) -> bool:
    import socket as _sock
    s = _sock.socket(); s.settimeout(0.4)
    try:
        s.connect(("127.0.0.1", port)); return True
    except OSError:
        return False
    finally:
        s.close()


def _kill_port(port: int) -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-NetTCPConnection -LocalPort {port} -State Listen -EA SilentlyContinue | "
             "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass



# ── provider tab URLs ─────────────────────────────────────────────────

PROVIDER_URLS: dict[str, str] = {
    "chatgpt":    "https://chatgpt.com/",
    "claude":     "https://claude.ai/",
    "gemini":     "https://gemini.google.com/",
    "deepseek":   "https://chat.deepseek.com/",
    "mistral":    "https://chat.mistral.ai/",
    "qwen":       "https://chat.qwen.ai/",
    "huggingchat":"https://huggingface.co/chat/",
    "perplexity": "https://www.perplexity.ai/",
    "grok":       "https://grok.com/",
    "poe":        "https://poe.com/",
}


# ── browser launch arguments ──────────────────────────────────────────

CDP_PORT = 9222   # ClaudeRuntime attaches here


def _chrome_args(profile_dir: pathlib.Path, off_screen: bool = True) -> list[str]:
    pos = "-32000,-32000" if off_screen else "100,100"
    return [
        f"--remote-debugging-port={CDP_PORT}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--remote-allow-origins=*",
        f"--window-position={pos}",
        "--window-size=1400,900",
        "--disable-features=ChromeWhatsNewUI",
    ]


# ── state ─────────────────────────────────────────────────────────────

@dataclass
class Tab:
    provider: str
    url: str
    page: Any = None       # patchright Page
    last_used: float = 0.0
    errors_since_success: int = 0


@dataclass
class BrowserState:
    pw: Any = None
    browser: Any = None
    context: Any = None
    tabs: dict[str, Tab] = field(default_factory=dict)
    started_at: float = 0.0
    restarts: int = 0
    ready: bool = False


# ── supervisor ────────────────────────────────────────────────────────

class BrowserSupervisor:
    """Owns one Patchright Chrome with one tab per provider."""

    def __init__(
        self,
        profile_dir: pathlib.Path,
        providers: list[str] | None = None,
        off_screen: bool = True,
        headless: bool = False,          # headless is False because Cloudflare
                                         # blocks headless; Chrome renders to
                                         # the desktop off-screen instead
        logger=None,
    ) -> None:
        self.profile_dir = pathlib.Path(profile_dir)
        self.providers = providers or list(PROVIDER_URLS.keys())
        self.off_screen = off_screen
        self.headless = headless
        self.log = logger or (lambda msg: print(f"[browser] {msg}", flush=True))
        self.state = BrowserState()
        self._lock = asyncio.Lock()
        self._watchdog_task: asyncio.Task | None = None
        self._stopping = False

    # ── lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Launch Chrome and open one tab per provider."""
        async with self._lock:
            if self.state.ready:
                return
            await self._launch()
            await self._open_all_tabs()
            self.state.ready = True
            self.state.started_at = time.time()
            self.log(f"ready: {len(self.state.tabs)} tabs")

    async def stop(self) -> None:
        self._stopping = True
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except (asyncio.CancelledError, Exception):
                pass
        async with self._lock:
            # We do NOT own the context (attached via CDP). Just detach.
            try:
                if self.state.browser:
                    await self.state.browser.close()
            except Exception:
                pass
            try:
                if self.state.pw:
                    await self.state.pw.stop()
            except Exception:
                pass
            # Kill the subprocess Chrome we launched
            try:
                proc = getattr(self, "_chrome_proc", None)
                if proc is not None:
                    proc.terminate()
            except Exception:
                pass
            self.state = BrowserState()

    # ── tab management ────────────────────────────────────────────────

    async def get_tab(self, provider: str) -> Tab:
        """Return the tab for a provider; open if missing or stale."""
        if provider not in PROVIDER_URLS:
            raise KeyError(f"unknown provider: {provider}")
        async with self._lock:
            tab = self.state.tabs.get(provider)
            if tab and tab.page and not tab.page.is_closed():
                tab.last_used = time.time()
                return tab
            # (re)open
            tab = await self._open_tab(provider)
            self.state.tabs[provider] = tab
            return tab

    async def _open_tab(self, provider: str) -> Tab:
        url = PROVIDER_URLS[provider]
        self.log(f"open tab: {provider} -> {url}")
        page = await self.state.context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        except Exception as e:
            self.log(f"goto failed for {provider}: {e}")
        return Tab(provider=provider, url=url, page=page, last_used=time.time())

    async def _open_all_tabs(self) -> None:
        for p in self.providers:
            if p not in self.state.tabs:
                try:
                    self.state.tabs[p] = await self._open_tab(p)
                except Exception as e:
                    self.log(f"tab open failed for {p}: {e}")

    # ── launch ────────────────────────────────────────────────────────


    async def _launch(self) -> None:
        """Launch Chrome as a plain subprocess — Playwright does NOT own it.

        This lets external CDP clients (like the runtime classes) attach
        simultaneously. The previous launch_persistent_context() approach
        made Playwright the owner of the CDP session, which caused every
        other client to time out.
        """
        try:
            from patchright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError(f"patchright not installed: {e}")

        self.profile_dir.mkdir(parents=True, exist_ok=True)
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
            raise RuntimeError(f"Chrome CDP did not bind on port {CDP_PORT}")

        # Now attach via CDP — we do not own the browser
        self.state.pw = await async_playwright().start()
        try:
            self.state.browser = await asyncio.wait_for(
                self.state.pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}"),
                timeout=15,
            )
        except Exception as e:
            raise RuntimeError(f"CDP attach failed: {e}")

        contexts = self.state.browser.contexts
        if not contexts:
            self.state.context = await self.state.browser.new_context(
                viewport={"width": 1400, "height": 900},
                locale="en-US",
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/130.0.0.0 Safari/537.36"),
            )
        else:
            self.state.context = contexts[0]
        self.log(f"attached: {len(contexts) if contexts else 0} contexts")


    async def start_watchdog(self, interval_s: float = 10.0) -> None:
        if self._watchdog_task:
            return
        self._watchdog_task = asyncio.create_task(self._watchdog(interval_s))

    async def _watchdog(self, interval_s: float) -> None:
        while not self._stopping:
            await asyncio.sleep(interval_s)
            if self._stopping:
                return
            if not self.is_alive():
                self.log("watchdog: chrome dead, restarting")
                try:
                    async with self._lock:
                        await self._launch()
                        await self._open_all_tabs()
                        self.state.ready = True
                        self.state.restarts += 1
                except Exception as e:
                    self.log(f"watchdog restart failed: {e}")


# ── off-screen enforcement (Windows) ──────────────────────────────────

def push_chrome_off_screen() -> int:
    """Move every visible Chrome window off-screen. Returns count moved."""
    if not sys.platform.startswith("win"):
        return 0
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        moved = 0

        def cb(hwnd, lp):
            nonlocal moved
            try:
                n = u.GetWindowTextLengthW(hwnd)
                if not n:
                    return True
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                title = buf.value.lower()
                if "chrome" not in title and not any(
                    k in title for k in ("claude", "chatgpt", "gemini", "deepseek",
                                         "mistral", "qwen", "perplexity", "grok", "poe")
                ):
                    return True
                if not u.IsWindowVisible(hwnd):
                    return True
                u.MoveWindow(hwnd, -32000, -32000, 1400, 900, True)
                moved += 1
            except Exception:
                pass
            return True

        u.EnumWindows(CB(cb), 0)
        return moved
    except Exception:
        return 0
