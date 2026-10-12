import asyncio, sys, pathlib, json
sys.path.insert(0, "backend")
sys.path.insert(0, ".")

from patchright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        page = None
        for p in ctx.pages:
            if "chatgpt.com" in (p.url or ""):
                page = p
                break
        if not page:
            print("no chatgpt tab"); return 1

        print(f"tab url: {page.url}")

        # raw CDP attach with default buffering
        cdp = await page.context.new_cdp_session(page)
        await cdp.send("Network.enable")

        body_parts = bytearray()
        active_ids = set()

        def on_req(ev):
            req = ev.get("request") or {}
            url = (req.get("url") or "").lower()
            if req.get("method") == "POST" and "backend-api/f/conversation" in url and "prepare" not in url:
                active_ids.add(ev.get("requestId"))
                print(f"  tracked: {ev.get('requestId')}")

        def on_resp(ev):
            rid = ev.get("requestId")
            if rid in active_ids:
                h = (ev.get("response") or {}).get("headers") or {}
                ct = h.get("content-type") or h.get("Content-Type")
                print(f"  response for {rid}: ctype={ct}")

        def on_data(ev):
            rid = ev.get("requestId")
            if rid in active_ids:
                import base64
                try:
                    body_parts.extend(base64.b64decode(ev.get("data") or ""))
                except Exception:
                    pass

        cdp.on("Network.requestWillBeSent", on_req)
        cdp.on("Network.responseReceived", on_resp)
        cdp.on("Network.dataReceived", on_data)

        # submit
        box = page.locator("#prompt-textarea").first
        if await box.count() == 0:
            box = page.locator('div[contenteditable="true"]').first
        await box.click()
        await box.fill("ping")
        await box.press("Enter")

        # wait for stream to end
        await asyncio.sleep(12)

        raw = bytes(body_parts)
        print(f"\n=== captured {len(raw)} bytes ===")

        # save
        out = pathlib.Path(".evidence/raw/chatgpt_manual.sse")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)
        print(f"saved: {out}")
        print("\n=== first 2000 chars ===")
        print(raw[:2000].decode("utf-8", errors="replace"))
        print("\n=== last 500 chars ===")
        print(raw[-500:].decode("utf-8", errors="replace"))

        await cdp.detach()
        return 0

sys.exit(asyncio.run(main()))
