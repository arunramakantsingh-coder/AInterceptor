import pathlib, subprocess

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend"
(BE / "scripts").mkdir(exist_ok=True)

probe = r'''"""DOM probe — dumps provider composer candidates.

Run inside the container:
    docker compose exec api python scripts/probe_providers.py
"""
import asyncio, json, sys, os, pathlib
sys.path.insert(0, "/app/backend")

from app.db.session import SessionLocal
from app.db.models import UserSession
from app.crypto.aes import decrypt_for_user

PROVIDERS = {
    "claude":   "https://claude.ai/",
    "chatgpt":  "https://chatgpt.com/",
    "gemini":   "https://gemini.google.com/",
    "deepseek": "https://chat.deepseek.com/",
}


async def probe_one(provider, home_url, state):
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-gpu",
        ])
        try:
            ctx = await browser.new_context(
                storage_state=state,
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/130.0.0.0 Safari/537.36"),
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            page = await ctx.new_page()
            await page.goto(home_url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4.0)
            url = page.url
            title = await page.title()

            # Dump all interactive candidates
            js = r"""
                () => {
                    const out = { textareas: [], contenteditables: [], buttons: [] };
                    document.querySelectorAll('textarea').forEach(el => {
                        out.textareas.push({
                            placeholder: el.placeholder || "",
                            id: el.id || "",
                            classes: (el.className||"").toString().slice(0,150),
                            visible: !!(el.offsetParent),
                            disabled: el.disabled,
                        });
                    });
                    document.querySelectorAll('[contenteditable]').forEach(el => {
                        out.contenteditables.push({
                            role: el.getAttribute('role')||"",
                            classes: (el.className||"").toString().slice(0,150),
                            ariaLabel: el.getAttribute('aria-label')||"",
                            dataTestId: el.getAttribute('data-testid')||"",
                            visible: !!(el.offsetParent),
                            editable: el.isContentEditable,
                        });
                    });
                    document.querySelectorAll('button').forEach(el => {
                        const t = (el.innerText||"").trim().slice(0,40);
                        const a = (el.getAttribute('aria-label')||"").slice(0,40);
                        if (t || a) out.buttons.push({text:t, ariaLabel:a,
                            classes:(el.className||"").toString().slice(0,100),
                            disabled: el.disabled});
                    });
                    return out;
                }
            """
            try:
                dump = await page.evaluate(js)
            except Exception as e:
                dump = {"error": str(e)}

            print(f"\n=== {provider} ===")
            print(f"URL   : {url}")
            print(f"TITLE : {title}")
            print(f"TEXTAREAS ({len(dump.get('textareas', []))}):")
            for t in dump.get("textareas", [])[:8]:
                print(f"  placeholder={t['placeholder']!r} id={t['id']!r} "
                      f"visible={t['visible']} disabled={t['disabled']}")
                print(f"    classes={t['classes']!r}")
            print(f"CONTENTEDITABLES ({len(dump.get('contenteditables', []))}):")
            for c in dump.get("contenteditables", [])[:8]:
                print(f"  role={c['role']!r} visible={c['visible']} "
                      f"editable={c['editable']} aria={c['ariaLabel']!r} test={c['dataTestId']!r}")
                print(f"    classes={c['classes']!r}")
            print(f"BUTTONS (showing send-like, first 5):")
            for b in dump.get("buttons", [])[:5]:
                print(f"  text={b['text']!r} aria={b['ariaLabel']!r} disabled={b['disabled']}")
        finally:
            await browser.close()


async def main():
    db = SessionLocal()
    rows = db.query(UserSession).all()
    if not rows:
        print("no sessions in DB")
        return
    for r in rows:
        provider = r.provider
        if provider not in PROVIDERS:
            continue
        try:
            raw = decrypt_for_user(r.user_id, r.encrypted_blob, r.nonce)
            state = json.loads(raw)
        except Exception as e:
            print(f"[{provider}] decrypt failed: {e}")
            continue
        try:
            await probe_one(provider, PROVIDERS[provider], state)
        except Exception as e:
            print(f"[{provider}] probe failed: {e}")
    db.close()


if __name__ == "__main__":
    asyncio.run(main())
'''

(BE / "scripts" / "probe_providers.py").write_text(probe, encoding="utf-8", newline="\n")
print("  [OK] backend/scripts/probe_providers.py")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","debug: provider DOM probe (dumps composer candidates)"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("Now run the probe inside the container:")
print()
print("  docker compose exec api python scripts/probe_providers.py")
