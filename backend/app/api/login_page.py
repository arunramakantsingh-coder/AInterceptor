"""Branded /login/<provider> page: password gate + embedded noVNC."""
from __future__ import annotations
import hashlib, hmac, os, pathlib, re, secrets, time
from typing import Optional
from fastapi import APIRouter, Cookie, Form, HTTPException, WebSocket
from fastapi.responses import HTMLResponse, RedirectResponse

TEMPLATES = pathlib.Path(__file__).parent / "templates"
COOKIE_NAME = "aint_login"
COOKIE_TTL  = 8 * 3600

router = APIRouter()


def _admin_pw() -> str:
    return os.environ.get("AINTERCEPTOR_WEB_LOGIN_PASSWORD", "")


def _cookie_secret() -> bytes:
    return os.environ.get("AINTERCEPTOR_WEB_COOKIE_SECRET", "").encode()


def _vnc_pw() -> str:
    return os.environ.get("AINTERCEPTOR_VNC_PASSWORD", "")


def _sign(provider: str, ts: int) -> str:
    return hmac.new(_cookie_secret(), f"{provider}|{ts}".encode(),
                    hashlib.sha256).hexdigest()


def _verify_cookie(provider: str, cookie: Optional[str]) -> bool:
    if not cookie:
        return False
    try:
        p, ts_s, sig = cookie.split("|", 2)
        if p != provider:
            return False
        ts = int(ts_s)
        if time.time() - ts > COOKIE_TTL:
            return False
        return hmac.compare_digest(sig, _sign(p, ts))
    except Exception:
        return False


def _render(template: str, **kw) -> str:
    html = (TEMPLATES / template).read_text()
    for k, v in kw.items():
        html = html.replace(f"__{k.upper()}__", str(v))
    return html


def _safe(name: str) -> str:
    if not re.match(r"^[a-z][a-z0-9_]*$", name):
        raise HTTPException(400, "invalid provider name")
    return name


def _move_chrome_onscreen(x: int, y: int) -> int:
    """Move every Chrome window to (x, y). Self-contained — no imports
    from scripts/ which is not on sys.path here."""
    import os, subprocess
    env = {**os.environ, "DISPLAY": os.environ.get("AINTERCEPTOR_DISPLAY", ":99")}
    wids: list[str] = []
    for args in (
        ["search", "--class", "google-chrome"],
        ["search", "--class", "Google-chrome"],
        ["search", "--name", "Chrome"],
    ):
        try:
            r = subprocess.run(["xdotool"] + args, capture_output=True,
                               text=True, timeout=5, env=env)
            wids.extend(w.strip() for w in r.stdout.split() if w.strip())
        except Exception:
            continue
    wids = list(dict.fromkeys(wids))
    moved = 0
    for wid in wids:
        try:
            subprocess.run(["xdotool", "windowmove", wid, str(x), str(y)],
                           capture_output=True, timeout=5, env=env)
            subprocess.run(["xdotool", "windowraise", wid],
                           capture_output=True, timeout=5, env=env)
            moved += 1
        except Exception:
            continue
    return moved


PROVIDER_DISPLAY = {
    "claude":       ("Claude",       "#d97706"),
    "chatgpt":      ("ChatGPT",      "#10a37f"),
    "gemini":       ("Gemini",       "#4285f4"),
    "deepseek":     ("DeepSeek",     "#4d6bfe"),
    "mistral":      ("Mistral",      "#ff7000"),
    "qwen":         ("Qwen",         "#615ced"),
    "huggingchat":  ("HuggingChat",  "#ffd21e"),
    "perplexity":   ("Perplexity",   "#20808d"),
    "grok":         ("Grok",         "#000000"),
    "poe":          ("Poe",          "#5d3fd3"),
    "kimi":         ("Kimi",         "#000000"),
    "yi":           ("Yi",           "#003425"),
    "lechat":       ("Le Chat",      "#ff7000"),
    "glm":          ("GLM",          "#3859ff"),
    "you":          ("You.com",      "#7c3aed"),
    "phind":        ("Phind",        "#2c7a7b"),
    "doubao":       ("Doubao",       "#1664ff"),
    "copilot":      ("Copilot",      "#0078d4"),
    "meta":         ("Meta AI",      "#0866ff"),
    "character":    ("Character.AI", "#0f0f0f"),
}


