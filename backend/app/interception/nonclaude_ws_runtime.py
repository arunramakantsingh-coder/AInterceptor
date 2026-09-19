"""WebSocket-based runtime for providers that stream over WS.

Used by Microsoft Copilot (SignalR-over-WebSocket) and Character.AI.
Same interface as NonClaudeWebRuntime but captures WebSocket frames
via CDP instead of HTTP responses.

Existing NonClaudeWebRuntime is untouched — this is a separate class.
"""
from __future__ import annotations

import asyncio
import base64
import pathlib
from typing import Any, AsyncIterator, Callable
from urllib.parse import urlparse

from app.interception.contracts import EventType, ProviderExecutionRequest, StreamEvent
from app.interception.runtime import ProviderRuntime
from app.interception.web_runtime import WebProviderSessionError, WebProviderSpec

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None


class NonClaudeWebSocketCapture:
    """Capture WebSocket frames via CDP."""

    def __init__(self, page: Any, spec: WebProviderSpec) -> None:
        self.page = page
        self.spec = spec
        self._cdp: Any = None
        self._active_id: str | None = None
        self._candidate_ids: set[str] = set()
        self._queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    @staticmethod
    def _matches(url: str, markers: tuple[str, ...]) -> bool:
        url = (url or "").lower()
        return any(m.lower() in url for m in markers)

    def _on_created(self, event: dict) -> None:
        url = str(event.get("url") or "")
        if not self._matches(url, self.spec.response_markers + self.spec.request_markers):
            return
        rid = str(event.get("requestId") or "")
        if rid:
            self._candidate_ids.add(rid)
            if self._active_id is None:
                self._active_id = rid
                self._queue.put_nowait(("opened", url))

    def _on_frame_received(self, event: dict) -> None:
        if str(event.get("requestId") or "") != self._active_id:
            return
        resp = event.get("response") or {}
        payload = resp.get("payloadData") or ""
        if not payload:
            return
        self._queue.put_nowait(("frame", payload))

    def _on_frame_error(self, event: dict) -> None:
        if str(event.get("requestId") or "") == self._active_id:
            self._queue.put_nowait(("error", event.get("errorMessage") or "ws frame error"))

    def _on_closed(self, event: dict) -> None:
        if str(event.get("requestId") or "") == self._active_id:
            self._queue.put_nowait(("closed", None))

    async def __aenter__(self) -> "NonClaudeWebSocketCapture":
        self._cdp = await self.page.context.new_cdp_session(self.page)
        await self._cdp.send("Network.enable", {
            "maxTotalBufferSize": 50 * 1024 * 1024,
            "maxResourceBufferSize": 10 * 1024 * 1024,
        })
        self._cdp.on("Network.webSocketCreated", self._on_created)
        self._cdp.on("Network.webSocketFrameReceived", self._on_frame_received)
        self._cdp.on("Network.webSocketFrameError", self._on_frame_error)
        self._cdp.on("Network.webSocketClosed", self._on_closed)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._cdp is not None:
            try:
                await self._cdp.send("Network.disable")
            except Exception:
                pass
            try:
                await self._cdp.detach()
            except Exception:
                pass
            self._cdp = None

    async def events(self, timeout: float = 180.0) -> AsyncIterator[tuple[str, Any]]:
        while True:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            except asyncio.TimeoutError:
                if not self._candidate_ids:
                    raise TimeoutError(f"{self.spec.provider}: no websocket observed")
                raise TimeoutError(f"{self.spec.provider}: websocket timed out")
            yield item
            if item[0] in {"closed", "error"}:
                return


