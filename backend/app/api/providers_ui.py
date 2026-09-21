"""Dashboard: providers page — catalog, per-user status, admin toggle."""
from __future__ import annotations
import os
import pathlib

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, UserSession
from app.deps import current_user_web
from app.api import web_common as W

router = APIRouter(prefix="/dashboard", tags=["dashboard-providers"])


CATALOG = {
    "claude":      ("Claude",       "#d97706", "Tier 1"),
    "chatgpt":     ("ChatGPT",      "#10a37f", "Tier 1"),
    "gemini":      ("Gemini",       "#4285f4", "Tier 1"),
    "deepseek":    ("DeepSeek",     "#4d6bfe", "Tier 1"),
    "mistral":     ("Mistral",      "#ff7000", "Tier 2"),
    "qwen":        ("Qwen",         "#615ced", "Tier 2"),
    "huggingchat": ("HuggingChat",  "#ffd21e", "Tier 2"),
    "perplexity":  ("Perplexity",   "#20808d", "Tier 2"),
    "grok":        ("Grok",         "#000000", "Tier 2"),
    "poe":         ("Poe",          "#5d3fd3", "Tier 2"),
    "kimi":        ("Kimi",         "#111827", "Tier 3"),
    "yi":          ("Yi",           "#003425", "Tier 3"),
    "lechat":      ("Le Chat",      "#ff7000", "Tier 3"),
    "glm":         ("GLM",          "#3859ff", "Tier 3"),
    "you":         ("You.com",      "#7c3aed", "Tier 3"),
    "phind":       ("Phind",        "#2c7a7b", "Tier 3"),
    "doubao":      ("Doubao",       "#1664ff", "Tier 3"),
    "copilot":     ("Copilot",      "#0078d4", "Tier 3"),
    "meta":        ("Meta AI",      "#0866ff", "Tier 3"),
    "character":   ("Character.AI", "#0f0f0f", "Tier 3"),
}


def _repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".env").exists() or (parent / ".git").exists():
            return parent
    return pathlib.Path.cwd()


def _active_set() -> set[str]:
    env = os.environ.get("AINTERCEPTOR_ACTIVE_PROVIDERS", "")
    return {p.strip().lower() for p in env.split(",") if p.strip()}


def _admin_email() -> str:
    return (os.environ.get("AINTERCEPTOR_ADMIN_EMAIL")
            or "admin@ainterceptor.local").strip().lower()


def _is_admin(user: User) -> bool:
    return (user.email or "").strip().lower() == _admin_email()


def _edit_env(provider: str, add: bool) -> tuple[bool, str]:
    """Read .env, modify AINTERCEPTOR_ACTIVE_PROVIDERS, write back."""
    root = _repo_root()
    env_file = root / ".env"
    if not env_file.exists():
        return False, f".env not found at {env_file}"

    lines = env_file.read_text().splitlines()
    out = []
    found = False
    for line in lines:
        if line.startswith("AINTERCEPTOR_ACTIVE_PROVIDERS="):
            parts = [p.strip() for p in line.split("=", 1)[1].split(",") if p.strip()]
            if add and provider not in parts:
                parts.append(provider)
            elif not add:
                parts = [p for p in parts if p != provider]
            out.append("AINTERCEPTOR_ACTIVE_PROVIDERS=" + ",".join(parts))
            found = True
        else:
            out.append(line)
    if not found:
        out.append("AINTERCEPTOR_ACTIVE_PROVIDERS=" + (provider if add else ""))

    try:
        env_file.write_text("\n".join(out) + "\n")
    except Exception as e:
        return False, f"write failed: {e}"

    new_val = next(
        (l.split("=", 1)[1] for l in out
         if l.startswith("AINTERCEPTOR_ACTIVE_PROVIDERS=")), ""
    )
    os.environ["AINTERCEPTOR_ACTIVE_PROVIDERS"] = new_val
    return True, new_val