@router.get("/login", response_class=HTMLResponse)
async def login_index():
    cards = []
    for name in PROVIDER_DISPLAY:
        label, color = PROVIDER_DISPLAY.get(name, (name.title(), "#333"))
        initial = label[0].upper()
        cards.append(
            f'<a href="/login/{name}" style="display:flex; align-items:center; gap:12px;'
            f' padding:16px; background:#111; border:1px solid #222; border-radius:8px;'
            f' text-decoration:none; color:#e6e6e6; font-weight:500; font-size:14px;'
            f' transition: all .15s;" '
            f'onmouseover="this.style.borderColor=\'{color}\';this.style.background=\'#161616\'" '
            f'onmouseout="this.style.borderColor=\'#222\';this.style.background=\'#111\'">'
            f'<span style="display:inline-flex; align-items:center; justify-content:center;'
            f' width:32px; height:32px; border-radius:6px; background:{color}; color:#fff;'
            f' font-weight:700; font-size:15px;">{initial}</span>'
            f'<span>{label}</span></a>'
        )
    cards_html = "".join(cards)
    body = (TEMPLATES / "login_index.html").read_text().replace("__CARDS__", cards_html)
    html = (TEMPLATES / "login.html").read_text().replace("__PROVIDER__", "AInterceptor")                                           .replace("__BODY__", body)
    return HTMLResponse(html)


@router.get("/login/{provider}", response_class=HTMLResponse)
async def login_page(provider: str, aint_login: Optional[str] = Cookie(None)):
    provider = _safe(provider)
    if _verify_cookie(provider, aint_login):
        # best-effort: bring Chrome on-screen + focus tab
        try:
            from app.runtime import supervisor_registry
            sup = supervisor_registry.get_supervisor()
            if sup is not None:
                tab = await sup.get_tab(provider)
                if tab and getattr(tab, "page", None):
                    try:
                        await tab.page.bring_to_front()
                    except Exception:
                        pass
            _move_chrome_onscreen(80, 60)
        except Exception:
            pass

        body = _render("login_ok.html", provider=provider, vnc_password=_vnc_pw())
    else:
        body = _render("login_denied.html", provider=provider, err="")
    return HTMLResponse(_render("login.html", provider=provider, body=body))


@router.post("/login/{provider}/auth", response_class=HTMLResponse)
async def login_auth(provider: str, password: str = Form(...)):
    provider = _safe(provider)
    admin = _admin_pw()
    if not admin:
        raise HTTPException(500, "AINTERCEPTOR_WEB_LOGIN_PASSWORD not set")
    if not secrets.compare_digest(password, admin):
        body = _render("login_denied.html", provider=provider,
                       err='<div class="err">Wrong password. Try again.</div>')
        return HTMLResponse(_render("login.html", provider=provider, body=body),
                            status_code=401)
    ts = int(time.time())
    cookie_val = f"{provider}|{ts}|{_sign(provider, ts)}"
    resp = RedirectResponse(url=f"/login/{provider}", status_code=303)
    resp.set_cookie(COOKIE_NAME, cookie_val, max_age=COOKIE_TTL,
                    httponly=True, samesite="lax", path="/login/")
    return resp


@router.get("/login/{provider}/logout")
async def login_logout(provider: str):
    provider = _safe(provider)
    resp = RedirectResponse(url=f"/login/{provider}", status_code=303)
    resp.delete_cookie(COOKIE_NAME, path="/login/")
    return resp


@router.websocket("/login/{provider}/ws")
async def ws_proxy(ws: WebSocket, provider: str):
    provider = _safe(provider)
    if not _verify_cookie(provider, ws.cookies.get(COOKIE_NAME)):
        await ws.close(code=1008)
        return

    # Echo back the first subprotocol the client offered; if none, accept bare.
    offered = ws.headers.get("sec-websocket-protocol", "")
    if offered:
        first = offered.split(",")[0].strip()
        await ws.accept(subprotocol=first)
    else:
        await ws.accept()

    import asyncio
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", 5900)
    except Exception:
        await ws.close(code=1011)
        return

    async def ws_to_tcp():
        try:
            while True:
                writer.write(await ws.receive_bytes())
                await writer.drain()
        except Exception:
            pass
        finally:
            try: writer.close()
            except Exception: pass

    async def tcp_to_ws():
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                await ws.send_bytes(data)
        except Exception:
            pass

    try:
        await asyncio.gather(ws_to_tcp(), tcp_to_ws())
    except Exception:
        pass
    finally:
        try: await ws.close()
        except Exception: pass
        try: writer.close()
        except Exception: pass
