"""Shared browser runtime for ChatGPT, Gemini and DeepSeek.

Claude intentionally does not use this module. Its dedicated transport remains
unchanged as the known-good streaming reference.
"""
from __future__ import annotations

import asyncio
import os
import base64
import pathlib
from typing import Any, AsyncIterator, Callable
from urllib.parse import urlparse

from app.interception.contracts import EventType, ProviderExecutionRequest, StreamEvent
from app.interception.runtime import ProviderRuntime
from app.interception.web_runtime import WebProviderSessionError, WebProviderSpec
from app.interception import registry as provider_registry

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None


class NonClaudeNetworkCapture:
    """CDP response capture using the same Network streaming path as Claude."""

    def __init__(self, page: Any, spec: WebProviderSpec) -> None:
        self._cdp_logged = False
        self.page = page
        self.spec = spec
        self._cdp: Any | None = None
        self._candidate_ids: set[str] = set()
        self._active_id: str | None = None
        self._status = 0
        self._content_type = ""
        self._queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    @staticmethod
    def _matches(url: str, markers: tuple[str, ...]) -> bool:
        url = (url or "").lower()
        return any(marker.lower() in url for marker in markers)

    def _on_request(self, event: dict[str, Any]) -> None:
        request = event.get("request") or {}
        if str(request.get("method") or "").upper() != "POST":
            return
        if not self._matches(str(request.get("url") or ""),
                             self.spec.response_markers + self.spec.request_markers):
            return
        request_id = str(event.get("requestId") or "")
        if request_id:
            self._candidate_ids.add(request_id)

    def _on_response(self, event: dict[str, Any]) -> None:
        request_id = str(event.get("requestId") or "")
        if request_id not in self._candidate_ids or self._active_id is not None:
            return
        response = event.get("response") or {}
        self._active_id = request_id
        self._status = int(response.get("status", 0))
        headers = response.get("headers") or {}
        self._content_type = str(headers.get("content-type") or headers.get("Content-Type") or "").lower()
        self._queue.put_nowait(("response_started", (self._status, self._content_type)))
        asyncio.create_task(self._start_stream(request_id))

    async def _start_stream(self, request_id: str) -> None:
        try:
            result = await self._cdp.send("Network.streamResourceContent", {"requestId": request_id})
            buffered = result.get("bufferedData") or ""
            if buffered:
                self._queue.put_nowait(("data", base64.b64decode(buffered)))
        except Exception as exc:
            self._queue.put_nowait(("failed", f"provider response streaming failed: {exc}"))

    def _on_data(self, event: dict[str, Any]) -> None:
        if str(event.get("requestId") or "") != self._active_id:
            return
        data = event.get("data")
        if not data:
            return
        try:
            payload = base64.b64decode(data)
        except Exception:
            payload = str(data).encode("utf-8", errors="replace")
        raw_path = getattr(self, "_raw_path", None)
        if raw_path is None:
            raw_path = self._raw_capture_path()
            self._raw_path = raw_path
        if raw_path:
            with open(raw_path, "ab") as fh:
                fh.write(payload)
        self._queue.put_nowait(("data", payload))

    def _on_finished(self, event: dict[str, Any]) -> None:
        if str(event.get("requestId") or "") == self._active_id:
            self._queue.put_nowait(("finished", None))

    def _on_failed(self, event: dict[str, Any]) -> None:
        if str(event.get("requestId") or "") == self._active_id:
            self._queue.put_nowait(("failed", event.get("errorText") or "network request failed"))

    def _raw_capture_path(self) -> str | None:
        d = os.environ.get("AINTERCEPTOR_RAW_CAPTURE_DIR")
        if not d:
            return None
        p = pathlib.Path(d)
        p.mkdir(parents=True, exist_ok=True)
        return str(p / f"{self.spec.provider}_{int(__import__('time').time())}.raw")

    async def __aenter__(self) -> "NonClaudeNetworkCapture":
        self._cdp = await self.page.context.new_cdp_session(self.page)
        try:
            await self._cdp.send("Network.enable", {
                "maxTotalBufferSize": 50 * 1024 * 1024,
                "maxResourceBufferSize": 10 * 1024 * 1024,
            })
        except Exception:
            pass
        try:
            await self._cdp.send("Network.setBypassServiceWorker", {"bypass": True})
        except Exception:
            pass
        self._cdp.on("Network.requestWillBeSent", self._on_request)
        self._cdp.on("Network.responseReceived", self._on_response)
        self._cdp.on("Network.dataReceived", self._on_data)
        self._cdp.on("Network.loadingFinished", self._on_finished)
        self._cdp.on("Network.loadingFailed", self._on_failed)
        return self

    async def events(self, timeout: float = 120.0):
        while True:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            except asyncio.TimeoutError:
                if not self._candidate_ids:
                    raise TimeoutError(f"{self.spec.provider} provider POST was not observed")
                raise TimeoutError(f"{self.spec.provider} provider response timed out")
            yield item
            if item[0] in {"finished", "failed"}:
                return

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

