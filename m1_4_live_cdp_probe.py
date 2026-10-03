import asyncio
from playwright.async_api import async_playwright

CDP_URL = "http://127.0.0.1:9222"

async def main():
    async with async_playwright() as p:
        print("Connecting to existing Chrome through CDP...")
        browser = await p.chromium.connect_over_cdp(CDP_URL)

        contexts = browser.contexts
        if not contexts:
            raise RuntimeError("No browser contexts found.")

        context = contexts[0]

        claude_pages = [
            page for page in context.pages
            if "claude.ai" in page.url
        ]

        if not claude_pages:
            raise RuntimeError("No claude.ai page found.")

        page = claude_pages[0]

        print("Claude page:", page.url)
        print("Claude title:", await page.title())

        cdp = await context.new_cdp_session(page)

        requests = {}
        completion_candidates = set()
        response_candidates = set()
        data_counts = {}

        def is_candidate(url):
            lower = url.lower()
            return (
                "completion" in lower
                or "chat_conversations" in lower
                or "/api/" in lower
            )

        def on_request(params):
            request = params.get("request") or {}
            request_id = params.get("requestId")
            url = request.get("url", "")
            method = request.get("method", "")

            if is_candidate(url):
                requests[request_id] = {
                    "url": url,
                    "method": method,
                }

                print()
                print("[REQUEST]")
                print("method:", method)
                print("url:", url)

                if (
                    method.upper() == "POST"
                    and (
                        "completion" in url.lower()
                        or "chat_conversations" in url.lower()
                    )
                ):
                    completion_candidates.add(request_id)

        def on_response(params):
            request_id = params.get("requestId")
            response = params.get("response") or {}
            url = response.get("url", "")

            if request_id in completion_candidates or is_candidate(url):
                response_candidates.add(request_id)

                headers = {
                    str(k).lower(): str(v)
                    for k, v in (response.get("headers") or {}).items()
                }

                print()
                print("[RESPONSE]")
                print("status:", response.get("status"))
                print("mimeType:", response.get("mimeType"))
                print("content-type:", headers.get("content-type", ""))
                print("url:", url)

        def on_data(params):
            request_id = params.get("requestId")

            if request_id in completion_candidates or request_id in response_candidates:
                encoded_length = len(params.get("data", "") or "")
                data_counts[request_id] = data_counts.get(request_id, 0) + 1

                print(
                    "[DATA]",
                    "requestId=", request_id,
                    "chunk=", data_counts[request_id],
                    "encoded_length=", encoded_length,
                )

        def on_finished(params):
            request_id = params.get("requestId")

            if request_id in completion_candidates or request_id in response_candidates:
                print(
                    "[FINISHED]",
                    request_id
                )

        def on_failed(params):
            request_id = params.get("requestId")

            if request_id in completion_candidates or request_id in response_candidates:
                print(
                    "[FAILED]",
                    request_id,
                    params.get("errorText")
                )

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

        cdp.on("Network.requestWillBeSent", on_request)
        cdp.on("Network.responseReceived", on_response)
        cdp.on("Network.dataReceived", on_data)
        cdp.on("Network.loadingFinished", on_finished)
        cdp.on("Network.loadingFailed", on_failed)

        print()
        print("==============================================")
        print("LIVE CDP NETWORK OBSERVER ACTIVE")
        print("==============================================")
        print()
        print("Now use the dedicated Claude window.")
        print()
        print("Enter a simple test prompt such as:")
        print()
        print("  Reply with exactly: AINTERCEPTOR-CDP-TEST")
        print()
        print("Wait until Claude finishes the response.")
        print("Then return to this terminal and press ENTER.")
        print()
        print("The probe records request metadata and chunk counts.")
        print("It does NOT print response bodies.")
        print("==============================================")
        print()

        input("Press ENTER after Claude finishes the response... ")

        print()
        print("==============================================")
        print("LIVE TRANSPORT SUMMARY")
        print("==============================================")

        print("Candidate requests:", len(completion_candidates))
        print("Candidate responses:", len(response_candidates))

        for request_id in completion_candidates:
            info = requests.get(request_id, {})
            print()
            print("REQUEST ID:", request_id)
            print("METHOD:", info.get("method"))
            print("URL:", info.get("url"))
            print("DATA CHUNKS:", data_counts.get(request_id, 0))

        print()
        print("=== PROBE COMPLETE ===")

        await cdp.detach()
        await browser.close()

asyncio.run(main())
