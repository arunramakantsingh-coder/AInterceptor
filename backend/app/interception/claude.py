"""Claude web provider runtime using browser transport interception."""
from __future__ import annotations

import asyncio
import os
import pathlib
import uuid
from typing import AsyncIterator

from app.interception.claude_transport import ClaudeCDPTransport, ClaudeSSEParser
from app.interception.contracts import EventType, ProviderExecutionRequest, StreamEvent
from app.interception.runtime import ProviderRuntime
from app.providers.base import Chunk

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None


class ClaudeSessionError(RuntimeError):
    """The provider web session cannot be used for an execution."""


class ClaudeTransportError(RuntimeError):
    """The provider communication transport failed."""


class ClaudeRuntime(ProviderRuntime):
    """Provider-local Claude browser/runtime implementation.

    Playwright is used only to establish/maintain the authenticated web
    session and submit a user-visible prompt. Response extraction happens
    through Chromium CDP Network events, never through the rendered DOM.

    Two session modes are supported:
      * storage-state mode: launch a dedicated browser from a Playwright
        storage-state file (legacy/default behaviour).
      * CDP attach mode: attach to an already authenticated Chromium instance
        exposed through AINTERCEPTOR_CLAUDE_CDP_URL. The externally-owned
        browser/context is never closed by this runtime.
    """

    provider = "claude"

    def __init__(
        self,
        session_path: str | None = None,
        headless: bool = True,
        cdp_url: str | None = None,
    ):
        self.session_path = session_path
        self.headless = headless
        self.cdp_url = cdp_url or os.getenv("AINTERCEPTOR_CLAUDE_CDP_URL")
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._cdp = None
        self._transport: ClaudeCDPTransport | None = None
        self._started = False
        self._owns_browser = False
        self._owns_context = False
        self._execute_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._started:
            return
        if async_playwright is None:
            raise RuntimeError("playwright not installed")

        self._pw = await async_playwright().start()

        if self.cdp_url:
            self._browser = await self._pw.chromium.connect_over_cdp(self.cdp_url)
            self._owns_browser = False
            self._owns_context = False
            contexts = self._browser.contexts
            if not contexts:
                raise ClaudeSessionError("CDP browser has no browser context")
            self._context = contexts[0]

            claude_pages = [
                page
                for page in self._context.pages
                if "claude.ai" in (page.url or "").lower()
            ]
            self._page = claude_pages[-1] if claude_pages else None
            if self._page is None:
                self._page = await self._context.new_page()
                await self._page.goto(
                    "https://claude.ai/",
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
        else:
            if not self.session_path:
                await self._pw.stop()
                self._pw = None
                raise ClaudeSessionError(
                    "Claude storage state is not configured; set "
                    "AINTERCEPTOR_CLAUDE_CDP_URL or provide session_path"
                )
            if not pathlib.Path(self.session_path).exists():
                await self._pw.stop()
                self._pw = None
                raise ClaudeSessionError("Claude storage state file does not exist")

            self._browser = await self._pw.chromium.launch(headless=self.headless)
            self._owns_browser = True
            self._context = await self._browser.new_context(
                storage_state=self.session_path,
                service_workers="block",
            )
            self._owns_context = True
            self._page = await self._context.new_page()
            await self._page.goto(
                "https://claude.ai/",
                wait_until="domcontentloaded",
                timeout=30_000,
            )

        if self._page is None:
            raise ClaudeSessionError("Claude browser has no usable page")
        if "/login" in self._page.url or "/auth" in self._page.url:
            raise ClaudeSessionError("Claude session is expired or not authenticated")

        self._cdp = await self._context.new_cdp_session(self._page)
        self._transport = ClaudeCDPTransport(self._cdp)
        await self._transport.start()
        self._started = True

    async def execute(
        self, request: ProviderExecutionRequest
    ) -> AsyncIterator[StreamEvent]:
        if request.provider != self.provider:
            raise ValueError(f"runtime provider mismatch: {request.provider}")
        if not self._started or self._page is None or self._transport is None:
            await self.start()

        prompt = self._last_user_prompt(request.messages)
        async with self._execute_lock:
            self._transport.prepare(request.request_id)
            try:
                textbox = self._page.get_by_role("textbox").last
                await textbox.fill(prompt)
                await textbox.press("Enter")
            except Exception:
                yield StreamEvent(
                    provider=self.provider,
                    request_id=request.request_id,
                    event_type=EventType.SESSION_RECOVERY_REQUIRED,
                    sequence=0,
                    metadata={"reason": "prompt_submission_failed"},
                )
                yield StreamEvent(
                    provider=self.provider,
                    request_id=request.request_id,
                    event_type=EventType.STREAM_FAILED,
                    sequence=1,
                    metadata={"reason": "provider_ui_submission_failed"},
                )
                return

            sequence = 0
            parser = ClaudeSSEParser()
            response_started = False
            terminal = False
            pending_finish_reason: str | None = None

            def emit_parsed(parsed: object) -> list[StreamEvent]:
                nonlocal sequence, terminal, pending_finish_reason
                emitted: list[StreamEvent] = []
                delta = getattr(parsed, "delta", "")
                finish_reason = getattr(parsed, "finish_reason", None)
                done = bool(getattr(parsed, "done", False))
                if delta:
                    emitted.append(
                        StreamEvent(
                            provider=self.provider,
                            request_id=request.request_id,
                            event_type=EventType.STREAM_DELTA,
                            sequence=sequence,
                            delta=delta,
                        )
                    )
                    sequence += 1
                if finish_reason:
                    pending_finish_reason = finish_reason
                if done:
                    emitted.append(
                        StreamEvent(
                            provider=self.provider,
                            request_id=request.request_id,
                            event_type=EventType.STREAM_COMPLETED,
                            sequence=sequence,
                            finish_reason=pending_finish_reason or "stop",
                        )
                    )
                    sequence += 1
                    terminal = True
                return emitted

            try:
                async for signal in self._transport.signals(timeout=120.0):
                    if signal.kind == "request_intercepted":
                        yield StreamEvent(
                            provider=self.provider,
                            request_id=request.request_id,
                            event_type=EventType.REQUEST_INTERCEPTED,
                            sequence=sequence,
                            metadata={"transport": "chromium-cdp-network"},
                        )
                        sequence += 1
                        continue

                    if signal.kind == "response_started":
                        status = int((signal.payload or {}).get("status", 0))
                        content_type = (signal.payload or {}).get("content_type", "")
                        if status in {401, 403}:
                            yield StreamEvent(
                                provider=self.provider,
                                request_id=request.request_id,
                                event_type=EventType.SESSION_EXPIRED,
                                sequence=sequence,
                                metadata={"status": status},
                            )
                            sequence += 1
                            yield StreamEvent(
                                provider=self.provider,
                                request_id=request.request_id,
                                event_type=EventType.SESSION_RECOVERY_REQUIRED,
                                sequence=sequence,
                                metadata={"reason": "provider_authentication_failed"},
                            )
                            return
                        if status >= 400:
                            yield StreamEvent(
                                provider=self.provider,
                                request_id=request.request_id,
                                event_type=EventType.STREAM_FAILED,
                                sequence=sequence,
                                metadata={"status": status},
                            )
                            return
                        if "text/event-stream" not in content_type.lower():
                            yield StreamEvent(
                                provider=self.provider,
                                request_id=request.request_id,
                                event_type=EventType.STREAM_FAILED,
                                sequence=sequence,
                                metadata={"reason": "response_not_sse"},
                            )
                            return
                        yield StreamEvent(
                            provider=self.provider,
                            request_id=request.request_id,
                            event_type=EventType.STREAM_STARTED,
                            sequence=sequence,
                            metadata={
                                "transport": "chromium-cdp-network",
                                "content_type": "text/event-stream",
                            },
                        )
                        sequence += 1
                        response_started = True
                        continue

                    if signal.kind == "data":
                        for parsed in parser.feed(signal.payload):
                            for event in emit_parsed(parsed):
                                yield event
                            if terminal:
                                break
                        if terminal:
                            break
                        continue

                    if signal.kind == "failed":
                        raise ClaudeTransportError(str(signal.payload))

                    if signal.kind == "finished":
                        for parsed in parser.finish():
                            for event in emit_parsed(parsed):
                                yield event
                            if terminal:
                                break
                        if not terminal:
                            yield StreamEvent(
                                provider=self.provider,
                                request_id=request.request_id,
                                event_type=EventType.STREAM_COMPLETED,
                                sequence=sequence,
                                finish_reason=pending_finish_reason or "stop",
                            )
                        terminal = True
                        break

            except asyncio.TimeoutError:
                yield StreamEvent(
                    provider=self.provider,
                    request_id=request.request_id,
                    event_type=EventType.STREAM_FAILED,
                    sequence=sequence,
                    metadata={"reason": "stream_timeout"},
                )
            except ClaudeTransportError as exc:
                yield StreamEvent(
                    provider=self.provider,
                    request_id=request.request_id,
                    event_type=EventType.STREAM_FAILED,
                    sequence=sequence,
                    metadata={"reason": str(exc)},
                )
            finally:
                if response_started and not terminal:
                    yield StreamEvent(
                        provider=self.provider,
                        request_id=request.request_id,
                        event_type=EventType.STREAM_FAILED,
                        sequence=sequence + 1,
                        metadata={"reason": "stream_terminated_without_terminal_event"},
                    )

    async def close(self) -> None:
        self._started = False
        if self._cdp is not None:
            try:
                await self._cdp.detach()
            except Exception:
                pass
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
        self._cdp = None
        self._transport = None
        self._page = None
        self._context = None
        self._browser = None
        self._pw = None
        self._owns_browser = False
        self._owns_context = False

    @staticmethod
    def _last_user_prompt(messages: list[dict]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str) and content.strip():
                    return content
        raise ValueError("Claude execution requires a non-empty user message")


class ClaudeInterceptor:
    """Compatibility facade for the legacy ProviderAdapter."""

    def __init__(
        self,
        session_path: str | None = None,
        headless: bool = True,
        cdp_url: str | None = None,
    ):
        self._runtime = ClaudeRuntime(
            session_path=session_path,
            headless=headless,
            cdp_url=cdp_url,
        )

    async def __aenter__(self):
        await self._runtime.start()
        return self

    async def __aexit__(self, *args):
        await self._runtime.close()

    async def stream(self, prompt: str) -> AsyncIterator[Chunk]:
        request_id = str(uuid.uuid4())
        request = ProviderExecutionRequest(
            provider="claude",
            request_id=request_id,
            messages=[{"role": "user", "content": prompt}],
        )
        async for event in self._runtime.execute(request):
            if event.event_type is EventType.STREAM_DELTA:
                yield Chunk(provider="claude", delta=event.delta or "")
            elif event.event_type is EventType.STREAM_COMPLETED:
                yield Chunk(
                    provider="claude",
                    delta="",
                    finish_reason=event.finish_reason or "stop",
                )
