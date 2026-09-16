"""Shared browser-backed transport runtime for non-Claude web providers.

Browser automation is limited to session establishment and prompt submission.
Provider responses are captured at the Chromium CDP Network boundary, never
from rendered provider DOM. Provider-specific classes supply request matching
and response normalization.
"""
from __future__ import annotations

import asyncio
import base64
import json
import pathlib
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable
from urllib.parse import urlparse

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
    request_markers: tuple[str, ...] = ()
    composer_selectors: tuple[str, ...] = (
        "textarea",
        '[contenteditable="true"]',
        '[role="textbox"]',
    )


class WebNetworkCapture:
    """Correlate one prompt with its Chromium CDP Network response."""

    def __init__(self, page: Any, spec: WebProviderSpec) -> None:
        self.page = page
        self.spec = spec
        self._cdp: Any | None = None
        self._request_id: str | None = None
        self._status: int = 0
        self._content_type = ""
        self._body: str | None = None
        self._error: str | None = None
        self._event = asyncio.Event()

    @staticmethod
    def _matches(url: str, markers: tuple[str, ...]) -> bool:
        lower = (url or "").lower()
        return any(marker.lower() in lower for marker in markers)

    def _on_request(self, event: dict[str, Any]) -> None:
        if self._request_id is not None:
            return
        request = event.get("request") or {}
        url = request.get("url", "")
        if self._matches(url, self.spec.response_markers + self.spec.request_markers):
            self._request_id = event.get("requestId")

    def _on_response(self, event: dict[str, Any]) -> None:
        if self._request_id is None or event.get("requestId") != self._request_id:
            return
        response = event.get("response") or {}
        self._status = int(response.get("status", 0))
        headers = response.get("headers") or {}
        self._content_type = str(headers.get("content-type") or headers.get("Content-Type") or "").lower()
        if self.spec.response_content_types and not any(marker in self._content_type for marker in self.spec.response_content_types):
            self._error = f"unexpected provider response content-type: {self._content_type or '<empty>'}"
            self._event.set()

    async def _on_finished(self, event: dict[str, Any]) -> None:
        if self._request_id is None or event.get("requestId") != self._request_id:
            return
        try:
            result = await self._cdp.send("Network.getResponseBody", {"requestId": self._request_id})
            body = str(result.get("body", ""))
            if result.get("base64Encoded"):
                body = base64.b64decode(body).decode("utf-8", errors="replace")
            self._body = body
        except Exception as exc:
            self._error = f"provider response body capture failed: {exc}"
        finally:
            self._event.set()

    def _on_failed(self, event: dict[str, Any]) -> None:
        if self._request_id is None or event.get("requestId") != self._request_id:
            return
        self._error = f"provider network request failed: {event.get('errorText', 'unknown error')}"
        self._event.set()

    async def __aenter__(self) -> "WebNetworkCapture":
        self._cdp = await self.page.context.new_cdp_session(self.page)
        await self._cdp.send("Network.enable", {"maxTotalBufferSize": 50 * 1024 * 1024, "maxResourceBufferSize": 10 * 1024 * 1024})
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
            if self._request_id is None:
                raise TimeoutError(f"{self.spec.provider} provider request was not observed")
            raise TimeoutError(f"{self.spec.provider} transport response timed out")
        if self._error:
            raise RuntimeError(self._error)
        if self._request_id is None:
            raise RuntimeError(f"{self.spec.provider} provider request was not observed")
        if self._body is None:
            raise RuntimeError(f"{self.spec.provider} provider response body was empty or unavailable")
        return self._status, self._content_type, self._body

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


def _walk_strings(value: Any, wanted: set[str]) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, str) and str(key).lower() in wanted and child.strip():
                found.append(child)
            else:
                found.extend(_walk_strings(child, wanted))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_strings(child, wanted))
    return found


def _best_text(value: Any) -> str:
    candidates = _walk_strings(value, {"content", "text", "completion", "response", "answer", "message", "parts"})
    candidates = [item.strip() for item in candidates if item.strip()]
    plausible = [item for item in candidates if len(item) < 200_000]
    return max(plausible or candidates, key=len, default="")


def _json_objects(body: str) -> list[Any]:
    objects: list[Any] = []
    text = body.lstrip()
    if text.startswith(")]}'"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    for line in text.splitlines():
        raw = line.strip()
        if raw.startswith("data:"):
            raw = raw[5:].strip()
        if not raw or raw == "[DONE]":
            continue
        try:
            objects.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    if objects:
        return objects
    try:
        return [json.loads(text)]
    except json.JSONDecodeError:
        return []


def parse_chatgpt(body: str) -> str:
    parts: list[str] = []
    for obj in _json_objects(body):
        if not isinstance(obj, dict):
            continue
        message = obj.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, dict) and isinstance(content.get("parts"), list):
            parts.extend(str(x) for x in content["parts"] if isinstance(x, str))
        elif isinstance(content, str):
            parts.append(content)
        else:
            text = _best_text(obj)
            if text:
                parts.append(text)
    return "".join(parts).strip()


def parse_deepseek(body: str) -> str:
    parts: list[str] = []
    for obj in _json_objects(body):
        if not isinstance(obj, dict):
            continue
        for key in ("response", "content", "text", "delta"):
            value = obj.get(key)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, dict):
                nested = value.get("content") or value.get("text") or value.get("response")
                if isinstance(nested, str):
                    parts.append(nested)
        choices = obj.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta")
                if isinstance(delta, dict):
                    text = delta.get("content") or delta.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                message = choice.get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    parts.append(message["content"])
    return "".join(parts).strip() or _best_text(_json_objects(body)).strip()


def parse_gemini(body: str) -> str:
    """Parse Gemini StreamGenerate's wrb.fr response frames."""
    candidates: list[str] = []
    for obj in _json_objects(body):
        if not isinstance(obj, list) or len(obj) < 3 or obj[0] != "wrb.fr":
            continue
        inner_raw = obj[2]
        if not isinstance(inner_raw, str):
            continue
        try:
            inner = json.loads(inner_raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(inner, list) or len(inner) <= 4 or not inner[4]:
            continue
        for part in inner[4]:
            if not isinstance(part, list) or len(part) <= 1 or not isinstance(part[1], list):
                continue
            for text in part[1]:
                if isinstance(text, str) and text.strip():
                    candidates.append(text)
    if candidates:
        return max(candidates, key=len).strip()
    return _best_text(_json_objects(body)).strip()


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
            self._context = await self._pw.chromium.launch_persistent_context(str(profile), headless=False if interactive else self.headless)
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
            async with WebNetworkCapture(self._page, self.spec) as capture:
                yield StreamEvent(self.provider, request.request_id, EventType.REQUEST_INTERCEPTED, sequence, metadata={"transport": "cdp-network"})
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
                yield StreamEvent(self.provider, request.request_id, EventType.STREAM_STARTED, sequence, metadata={"transport": "cdp-network", "content_type": content_type})
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
