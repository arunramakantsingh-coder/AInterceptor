import asyncio, sys, pathlib
sys.path.insert(0, str(pathlib.Path("backend")))
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
        ctx = browser.contexts[0]
        page = None
        for p in ctx.pages:
            if "deepseek.com" in (p.url or ""):
                page = p
                break
        if not page:
            print("[FAIL] no deepseek page"); return 1

        print("URL:", page.url)
        print("=" * 60)

        # Probe many selectors
        selectors = [
            ".ds-markdown",
            ".ds-markdown--block",
            "[class*='ds-markdown']",
            "[class*='markdown']",
            "[data-message-author-role]",
            "[data-message-author-role='assistant']",
            ".model-response-text",
            "message-content",
            "[class*='message']",
            "[class*='Message']",
            "div[class*='chat']",
        ]
        print("SELECTOR COUNTS:")
        for s in selectors:
            try:
                n = await page.locator(s).count()
                print(f"  {n:>3}  {s}")
            except Exception as e:
                print(f"  ERR  {s}: {e}")

        print("=" * 60)
        # Dump the last 5 elements that look like messages
        print("DUMP of last assistant-looking node:")
        js = r"""
            () => {
                const out = [];
                // Walk all elements, find those whose text is > 20 chars
                // and look like a chat message
                const all = document.querySelectorAll('div');
                const hits = [];
                for (const el of all) {
                    const t = (el.innerText || "").trim();
                    if (t.length < 20 || t.length > 5000) continue;
                    const cls = el.className || "";
                    if (typeof cls !== "string") continue;
                    if (!cls.match(/markdown|message|chat|bubble|response/i)) continue;
                    hits.push({
                        tag: el.tagName,
                        cls: cls.slice(0, 120),
                        text: t.slice(0, 80),
                        depth: (function(n){let d=0;while(n.parentElement){d++;n=n.parentElement;}return d;})(el),
                    });
                }
                // deduplicate by (cls, text)
                const seen = new Set();
                const uniq = [];
                for (const h of hits) {
                    const k = h.cls + "|" + h.text;
                    if (seen.has(k)) continue;
                    seen.add(k);
                    uniq.push(h);
                }
                return uniq.slice(-15);
            }
        """
        try:
            rows = await page.evaluate(js)
            for r in rows:
                print(f"  depth={r['depth']:<3} cls={r['cls']!r}")
                print(f"           text={r['text']!r}")
        except Exception as e:
            print("evaluate failed:", e)

        return 0

sys.exit(asyncio.run(main()))
