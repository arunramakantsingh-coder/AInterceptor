"""amonitor - live dispatcher probe board.

Only probes ACTIVE providers (from .env). Refreshes in place. Ctrl+C to exit.

Default: lightweight (session cookies + CDP tab state, ~1s).
--real:   full dispatcher call with a ping prompt (slow, ~30s per provider).
"""
from __future__ import annotations
import argparse, asyncio, json, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, "backend")

CLEAR = "\033[H\033[J"
HIDE = "\033[?25l"
SHOW = "\033[?25h"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
RESET = "\033[0m"

DOMAINS = {
    "chatgpt": "chatgpt.com",
    "claude": "claude.ai",
    "gemini": "gemini.google.com",
    "deepseek": "chat.deepseek.com",
}
COOKIE_DOMAIN = {
    "chatgpt": "chatgpt.com",
    "gemini": "google.com",
    "deepseek": "deepseek.com",
    "claude": "claude.ai",
}


def _active_providers():
    envf = Path.home() / "ainterceptor" / ".env"
    if not envf.exists():
        return []
    for line in envf.read_text().splitlines():
        if line.startswith("AINTERCEPTOR_ACTIVE_PROVIDERS="):
            v = line.split("=", 1)[1].strip()
            return [p.strip() for p in v.split(",") if p.strip()]
    return []


def _cdp_tab(provider):
    try:
        with urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=2) as r:
            tabs = json.loads(r.read())
    except Exception:
        return None
    dom = DOMAINS.get(provider)
    if not dom:
        return None
    for t in tabs:
        u = t.get("url", "")
        if dom in u and not u.startswith("blob:"):
            return t
    return None


async def _probe_light(provider, state):
    out = {"provider": provider, "paths": {}}

    if provider == "claude":
        tab = _cdp_tab("claude")
        if not tab:
            out["paths"]["claude"] = {"ok": False, "ms": 0, "detail": "no tab"}
        else:
            title = (tab.get("title") or "")[:40]
            url = tab.get("url", "")
            if "Just a moment" in title or "challenge" in url:
                out["paths"]["claude"] = {"ok": False, "ms": 0, "detail": "cloudflare challenge"}
            elif "/login" in url or "/signin" in url:
                out["paths"]["claude"] = {"ok": False, "ms": 0, "detail": "login page"}
            else:
                out["paths"]["claude"] = {"ok": True, "ms": 0, "detail": title or "ok"}
        return out

    # path A
    cookies = (state or {}).get("cookies", [])
    dom = COOKIE_DOMAIN.get(provider, "")
    relevant = [c for c in cookies if dom in (c.get("domain", "") or "")]
    if relevant:
        out["paths"]["A"] = {"ok": True, "ms": 0, "detail": f"{len(relevant)} cookies"}
    else:
        out["paths"]["A"] = {"ok": False, "ms": 0, "detail": "no session cookies"}

    # path B
    tab = _cdp_tab(provider)
    if not tab:
        out["paths"]["B"] = {"ok": False, "ms": 0, "detail": "no tab"}
    else:
        title = (tab.get("title") or "")[:40]
        url = tab.get("url", "")
        if "Just a moment" in title or "challenge" in url:
            out["paths"]["B"] = {"ok": False, "ms": 0, "detail": "cloudflare challenge"}
        elif "/login" in url or "/signin" in url:
            out["paths"]["B"] = {"ok": False, "ms": 0, "detail": "login page"}
        else:
            out["paths"]["B"] = {"ok": True, "ms": 0, "detail": title or "ok"}
    return out


async def _probe_real(provider, state):
    from app.runtime import dispatcher
    out = {"provider": provider, "paths": {}}
    paths = ["claude"] if provider == "claude" else ["A", "B"]
    for path in paths:
        t0 = time.monotonic()
        try:
            got = False
            async for d in dispatcher.stream_reply(provider, state or {}, "ping", force_path=path):
                if d:
                    got = True
                    break
            ms = int((time.monotonic() - t0) * 1000)
            out["paths"][path] = {"ok": got, "ms": ms,
                                  "detail": "OK" if got else "no text"}
        except Exception as e:
            ms = int((time.monotonic() - t0) * 1000)
            out["paths"][path] = {"ok": False, "ms": ms, "detail": str(e)[:44]}
    return out


def _load_state(email, provider):
    """Load session state. Never raises: a corrupt/undecryptable row returns
    an empty dict so the monitor keeps drawing the other providers."""
    from app.db.session import SessionLocal
    from app.db.models import User
    from app.api.sessions_routes import load_session_state
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return {}
        try:
            return load_session_state(db, user.id, provider) or {}
        except Exception as e:
            # InvalidTag, missing row, etc. Record it and move on.
            return {"_load_error": str(e)[:80]}
    finally:
        db.close()


def _draw(results, cycle, interval, real):
    now = time.strftime("%H:%M:%S", time.localtime())
    mode = "REAL" if real else "light"
    out = [
        "",
        f"{BOLD}AInterceptor - live dispatcher monitor{RESET}"
        f"        {DIM}{now} UTC . mode={mode} . cycle #{cycle}{RESET}",
        f"{DIM}Ctrl+C to exit . refresh every {interval}s"
        f" . only ACTIVE providers shown{RESET}",
        "",
        f"  {'provider':12s}  {'path':8s}  {'status':8s}  {'ms':>7s}  detail",
        "  " + "-" * 74,
    ]
    ok_count = 0
    total = 0
    for r in results:
        first = True
        for p, info in r.get("paths", {}).items():
            total += 1
            ok = info.get("ok")
            if ok:
                ok_count += 1
            color = GREEN if ok else RED
            label = "OK" if ok else "FAIL"
            ms = info.get("ms", 0)
            detail = (info.get("detail") or "")[:44]
            prov_col = r["provider"] if first else ""
            first = False
            out.append(
                f"  {prov_col:12s}  {p:8s}  {color}{label:8s}{RESET}  "
                f"{ms:>7d}  {DIM}{detail}{RESET}"
            )
    out.append("")
    out.append(f"  {ok_count}/{total} checks OK")
    out.append("")
    sys.stdout.write(CLEAR + "\n".join(out))
    sys.stdout.flush()


async def main_async(args):
    active = _active_providers()
    if not active:
        print("No active providers in ~/ainterceptor/.env")
        return 1
    states = {p: _load_state(args.email, p) for p in active}
    sys.stdout.write(HIDE)
    cycle = 0
    try:
        while True:
            cycle += 1
            if args.real:
                results = await asyncio.gather(
                    *[_probe_real(p, states.get(p, {})) for p in active]
                )
            else:
                results = await asyncio.gather(
                    *[_probe_light(p, states.get(p, {})) for p in active]
                )
            _draw(list(results), cycle, args.interval, args.real)
            if args.once:
                break
            await asyncio.sleep(args.interval)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        sys.stdout.write(SHOW)
        sys.stdout.flush()
    return 0


def cli():
    ap = argparse.ArgumentParser(prog="amonitor")
    ap.add_argument("--real", action="store_true",
                    help="full dispatcher call with a ping prompt")
    ap.add_argument("--interval", type=int, default=5,
                    help="seconds between cycles (default 5)")
    ap.add_argument("--once", action="store_true",
                    help="run one cycle and exit")
    ap.add_argument("--email", default="arunramakantsingh@gmail.com")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(cli())
