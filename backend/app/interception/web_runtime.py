"""Shared browser-backed transport runtime for non-Claude web providers.

Browser automation is limited to session establishment and prompt submission.
Provider responses are read from Chromium network responses, never from the
rendered DOM. Provider-specific classes supply URL matching and normalization.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import pathlib
import re
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


class WebNetworkCapture:
    """Legacy Playwright response capture used only when CDP is unavailable."""
    def __init__(self, page: Any, spec: WebProviderSpec) -> None:
        self.page, self.spec = page, spec
        self._response: Any | None = None
        self._event = asyncio.Event()
    def _matches(self, response: Any) -> bool:
        url = (response.url or "").lower()
        if not any(m.lower() in url for m in self.spec.response_markers): return False
        ct = (response.headers.get("content-type") or "").lower()
        return not self.spec.response_content_types or any(m in ct for m in self.spec.response_content_types)
    def _on_response(self, response: Any) -> None:
        if self._response is None and self._matches(response): self._response, _ = response, self._event.set()
    async def __aenter__(self) -> "WebNetworkCapture":
        self.page.on("response", self._on_response); return self
    async def wait(self, timeout: float = 120.0) -> tuple[int, str, str]:
        try: await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError as exc: raise TimeoutError(f"{self.spec.provider} transport response timed out") from exc
        if self._response is None: raise RuntimeError("provider response not captured")
        return self._response.status, self._response.headers.get("content-type", ""), await self._response.text()
    async def __aexit__(self, *args: Any) -> None:
        try: self.page.remove_listener("response", self._on_response)
        except Exception: pass


def _best_text(value: Any) -> str:
    candidates: list[str] = []
    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str) and v.strip() and str(k).lower() in {"content", "text", "completion", "response", "answer", "message"}: candidates.append(v)
                else: visit(v)
        elif isinstance(node, list):
            for item in node: visit(item)
    visit(value)
    candidates = [x.strip() for x in candidates if x.strip()]
    plausible = [x for x in candidates if len(x) < 200_000]
    return max(plausible or candidates, key=len, default="")


def parse_chatgpt(body: str) -> str:
    parts: list[str] = []
    for line in body.splitlines():
        if not line.startswith("data:"): continue
        payload = line[5:].strip()
        if payload == "[DONE]": continue
        try: obj = json.loads(payload)
        except json.JSONDecodeError: continue
        if not isinstance(obj, dict): continue
        message = obj.get("message"); content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, dict):
            values = content.get("parts")
            if isinstance(values, list): parts.extend(str(x) for x in values if isinstance(x, str))
            elif isinstance(content.get("text"), str): parts.append(content["text"])
        else:
            text = _best_text(obj)
            if text: parts.append(text)
    return "".join(parts).strip()


def parse_deepseek(body: str) -> str:
    parts: list[str] = []
    for line in body.splitlines():
        raw = line.strip()
        if raw.startswith("data:"): raw = raw[5:].strip()
        if not raw or raw == "[DONE]": continue
        try: obj = json.loads(raw)
        except json.JSONDecodeError: continue
        if isinstance(obj, dict):
            for key in ("response", "content", "text", "delta"):
                value = obj.get(key)
                if isinstance(value, str): parts.append(value)
                elif isinstance(value, dict):
                    nested = value.get("content") or value.get("text")
                    if isinstance(nested, str): parts.append(nested)
            choices = obj.get("choices")
            if isinstance(choices, list):
                for choice in choices:
                    if isinstance(choice, dict):
                        delta = choice.get("delta") or choice.get("message") or choice.get("content")
                        if isinstance(delta, str): parts.append(delta)
                        elif isinstance(delta, dict):
                            value = delta.get("content") or delta.get("text")
                            if isinstance(value, str): parts.append(value)
    return "".join(parts).strip() if parts else _best_text(_safe_json(body))


def parse_gemini(body: str) -> str:
    """Parse Gemini Web StreamGenerate's wrb.fr line-delimited response."""
    texts: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if '"wrb.fr"' not in line: continue
        try:
            outer = json.loads(line)
            inner_raw = outer[0][2]
            inner = json.loads(inner_raw) if isinstance(inner_raw, str) else inner_raw
        except (json.JSONDecodeError, IndexError, TypeError, KeyError):
            continue
        if not isinstance(inner, list) or len(inner) <= 4 or not inner[4]: continue
        try:
            for part in inner[4]:
                if isinstance(part, list) and len(part) > 1 and isinstance(part[1], list):
                    for text in part[1]:
                        if isinstance(text, str) and text.strip(): texts.append(text.strip())
        except (IndexError, TypeError):
            continue
    if texts: return texts[-1]
    # Keep compatibility with alternate/older length-prefixed responses.
    return _best_text(_safe_json(body))


