"""Shared browser runtime for ChatGPT, Gemini and DeepSeek.

Claude intentionally does not use this module. Claude's dedicated transport is
left untouched because it is the known-good reference implementation.
"""
from __future__ import annotations

import asyncio
import base64
import json
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


class NonClaudeNetworkCapture:
    """Capture the provider POST response after prompt submission.

    Multiple matching POSTs can occur for one UI action (for example a
    response request plus ancillary provider activity). We therefore inspect
    every matching completed body and select the first body that the
    provider-specific parser can identify as an actual answer. This prevents
    chat titles/metadata from being mistaken for assistant output.
    """

    def __init__(self, page: Any, spec: WebProviderSpec, parser: Callable[[str], str]) -> None:
        self.page = page
        self.spec = spec
        self.parser = parser
        self._cdp: Any | None = None
        self._candidate_ids: set[str] = set()
        self._seen_ids: set[str] = set()
        self._status_by_id: dict[str, int] = {}
        self._content_type_by_id: dict[str, str] = {}
        self._answer: tuple[str, int, str, str] | None = None
        self._error: str | None = None
        self._event = asyncio.Event()

    @staticmethod
    def _matches(url: str, markers: tuple[str, ...]) -> bool:
        lower = (url or "").lower()
        return any(marker.lower() in lower for marker in markers)

    def _on_request(self, event: dict[str, Any]) -> None:
        request = event.get("request") or {}
        method = str(request.get("method") or "").upper()
        url = str(request.get("url") or "")
        if method != "POST":
            return
        if not self._matches(url, self.spec.response_markers + self.spec.request_markers):
            return
        request_id = event.get("requestId")
        if request_id:
            self._candidate_ids.add(str(request_id))

    def _on_response(self, event: dict[str, Any]) -> None:
        request_id = str(event.get("requestId") or "")
        if request_id not in self._candidate_ids:
            return
        response = event.get("response") or {}
        self._status_by_id[request_id] = int(response.get("status", 0))
        headers = response.get("headers") or {}
        self._content_type_by_id[request_id] = str(
            headers.get("content-type") or headers.get("Content-Type") or ""
        ).lower()

    async def _on_finished(self, event: dict[str, Any]) -> None:
        request_id = str(event.get("requestId") or "")
        if request_id not in self._candidate_ids or request_id in self._seen_ids:
            return
        self._seen_ids.add(request_id)
        try:
            result = await self._cdp.send("Network.getResponseBody", {"requestId": request_id})
            body = str(result.get("body", ""))
            if result.get("base64Encoded"):
                body = base64.b64decode(body).decode("utf-8", errors="replace")
            if not body.strip():
                return
            text = self.parser(body)
            status = self._status_by_id.get(request_id, 0)
            content_type = self._content_type_by_id.get(request_id, "")
            if status >= 400:
                if status in {401, 403}:
                    self._error = f"SESSION:{status}"
                elif self._error is None:
                    self._error = f"HTTP:{status}"
                self._event.set()
                return
            if text.strip():
                self._answer = (text.strip(), status, content_type, request_id)
                self._event.set()
        except Exception as exc:
            self._error = f"provider response body capture failed: {exc}"
            self._event.set()

    def _on_failed(self, event: dict[str, Any]) -> None:
        request_id = str(event.get("requestId") or "")
        if request_id not in self._candidate_ids:
            return
        self._error = f"provider network request failed: {event.get('errorText', 'unknown error')}"
        self._event.set()

    async def __aenter__(self) -> "NonClaudeNetworkCapture":
        self._cdp = await self.page.context.new_cdp_session(self.page)
        await self._cdp.send(
            "Network.enable",
            {"maxTotalBufferSize": 50 * 1024 * 1024, "maxResourceBufferSize": 10 * 1024 * 1024},
        )
        try:
            await self._cdp.send("Network.setBypassServiceWorker", {"bypass": True})
        except Exception:
            pass
        self._cdp.on("Network.requestWillBeSent", self._on_request)
        self._cdp.on("Network.responseReceived", self._on_response)
        self._cdp.on("Network.loadingFinished", lambda event: asyncio.create_task(self._on_finished(event)))
        self._cdp.on("Network.loadingFailed", self._on_failed)
        return self

    async def wait(self, timeout: float = 120.0) -> tuple[int, str, str]:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            if not self._candidate_ids:
                raise TimeoutError(f"{self.spec.provider} provider POST was not observed")
            raise TimeoutError(f"{self.spec.provider} provider answer response timed out")
        if self._answer is not None:
            text, status, content_type, _ = self._answer
            return status, content_type, text
        if self._error == "SESSION:401" or self._error == "SESSION:403":
            raise WebProviderSessionError(f"{self.spec.provider} session expired")
        raise RuntimeError(self._error or f"{self.spec.provider} response did not contain an assistant answer")

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

    def __init__(
        self,
        spec: WebProviderSpec,
        session_path: str | None,
        cdp_url: str | None,
        headless: bool,
        parser: Callable[[str], str],
    ) -> None:
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
            pages = [p for p in self._context.pages if host == urlparse(p.url or "").netloc]
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
                str(profile), headless=False if interactive else self.headless
            )
            self._owns_context = True
            self._owns_browser = False
            pages = list(self._context.pages)
            self._page = pages[-1] if pages else await self._context.new_page()
        current_host = urlparse(self._page.url or "").netloc
        home_host = urlparse(self.spec.home_url).netloc
        if current_host != home_host:
            await self._page.goto(self.spec.home_url, wait_until="domcontentloaded", timeout=30_000)

    def _is_login_page(self) -> bool:
        url = (self._page.url or "").lower()
        return any(marker.lower() in url for marker in self.spec.login_markers)

    async def start(self) -> None:
        if self._started:
            return
        await self._ensure_page(interactive=False)
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
            count = await locator.count()
            for index in range(count - 1, -1, -1):
                candidate = locator.nth(index)
                try:
                    if await candidate.is_visible() and await candidate.is_editable():
                        return candidate
                except Exception:
                    continue
        raise WebProviderSessionError(f"{self.provider} composer textbox is not available")

    async def execute(self, request: ProviderExecutionRequest) -> AsyncIterator[StreamEvent]:
        if request.provider != self.provider:
            raise ValueError(f"runtime provider mismatch: {request.provider}")
        await self.start()
        prompt = next((m.get("content", "") for m in reversed(request.messages) if m.get("role") == "user"), "")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("execution requires a non-empty user message")
        async with self._lock:
            sequence = 0
            async with NonClaudeNetworkCapture(self._page, self.spec, self.parser) as capture:
                yield StreamEvent(self.provider, request.request_id, EventType.REQUEST_INTERCEPTED, sequence, metadata={"transport": "chromium-cdp-network", "correlation": "provider-post-and-parser"})
                sequence += 1
                try:
                    await self._page.bring_to_front()
                    textbox = await self._prompt_textbox()
                    await textbox.fill(prompt)
                    await textbox.press("Enter")
                except Exception as exc:
                    yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"reason": f"prompt_submission_failed: {exc}"})
                    return
                try:
                    status, content_type, text = await capture.wait()
                except WebProviderSessionError:
                    yield StreamEvent(self.provider, request.request_id, EventType.SESSION_EXPIRED, sequence, metadata={"reason": "provider_session_expired"})
                    sequence += 1
                    yield StreamEvent(self.provider, request.request_id, EventType.SESSION_RECOVERY_REQUIRED, sequence, metadata={"reason": "provider_authentication_failed"})
                    return
                except TimeoutError as exc:
                    yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"reason": str(exc)})
                    return
                except Exception as exc:
                    yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"reason": str(exc)})
                    return
                if status >= 400:
                    yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"status": status})
                    return
                yield StreamEvent(self.provider, request.request_id, EventType.STREAM_STARTED, sequence, metadata={"transport": "chromium-cdp-network", "content_type": content_type})
                sequence += 1
                yield StreamEvent(self.provider, request.request_id, EventType.STREAM_DELTA, sequence, delta=text)
                sequence += 1
                yield StreamEvent(self.provider, request.request_id, EventType.STREAM_COMPLETED, sequence, finish_reason="stop")

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
