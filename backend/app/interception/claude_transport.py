from __future__ import annotations

import asyncio
import base64
import codecs
import json
import re
from dataclasses import dataclass
from typing import Any, AsyncIterator


@dataclass(frozen=True)
class ClaudeSSEEvent:
    """Provider-local parsed SSE payload; never crosses the runtime boundary."""

    delta: str = ""
    finish_reason: str | None = None
    done: bool = False


class ClaudeSSEParser:
    """Incrementally parse Claude's SSE response without buffering the stream."""

    _FRAME_SEPARATOR = re.compile(r"\r?\n\r?\n")

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")()
        self._buffer = ""

    def feed(self, payload: bytes) -> list[ClaudeSSEEvent]:
        self._buffer += self._decoder.decode(payload)
        events: list[ClaudeSSEEvent] = []

        while True:
            match = self._FRAME_SEPARATOR.search(self._buffer)
            if match is None:
                break
            frame = self._buffer[: match.start()]
            self._buffer = self._buffer[match.end() :]
            event = self._parse_frame(frame)
            if event is not None:
                events.append(event)
        return events

    def finish(self) -> list[ClaudeSSEEvent]:
        tail = self._decoder.decode(b"", final=True)
        if tail:
            self._buffer += tail
        if not self._buffer.strip():
            return []
        event = self._parse_frame(self._buffer)
        self._buffer = ""
        return [event] if event is not None else []

    @staticmethod
    def _parse_frame(frame: str) -> ClaudeSSEEvent | None:
        data_lines: list[str] = []
        for line in frame.splitlines():
            if not line or line.startswith(":"):
                continue
            field, separator, value = line.partition(":")
            if separator and field == "data":
                data_lines.append(value[1:] if value.startswith(" ") else value)

        if not data_lines:
            return None

        payload = "\n".join(data_lines).strip()
        if payload == "[DONE]":
            return ClaudeSSEEvent(done=True, finish_reason="stop")

        try:
            data: Any = json.loads(payload)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None

        event_type = data.get("type")
        if event_type == "content_block_delta":
            nested_delta = data.get("delta")
            if isinstance(nested_delta, dict):
                text = nested_delta.get("text")
                return ClaudeSSEEvent(delta=text if isinstance(text, str) else "")
            return ClaudeSSEEvent()

        if event_type == "message_delta":
            nested_delta = data.get("delta")
            finish_reason = None
            if isinstance(nested_delta, dict):
                value = nested_delta.get("stop_reason")
                if isinstance(value, str) and value:
                    finish_reason = value
            return ClaudeSSEEvent(finish_reason=finish_reason)

        if event_type == "message_stop":
            return ClaudeSSEEvent(done=True, finish_reason="stop")

        # Backward compatibility with earlier/synthetic Claude SSE shapes.
        delta = data.get("completion") or data.get("delta") or ""
        if isinstance(delta, dict):
            delta = delta.get("text") or delta.get("content") or ""
        if not isinstance(delta, str):
            delta = ""

        finish_reason = data.get("stop_reason") or data.get("finish_reason")
        return ClaudeSSEEvent(delta=delta, finish_reason=finish_reason)


@dataclass(frozen=True)
class TransportSignal:
    kind: str
    request_id: str | None = None
    payload: Any = None


class ClaudeCDPTransport:
    """Chromium CDP network observer for Claude's web transport.

    The browser page initiates the provider request. This component only
    observes the communication path through Chromium's Network domain and
    incrementally receives response bytes using Network.streamResourceContent.
    """

    COMPLETION_MARKER = "/chat_conversations/"
    COMPLETION_SUFFIX = "/completion"

    def __init__(self, cdp: Any) -> None:
        self._cdp = cdp
        self._signals: asyncio.Queue[TransportSignal] = asyncio.Queue()
        self._active_request_id: str | None = None
        self._prepared_request_id: str | None = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        await self._cdp.send(
            "Network.enable",
            {
                "maxTotalBufferSize": 20 * 1024 * 1024,
                "maxResourceBufferSize": 10 * 1024 * 1024,
            },
        )
        await self._cdp.send("Network.setBypassServiceWorker", {"bypass": True})
        self._cdp.on("Network.requestWillBeSent", self._on_request)
        self._cdp.on("Network.responseReceived", self._on_response)
        self._cdp.on("Network.dataReceived", self._on_data)
        self._cdp.on("Network.loadingFinished", self._on_finished)
        self._cdp.on("Network.loadingFailed", self._on_failed)
        self._started = True

    def prepare(self, request_id: str) -> None:
        self._prepared_request_id = request_id
        self._active_request_id = None
        while not self._signals.empty():
            try:
                self._signals.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def signals(self, timeout: float = 120.0) -> AsyncIterator[TransportSignal]:
        while True:
            signal = await asyncio.wait_for(self._signals.get(), timeout=timeout)
            yield signal
            if signal.kind in {"finished", "failed"}:
                return

    def _is_completion(self, url: str) -> bool:
        return self.COMPLETION_MARKER in url and url.endswith(self.COMPLETION_SUFFIX)

    def _on_request(self, params: dict[str, Any]) -> None:
        request = params.get("request") or {}
        url = request.get("url", "")
        if request.get("method") == "POST" and self._is_completion(url):
            self._signals.put_nowait(
                TransportSignal("request_intercepted", params.get("requestId"))
            )

    def _on_response(self, params: dict[str, Any]) -> None:
        request_id = params.get("requestId")
        response = params.get("response") or {}
        if not request_id or not self._is_completion(response.get("url", "")):
            return

        status = int(response.get("status", 0))
        headers = {
            str(key).lower(): str(value)
            for key, value in (response.get("headers") or {}).items()
        }
        content_type = headers.get("content-type", "")
        self._active_request_id = request_id
        self._signals.put_nowait(
            TransportSignal(
                "response_started",
                request_id,
                {"status": status, "content_type": content_type},
            )
        )
        asyncio.create_task(self._enable_stream(request_id))

    async def _enable_stream(self, request_id: str) -> None:
        try:
            result = await self._cdp.send(
                "Network.streamResourceContent", {"requestId": request_id}
            )
            buffered = result.get("bufferedData") or ""
            if buffered:
                self._signals.put_nowait(
                    TransportSignal(
                        "data",
                        request_id,
                        base64.b64decode(buffered),
                    )
                )
        except Exception as exc:
            self._signals.put_nowait(
                TransportSignal("failed", request_id, f"stream-enable-failed: {exc}")
            )

    def _on_data(self, params: dict[str, Any]) -> None:
        request_id = params.get("requestId")
        if request_id != self._active_request_id:
            return
        encoded = params.get("data")
        if not encoded:
            return
        try:
            payload = base64.b64decode(encoded)
        except Exception as exc:
            self._signals.put_nowait(
                TransportSignal("failed", request_id, f"invalid-network-data: {exc}")
            )
            return
        self._signals.put_nowait(TransportSignal("data", request_id, payload))

    def _on_finished(self, params: dict[str, Any]) -> None:
        request_id = params.get("requestId")
        if request_id == self._active_request_id:
            self._signals.put_nowait(TransportSignal("finished", request_id))

    def _on_failed(self, params: dict[str, Any]) -> None:
        request_id = params.get("requestId")
        if request_id == self._active_request_id:
            self._signals.put_nowait(
                TransportSignal(
                    "failed",
                    request_id,
                    params.get("errorText") or "network request failed",
                )
            )
