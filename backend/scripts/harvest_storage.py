
"""One-time: pull cookies + storage from the running CDP Chromes so we
can run future chats in a hidden headless browser.
"""
import asyncio, json, pathlib, sys
from playwright.async_api import async_playwright

TARGETS = {
    "deepseek": "http://127.0.0.1:9223",
    "claude":   "http://127.0.0.1:9222",
    "chatgpt":  "http://127.0.0.1:9224",
    "gemini":   "http://127.0.0.1:9225",
}

async def harvest(name, cdp_url):
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(cdp_url)
            if not browser.contexts:
                print(f"[{name}] no context on {cdp_url}"); return False
            ctx = browser.contexts[0]
            state = await ctx.storage_state()
            out = pathlib.Path(".ainterceptor") / name / "storage_state.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(state, indent=2), encoding="utf-8")
            ck = len(state.get("cookies", []))
            print(f"[{name}] saved {ck} cookies -> {out}")
            return True
    except Exception as e:
        print(f"[{name}] FAIL: {e}")
        return False

async def main():
    ok = 0
    for name, url in TARGETS.items():
        if await harvest(name, url):
            ok += 1
    print(f"harvested {ok}/{len(TARGETS)}")
    return 0

sys.exit(asyncio.run(main()))
