"""Admin CLI for AInterceptor (Linux).

One entry point, five commands:
    providers [list|enable|disable|info]
    login   <provider>     bring Chrome on-screen, wait, save storage_state
    logout  <provider>     clear only that provider's cookies (CDP)
    show                   move all Chrome windows on-screen
    hide                   move all Chrome windows off-screen

Designed for the Debian VM + Xvfb :99 + x11vnc setup.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import pathlib
import subprocess
import sys
import time

# ── paths ───────────────────────────────────────────────────────────
_HERE = pathlib.Path(__file__).resolve()
ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

ENV_FILE   = ROOT / ".env"
EXPORT_DIR = ROOT / ".ainterceptor" / "exports"

CDP_PORT = 9222
CDP_URL  = f"http://127.0.0.1:{CDP_PORT}"

# ── provider tables ─────────────────────────────────────────────────
ALL_PROVIDERS = [
    # tier 1 (original 10)
    "claude", "chatgpt", "gemini", "deepseek", "mistral",
    "qwen", "huggingchat", "perplexity", "grok", "poe",
    # tier A (10 more)
    "kimi", "yi", "lechat", "glm", "you",
    "phind", "doubao", "copilot", "meta", "character",
]

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

PROVIDER_URLS = {
    "claude":      "https://claude.ai/",
    "chatgpt":     "https://chatgpt.com/",
    "gemini":      "https://gemini.google.com/app",
    "deepseek":    "https://chat.deepseek.com/",
    "mistral":     "https://chat.mistral.ai/",
    "qwen":        "https://chat.qwen.ai/",
    "huggingchat": "https://huggingface.co/chat/",
    "perplexity":  "https://www.perplexity.ai/",
    "grok":        "https://grok.com/",
    "poe":         "https://poe.com/",
    "kimi":        "https://kimi.com/",
    "yi":          "https://www.yi.com/",
    "lechat":      "https://chat.mistral.ai/",
    "glm":         "https://chatglm.cn/",
    "you":         "https://you.com/",
    "phind":       "https://www.phind.com/",
    "doubao":      "https://www.doubao.com/",
    "copilot":     "https://copilot.microsoft.com/",
    "meta":        "https://www.meta.ai/",
    "character":   "https://character.ai/",
}

# ── env helpers ─────────────────────────────────────────────────────
def read_env() -> dict[str, str]:
    d: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    return d


def write_env_key(key: str, value: str) -> None:
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    out: list[str] = []
    found = False
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(out) + "\n")


def active_providers() -> list[str]:
    raw = read_env().get("AINTERCEPTOR_ACTIVE_PROVIDERS", "")
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


def set_active_providers(names: list[str]) -> None:
    # preserve order, deduplicate
    seen: list[str] = []
    for n in names:
        if n and n not in seen:
            seen.append(n)
    write_env_key("AINTERCEPTOR_ACTIVE_PROVIDERS", ",".join(seen))


# ── xdotool helpers ─────────────────────────────────────────────────
def _xdotool_bin() -> str | None:
    try:
        r = subprocess.run(["which", "xdotool"], capture_output=True, text=True, timeout=3)
        return r.stdout.strip() or None
    except Exception:
        return None


def move_chrome_windows(x: int, y: int) -> int:
    """Move all Chrome windows to (x, y) via xdotool. Returns count moved."""
    if _xdotool_bin() is None:
        print("[warn] xdotool not installed — window move skipped")
        return 0
    wids: list[str] = []
    # try multiple search modes — Chrome window class is google-chrome / Google-chrome
    for args in (
        ["search", "--class", "google-chrome"],
        ["search", "--class", "Google-chrome"],
        ["search", "--name", "Chrome"],
        ["search", "--name", "ChatGPT"],
        ["search", "--name", "Claude"],
        ["search", "--name", "Gemini"],
        ["search", "--name", "DeepSeek"],
    ):
        try:
            r = subprocess.run(
                ["xdotool"] + args,
                capture_output=True, text=True, timeout=5,
                env={**os.environ, "DISPLAY": os.environ.get("AINTERCEPTOR_DISPLAY", ":99")},
            )
            wids.extend(w.strip() for w in r.stdout.split() if w.strip())
        except Exception:
            continue
    wids = list(dict.fromkeys(wids))  # unique, order-preserving
    moved = 0
    for wid in wids:
        env = {**os.environ,
               "DISPLAY": os.environ.get("AINTERCEPTOR_DISPLAY", ":99")}
        try:
            subprocess.run(["xdotool", "windowmove", wid, str(x), str(y)],
                           capture_output=True, timeout=5, env=env)
            subprocess.run(["xdotool", "windowraise", wid],
                           capture_output=True, timeout=5, env=env)
            moved += 1
        except Exception:
            continue
    return moved


# ── CDP helpers ─────────────────────────────────────────────────────
def cdp_alive() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=1.5) as r:
            return "Browser" in r.read().decode("utf-8", "replace")
    except Exception:
        return False


def require_cdp() -> bool:
    if cdp_alive():
        return True
    print("============================================================")
    print("CDP NOT AVAILABLE on port 9222")
    print("============================================================")
    print("The daemon is not running (or its Chrome is not up).")
    print()
    print("  start it:   cd ~/ainterceptor && ./run-linux.sh")
    print("  status:     astatus")
    return False


# ── providers subcommand ────────────────────────────────────────────
def cmd_providers_list() -> int:
    act = set(active_providers())
    print(f"{'PROVIDER':14s} {'STATUS':10s} {'HOST':28s}  LOGIN_URL")
    print("-" * 90)
    for p in ALL_PROVIDERS:
        status = "ACTIVE" if p in act else "inactive"
        host = PROVIDER_HOSTS.get(p, "?")
        url = PROVIDER_URLS.get(p, "?")
        print(f"{p:14s} {status:10s} {host:28s}  {url}")
    print("-" * 90)
    print(f"Active: {len(act)} of {len(ALL_PROVIDERS)}")
    print()
    print("Next:")
    print("  aproviders enable <name>     activate a provider")
    print("  aproviders disable <name>    deactivate a provider")
    print("  aproviders info <name>       detailed info")
    print("  aprobe                       health check of active providers")
    return 0


def cmd_providers_enable(name: str) -> int:
    name = name.lower().strip()
    if name not in ALL_PROVIDERS:
        print(f"[FAIL] unknown provider: {name}")
        print(f"       valid: {', '.join(ALL_PROVIDERS)}")
        return 1
    act = active_providers()
    if name in act:
        print(f"[i] {name} is already active")
        return 0
    act.append(name)
    set_active_providers(act)
    print(f"[OK] {name} enabled  (now {len(act)} active)")
    print()
    print("Restart the daemon to apply:")
    print("  pkill -f app.runtime.daemon && cd ~/ainterceptor && ./run-linux.sh")
    return 0


def cmd_providers_disable(name: str) -> int:
    name = name.lower().strip()
    if name not in ALL_PROVIDERS:
        print(f"[FAIL] unknown provider: {name}")
        return 1
    act = active_providers()
    if name not in act:
        print(f"[i] {name} is not active")
        return 0
    act = [p for p in act if p != name]
    set_active_providers(act)
    print(f"[OK] {name} disabled  ({len(act)} active remain)")
    print()
    print("Restart the daemon to apply:")
    print("  pkill -f app.runtime.daemon && cd ~/ainterceptor && ./run-linux.sh")
    return 0


def cmd_providers_info(name: str) -> int:
    name = name.lower().strip()
    if name not in ALL_PROVIDERS:
        print(f"[FAIL] unknown provider: {name}")
        return 1
    act = active_providers()
    print(f"Provider:  {name}")
    print(f"  status:  {'ACTIVE' if name in act else 'inactive'}")
    print(f"  host:    {PROVIDER_HOSTS.get(name, '?')}")
    print(f"  url:     {PROVIDER_URLS.get(name, '?')}")
    try:
        from app.runtime.login_helper import LOGIN_MARKERS
        markers = LOGIN_MARKERS.get(name, ())
        print(f"  login markers: {markers}")
    except Exception:
        pass
    return 0


def handle_providers(args: list[str]) -> int:
    if not args or args[0] in ("list", "ls"):
        return cmd_providers_list()
    sub = args[0].lower()
    if sub == "enable":
        if len(args) < 2:
            print("usage: aproviders enable <name>")
            return 1
        return cmd_providers_enable(args[1])
    if sub == "disable":
        if len(args) < 2:
            print("usage: aproviders disable <name>")
            return 1
        return cmd_providers_disable(args[1])
    if sub in ("info", "show"):
        if len(args) < 2:
            print("usage: aproviders info <name>")
            return 1
        return cmd_providers_info(args[1])
    if sub == "test":
        if len(args) < 2:
            print("usage: aproviders test <name>  (alias: aprobe <name>)")
            return 1
        # delegate to probe_live
        try:
            from scripts import probe_live
            return asyncio.run(probe_live.run([args[1].lower()]))
        except Exception as e:
            print(f"[FAIL] probe failed: {e}")
            return 1
    print(f"unknown subcommand: {sub}")
    print("usage: aproviders [list|enable <n>|disable <n>|info <n>|test <n>]")
    return 1


# ── login / logout ──────────────────────────────────────────────────
async def _do_login(provider: str) -> int:
    if not require_cdp():
        return 2
    provider = provider.lower()
    host = PROVIDER_HOSTS.get(provider)
    if not host:
        print(f"[FAIL] unknown provider: {provider}")
        return 1
    try:
        from patchright.async_api import async_playwright
    except ImportError:
        print("[FAIL] patchright not installed")
        return 2

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.connect_over_cdp(CDP_URL)
    except Exception as e:
        print(f"[FAIL] attach: {e}")
        await pw.stop()
        return 2

    target_page = None
    try:
        for ctx in browser.contexts:
            for pg in await ctx.pages() if hasattr(ctx.pages, "__call__") else ctx.pages:
                url = pg.url or ""
                if host in url:
                    target_page = pg
                    break
            if target_page:
                break
    except Exception as e:
        print(f"[warn] page scan: {e}")

    if target_page is None:
        print(f"[FAIL] no tab found for {provider} (host {host})")
        print("       restart the daemon to open the tab:")
        print("       pkill -f app.runtime.daemon && cd ~/ainterceptor && ./run-linux.sh")
        try:
            await browser.close()
        except Exception:
            pass
        await pw.stop()
        return 1

    # bring tab to front, move window on-screen
    try:
        await target_page.bring_to_front()
    except Exception:
        pass
    n = move_chrome_windows(100, 100)
    print(f"[OK] Chrome moved on-screen ({n} window(s))")

    # if we're on a login page, navigate to provider home to trigger the flow
    try:
        from app.runtime.login_helper import _is_login_page
        if _is_login_page(provider, target_page.url or ""):
            print(f"     navigating to {PROVIDER_URLS.get(provider)}")
            await target_page.goto(PROVIDER_URLS.get(provider),
                                   wait_until="domcontentloaded", timeout=45_000)
    except Exception as e:
        print(f"     [warn] navigate: {e}")

    print()
    print("============================================================")
    print(f" VNC is on 100.82.62.82:5900 — you should see Chrome")
    print(f" Log into {provider} in that window.")
    print(f" Then come back here; we poll every 2s for up to 5 minutes.")
    print("============================================================")

    t0 = time.monotonic()
    deadline = t0 + 300
    logged_in = False
    while time.monotonic() < deadline:
        await asyncio.sleep(2.0)
        try:
            url = target_page.url or ""
        except Exception:
            continue
        try:
            from app.runtime.login_helper import _is_login_page
            still_login = _is_login_page(provider, url)
        except Exception:
            still_login = "/login" in url or "/signin" in url
        if not still_login:
            # confirm stability
            await asyncio.sleep(2.0)
            try:
                url2 = target_page.url or ""
            except Exception:
                url2 = url
            try:
                from app.runtime.login_helper import _is_login_page
                still_login2 = _is_login_page(provider, url2)
            except Exception:
                still_login2 = "/login" in url2 or "/signin" in url2
            if not still_login2:
                logged_in = True
                break
        elapsed = int(time.monotonic() - t0)
        if elapsed % 30 < 2:
            print(f"     ...waiting ({elapsed}s)  current url: {url[:70]}")

    if not logged_in:
        move_chrome_windows(-32000, -32000)
        print(f"[FAIL] login not detected within 5 min")
        print("       try again: alogin " + provider)
        try:
            await browser.close()
        except Exception:
            pass
        await pw.stop()
        return 1

    took = int(time.monotonic() - t0)
    print(f"[OK] login detected after {took}s — saving storage_state")

    # capture storage_state via the attached context
    try:
        ctx = target_page.context
        state = await ctx.storage_state()
    except Exception as e:
        print(f"[FAIL] storage_state: {e}")
        move_chrome_windows(-32000, -32000)
        try:
            await browser.close()
        except Exception:
            pass
        await pw.stop()
        return 1

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    target = EXPORT_DIR / f"{provider}.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(target)

    move_chrome_windows(-32000, -32000)
    print(f"[OK] saved: {target}")
    print(f"     cookies: {len(state.get('cookies', []))}")
    print()
    print("Next:")
    print(f"  aprobe {provider}    confirm REACHABLE")
    print(f"  {provider}           start chatting")

    try:
        await browser.close()
    except Exception:
        pass
    await pw.stop()
    return 0


async def _do_logout(provider: str) -> int:
    if not require_cdp():
        return 2
    provider = provider.lower()
    host = PROVIDER_HOSTS.get(provider)
    if not host:
        print(f"[FAIL] unknown provider: {provider}")
        return 1
    try:
        from patchright.async_api import async_playwright
    except ImportError:
        print("[FAIL] patchright not installed")
        return 2

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.connect_over_cdp(CDP_URL)
    except Exception as e:
        print(f"[FAIL] attach: {e}")
        await pw.stop()
        return 2

    cleared = 0
    for ctx in browser.contexts:
        try:
            pages = ctx.pages
        except Exception:
            pages = []
        # need a page to open a CDP session
        page = pages[0] if pages else None
        if page is None:
            continue
        try:
            session = await ctx.new_cdp_session(page)
            await session.send("Storage.clearDataForOrigin", {
                "origin": f"https://{host}",
                "storageTypes": "cookies,local_storage,indexeddb,cache_storage",
            })
            cleared += 1
        except Exception as e:
            print(f"[warn] clear failed on one context: {e}")

    try:
        await browser.close()
    except Exception:
        pass
    await pw.stop()

    if cleared == 0:
        print(f"[warn] nothing cleared for {provider} (host {host})")
        return 1
    print(f"[OK] cleared cookies + storage for {provider} ({host})")
    print(f"     other providers in the same profile are unaffected")
    print()
    print("Next:")
    print(f"  alogin {provider}    log back in (VNC)")
    return 0


# ── show / hide ─────────────────────────────────────────────────────
def do_show() -> int:
    n = move_chrome_windows(100, 100)
    if n == 0:
        print("[warn] no Chrome windows found — is the daemon running?")
        print("       astatus")
        return 1
    print(f"[OK] Chrome moved on-screen ({n} window(s))")
    print("     VNC: 100.82.62.82:5900")
    return 0


def do_hide() -> int:
    n = move_chrome_windows(-32000, -32000)
    print(f"[OK] Chrome moved off-screen ({n} window(s))")
    return 0


# ── main ────────────────────────────────────────────────────────────
def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print("AInterceptor admin CLI")
        print()
        print("  aproviders [list|enable <n>|disable <n>|info <n>|test <n>]")
        print("  alogin <provider>      bring Chrome on-screen, wait, save state")
        print("  alogout <provider>     clear that provider's cookies only")
        print("  ashow                  move Chrome on-screen")
        print("  ahide                  move Chrome off-screen")
        return 0

    cmd = args[0].lower()
    rest = args[1:]

    if cmd == "providers":
        return handle_providers(rest)
    if cmd == "login":
        if not rest:
            print("usage: alogin <provider>")
            return 1
        return asyncio.run(_do_login(rest[0]))
    if cmd == "logout":
        if not rest:
            print("usage: alogout <provider>")
            return 1
        return asyncio.run(_do_logout(rest[0]))
    if cmd == "show":
        return do_show()
    if cmd == "hide":
        return do_hide()

    print(f"unknown command: {cmd}")
    print("try: aproviders | alogin | alogout | ashow | ahide")
    return 1


if __name__ == "__main__":
    sys.exit(main())
