"""Read-only provider probe (admin CLI).

Connects to the running daemon's Chrome via CDP, inspects each active
provider's tab, and classifies its state. Sends NO messages. Safe to
run at any time.

States:
  REACHABLE        tab open, past login wall, chat input present
  LOGIN_REQUIRED   URL matches provider login markers
  CLOUDFLARE       page title/URL indicates CF challenge
  SESSION_EXPIRED  no login URL but no chat input either
  NO_TAB           no matching tab in the browser
  DOWN             CDP unreachable or page evaluate failed
"""
from __future__ import annotations
import asyncio
import json
import pathlib
import sys
import urllib.request

# make backend importable
_HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent))

CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"

# domain keyword per provider — used to locate the tab
PROVIDER_HOSTS = {
    "claude": "claude.ai",
    "chatgpt": "chatgpt.com",
    "gemini": "gemini.google.com",
    "deepseek": "chat.deepseek.com",
    "mistral": "chat.mistral.ai",
    "qwen": "chat.qwen.ai",
    "huggingchat": "huggingface.co",
    "perplexity": "perplexity.ai",
    "grok": "grok.com",
    "poe": "poe.com",
    "kimi": "kimi.com",
    "yi": "yi.com",
    "lechat": "chat.mistral.ai",
    "glm": "chatglm.cn",
    "you": "you.com",
    "phind": "phind.com",
    "doubao": "doubao.com",
    "copilot": "copilot.microsoft.com",
    "meta": "meta.ai",
    "character": "character.ai",
}

CHAT_INPUT_SELECTORS = [
    'div[contenteditable="true"]',
    'textarea[placeholder]',
    '[role="textbox"]',
    '#prompt-textarea',
    'textarea#prompt-textarea',
    'div.ProseMirror',
]

# text on the page indicating "not logged in" even though URL is clean
ANON_MARKERS = (
    "log in to get answers",
    "sign up for free",
    "log in to chat",
    "sign in to continue",
    "please log in",
    "please sign in",
)

CF_MARKERS = (
    "just a moment",
    "checking your browser",
    "attention required",
    "cf-challenge",
)


def _http_get_json(path: str, timeout: float = 2.0):
    with urllib.request.urlopen(f"{CDP_URL}{path}", timeout=timeout) as r:
        return json.loads(r.read())


def cdp_alive() -> bool:
    try:
        v = _http_get_json("/json/version", 1.5)
        return "Browser" in v
    except Exception:
        return False


def get_active_providers() -> list[str]:
    try:
        from app.control_plane.state import get_state
        return list(get_state().list_active())
    except Exception:
        return ["chatgpt", "claude", "gemini", "deepseek"]


def url_matches_provider(url: str, provider: str) -> bool:
    host = PROVIDER_HOSTS.get(provider)
    return bool(host and host.lower() in (url or "").lower())


def is_login_url(provider: str, url: str) -> bool:
    try:
        from app.runtime.login_helper import LOGIN_MARKERS
        markers = LOGIN_MARKERS.get(provider, ("/login", "/auth", "/signin"))
    except Exception:
        markers = ("/login", "/auth", "/signin")
    u = (url or "").lower()
    return any(m.lower() in u for m in markers)


async def _probe_page(page, provider: str) -> dict:
    try:
        url = page.url or ""
        title = await page.title()
    except Exception as e:
        return {"provider": provider, "state": "DOWN", "detail": str(e)[:120]}

    tl = title.lower()
    ul = url.lower()

    if any(m in tl or m in ul for m in CF_MARKERS):
        return {"provider": provider, "state": "CLOUDFLARE",
                "url": url[:90], "title": title[:70]}

    # Anonymous page check (URL clean but body shows "Log in" prompt)
    try:
        body_text = (await page.evaluate("document.body.innerText") or "").lower()
    except Exception:
        body_text = ""
    if body_text and any(m in body_text for m in ANON_MARKERS):
        return {"provider": provider, "state": "LOGIN_REQUIRED",
                "url": url[:90], "title": title[:70],
                "detail": "anonymous page (login prompt in body)"}

    if is_login_url(provider, url):
        return {"provider": provider, "state": "LOGIN_REQUIRED",
                "url": url[:90], "title": title[:70]}

    found = None
    for sel in CHAT_INPUT_SELECTORS:
        try:
            el = await page.query_selector(sel)
            if el:
                found = sel
                break
        except Exception:
            continue

    if found:
        return {"provider": provider, "state": "REACHABLE",
                "url": url[:90], "title": title[:70], "selector": found}

    return {"provider": provider, "state": "SESSION_EXPIRED",
            "url": url[:90], "title": title[:70],
            "detail": "no chat input found"}