def _safe_json(value: str) -> Any:
    try: return json.loads(value)
    except json.JSONDecodeError: return {}


class BrowserWebRuntime(ProviderRuntime):
    """Reusable browser/session/transport boundary for a web provider."""
    def __init__(self, spec: WebProviderSpec, session_path: str | None = None, cdp_url: str | None = None,
                 headless: bool = False, parser: Callable[[str], str] = parse_chatgpt) -> None:
        self.spec, self.provider = spec, spec.provider
        self.session_path, self.cdp_url, self.headless, self.parser = session_path, cdp_url, headless, parser
        self._pw = self._browser = self._context = self._page = self._cdp = None
        self._owns_browser = self._owns_context = False
        self._started = False
        self._lock = asyncio.Lock()

    async def _ensure_page(self, interactive: bool = False) -> None:
        if async_playwright is None: raise WebProviderSessionError("playwright is not installed")
        if self._pw is None: self._pw = await async_playwright().start()
        if self.cdp_url:
            self._browser = await self._pw.chromium.connect_over_cdp(self.cdp_url)
            contexts = self._browser.contexts
            if not contexts: raise WebProviderSessionError("CDP browser has no context")
            self._context = contexts[0]; self._owns_browser = self._owns_context = False
            host = urlparse(self.spec.home_url).netloc
            pages = [p for p in self._context.pages if host == urlparse(p.url or "").netloc]
            self._page = pages[-1] if pages else await self._context.new_page()
        elif self.session_path and pathlib.Path(self.session_path).exists():
            self._browser = await self._pw.chromium.launch(headless=self.headless)
            self._context = await self._browser.new_context(storage_state=self.session_path)
            self._owns_browser = self._owns_context = True; self._page = await self._context.new_page()
        else:
            profile = pathlib.Path(".ainterceptor") / "profiles" / self.provider; profile.mkdir(parents=True, exist_ok=True)
            self._context = await self._pw.chromium.launch_persistent_context(str(profile), headless=False if interactive else self.headless)
            self._owns_context = True; self._page = self._context.pages[-1] if self._context.pages else await self._context.new_page()
        if urlparse(self._page.url or "").netloc != urlparse(self.spec.home_url).netloc:
            await self._page.goto(self.spec.home_url, wait_until="domcontentloaded", timeout=30_000)
        if self.cdp_url and self._cdp is None:
            self._cdp = await self._context.new_cdp_session(self._page)
            await self._cdp.send("Network.enable", {"maxTotalBufferSize": 20 * 1024 * 1024, "maxResourceBufferSize": 10 * 1024 * 1024})
            try: await self._cdp.send("Network.setBypassServiceWorker", {"bypass": True})
            except Exception: pass

    def _is_login_page(self) -> bool:
        url = (self._page.url or "").lower(); return any(m.lower() in url for m in self.spec.login_markers)
    async def start(self) -> None:
        if self._started: return
        await self._ensure_page(False)
        if self._is_login_page(): raise WebProviderSessionError(f"{self.provider} session is not authenticated; use provider login")
        self._started = True
    async def login(self) -> None:
        await self._ensure_page(True)
        if self._is_login_page():
            print(f"{self.provider}: browser opened. Complete login in the provider window."); print("Waiting for authenticated provider session...")
            for _ in range(180):
                await asyncio.sleep(1)
                if not self._is_login_page(): break
        if self._is_login_page(): raise WebProviderSessionError(f"{self.provider} login was not completed")
        path = self.session_path or str(pathlib.Path(".ainterceptor") / self.provider / "storage_state.json")
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True); await self._context.storage_state(path=path)
        self.session_path = path; self._started = True; print(f"{self.provider}: authenticated session saved to {path}.")

    async def _prompt_textbox(self) -> Any:
        selectors = ("textarea", '[contenteditable="true"]', '[role="textbox"]')
        for selector in selectors:
            locator = self._page.locator(selector); count = await locator.count()
            for index in range(count - 1, -1, -1):
                candidate = locator.nth(index)
                try:
                    if await candidate.is_visible() and await candidate.is_editable(): return candidate
                except Exception: pass
        raise WebProviderSessionError(f"{self.provider} composer textbox is not available")

    def _is_provider_request(self, url: str, method: str) -> bool:
        return method.upper() == "POST" and any(m.lower() in url.lower() for m in self.spec.response_markers)

    async def _execute_cdp(self, request: ProviderExecutionRequest) -> AsyncIterator[StreamEvent]:
        sequence = 0; active_request: str | None = None; response_status: int | None = None
        response_type = ""; response_url = ""; chunks: list[bytes] = []; finished = asyncio.Event(); failure: str | None = None
        request_seen = asyncio.Event()
        def on_request(params: dict[str, Any]) -> None:
            nonlocal active_request
            req = params.get("request") or {}; url = str(req.get("url") or "")
            if active_request is None and self._is_provider_request(url, str(req.get("method") or "GET")):
                active_request = str(params.get("requestId") or ""); request_seen.set()
        async def enable_stream(rid: str) -> None:
            nonlocal failure
            try:
                result = await self._cdp.send("Network.streamResourceContent", {"requestId": rid})
                buffered = result.get("bufferedData") or ""
                if buffered: chunks.append(base64.b64decode(buffered))
            except Exception as exc:
                failure = f"stream-enable-failed: {exc}"; finished.set()
        def on_response(params: dict[str, Any]) -> None:
            nonlocal response_status, response_type, response_url
            rid = str(params.get("requestId") or "")
            if not active_request or rid != active_request: return
            response = params.get("response") or {}; response_url = str(response.get("url") or ""); response_status = int(response.get("status") or 0)
            headers = {str(k).lower(): str(v) for k, v in (response.get("headers") or {}).items()}; response_type = headers.get("content-type", "") or str(response.get("mimeType") or "")
            asyncio.create_task(enable_stream(rid))
        def on_data(params: dict[str, Any]) -> None:
            rid = str(params.get("requestId") or "")
            if active_request and rid == active_request and params.get("data"):
                try: chunks.append(base64.b64decode(params["data"]))
                except Exception as exc:
                    nonlocal_failure[0] = f"invalid network data: {exc}"
        nonlocal_failure = [None]
        def on_finished(params: dict[str, Any]) -> None:
            if active_request and str(params.get("requestId") or "") == active_request: finished.set()
        def on_failed(params: dict[str, Any]) -> None:
            nonlocal failure
            if active_request and str(params.get("requestId") or "") == active_request: failure = str(params.get("errorText") or "network request failed"); finished.set()
        handlers = (("Network.requestWillBeSent", on_request), ("Network.responseReceived", on_response), ("Network.dataReceived", on_data), ("Network.loadingFinished", on_finished), ("Network.loadingFailed", on_failed))
        for name, handler in handlers: self._cdp.on(name, handler)
        try:
            await self._page.bring_to_front(); textbox = await self._prompt_textbox(); prompt = next((m.get("content", "") for m in reversed(request.messages) if m.get("role") == "user"), "")
            yield StreamEvent(self.provider, request.request_id, EventType.REQUEST_INTERCEPTED, sequence, metadata={"transport": "cdp-network"}); sequence += 1
            await textbox.fill(prompt); await textbox.press("Enter")
            await asyncio.wait_for(request_seen.wait(), timeout=15.0); await asyncio.wait_for(finished.wait(), timeout=120.0)
            if nonlocal_failure[0]: failure = nonlocal_failure[0]
            if failure:
                yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"reason": failure}); return
            if response_status in {401, 403}:
                yield StreamEvent(self.provider, request.request_id, EventType.SESSION_EXPIRED, sequence, metadata={"status": response_status}); sequence += 1
                yield StreamEvent(self.provider, request.request_id, EventType.SESSION_RECOVERY_REQUIRED, sequence, metadata={"reason": "provider_authentication_failed"}); return
            if response_status is None or response_status >= 400:
                yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"status": response_status, "url": response_url}); return
            yield StreamEvent(self.provider, request.request_id, EventType.STREAM_STARTED, sequence, metadata={"transport": "cdp-network", "content_type": response_type}); sequence += 1
            text = self.parser(b"".join(chunks).decode("utf-8", errors="replace"))
            if not text:
                yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"reason": "provider_response_parser_returned_empty", "response_url": response_url}); return
            yield StreamEvent(self.provider, request.request_id, EventType.STREAM_DELTA, sequence, delta=text); sequence += 1
            yield StreamEvent(self.provider, request.request_id, EventType.STREAM_COMPLETED, sequence, finish_reason="stop")
        except Exception as exc:
            yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"reason": f"transport_failed: {exc}"})
        finally:
            for name, handler in handlers:
                try: self._cdp.remove_listener(name, handler)
                except Exception: pass

    async def execute(self, request: ProviderExecutionRequest) -> AsyncIterator[StreamEvent]:
        if request.provider != self.provider: raise ValueError(f"runtime provider mismatch: {request.provider}")
        await self.start(); prompt = next((m.get("content", "") for m in reversed(request.messages) if m.get("role") == "user"), "")
        if not isinstance(prompt, str) or not prompt.strip(): raise ValueError("execution requires a non-empty user message")
        async with self._lock:
            if self.cdp_url and self._cdp is not None:
                async for event in self._execute_cdp(request): yield event
                return
            async with WebNetworkCapture(self._page, self.spec) as capture:
                sequence = 0; yield StreamEvent(self.provider, request.request_id, EventType.REQUEST_INTERCEPTED, sequence, metadata={"transport": "playwright-network"}); sequence += 1
                try:
                    await self._page.bring_to_front(); textbox = await self._prompt_textbox(); await textbox.fill(prompt); await textbox.press("Enter")
                except Exception as exc:
                    yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"reason": f"prompt_submission_failed: {exc}"}); return
                try: status, content_type, body = await capture.wait()
                except Exception as exc:
                    yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"reason": str(exc)}); return
                if status in {401, 403}:
                    yield StreamEvent(self.provider, request.request_id, EventType.SESSION_EXPIRED, sequence, metadata={"status": status}); sequence += 1; yield StreamEvent(self.provider, request.request_id, EventType.SESSION_RECOVERY_REQUIRED, sequence, metadata={"reason": "provider_authentication_failed"}); return
                if status >= 400: yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"status": status}); return
                yield StreamEvent(self.provider, request.request_id, EventType.STREAM_STARTED, sequence, metadata={"transport": "playwright-network", "content_type": content_type}); sequence += 1
                text = self.parser(body)
                if not text: yield StreamEvent(self.provider, request.request_id, EventType.STREAM_FAILED, sequence, metadata={"reason": "provider_response_parser_returned_empty"}); return
                yield StreamEvent(self.provider, request.request_id, EventType.STREAM_DELTA, sequence, delta=text); sequence += 1; yield StreamEvent(self.provider, request.request_id, EventType.STREAM_COMPLETED, sequence, finish_reason="stop")

    async def close(self) -> None:
        self._started = False
        if self._cdp is not None:
            try: await self._cdp.detach()
            except Exception: pass
        if self._owns_context and self._context is not None:
            try: await self._context.close()
            except Exception: pass
        if self._owns_browser and self._browser is not None:
            try: await self._browser.close()
            except Exception: pass
        if self._pw is not None:
            try: await self._pw.stop()
            except Exception: pass
        self._pw = self._browser = self._context = self._page = self._cdp = None
        self._owns_browser = self._owns_context = False