class NonClaudeWebRuntime(ProviderRuntime):
    """Reusable runtime boundary for the three non-Claude web providers."""

    def __init__(self, spec: WebProviderSpec, session_path: str | None, cdp_url: str | None, headless: bool, parser: Callable[[str], str]) -> None:
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

    def _record_port_attachment(self) -> None:
        """Append a line to .ainterceptor/ports.log the first time this
        runtime attaches to a provider CDP endpoint. Format:
            2026-09-18T12:34:56Z  deepseek  http://127.0.0.1:9223
        """
        try:
            import datetime as _dt
            log_dir = pathlib.Path(".ainterceptor")
            log_dir.mkdir(parents=True, exist_ok=True)
            line = (
                _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                + f"  {self.provider:<10} {self.cdp_url}\n"
            )
            with open(log_dir / "ports.log", "a", encoding="utf-8") as fh:
                fh.write(line)
        except Exception:
            pass

    async def _ensure_page(self, interactive: bool = False) -> None:
        if async_playwright is None:
            raise WebProviderSessionError("playwright is not installed")
        if self._pw is None:
            self._pw = await async_playwright().start()

        # CDP resolution: registry-first, env override honored, never fall
        # back to a shared "existing_chrome_cdp()" that could attach us to
        # another provider's browser.
        env_key = f"AINTERCEPTOR_{self.provider.upper()}_CDP_URL"
        env_val = os.environ.get(env_key)
        if env_val == "":
            self.cdp_url = None
        elif env_val:
            self.cdp_url = env_val
        else:
            self.cdp_url = provider_registry.cdp_url(self.provider)
        if not getattr(self, "_cdp_logged", False):
            self._cdp_logged = True
            self._record_port_attachment()

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
            await self._page.goto(self.spec.home_url, wait_until="domcontentloaded",
                                  timeout=30_000)
    def _is_login_page(self) -> bool:
        url = (self._page.url or "").lower()
        return any(marker.lower() in url for marker in self.spec.login_markers)

    async def start(self) -> None:
        if self._started:
            return
        await self._ensure_page()
        if self._is_login_page():
            raise WebProviderSessionError(f"{self.provider} session is not authenticated; use provider login")
        self._started = True

    async def login(self) -> None:
        await self._ensure_page(interactive=True)
        if self._is_login_page():
            print(f"{self.provider}: browser opened. Complete login in the provider window.")
            print("Waiting for authenticated provider session...")
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

    async def execute(self, request: ProviderExecutionRequest):
        """Submit prompt, wait for assistant bubble to stabilise, return it.

        Transport-layer decoding is intentionally NOT used here. The DOM is
        the authoritative source for the reply text. Provider-specific
        transport decoders remain available for future streaming work but
        are not on the critical path.
        """
        if request.provider != self.provider:
            raise ValueError(f"runtime provider mismatch: {request.provider}")
        await self.start()

        prompt = next(
            (m.get("content", "") for m in reversed(request.messages)
             if m.get("role") == "user"), ""
        )
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("execution requires a non-empty user message")

        async with self._lock:
            seq = 0
            yield StreamEvent(self.provider, request.request_id,
                              EventType.REQUEST_INTERCEPTED, seq,
                              metadata={"transport": "dom"})
            seq += 1

            # Snapshot current number of assistant bubbles
            before = await self._assistant_count()

            # Submit
            try:
                await self._page.bring_to_front()
                box = await self._prompt_textbox()
                await box.fill(prompt)
                await box.press("Enter")
            except Exception as exc:
                yield StreamEvent(self.provider, request.request_id,
                                  EventType.STREAM_FAILED, seq,
                                  metadata={"reason": f"submit_failed: {exc}"})
                return

            yield StreamEvent(self.provider, request.request_id,
                              EventType.STREAM_STARTED, seq,
                              metadata={"transport": "dom"})
            seq += 1

            # Wait for a NEW assistant bubble
            text = ""
            stable_reads = 0
            for _ in range(120):  # up to 60s
                await asyncio.sleep(0.5)
                count = await self._assistant_count()
                if count <= before:
                    continue
                current = await self._read_last_assistant_text()
                if current and current == text and len(current) > 0:
                    stable_reads += 1
                    if stable_reads >= 2:
                        break
                else:
                    stable_reads = 0
                    text = current

            if not text:
                yield StreamEvent(self.provider, request.request_id,
                                  EventType.STREAM_FAILED, seq,
                                  metadata={"reason": "no assistant reply observed"})
                return

            yield StreamEvent(self.provider, request.request_id,
                              EventType.STREAM_DELTA, seq, delta=text)
            seq += 1
            yield StreamEvent(self.provider, request.request_id,
                              EventType.STREAM_COMPLETED, seq,
                              finish_reason="stop")
            return

    async def _assistant_count(self) -> int:
        sels = ['.ds-markdown', '[data-message-author-role="assistant"]',
                '.model-response-text', 'message-content']
        for s in sels:
            try:
                n = await self._page.locator(s).count()
                if n > 0:
                    return n
            except Exception:
                continue
        return 0

    async def _read_last_assistant_text(self) -> str:
        sels = ['.ds-markdown', '.ds-markdown--block',
                '[data-message-author-role="assistant"]',
                '.model-response-text', 'message-content']
        best = ""
        for s in sels:
            try:
                loc = self._page.locator(s)
                n = await loc.count()
                if n == 0:
                    continue
                txt = (await loc.nth(n - 1).inner_text()).strip()
                if len(txt) > len(best):
                    best = txt
            except Exception:
                continue
        return best


    async def close(self) -> None:
        self._started = False
        if self._owns_context and self._context is not None:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._owns_browser and self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self._pw = self._browser = self._context = self._page = None
        self._owns_browser = self._owns_context = False
