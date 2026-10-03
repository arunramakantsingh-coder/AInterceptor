from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.interception.claude_transport import ClaudeSSEParser


CDP_ENDPOINT = "http://127.0.0.1:9222"
COMPLETION_MARKER = "/chat_conversations/"
COMPLETION_SUFFIX = "/completion"


async def main():
    print("Connecting to existing Chrome through CDP...")

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(CDP_ENDPOINT)

        pages = [
            page
            for context in browser.contexts
            for page in context.pages
        ]

        claude_page = next(
            (page for page in pages if "claude.ai" in page.url),
            None,
        )

        if claude_page is None:
            print("ERROR: No Claude page found.")
            return 1

        print(f"Claude page: {claude_page.url}")
        print(f"Claude title: {await claude_page.title()}")

        cdp = await claude_page.context.new_cdp_session(claude_page)

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

        parser = ClaudeSSEParser()

        state = {
            "request_id": None,
            "url": None,
            "status": None,
            "mime": None,
            "content_type": None,
            "chunks": 0,
            "bytes": 0,
            "parser_events": 0,
            "delta_events": 0,
            "delta_chars": 0,
            "done_events": 0,
            "finish_reasons": [],
            "finished": False,
            "failed": False,
            "failed_error": None,
            "stream_enabled": False,
            "stream_enable_error": None,
        }

        stream_ready = asyncio.Event()
        network_done = asyncio.Event()

        def consume(payload: bytes, source: str):
            if not payload:
                return

            state["bytes"] += len(payload)

            events = parser.feed(payload)

            for event in events:
                state["parser_events"] += 1

                if event.delta:
                    state["delta_events"] += 1
                    state["delta_chars"] += len(event.delta)

                if event.done:
                    state["done_events"] += 1

                if event.finish_reason:
                    if event.finish_reason not in state["finish_reasons"]:
                        state["finish_reasons"].append(
                            event.finish_reason
                        )

            print(
                f"[PAYLOAD] {source} "
                f"bytes={len(payload)} "
                f"total={state['bytes']} "
                f"events={state['parser_events']} "
                f"deltas={state['delta_events']}"
            )

        async def enable_stream(request_id: str):
            try:
                result = await cdp.send(
                    "Network.streamResourceContent",
                    {"requestId": request_id},
                )

                state["stream_enabled"] = True
                stream_ready.set()

                buffered = result.get("bufferedData") or ""

                if buffered:
                    payload = base64.b64decode(buffered)

                    consume(
                        payload,
                        "streamResourceContent.bufferedData",
                    )

            except Exception as exc:
                state["stream_enable_error"] = str(exc)
                stream_ready.set()

        def on_request(params):
            request = params.get("request") or {}
            method = request.get("method")
            url = request.get("url", "")

            if (
                method == "POST"
                and COMPLETION_MARKER in url
                and url.endswith(COMPLETION_SUFFIX)
            ):
                state["request_id"] = params.get("requestId")
                state["url"] = url

                print()
                print("[COMPLETION REQUEST]")
                print(f"method={method}")
                print(f"url={url}")

        def on_response(params):
            request_id = params.get("requestId")

            if request_id != state["request_id"]:
                return

            response = params.get("response") or {}

            state["status"] = response.get("status")
            state["mime"] = response.get("mimeType", "")

            headers = {
                str(k).lower(): str(v)
                for k, v in (response.get("headers") or {}).items()
            }

            state["content_type"] = headers.get(
                "content-type",
                "",
            )

            print()
            print("[COMPLETION RESPONSE]")
            print(f"status={state['status']}")
            print(f"mimeType={state['mime']}")
            print(f"content-type={state['content_type']}")

            asyncio.create_task(
                enable_stream(request_id)
            )

        def on_data(params):
            request_id = params.get("requestId")

            if request_id != state["request_id"]:
                return

            encoded = params.get("data")

            if not encoded:
                return

            try:
                payload = base64.b64decode(encoded)
            except Exception as exc:
                print(
                    "[ERROR] Unable to decode Network.dataReceived:",
                    exc,
                )
                return

            state["chunks"] += 1

            # IMPORTANT:
            # CDP callbacks execute serially on the Playwright event loop.
            # Feed the parser directly rather than scheduling another task.
            consume(
                payload,
                f"Network.dataReceived.chunk-{state['chunks']}",
            )

        def on_finished(params):
            if params.get("requestId") != state["request_id"]:
                return

            state["finished"] = True
            network_done.set()

            print("[FINISHED] completion request")

        def on_failed(params):
            if params.get("requestId") != state["request_id"]:
                return

            state["failed"] = True
            state["failed_error"] = (
                params.get("errorText") or "unknown"
            )

            # ERR_ABORTED can occur after the response stream has already
            # delivered its payload. Do not immediately classify it as
            # parser failure.
            network_done.set()

            print(
                f"[NETWORK END] {state['failed_error']}"
            )

        cdp.on(
            "Network.requestWillBeSent",
            on_request,
        )
        cdp.on(
            "Network.responseReceived",
            on_response,
        )
        cdp.on(
            "Network.dataReceived",
            on_data,
        )
        cdp.on(
            "Network.loadingFinished",
            on_finished,
        )
        cdp.on(
            "Network.loadingFailed",
            on_failed,
        )

        print()
        print("=" * 64)
        print("LIVE CLAUDE SSE -> PARSER VALIDATION")
        print("=" * 64)
        print()
        print("Use the dedicated Claude Chrome window.")
        print()
        print("Enter:")
        print()
        print("  Reply with exactly: AINTERCEPTOR-SSE-PARSER-TEST")
        print()
        print("Wait until Claude finishes completely.")
        print("Then return here and press ENTER.")
        print()
        print("No Claude response text will be displayed.")
        print("=" * 64)
        print()

        await asyncio.to_thread(
            input,
            "Press ENTER after Claude finishes... ",
        )

        # Give the CDP event loop time to finish all callbacks.
        try:
            await asyncio.wait_for(
                network_done.wait(),
                timeout=10,
            )
        except asyncio.TimeoutError:
            print(
                "[INFO] Network lifecycle did not signal completion "
                "within 10 seconds."
            )

        # Allow any streamResourceContent task to finish.
        await asyncio.sleep(1)

        # Flush parser tail.
        tail_events = parser.finish()

        for event in tail_events:
            state["parser_events"] += 1

            if event.delta:
                state["delta_events"] += 1
                state["delta_chars"] += len(event.delta)

            if event.done:
                state["done_events"] += 1

            if event.finish_reason:
                if event.finish_reason not in state["finish_reasons"]:
                    state["finish_reasons"].append(
                        event.finish_reason
                    )

        print()
        print("=" * 64)
        print("VALIDATION SUMMARY")
        print("=" * 64)

        print(
            f"Completion request observed : "
            f"{state['request_id'] is not None}"
        )
        print(
            f"HTTP status                 : "
            f"{state['status']}"
        )
        print(
            f"Content-Type                : "
            f"{state['content_type']}"
        )
        print(
            f"Stream enabled              : "
            f"{state['stream_enabled']}"
        )
        print(
            f"Stream enable error         : "
            f"{state['stream_enable_error']}"
        )
        print(
            f"Network data chunks         : "
            f"{state['chunks']}"
        )
        print(
            f"Decoded payload bytes       : "
            f"{state['bytes']}"
        )
        print(
            f"Parsed SSE events           : "
            f"{state['parser_events']}"
        )
        print(
            f"Delta events                : "
            f"{state['delta_events']}"
        )
        print(
            f"Delta character count       : "
            f"{state['delta_chars']}"
        )
        print(
            f"DONE events                 : "
            f"{state['done_events']}"
        )
        print(
            f"Finish reasons              : "
            f"{state['finish_reasons']}"
        )
        print(
            f"Network loadingFinished     : "
            f"{state['finished']}"
        )
        print(
            f"Network loadingFailed      : "
            f"{state['failed']}"
        )
        print(
            f"Network failure             : "
            f"{state['failed_error']}"
        )

        transport_pass = (
            state["request_id"] is not None
            and state["status"] == 200
            and "text/event-stream"
            in (state["content_type"] or "").lower()
            and state["chunks"] > 0
            and state["bytes"] > 0
        )

        parser_pass = (
            state["parser_events"] > 0
            and state["delta_events"] > 0
        )

        terminal_pass = (
            state["done_events"] > 0
            or len(state["finish_reasons"]) > 0
            or state["finished"]
        )

        overall = (
            transport_pass
            and parser_pass
            and terminal_pass
        )

        print()
        print(
            "TRANSPORT PAYLOAD CHECK :",
            "PASS" if transport_pass else "FAIL",
        )
        print(
            "SSE PARSER CHECK        :",
            "PASS" if parser_pass else "FAIL",
        )
        print(
            "TERMINAL STREAM CHECK   :",
            "PASS" if terminal_pass else "FAIL",
        )
        print()
        print(
            "OVERALL LIVE VALIDATION :",
            "PASS" if overall else "FAIL",
        )
        print()

        await cdp.detach()

        return 0 if overall else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
