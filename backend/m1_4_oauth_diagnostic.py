import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        def on_console(msg):
            print(f"[CONSOLE] {msg.type}: {msg.text}")

        def on_page_error(exc):
            print(f"[PAGE ERROR] {exc}")

        page.on("console", on_console)
        page.on("pageerror", on_page_error)

        print("Opening Claude...")
        await page.goto(
            "https://claude.ai/login",
            wait_until="domcontentloaded",
            timeout=60000,
        )

        print()
        print("==============================================")
        print("Click 'Continue with Google' manually.")
        print("==============================================")
        print()

        try:
            async with context.expect_page(timeout=15000) as popup_info:
                await page.get_by_text("Continue with Google").click()

            popup = await popup_info.value

            print()
            print("=== POPUP DETECTED ===")
            print("Initial URL:", popup.url)

            popup.on(
                "framenavigated",
                lambda frame: print(
                    "[NAVIGATION]",
                    frame.url
                )
            )

            await popup.wait_for_load_state(
                "domcontentloaded",
                timeout=30000
            )

            print("Final URL:", popup.url)
            print("Title:", await popup.title())

        except Exception as exc:
            print()
            print("=== POPUP DIAGNOSTIC RESULT ===")
            print(type(exc).__name__, str(exc))

        print()
        print("Browser will remain open for 30 seconds.")
        await page.wait_for_timeout(30000)

        await browser.close()

asyncio.run(main())