async def run(providers: list[str]) -> int:
    if not cdp_alive():
        print("=" * 60)
        print("PROBE — FAIL")
        print("=" * 60)
        print("CDP not reachable on port 9222.")
        print("The daemon is probably not running.")
        print()
        print("  start it:   cd ~/ainterceptor && ./run-linux.sh")
        print("  check state: astatus")
        return 2

    try:
        from patchright.async_api import async_playwright
    except ImportError as e:
        print(f"[FAIL] patchright not installed: {e}")
        return 2

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.connect_over_cdp(CDP_URL)
        pages = []
        for ctx in browser.contexts:
            try:
                pages.extend(ctx.pages)
            except Exception:
                continue
    except Exception as e:
        print(f"[FAIL] could not attach: {e}")
        await pw.stop()
        return 2

    results: list[dict] = []
    for provider in providers:
        match = None
        for p in pages:
            try:
                if url_matches_provider(p.url or "", provider):
                    match = p
                    break
            except Exception:
                continue
        if match is None:
            results.append({"provider": provider, "state": "NO_TAB",
                            "detail": "no matching tab found"})
            continue
        results.append(await _probe_page(match, provider))

    try:
        await browser.close()
    except Exception:
        pass
    await pw.stop()

    # ── output ──────────────────────────────────────────────────
    icon = {
        "REACHABLE":       "[ OK ]",
        "LOGIN_REQUIRED":  "[ AUTH ]",
        "CLOUDFLARE":      "[ CF ]",
        "SESSION_EXPIRED": "[ EXP ]",
        "NO_TAB":          "[ NONE ]",
        "DOWN":            "[ DOWN ]",
    }
    print("=" * 60)
    print(f"PROBE — read-only check of {len(results)} provider(s)")
    print("=" * 60)
    for r in results:
        print(f"  {icon.get(r['state'], '[ ?? ]'):9s} {r['provider']:12s}  {r['state']}")
        if r.get("title"):
            print(f"             title: {r['title']}")
        if r.get("url"):
            print(f"             url:   {r['url']}")
        if r.get("detail"):
            print(f"             note:  {r['detail']}")
    print("=" * 60)

    ok = sum(1 for r in results if r["state"] == "REACHABLE")
    print(f"RESULT: {ok}/{len(results)} reachable")

    hints: list[str] = []
    for r in results:
        if r["state"] == "LOGIN_REQUIRED":
            hints.append(f"  {r['provider']}: run `alogin {r['provider']}` (needs VNC)")
        elif r["state"] == "SESSION_EXPIRED":
            hints.append(f"  {r['provider']}: session lost — run `alogin {r['provider']}`")
        elif r["state"] == "CLOUDFLARE":
            hints.append(f"  {r['provider']}: Cloudflare challenge — reload the tab or wait 1-2 min")
        elif r["state"] == "NO_TAB":
            hints.append(f"  {r['provider']}: no tab — restart daemon (./run-linux.sh)")
        elif r["state"] == "DOWN":
            hints.append(f"  {r['provider']}: tab unreachable — check daemon")
    if hints:
        print()
        print("Next steps:")
        for h in hints:
            print(h)

    return 0 if ok == len(results) else 1


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help", "help"):
        print("usage: aprobe [provider ...]")
        print("       aprobe              probe all active providers")
        print("       aprobe claude       probe one")
        return 0
    if args:
        providers = [a.lower() for a in args if a]
    else:
        providers = get_active_providers()
    return asyncio.run(run(providers))


if __name__ == "__main__":
    sys.exit(main())
