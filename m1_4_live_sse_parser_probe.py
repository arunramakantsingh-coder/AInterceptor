from __future__ import annotations

import asyncio
import base64
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

# Make backend/app importable from repository root.
ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.interception.claude_transport import ClaudeSSEParser


CDP_ENDPOINT = "http://127.0.0.1:9222"
COMPLETION_MARKER = "/chat_conversations/"
COMPLETION_SUFFIX = "/completion"


async def main():
    print("Connecting to existing Chrome through CDP...")

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(CDP_ENDPOINT)

        pages = []
        for context in browser.contexts:
            pages.extend(context.pages)

        claude_page = next(
            (p for p in pages if "claude.ai" in p.url),
            None,
        )

        if claude_page is None:
            print("ERROR: No Claude page found.")
            return 1

        print(f"Claude page: {claude_page.url}")
        print(f"Claude title: {await claude_page.title()}")

        context = claude_page.context
        cdp = await context.new_cdp_session(claude_page)

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

        state = {
            "completion_request_id": None,
            "request_url": None,
            "status": None,
            "content_type": None,
            "chunks": 0,
            "decoded_bytes": 0,
            "parser_events": 0,
            "delta_events": 0,
            "delta_characters": 0,
            "done_events": 0,
            "finish_reasons": [],
            "loading_finished": False,
            "loading_failed": False,
            "stream_enabled": False,
            "stream_enable_error": None,
            "request_seen": False,
            "response_seen": False,
        }

        parser = ClaudeSSEParser()
        parser_lock = asyncio.Lock()

        async def process_payload(payload: bytes, source: str):
            if not payload:
                return

            state["decoded_bytes"] += len(payload)

            async with parser_lock:
                events = parser.feed(payload)

            for event in events:
                state["parser_events"] += 1

                if event.delta:
                    state["delta_events"] += 1
                    state["delta_characters"] += len(event.delta)

                if event.done:
                    state["done_events"] += 1

                if event.finish_reason:
                    if event.finish_reason not in state["finish_reasons"]:
                        state["finish_reasons"].append(event.finish_reason)

            print(
                f"[PAYLOAD] source={source} "
                f"bytes={len(payload)} "
                f"total_bytes={state['decoded_bytes']} "
                f"parser_events={state['parser_events']} "
                f"deltas={state['delta_events']} "
                f"done={state['done_events']}"
            )

        async def enable_stream(request_id: str):
            try:
                result = await cdp.send(
                    "Network.streamResourceContent",
                    {"requestId": request_id},
                )

                state["stream_enabled"] = True

                buffered = result.get("bufferedData") or ""

                if buffered:
                    try:
                        payload = base64.b64decode(buffered)
                    except Exception as exc:
                        state["stream_enable_error"] = (
                            f"bufferedData decode failed: {exc}"
                        )
                        return

                    await process_payload(
                        payload,
                        "streamResourceContent.bufferedData",
                    )

            except Exception as exc:
                state["stream_enable_error"] = str(exc)

        def on_request(params):
            request = params.get("request") or {}
            method = request.get("method")
            url = request.get("url", "")

            if (
                method == "POST"
                and COMPLETION_MARKER in url
                and url.endswith(COMPLETION_SUFFIX)
            ):
                state["request_seen"] = True
                state["completion_request_id"] = params.get("requestId")
                state["request_url"] = url

                print()
                print("[COMPLETION REQUEST]")
                print(f"method={method}")
                print(f"url={url}")

        def on_response(params):
            request_id = params.get("requestId")

            if request_id != state["completion_request_id"]:
                return

            response = params.get("response") or {}

            state["response_seen"] = True
            state["status"] = response.get("status")

            headers = {
                str(k).lower(): str(v)
                for k, v in (response.get("headers") or {}).items()
            }

            state["content_type"] = headers.get("content-type", "")

            print()
            print("[COMPLETION RESPONSE]")
            print(f"status={state['status']}")
            print(f"mimeType={response.get('mimeType', '')}")
            print(f"content-type={state['content_type']}")
            print("transport=text/event-stream expected")

            asyncio.create_task(
                enable_stream(request_id)
            )

        def on_data(params):
            request_id = params.get("requestId")

            if request_id != state["completion_request_id"]:
                return

            encoded = params.get("data")

            if not encoded:
                return

            try:
                payload = base64.b64decode(encoded)
            except Exception as exc:
                print(f"[ERROR] dataReceived decode failed: {exc}")
                return

            state["chunks"] += 1

            asyncio.create_task(
                process_payload(
                    payload,
                    f"Network.dataReceived.chunk-{state['chunks']}",
                )
            )

        def on_finished(params):
            if params.get("requestId") != state["completion_request_id"]:
                return

            state["loading_finished"] = True
            print("[FINISHED] completion request")

        def on_failed(params):
            if params.get("requestId") != state["completion_request_id"]:
                return

            state["loading_failed"] = True
            print(
                f"[FAILED] completion request: "
                f"{params.get('errorText', 'unknown')}"
            )

        cdp.on("Network.requestWillBeSent", on_request)
        cdp.on("Network.responseReceived", on_response)
        cdp.on("Network.dataReceived", on_data)
        cdp.on("Network.loadingFinished", on_finished)
        cdp.on("Network.loadingFailed", on_failed)

        print()
        print("=" * 60)
        print("LIVE CLAUDE SSE PAYLOAD -> PARSER VALIDATION")
        print("=" * 60)
        print()
        print("Use the dedicated Claude Chrome window.")
        print()
        print("Enter:")
        print()
        print("  Reply with exactly: AINTERCEPTOR-SSE-PARSER-TEST")
        print()
        print("Wait until Claude completely finishes.")
        print("Then return here and press ENTER.")
        print()
        print("The probe will NOT print Claude response text.")
        print("It only reports byte/event counters and finish metadata.")
        print("=" * 60)
        print()

        await asyncio.to_thread(input, "Press ENTER after Claude finishes... ")

        # Allow outstanding CDP callbacks/tasks to complete.
        await asyncio.sleep(2.0)

        # Flush any parser tail.
        async with parser_lock:
            tail_events = parser.finish()

        for event in tail_events:
            state["parser_events"] += 1

            if event.delta:
                state["delta_events"] += 1
                state["delta_characters"] += len(event.delta)

            if event.done:
                state["done_events"] += 1

            if event.finish_reason:
                if event.finish_reason not in state["finish_reasons"]:
                    state["finish_reasons"].append(event.finish_reason)

        print()
        print("=" * 60)
        print("LIVE VALIDATION SUMMARY")
        print("=" * 60)

        print(f"Completion request observed : {state['request_seen']}")
        print(f"Completion response observed: {state['response_seen']}")
        print(f"HTTP status                 : {state['status']}")
        print(f"Content-Type                : {state['content_type']}")
        print(f"Stream enabled              : {state['stream_enabled']}")
        print(f"Stream enable error        : {state['stream_enable_error']}")
        print(f"Network data chunks         : {state['chunks']}")
        print(f"Decoded payload bytes       : {state['decoded_bytes']}")
        print(f"Parsed SSE events           : {state['parser_events']}")
        print(f"Delta events                : {state['delta_events']}")
        print(f"Delta character count      : {state['delta_characters']}")
        print(f"DONE events                 : {state['done_events']}")
        print(f"Finish reasons              : {state['finish_reasons']}")
        print(f"Loading finished            : {state['loading_finished']}")
        print(f"Loading failed              : {state['loading_failed']}")

        transport_pass = (
            state["request_seen"]
            and state["response_seen"]
            and state["status"] == 200
            and "text/event-stream" in (state["content_type"] or "").lower()
            and state["chunks"] > 0
            and state["decoded_bytes"] > 0
        )

        parser_pass = (
            state["parser_events"] > 0
            and state["delta_events"] > 0
            and (
                state["done_events"] > 0
                or len(state["finish_reasons"]) > 0
                or state["loading_finished"]
            )
        )

        print()
        print("TRANSPORT PAYLOAD CHECK:", "PASS" if transport_pass else "FAIL")
        print("SSE PARSER CHECK       :", "PASS" if parser_pass else "FAIL")

        overall = transport_pass and parser_pass

        print()
        print(
            "OVERALL LIVE PAYLOAD VALIDATION:",
            "PASS" if overall else "FAIL",
        )
        print()

        await cdp.detach()

        return 0 if overall else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
