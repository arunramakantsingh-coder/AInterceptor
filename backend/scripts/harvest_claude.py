"""Harvest Claude web session once (headed). Saves sessions/claude.json."""
import asyncio, pathlib, sys
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SESSION = ROOT / "sessions" / "claude.json"
SESSION.parent.mkdir(exist_ok=True)


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto("https://claude.ai/")

        print("\n==> Log in to Claude in the browser window.")
        print("==> When you reach the main chat screen, press ENTER here.\n")
        input()

        state = await ctx.storage_state()
        import json
        SESSION.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(f"[OK] session saved: {SESSION}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
