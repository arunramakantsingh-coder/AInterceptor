import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        print("Connecting to Chrome through CDP...")
        browser = await p.chromium.connect_over_cdp(
            "http://127.0.0.1:9222"
        )

        contexts = browser.contexts

        print("Contexts:", len(contexts))

        if not contexts:
            raise RuntimeError("No browser context available.")

        context = contexts[0]
        pages = context.pages

        print("Pages:", len(pages))

        for index, page in enumerate(pages):
            print(f"PAGE {index}: {page.url}")

        claude_pages = [
            page for page in pages
            if "claude.ai" in page.url
        ]

        if not claude_pages:
            raise RuntimeError(
                "No Claude page found in the CDP-connected browser."
            )

        page = claude_pages[0]

        print("Claude URL:", page.url)
        print("Claude title:", await page.title())

        if "/login" in page.url or "/auth" in page.url:
            raise RuntimeError(
                "Claude is still on an authentication page."
            )

        print("")
        print("AUTHENTICATED CLAUDE SESSION CONFIRMED")

        await browser.close()

asyncio.run(main())