class NonClaudeWebSocketRuntime(ProviderRuntime):
    """Runtime for WS-based providers. Same interface as NonClaudeWebRuntime."""

    def __init__(self, spec: WebProviderSpec, session_path: str | None,
                 cdp_url: str | None, headless: bool,
                 parser: Callable[[str], str]) -> None:
        self.spec = spec
        self.provider = spec.provider
        self.session_path = session_path
        self.cdp_url = cdp_url
        self.headless = headless
        self.parser = parser
        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._owns_browser = False
        self._owns_context = False
        self._started = False
        self._lock = asyncio.Lock()

    async def _ensure_page(self, interactive: bool = False) -> None:
        if async_playwright is None:
            raise WebProviderSessionError("playwright is not installed")
        if self._pw is None:
            self._pw = await async_playwright().start()
        if self.cdp_url:
            self._browser = await self._pw.chromium.connect_over_cdp(self.cdp_url)
            contexts = self._browser.contexts
            if not contexts:
                raise WebProviderSessionError("CDP browser has no context")
            self._context = contexts[0]
            self._owns_browser = self._owns_context = False
            host = urlparse(self.spec.home_url).netloc
            pages = [p for p in self._context.pages
                     if host == urlparse(p.url or "").netloc]
            self._page = pages[-1] if pages else await self._context.new_page()
        elif self.session_path and pathlib.Path(self.session_path).exists():
            self._browser = await self._pw.chromium.launch(headless=self.headless)
            self._context = await self._browser.new_context(storage_state=self.session_path)
            self._owns_browser = self._owns_context = True
            self._page = await self._context.new_page()
        else:
            profile = pathlib.Path(".ainterceptor") / "profiles" / self.provider
            profile.mkdir(parents=True, exist_ok=True)
            self._context = await self._pw.chromium.launch_persistent_context(
                str(profile), headless=False if interactive else self.headless)
            self._owns_context = True
            pages = list(self._context.pages)
            self._page = pages[-1] if pages else await self._context.new_page()
        if urlparse(self._page.url or "").netloc != urlparse(self.spec.home_url).netloc:
            await self._page.goto(self.spec.home_url, wait_until="domcontentloaded", timeout=30_000)

    def _is_login_page(self) -> bool:
        url = (self._page.url or "").lower()
        return any(m.lower() in url for m in self.spec.login_markers)

    async def start(self) -> None:
        if self._started:
            return
        await self._ensure_page()
        self._started = True

    async def login(self) -> None:
        await self._ensure_page(interactive=True)
        if self._is_login_page():
            print(f"{self.provider}: browser opened. Complete login in the provider window.")
            for _ in range(180):
                await asyncio.sleep(1)
                if not self._is_login_page():
                    break
        if self._is_login_page():
            raise WebProviderSessionError(f"{self.provider} login was not completed")
        path = self.session_path or str(pathlib.Path(".ainterceptor") / self.provider / "storage_state.json")
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        await self._context.storage_state(path=path)
        self.session_path = path
        self._started = True
        print(f"{self.provider}: authenticated session saved to {path}.")

    async def _prompt_textbox(self) -> Any:
        for selector in self.spec.composer_selectors:
            locator = self._page.locator(selector)
            for index in range(await locator.count() - 1, -1, -1):
                candidate = locator.nth(index)
                try:
                    if await candidate.is_visible() and await candidate.is_editable():
                        return candidate
                except Exception:
                    pass
        raise WebProviderSessionError(f"{self.provider} composer textbox is not available")

    async def execute(self, request: ProviderExecutionRequest) -> AsyncIterator[StreamEvent]:
        if request.provider != self.provider:
            raise ValueError(f"runtime provider mismatch: {request.provider}")
        await self.start()
        prompt = next((m.get("content", "") for m in reversed(request.messages)
                       if m.get("role") == "user"), "")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("execution requires a non-empty user message")
        async with self._lock:
            sequence = 0
            emitted = ""
            body = bytearray()
            async with NonClaudeWebSocketCapture(self._page, self.spec) as capture:
                yield StreamEvent(self.provider, request.request_id,
                                  EventType.REQUEST_INTERCEPTED, sequence,
                                  metadata={"transport": "chromium-cdp-websocket"})
                sequence += 1
                try:
                    textbox = await self._prompt_textbox()
                    await textbox.fill(prompt)
                    await textbox.press("Enter")
                except Exception as exc:
                    yield StreamEvent(self.provider, request.request_id,
                                      EventType.STREAM_FAILED, sequence,
                                      metadata={"reason": f"prompt_submission_failed: {exc}"})
                    return
                try:
                    async for kind, payload in capture.events():
                        if kind == "frame":
                            body.extend(payload.encode("utf-8"))
                            current = self.parser(body.decode("utf-8", errors="replace"))
                            if current and current.startswith(emitted):
                                delta = current[len(emitted):]
                            elif current and len(current) > len(emitted):
                                delta = current
                            else:
                                delta = ""
                            if delta:
                                yield StreamEvent(self.provider, request.request_id,
                                                  EventType.STREAM_DELTA, sequence, delta=delta)
                                sequence += 1
                                emitted = current if current.startswith(emitted) else emitted + delta
                        elif kind == "error":
                            yield StreamEvent(self.provider, request.request_id,
                                              EventType.STREAM_FAILED, sequence,
                                              metadata={"reason": str(payload)})
                            return
                        elif kind == "closed":
                            final = self.parser(body.decode("utf-8", errors="replace")).strip()
                            if final and final.startswith(emitted):
                                delta = final[len(emitted):]
                            elif final and final != emitted:
                                delta = final
                            else:
                                delta = ""
                            if delta:
                                yield StreamEvent(self.provider, request.request_id,
                                                  EventType.STREAM_DELTA, sequence, delta=delta)
                                sequence += 1
                            yield StreamEvent(self.provider, request.request_id,
                                              EventType.STREAM_COMPLETED, sequence,
                                              finish_reason="stop")
                            return
                except TimeoutError as exc:
                    yield StreamEvent(self.provider, request.request_id,
                                      EventType.STREAM_FAILED, sequence,
                                      metadata={"reason": str(exc)})
                except Exception as exc:
                    yield StreamEvent(self.provider, request.request_id,
                                      EventType.STREAM_FAILED, sequence,
                                      metadata={"reason": str(exc)})

    async def close(self) -> None:
        self._started = False
        if self._owns_context and self._context is not None:
            try: await self._context.close()
            except Exception: pass
        if self._owns_browser and self._browser is not None:
            try: await self._browser.close()
            except Exception: pass
        if self._pw is not None:
            try: await self._pw.stop()
            except Exception: pass
        self._pw = self._browser = self._context = self._page = None
        self._owns_browser = self._owns_context = False
