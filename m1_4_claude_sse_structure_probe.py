from __future__ import annotations

import asyncio
import base64
import json
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

CDP_ENDPOINT = "http://127.0.0.1:9222"
MARKER = "/chat_conversations/"
SUFFIX = "/completion"


class SafeSSEInspector:
    def __init__(self):
        self.buffer = ""
        self.decoder = __import__("codecs").getincrementaldecoder("utf-8")()
        self.frames = 0

    def feed(self, payload: bytes):
        self.buffer += self.decoder.decode(payload)

        while True:
            match = re.search(r"\r?\n\r?\n", self.buffer)
            if not match:
                break

            frame = self.buffer[:match.start()]
            self.buffer = self.buffer[match.end():]

            self.inspect_frame(frame)

    def finish(self):
        tail = self.decoder.decode(b"", final=True)
        if tail:
            self.buffer += tail

        if self.buffer.strip():
            self.inspect_frame(self.buffer)

    def inspect_frame(self, frame: str):
        event_name = None
        data_lines = []

        for line in frame.splitlines():
            if not line or line.startswith(":"):
                continue

            field, sep, value = line.partition(":")
            if not sep:
                continue

            value = value[1:] if value.startswith(" ") else value

            if field == "event":
                event_name = value

            elif field == "data":
                data_lines.append(value)

        if not data_lines:
            return

        self.frames += 1

        payload = "\n".join(data_lines).strip()

        if payload == "[DONE]":
            print(
                f"[FRAME {self.frames}] "
                f"event={event_name!r} "
                f"DATA=[DONE]"
            )
            return

        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            print(
                f"[FRAME {self.frames}] "
                f"event={event_name!r} "
                f"JSON=INVALID "
                f"length={len(payload)}"
            )
            return

        if not isinstance(obj, dict):
            print(
                f"[FRAME {self.frames}] "
                f"event={event_name!r} "
                f"JSON_TYPE={type(obj).__name__}"
            )
            return

        keys = sorted(obj.keys())

        structural = {}

        for key in (
            "type",
            "completion",
            "delta",
            "stop_reason",
            "finish_reason",
            "message",
            "content",
            "usage",
            "index",
            "id",
        ):
            if key not in obj:
                continue

            value = obj[key]

            if isinstance(value, dict):
                structural[key] = {
                    "type": "object",
                    "keys": sorted(value.keys()),
                }

            elif isinstance(value, list):
                structural[key] = {
                    "type": "array",
                    "length": len(value),
                }

            elif isinstance(value, str):
                # Deliberately do NOT print the string value.
                structural[key] = {
                    "type": "string",
                    "length": len(value),
                }

            elif value is None:
                structural[key] = {
                    "type": "null"
                }

            else:
                structural[key] = {
                    "type": type(value).__name__
                }

        print(
            f"[FRAME {self.frames}] "
            f"event={event_name!r} "
            f"keys={keys}"
        )

        if structural:
            print(
                f"             structure={structural}"
            )


async def main():
    print("Connecting to existing Chrome through CDP...")

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(CDP_ENDPOINT)

        pages = [
            page
            for context in browser.contexts
            for page in context.pages
        ]

        page = next(
            (p for p in pages if "claude.ai" in p.url),
            None,
        )

        if page is None:
            print("ERROR: Claude page not found.")
            return 1

        print(f"Claude page: {page.url}")
        print(f"Claude title: {await page.title()}")

        cdp = await page.context.new_cdp_session(page)

        await cdp.send(
            "Network.enable",
            {
                "maxTotalBufferSize": 20 * 1024 * 1024,
                "maxResourceBufferSize": 10 * 1024 * 1024,
            },
        )

        await cdp.send(
            "Network.setBypassServiceWorker",
            {"bypass": True},
        )

        inspector = SafeSSEInspector()

        state = {
            "request_id": None,
            "status": None,
            "content_type": None,
            "chunks": 0,
            "bytes": 0,
            "ended": False,
        }

        async def stream(request_id):
            try:
                result = await cdp.send(
                    "Network.streamResourceContent",
                    {"requestId": request_id},
                )

                buffered = result.get("bufferedData") or ""

                if buffered:
                    payload = base64.b64decode(buffered)
                    state["bytes"] += len(payload)
                    inspector.feed(payload)

            except Exception as exc:
                print(
                    "[streamResourceContent error]",
                    type(exc).__name__,
                    str(exc),
                )

        def request_handler(params):
            request = params.get("request") or {}
            url = request.get("url", "")

            if (
                request.get("method") == "POST"
                and MARKER in url
                and url.endswith(SUFFIX)
            ):
                state["request_id"] = params.get("requestId")
                print()
                print("[COMPLETION REQUEST DETECTED]")

        def response_handler(params):
            if params.get("requestId") != state["request_id"]:
                return

            response = params.get("response") or {}

            state["status"] = response.get("status")

            headers = {
                str(k).lower(): str(v)
                for k, v in (response.get("headers") or {}).items()
            }

            state["content_type"] = headers.get(
                "content-type",
                "",
            )

            print(
                f"[RESPONSE] "
                f"status={state['status']} "
                f"content_type={state['content_type']}"
            )

            asyncio.create_task(
                stream(state["request_id"])
            )

        def data_handler(params):
            if params.get("requestId") != state["request_id"]:
                return

            encoded = params.get("data")

            if not encoded:
                return

            try:
                payload = base64.b64decode(encoded)
            except Exception as exc:
                print(
                    "[decode error]",
                    type(exc).__name__,
                    str(exc),
                )
                return

            state["chunks"] += 1
            state["bytes"] += len(payload)

            inspector.feed(payload)

        def finished_handler(params):
            if params.get("requestId") == state["request_id"]:
                state["ended"] = True
                print("[NETWORK] loadingFinished")

        def failed_handler(params):
            if params.get("requestId") == state["request_id"]:
                state["ended"] = True
                print(
                    "[NETWORK] loadingFailed:",
                    params.get("errorText"),
                )

        cdp.on(
            "Network.requestWillBeSent",
            request_handler,
        )
        cdp.on(
            "Network.responseReceived",
            response_handler,
        )
        cdp.on(
            "Network.dataReceived",
            data_handler,
        )
        cdp.on(
            "Network.loadingFinished",
            finished_handler,
        )
        cdp.on(
            "Network.loadingFailed",
            failed_handler,
        )

        print()
        print("=" * 64)
        print("CLAUDE SSE STRUCTURE INSPECTION")
        print("=" * 64)
        print()
        print("Use the dedicated Claude window.")
        print()
        print("Enter:")
        print()
        print("  Reply with exactly: AINTERCEPTOR-SSE-SCHEMA-TEST")
        print()
        print("Wait until the response finishes.")
        print("Then press ENTER here.")
        print()
        print("NO RESPONSE TEXT WILL BE PRINTED.")
        print("Only protocol structure is displayed.")
        print("=" * 64)
        print()

        await asyncio.to_thread(
            input,
            "Press ENTER after Claude finishes... ",
        )

        await asyncio.sleep(2)

        inspector.finish()

        print()
        print("=" * 64)
        print("STRUCTURE SUMMARY")
        print("=" * 64)
        print(f"HTTP status       : {state['status']}")
        print(f"Content-Type      : {state['content_type']}")
        print(f"Network chunks    : {state['chunks']}")
        print(f"Decoded bytes     : {state['bytes']}")
        print(f"SSE frames        : {inspector.frames}")
        print(f"Network ended     : {state['ended']}")
        print("=" * 64)

        await cdp.detach()

        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
