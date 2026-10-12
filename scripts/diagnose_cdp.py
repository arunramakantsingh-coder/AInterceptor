import asyncio, sys, pathlib
sys.path.insert(0, "backend")

from patchright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        # Attach to daemon's Chrome on 9222
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        # Find the ChatGPT tab
        page = None
        for p in ctx.pages:
            if "chatgpt.com" in (p.url or ""):
                page = p
                break
        if not page:
            print("no chatgpt tab"); return 1

        print(f"tab url: {page.url}")
        print("submitting 'ping' and dumping all matching requests...")

        # Attach CDP raw
        cdp = await page.context.new_cdp_session(page)
        # Try WITHOUT maxTotalBufferSize override
        await cdp.send("Network.enable")

        seen = []

        def on_req(ev):
            req = ev.get("request") or {}
            if req.get("method") in ("POST", "PUT"):
                seen.append({
                    "url": req.get("url", "")[:120],
                    "method": req.get("method"),
                })

        def on_resp(ev):
            resp = ev.get("response") or {}
            url = resp.get("url", "")[:120]
            h = resp.get("headers") or {}
            ct = h.get("content-type") or h.get("Content-Type") or "?"
            for s in seen:
                if s["url"] == url[:120]:
                    s["status"] = resp.get("status")
                    s["ctype"] = ct

        cdp.on("Network.requestWillBeSent", on_req)
        cdp.on("Network.responseReceived", on_resp)

        # Submit
        box = page.locator("#prompt-textarea").first
        if await box.count() == 0:
            box = page.locator('div[contenteditable="true"]').first
        await box.click()
        await box.fill("ping")
        await box.press("Enter")
        await asyncio.sleep(8)

        print("\nAll POST/PUT requests seen:")
        for s in seen:
            print(f"  {s.get('status','?')}  {s.get('ctype','?')[:40]:40}  {s['url']}")

        await cdp.detach()
        return 0

sys.exit(asyncio.run(main()))
