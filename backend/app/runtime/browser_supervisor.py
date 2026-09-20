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

from app.runtime._chrome_helpers import (
    find_chrome as _find_chrome,
    port_open as _port_open,
    cdp_alive as _cdp_alive,
    kill_port as _kill_port,
    kill_our_chromes as _kill_our_chromes,
)








CDP_PORT = 9222


PROVIDER_URLS: dict[str, str] = {
    "chatgpt":     "https://chatgpt.com/",
    "claude":      "https://claude.ai/",
    "gemini":      "https://gemini.google.com/",
    "deepseek":    "https://chat.deepseek.com/",
    "mistral":     "https://chat.mistral.ai/",
    "lechat":      "https://chat.mistral.ai/chat",
    "qwen":        "https://chat.qwen.ai/",
    "kimi":        "https://www.kimi.com/",
    "yi":          "https://platform.lingyiwanwu.com/",
    "glm":         "https://chat.z.ai/",
    "doubao":      "https://www.dola.com/",
    "huggingchat": "https://huggingface.co/chat/",
    "perplexity":  "https://www.perplexity.ai/",
    "you":         "https://you.com/",
    "phind":       "https://www.phind.com/",
    "grok":        "https://grok.com/",
    "meta":        "https://www.meta.ai/",
    "copilot":     "https://copilot.microsoft.com/",
    "character":   "https://character.ai/",
    "poe":         "https://poe.com/",
}


def _chrome_args(profile_dir: pathlib.Path, off_screen: bool = True) -> list[str]:
    pos = "-32000,-32000" if off_screen else "100,100"
    return [
        f"--user-data-dir={profile_dir}",
        f"--remote-debugging-port={CDP_PORT}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--remote-allow-origins=*",
        f"--window-position={pos}",
        "--window-size=1400,900",
        "--disable-features=ChromeWhatsNewUI",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
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
                if proc is not None and proc.poll() is None:
                    # Only kill the Chrome if WE launched it
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

        if _cdp_alive(CDP_PORT):
            # Reuse the existing Chrome — do not launch a second one.
            self.log(f"reusing existing Chrome on port {CDP_PORT}")
            self._chrome_proc = None
            ready = True
        else:
            # Kill any Chrome holding our profile — otherwise a new launch
            # silently delegates to the running one and never binds CDP.
            killed = _kill_our_chromes()
            if killed:
                self.log(f"killed {killed} stale Chrome(s) using our profile")
                await asyncio.sleep(2.5)

            # Also clear any zombie listener on 9222
            if _port_open(CDP_PORT):
                self.log(f"port {CDP_PORT} held by non-CDP process — killing")
                _kill_port(CDP_PORT)
                await asyncio.sleep(2.0)

            chrome = _find_chrome()
            if not chrome:
                raise RuntimeError("chrome.exe not found")

            args = _chrome_args(self.profile_dir, off_screen=self.off_screen)
            cmd = [chrome] + args
            self.log(f"launching Chrome: {chrome}")
            log_dir = pathlib.Path(".ainterceptor")
            log_dir.mkdir(parents=True, exist_ok=True)
            chrome_log = open(log_dir / "chrome_launch.log", "ab")
            popen_kwargs = {"stdout": chrome_log, "stderr": chrome_log}
            if sys.platform.startswith("win"):
                popen_kwargs["creationflags"] = (
                    getattr(subprocess, "DETACHED_PROCESS", 0)
                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
            else:
                popen_kwargs["start_new_session"] = True
            self._chrome_proc = subprocess.Popen(cmd, **popen_kwargs)
            self.log(f"Chrome PID: {self._chrome_proc.pid}")

            ready = False
            for _ in range(60):
                await asyncio.sleep(0.5)
                if _cdp_alive(CDP_PORT):
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
    if not sys.platform.startswith("win"):
        # Xvfb has no physical screen — nothing to hide
        return 0
    """Hide every Chrome window belonging to us. Belt-and-suspenders:
    MoveWindow off-screen + ShowWindow(SW_HIDE). Returns count hidden.
    """
    if not sys.platform.startswith("win"):
        return 0
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        SW_HIDE = 0

        # Titles we consider "ours" — anything with our provider names
        # or Chrome running with our debug port marker.
        markers = (
            "chatgpt", "claude", "gemini", "deepseek", "mistral", "qwen",
            "kimi", "grok", "perplexity", "poe", "copilot", "meta",
            "ainterceptor", "chrome",
        )
        hidden = 0

        def cb(hwnd, lp):
            nonlocal hidden
            try:
                n = u.GetWindowTextLengthW(hwnd)
                if not n:
                    return True
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                title = buf.value.lower()
                if not any(k in title for k in markers):
                    return True
                # Belt
                u.MoveWindow(hwnd, -32000, -32000, 1400, 900, True)
                # Suspenders
                u.ShowWindow(hwnd, SW_HIDE)
                hidden += 1
            except Exception:
                pass
            return True

        u.EnumWindows(CB(cb), 0)
        return hidden
    except Exception:
        return 0

