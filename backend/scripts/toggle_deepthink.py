
import asyncio, sys, pathlib
sys.path.insert(0, r"C:\Projects\AInterceptor-M1.5\backend")
from playwright.async_api import async_playwright

TOGGLE_SELECTORS = [
    # DeepSeek's DeepThink toggle variants observed across UI versions
    "button:has-text('DeepThink')",
    "button:has-text('Deep Think')",
    "[role='button']:has-text('DeepThink')",
    "[role='button']:has-text('Deep Think')",
    "div[class*='think'] button",
    "button[aria-label*='think' i]",
    "button[aria-label*='DeepThink' i]",
    "button[aria-pressed]",
]

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
        ctx = browser.contexts[0]
        page = None
        for p in ctx.pages:
            if "deepseek.com" in (p.url or ""):
                page = p
                break
        if page is None:
            print("[FAIL] no deepseek page found"); return 1

        await page.bring_to_front()
        await asyncio.sleep(0.5)

        found = None
        for sel in TOGGLE_SELECTORS:
            try:
                loc = page.locator(sel)
                n = await loc.count()
                if n > 0 and await loc.first.is_visible():
                    found = loc.first
                    print(f"[OK] toggle candidate: {sel}")
                    break
            except Exception:
                continue

        if found is None:
            print("[WARN] no toggle found — toggle manually and rerun")
            return 0

        pressed = await found.get_attribute("aria-pressed")
        cls = await found.get_attribute("class") or ""
        text = (await found.inner_text()).strip()
        print(f"     aria-pressed={pressed} class={cls[:60]} text={text[:40]!r}")

        # If it looks ON, click it OFF
        looks_on = (pressed == "true") or ("active" in cls.lower()) or ("on" in cls.lower())
        if looks_on:
            await found.click()
            await asyncio.sleep(0.5)
            print("[OK] clicked toggle OFF")
        else:
            print("[OK] toggle already OFF (or unknown state — verify in browser)")
        return 0

sys.exit(asyncio.run(main()))
