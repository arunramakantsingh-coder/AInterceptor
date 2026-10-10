import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SESSION_FILE = Path(r"C:\\Projects\\AInterceptor\\backend\\sessions\\claude_storage_state.json")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        context = await browser.new_context()

        page = await context.new_page()

        print("Opening Claude...")
        await page.goto(
            "https://claude.ai/",
            wait_until="domcontentloaded",
            timeout=60000,
        )

        print()
        print("==============================================")
        print(" MANUAL CLAUDE LOGIN")
        print("==============================================")
        print("Complete the Claude login manually in Chromium.")
        print("Do NOT paste credentials into this terminal.")
        print()
        print("After you are fully logged in and Claude's")
        print("normal chat interface is visible, return here.")
        print("==============================================")
        print()

        input("Press ENTER here after login is complete... ")

        await page.wait_for_timeout(3000)

        print()
        print("Current URL:", page.url)

        if "/login" in page.url or "/auth" in page.url:
            raise RuntimeError(
                "Claude still appears to be on an authentication page."
            )

        await context.storage_state(path=str(SESSION_FILE))

        print()
        print("Storage state saved.")
        print("File:", SESSION_FILE)
        print("Size:", SESSION_FILE.stat().st_size, "bytes")

        await browser.close()

asyncio.run(main())
