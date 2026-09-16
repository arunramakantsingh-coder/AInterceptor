"""Shared browser-backed transport runtime for non-Claude web providers.

Browser automation is limited to session establishment and prompt submission.
Provider responses are read from Chromium network responses, never from the
rendered DOM. Provider-specific classes supply URL matching and normalization.
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable

from app.interception.contracts import EventType, ProviderExecutionRequest, StreamEvent
from app.interception.runtime import ProviderRuntime

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None


class WebProviderSessionError(RuntimeError):
    """The provider web session is unavailable or unauthenticated."""


@dataclass(frozen=True)
class WebProviderSpec:
    provider: str
    home_url: str
    login_markers: tuple[str, ...]
    response_markers: tuple[str, ...]
    response_content_types: tuple[str, ...] = ("text/event-stream", "application/json", "text/plain")
    default_model: str | None = None


class WebNetworkCapture:
    """Capture one provider response at the Chromium transport boundary."""

    def __init__(self, page: Any, spec: WebProviderSpec) -> None:
        self.page = page
        self.spec = spec
        self._response: Any | None = None
        self._event = asyncio.Event()
        self._response_error: str | None = None

    def _matches(self, response: Any) -> bool:
        url = (response.url or "").lower()
        if not any(marker.lower() in url for marker in self.spec.response_markers):
            return False
        content_type = (response.headers.get("content-type") or "").lower()
        return not self.spec.response_content_types or any(
            marker in content_type for marker in self.spec.response_content_types
        )

    def _on_response(self, response: Any) -> None:
        if self._response is None and self._matches(response):
            self._response = response
            self._event.set()

    async def __aenter__(self) -> "WebNetworkCapture":
        self.page.on("response", self._on_response)
        return self

    async def wait(self, timeout: float = 120.0) -> tuple[int, str, str]:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"{self.spec.provider} transport response timed out")
        if self._response is None:
            raise RuntimeError(self._response_error or "provider response not captured")
        status = self._response.status
        content_type = self._response.headers.get("content-type", "")
        body = await self._response.text()
        return status, content_type, body

    async def __aexit__(self, *args: Any) -> None:
        try:
            self.page.remove_listener("response", self._on_response)
        except Exception:
            pass


def _best_text(value: Any) -> str:
    """Find a likely assistant-text field without reading page DOM."""
    candidates: list[str] = []

    def visit(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                lk = str(k).lower()
                if isinstance(v, str) and v.strip() and lk in {
                    "content", "text", "completion", "response", "answer", "message",
                }:
                    candidates.append(v)
                else:
                    visit(v, lk)
        elif isinstance(node, list):
            for item in node:
                visit(item, key)

    visit(value)
    candidates = [item for item in candidates if len(item.strip()) > 0]
    if not candidates:
        return ""
    # Prefer the longest plausible natural-language field while avoiding
    # giant serialized request/config blobs.
    plausible = [item for item in candidates if len(item) < 200_000]
    return max(plausible or candidates, key=len).strip()


def parse_chatgpt(body: str) -> str:
    parts: list[str] = []
    for line in body.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        message = obj.get("message") if isinstance(obj, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, dict):
            values = content.get("parts")
            if isinstance(values, list):
                parts.extend(str(x) for x in values if isinstance(x, str))
            elif isinstance(content.get("text"), str):
                parts.append(content["text"])
        elif isinstance(obj, dict):
            text = _best_text(obj)
            if text:
                parts.append(text)
    return "".join(parts).strip()


def parse_deepseek(body: str) -> str:
    parts: list[str] = []
    for line in body.splitlines():
        raw = line.strip()
        if raw.startswith("data:"):
            raw = raw[5:].strip()
        if not raw or raw == "[DONE]":
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            for key in ("response", "content", "text", "delta"):
                value = obj.get(key)
                if isinstance(value, str):
                    parts.append(value)
                elif isinstance(value, dict):
                    nested = value.get("content") or value.get("text")
                    if isinstance(nested, str):
                        parts.append(nested)
    if parts:
        return "".join(parts).strip()
    return _best_text(_safe_json(body)).strip()


def parse_gemini(body: str) -> str:
    # Gemini Web uses length-prefixed JSON frames. We intentionally keep this
    # parser tolerant because the private Web framing can drift between builds.
    text = body.lstrip()
    if text.startswith(")]}'"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    candidates: list[str] = []
    pos = 0
    while pos < len(text):
        match = re.match(r"(\d+)\n", text[pos:])
        if not match:
            break
        length = int(match.group(1))
        start = pos + match.end()
        frame = text[start : start + length]
        pos = start + length
        try:
            obj = json.loads(frame)
        except json.JSONDecodeError:
            continue
        value = _best_text(obj)
        if value:
            candidates.append(value)
    if candidates:
        return max(candidates, key=len)
    return _best_text(_safe_json(text)).strip()


def _safe_json(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


class BrowserWebRuntime(ProviderRuntime):
    """Reusable browser/session/transport boundary for a web provider."""

    def __init__(self, spec: WebProviderSpec, session_path: str | None = None,
                 cdp_url: str | None = None, headless: bool = False,
                 parser: Callable[[str], str] = parse_chatgpt) -> None:
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
            self._owns_browser = False
            self._owns_context = False
            pages = [p for p in self._context.pages if self.spec.home_url.split("/")[2] in (p.url or "")]
            self._page = pages[-1] if pages else await self._context.new_page()
        elif self.session_path and pathlib.Path(self.session_path).exists():
            self._browser = await self._pw.chromium.launch(headless=self.headless)
            self._context = await self._browser.new_context(storage_state=self.session_path)
            self._owns_browser = True
            self._owns_context = True
            self._page = await self._context.new_page()
        else:
            profile = pathlib.Path(".ainterceptor") / "profiles" / self.provider
            profile.mkdir(parents=True, exist_ok=True)
            self._context = await self._pw.chromium.launch_persistent_context(
                str(profile), headless=False if interactive else self.headless,
            )
            self._owns_context = True
            self._owns_browser = False
            pages = list(self._context.pages)
            self._page = pages[-1] if pages else await self._context.new_page()

        if self._page.url != self.spec.home_url:
            await self._page.goto(self.spec.home_url, wait_until="domcontentloaded", timeout=30_000)

    def _is_login_page(self) -> bool:
        url = (self._page.url or "").lower()
        return any(marker.lower() in url for marker in self.spec.login_markers)

    async def start(self) -> None:
        if self._started:
            return
        await self._ensure_page(interactive=False)
        if self._is_login_page():
            raise WebProviderSessionError(
                f"{self.provider} session is not authenticated; use provider login"
            )
        self._started = True

    async def login(self) -> None:
        """Open an isolated visible provider session and wait for manual login."""
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

    async def execute(self, request: ProviderExecutionRequest) -> AsyncIterator[StreamEvent]:
        if request.provider != self.provider:
            raise ValueError(f"runtime provider mismatch: {request.provider}")
        await self.start()
        prompt = next((m.get("content", "") for m in reversed(request.messages) if m.get("role") == "user"), "")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("execution requires a non-empty user message")

        async with self._lock:
            sequence = 0
            async with WebNetworkCapture(self._page, self.spec) as capture:
                yield StreamEvent(self.provider, request.request_id, EventType.REQUEST_INTERCEPTED, sequence, metadata={"transport": "playwright-network"})
                sequence += 1
                textbox = self._page.get_by_role("textbox").last
                await textbox.fill(prompt)
                await textbox.press("Enter")
                try:
                    status, content_type, body = await capture.wait()
                except Exception as exc:
                    yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"reason": str(exc)})
                    return

                if status in {401, 403}:
                    yield StreamEvent(self.provider, request.request_id, EventType.SESSION_EXPIRED, sequence, metadata={"status": status})
                    sequence += 1
                    yield StreamEvent(self.provider, request.request_id, EventType.SESSION_RECOVERY_REQUIRED, sequence, metadata={"reason": "provider_authentication_failed"})
                    return
                if status >= 400:
                    yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"status": status})
                    return
                yield StreamEvent(self.provider, request.request_id, EventType.STREAM_STARTED, sequence, metadata={"transport": "playwright-network", "content_type": content_type})
                sequence += 1
                text = self.parser(body)
                if not text:
                    yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"reason": "provider_response_parser_returned_empty"})
                    return
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
