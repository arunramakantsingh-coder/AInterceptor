"""Shared browser runtime for ChatGPT, Gemini and DeepSeek.

Claude intentionally does not use this module. Its dedicated transport remains
unchanged as the known-good streaming reference.
"""
from __future__ import annotations

import asyncio
import base64
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


class NetworkCapture:
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
        # Intentionally a no-op. Network.streamResourceContent starves the
        # Network.dataReceived channel — using it made the whole capture
        # return zero bytes. The body is fetched via getResponseBody when
        # Network.loadingFinished fires (see _fetch_body below).
        return

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
            asyncio.create_task(self._fetch_body())

    async def _fetch_body(self) -> None:
        try:
            result = await self._cdp.send(
                "Network.getResponseBody", {"requestId": self._active_id}
            )
            body = result.get("body", "") or ""
            if result.get("base64Encoded"):
                data = base64.b64decode(body)
            else:
                data = body.encode("utf-8", errors="replace")
            if data:
                self._queue.put_nowait(("data", data))
        except Exception as e:
            self._queue.put_nowait(("failed", f"getResponseBody: {e}"))
        finally:
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

    async def __aenter__(self) -> "NetworkCapture":
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

class WebRuntimeBase(ProviderRuntime):
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

        # Prefer CDP: the visible Chrome holds the real login; headless
        # Chromium trips Google/Cloudflare bot detection. Only fall back to
        # headless if the user explicitly sets AINTERCEPTOR_HEADLESS=1 AND
        # no CDP is reachable.
        import socket as _sock
        def _cdp_alive(url: str | None) -> bool:
            if not url: return False
            try:
                host = url.split("://", 1)[-1].split(":")[0]
                port = int(url.rsplit(":", 1)[-1].split("/")[0])
            except Exception:
                return False
            s = _sock.socket(); s.settimeout(0.3)
            try: s.connect((host, port)); return True
            except OSError: return False
            finally: s.close()

        target_cdp = env_val if env_val else provider_registry.cdp_url(self.provider)
        force_headless = os.environ.get("AINTERCEPTOR_HEADLESS", "") in {"1","true","yes"}
        if force_headless and not _cdp_alive(target_cdp):
            self.cdp_url = None
        elif env_val == "":
            self.cdp_url = None
        elif env_val:
            self.cdp_url = env_val
        else:
            self.cdp_url = provider_registry.cdp_url(self.provider)
        if not getattr(self, "_cdp_logged", False):
            self._cdp_logged = True
            self._record_port_attachment()

        if self.cdp_url:
            # CDP attach on a busy Chrome (4 tabs + Xvfb + exporter)
            # can take 15-50s on the VM. The prior 15s ceiling fired
            # under contention and surfaced as an empty
            # asyncio.TimeoutError. 45s gives headroom without hanging
            # forever.
            self._browser = await asyncio.wait_for(
                self._pw.chromium.connect_over_cdp(self.cdp_url),
                timeout=45,
            )
            contexts = self._browser.contexts
            if not contexts:
                raise WebProviderSessionError("CDP browser has no context")
            self._context = contexts[0]
            self._owns_browser = self._owns_context = False
            # Find the tab whose URL matches this provider's home host.
            # If none exists, open a new tab to the provider home.
            host = urlparse(self.spec.home_url).netloc
            matching = [p for p in self._context.pages
                        if host in (p.url or "")]
            if matching:
                self._page = matching[-1]
            else:
                self._page = await self._context.new_page()
                try:
                    await self._page.goto(self.spec.home_url,
                                          wait_until="domcontentloaded",
                                          timeout=30_000)
                except Exception:
                    pass
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
        """Submit prompt, capture the provider's response at the CDP
        Network layer, parse it, and emit the full text as a delta.

        No DOM polling. The response body is captured by
        NetworkCapture (already defined above) which uses
        Network.streamResourceContent + Network.dataReceived.
        """
        if request.provider != self.provider:
            raise ValueError(f"runtime provider mismatch: {request.provider}")
        await self.start()

        prompt = next(
            (m.get("content", "") for m in reversed(request.messages)
             if m.get("role") == "user"), "",
        )
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("execution requires a non-empty user message")

        async with self._lock:
            # Reset parser state. The runtime — and its parser — are
            # cached per provider (see _get_runtime in path_b.py) so
            # they survive across requests. Without this reset, the
            # prior request's fragments leak into this one. Symptom:
            #   prompt "say PONG" -> reply "PONG\n\nhi again"
            # Calling __init__() re-runs the parser's own initializer,
            # which is the parser's contract for "start clean".
            try:
                self.parser.__init__()
            except Exception:
                pass
            seq = 0
            yield StreamEvent(self.provider, request.request_id,
                              EventType.REQUEST_INTERCEPTED, seq,
                              metadata={"transport": "cdp-network"})
            seq += 1

            async with NetworkCapture(self._page, self.spec) as cap:
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
                                  metadata={"transport": "cdp-network"})
                seq += 1

                body = bytearray()
                status_code = 0
                last_text = ""
                async for kind, payload in cap.events(timeout=120.0):
                    if kind == "response_started":
                        try:
                            status_code = int(payload[0] or 0)
                        except Exception:
                            status_code = 0
                    elif kind == "data":
                        body.extend(payload)
                        # Incremental delta: the parser is monotone —
                        # __call__ returns the longest text seen so far
                        # for the cumulative body. Yield only the new
                        # suffix on each chunk so the client sees tokens
                        # arrive live instead of one blob at the end.
                        try:
                            partial = self.parser(body.decode("utf-8", errors="replace"))
                            if partial and len(partial) > len(last_text):
                                delta = partial[len(last_text):]
                                if delta:
                                    yield StreamEvent(
                                        self.provider, request.request_id,
                                        EventType.STREAM_DELTA, seq,
                                        delta=delta)
                                    seq += 1
                                    last_text = partial
                        except Exception:
                            pass
                    elif kind == "failed":
                        yield StreamEvent(self.provider, request.request_id,
                                          EventType.STREAM_FAILED, seq,
                                          metadata={"reason": str(payload)[:200]})
                        return
                    elif kind == "finished":
                        break

                if status_code in (401, 403):
                    yield StreamEvent(self.provider, request.request_id,
                                      EventType.SESSION_EXPIRED, seq,
                                      metadata={"status": status_code})
                    seq += 1
                    yield StreamEvent(self.provider, request.request_id,
                                      EventType.SESSION_RECOVERY_REQUIRED, seq,
                                      metadata={"reason": "auth_failed"})
                    return

                if status_code >= 400:
                    yield StreamEvent(self.provider, request.request_id,
                                      EventType.STREAM_FAILED, seq,
                                      metadata={"status": status_code})
                    return

                text = ""
                if body:
                    text = self.parser(body.decode("utf-8", errors="replace"))
                    # Finalize any partial line still buffered inside
                    # the parser. The last SSE chunk often has no
                    # trailing newline, so it stays in _pending until
                    # finish() processes it. Symptom without this:
                    #   "say ZZZ" -> reply "ZZ" (missing last char).
                    if hasattr(self.parser, "finish"):
                        try:
                            finalized = self.parser.finish()
                            if finalized and len(finalized) >= len(text or ""):
                                text = finalized
                        except Exception:
                            pass
                if not text:
                    yield StreamEvent(self.provider, request.request_id,
                                      EventType.STREAM_FAILED, seq,
                                      metadata={"reason": "parser_returned_empty"})
                    return

                # Only emit the residual text not already streamed.
                if text and len(text) > len(last_text):
                    residual = text[len(last_text):]
                    if residual:
                        yield StreamEvent(self.provider, request.request_id,
                                          EventType.STREAM_DELTA, seq, delta=residual)
                        seq += 1
                yield StreamEvent(self.provider, request.request_id,
                                  EventType.STREAM_COMPLETED, seq,
                                  finish_reason="stop")


    async def _assistant_count(self) -> int:
        """Count assistant bubbles. Uses the widest single selector that
        matches DeepSeek's current UI; falls back to alternates."""
        for s in (".ds-markdown",
                  "[data-message-author-role='assistant']",
                  ".model-response-text",
                  "message-content"):
            try:
                n = await self._page.locator(s).count()
                if n > 0:
                    return n
            except Exception:
                continue
        return 0

    async def _read_last_assistant_text(self) -> str:
        """Read the newest non-think assistant reply.

        DeepSeek's DOM changed: the top-level message container no longer
        carries `.ds-markdown`. Instead, each paragraph inside a message is
        `.ds-markdown-paragraph`, and there is no single wrapper element.
        So we identify the message bubble by its parent wrapper and join
        every paragraph inside it.

        We treat `[class*="ds-markdown"]` as the reliable anchor now; the
        paragraph nodes it matches are grouped by their nearest shared
        parent, and the last group (newest message) is read in full.
        """
        cached = getattr(self, "_cached_node", None)
        if cached is not None:
            try:
                txt = await cached.evaluate(
                    "n => (n.isConnected ? (n.innerText || '').trim() : null)"
                )
                if txt is not None:
                    return txt
            except Exception:
                pass
            self._cached_node = None

        # Find the newest assistant message bubble's *container* and return
        # it as a JSHandle so we can cache it.
        js_find_container = r"""
            () => {
                const thinkingRe = /think|reason|analysis|cot|chain-of-thought/i;

                // DeepSeek renders each message inside a wrapper that holds
                // user or assistant content. The most reliable anchor today
                // is a group of `.ds-markdown-paragraph` (or similar) nodes
                // under a common parent.
                //
                // Strategy: collect candidate container elements in DOM order,
                // then reject any inside a think/reason/analysis subtree.
                const candidates = new Set();

                // Direct paragraphs → walk up to the nearest meaningful wrapper
                for (const p of document.querySelectorAll('.ds-markdown-paragraph, .ds-markdown')) {
                    let el = p;
                    // walk up at most 6 levels to find a container that holds
                    // several sibling paragraphs (or a lone one)
                    for (let i = 0; i < 6 && el.parentElement; i++) {
                        el = el.parentElement;
                        const cls = (typeof el.className === 'string'
                                     ? el.className
                                     : (el.className && el.className.baseVal) || '');
                        if (/message|assistant|markdown-content|chat-message/i.test(cls)) {
                            candidates.add(el);
                            break;
                        }
                    }
                }

                // Also consider role-tagged elements (ChatGPT-style)
                for (const el of document.querySelectorAll(
                        '[data-message-author-role="assistant"], .model-response-text')) {
                    candidates.add(el);
                }

                if (!candidates.size) return null;

                // Order by DOM position, filter out think blocks, pick last.
                const list = Array.from(candidates);
                list.sort((a, b) => {
                    const pos = a.compareDocumentPosition(b);
                    if (pos & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
                    if (pos & Node.DOCUMENT_POSITION_PRECEDING) return 1;
                    return 0;
                });

                for (let i = list.length - 1; i >= 0; i--) {
                    const el = list[i];
                    if (!el.offsetParent && getComputedStyle(el).display === 'none') continue;
                    let p = el.parentElement;
                    let isThink = false;
                    while (p && p !== document.body) {
                        const cls = (typeof p.className === 'string'
                                     ? p.className
                                     : (p.className && p.className.baseVal) || '');
                        if (thinkingRe.test(cls)) { isThink = true; break; }
                        p = p.parentElement;
                    }
                    if (isThink) continue;
                    return el;
                }
                return null;
            }
        """

        try:
            handle = await self._page.evaluate_handle(js_find_container)
            el = handle.as_element()
            if el is None:
                return ""
            self._cached_node = el
            txt = await el.evaluate("n => (n.innerText || '').trim()")
            return txt or ""
        except Exception:
            self._cached_node = None
            return ""

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
