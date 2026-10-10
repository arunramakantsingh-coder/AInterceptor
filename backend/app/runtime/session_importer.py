"""Apply a storage_state (agent upload or file) to a live provider tab.

CDP-inject: cookies via Playwright's context.add_cookies, localStorage via
CDP DOMStorage.setDOMStorageItem, then reload the provider tab.
"""
from __future__ import annotations
from typing import Any


def _clean_cookie(c: dict) -> dict | None:
    name = c.get("name")
    value = c.get("value")
    domain = c.get("domain")
    if not (name and value is not None and domain):
        return None
    out: dict[str, Any] = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": c.get("path") or "/",
    }
    exp = c.get("expires")
    if isinstance(exp, (int, float)) and exp > 0:
        out["expires"] = float(exp)
    for f in ("httpOnly", "secure"):
        if f in c:
            out[f] = bool(c[f])
    ss = c.get("sameSite")
    if ss in ("Strict", "Lax", "None"):
        out["sameSite"] = ss
    return out


async def apply_state_to_provider(supervisor: Any, provider: str, state: dict) -> dict:
    tab = await supervisor.get_tab(provider)
    if tab is None or tab.page is None:
        return {"ok": False, "error": f"no tab for {provider}"}
    try:
        if tab.page.is_closed():
            return {"ok": False, "error": f"{provider} tab closed"}
    except Exception:
        pass

    page = tab.page
    context = page.context

    # ── cookies ──
    raw_cookies = state.get("cookies") or []
    cookies = [c for c in (_clean_cookie(x) for x in raw_cookies) if c]
    added = 0
    try:
        if cookies:
            await context.add_cookies(cookies)
            added = len(cookies)
    except Exception as e:
        return {"ok": False, "error": f"add_cookies: {e}"}

    # ── localStorage via CDP ──
    set_local = 0
    origins = state.get("origins") or []
    if origins:
        try:
            session = await context.new_cdp_session(page)
            for o in origins:
                origin = o.get("origin")
                if not origin:
                    continue
                for item in (o.get("localStorage") or []):
                    try:
                        await session.send("DOMStorage.setDOMStorageItem", {
                            "storageId": {"securityOrigin": origin, "isLocalStorage": True},
                            "key": item.get("name", ""),
                            "value": item.get("value", ""),
                        })
                        set_local += 1
                    except Exception:
                        continue
        except Exception:
            pass  # not fatal

    # ── reload ──
    reload_err = None
    try:
        await page.reload(wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        reload_err = str(e)[:160]

    return {
        "ok": True,
        "cookies": added,
        "local_storage": set_local,
        "reload_error": reload_err,
    }