def _provider_card(name, label, color, active_global, session, is_admin):
    badge = (
        '<span style="color:#4ade80; font-weight:600;">&#9679; active</span>'
        if active_global else
        '<span style="color:#888;">&#9675; inactive</span>'
    )
    if session and session.status == "active":
        sess_badge = ('<span style="color:#4ade80; font-size:12px;">'
                      'session on file</span>')
    else:
        sess_badge = ('<span class="muted" style="font-size:12px;">'
                      'no session</span>')

    if is_admin:
        if active_global:
            action = (
                '<form method="POST" action="/dashboard/providers/' + name +
                '/disable" style="display:inline">'
                '<button type="submit" class="btn-secondary" '
                'style="padding:5px 12px;font-size:12px;">disable</button>'
                '</form>'
            )
        else:
            action = (
                '<form method="POST" action="/dashboard/providers/' + name +
                '/enable" style="display:inline">'
                '<button type="submit" class="btn" '
                'style="padding:5px 12px;font-size:12px;">enable</button>'
                '</form>'
            )
    else:
        action = '<span class="muted" style="font-size:11px;">admin only</span>'

    return (
        '<div style="display:flex; align-items:center; gap:14px; padding:14px 0; '
        'border-bottom:1px solid #1f1f1f;">'
        '<span style="width:34px; height:34px; border-radius:6px; background:' + color + ';'
        ' display:inline-flex; align-items:center; justify-content:center;'
        ' font-weight:700; color:#fff;">' + label[0].upper() + '</span>'
        '<div style="flex:1; min-width:0;">'
        '<div style="font-weight:600;">' + W.esc(label) + '</div>'
        '<div class="muted" style="font-size:12px; margin-top:2px;">'
        + W.esc(name) + ' &middot; ' + sess_badge + '</div></div>'
        '<div style="min-width:90px; font-size:12px;">' + badge + '</div>'
        '<div style="min-width:80px; text-align:right;">' + action + '</div>'
        '</div>'
    )


@router.get("/providers", response_class=HTMLResponse)
def providers_page(user: User = Depends(current_user_web),
                   db: Session = Depends(get_db)):
    active = _active_set()
    admin = _is_admin(user)
    sessions = (db.query(UserSession)
                .filter(UserSession.user_id == user.id)
                .all())
    sess_by_provider = {s.provider: s for s in sessions}

    tiers: dict[str, list[str]] = {}
    for name, (_label, _color, tier) in CATALOG.items():
        tiers.setdefault(tier, []).append(name)

    blocks = []
    for tier in ("Tier 1", "Tier 2", "Tier 3"):
        names = tiers.get(tier, [])
        if not names:
            continue
        rows = []
        for name in names:
            label, color, _ = CATALOG[name]
            rows.append(_provider_card(
                name, label, color,
                active_global=(name in active),
                session=sess_by_provider.get(name),
                is_admin=admin,
            ))
        blocks.append(
            '<div class="card" style="margin-top:20px;">'
            '<h3>' + tier + '</h3>' + "".join(rows) + '</div>'
        )

    hint = (
        '<p class="muted" style="font-size:12px; margin-top:10px;">'
        + ('As admin you can enable/disable providers globally. '
           'Changes take effect after <code>arestart</code>.'
           if admin else
           'Only admins can toggle providers. Active ones are used '
           'automatically by <code>/v1/chat/completions</code>.')
        + '</p>'
    )

    body = (
        W.dashboard_nav("/dashboard/providers")
        + '<div class="container">'
        + '<h2>Providers</h2>'
        + '<p class="muted">Every provider AInterceptor knows about. '
        + 'Active = live, inactive = dormant.</p>'
        + "".join(blocks)
        + hint
        + '</div>'
    )
    return HTMLResponse(W.page("Providers", body, W.topbar(user.email)))


@router.post("/providers/{name}/enable")
def providers_enable(name: str, user: User = Depends(current_user_web)):
    if not _is_admin(user):
        return RedirectResponse(url="/dashboard/providers", status_code=303)
    name = name.lower().strip()
    if name in CATALOG:
        ok, msg = _edit_env(name, add=True)
        print(f"[providers] enable {name}: ok={ok} msg={msg}", flush=True)
    return RedirectResponse(url="/dashboard/providers", status_code=303)


@router.post("/providers/{name}/disable")
def providers_disable(name: str, user: User = Depends(current_user_web)):
    if not _is_admin(user):
        return RedirectResponse(url="/dashboard/providers", status_code=303)
    name = name.lower().strip()
    if name in CATALOG:
        ok, msg = _edit_env(name, add=False)
        print(f"[providers] disable {name}: ok={ok} msg={msg}", flush=True)
    return RedirectResponse(url="/dashboard/providers", status_code=303)
