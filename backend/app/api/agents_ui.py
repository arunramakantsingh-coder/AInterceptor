"""Dashboard: agents page — one-click provider login via local helper."""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, Device, UserSession
from app.deps import current_user_web
from app.api import web_common as W

router = APIRouter(prefix="/dashboard", tags=["dashboard-agents"])

PROVIDERS = ["chatgpt", "claude", "deepseek", "gemini"]


def _fmt_age(ts):
    if not ts:
        return "never"
    try:
        s = int((datetime.now(timezone.utc) - ts).total_seconds())
    except Exception:
        return str(ts)[:19]
    if s < 60:    return str(s) + "s ago"
    if s < 3600:  return str(s // 60) + "m ago"
    if s < 86400: return str(s // 3600) + "h ago"
    return str(s // 86400) + "d ago"


def _status_card():
    return (
        '<div id="agent-status" class="card" style="margin-top:20px; border-color:#333;">'
        '<div style="display:flex; align-items:center; gap:12px;">'
        '<span id="agent-dot" style="font-size:20px; line-height:1;">&#9679;</span>'
        '<div style="flex:1;">'
        '<div id="agent-title" style="font-weight:600;">Checking for local agent&hellip;</div>'
        '<div id="agent-detail" class="muted" style="font-size:12px; margin-top:2px;">Looking at http://127.0.0.1:45231</div>'
        '</div>'
        '<button type="button" class="btn-secondary" style="padding:6px 14px; font-size:12px;" onclick="checkAgent()">Recheck</button>'
        '</div>'
        '<div id="agent-help" class="muted" style="font-size:12px; margin-top:10px; display:none;">'
        'Run this on your laptop: '
        '<code style="padding:4px 8px; background:#0a0a0a; border-radius:4px;">airouter-agent serve</code> '
        '<button type="button" class="btn-secondary" data-copy="airouter-agent serve" style="padding:3px 10px; font-size:11px;">copy</button>'
        '<div style="margin-top:6px;">Keep it open while setting up. Nothing sensitive passes through it.</div>'
        '</div>'
        '</div>'
    )


def _devices_card(devices):
    if not devices:
        return ('<p class="muted">No devices connected. '
                'Use the <a href="/dashboard/devices">devices page</a> to connect one.</p>')
    parts = []
    for d in devices:
        parts.append(
            '<div style="padding:12px 0; border-bottom:1px solid #1f1f1f;">'
            '<div style="font-weight:600;">' + W.esc(d.name) + '</div>'
            '<div class="muted" style="font-size:12px; margin-top:2px;">'
            + W.esc(d.os or "unknown OS") + ' &middot; last seen ' + _fmt_age(d.last_seen_at)
            + '</div></div>'
        )
    return "".join(parts)


def _providers_card(sess_by_provider):
    parts = []
    for p in PROVIDERS:
        s = sess_by_provider.get(p)
        if s and s.status == "active":
            badge = ('<span style="color:#4ade80; font-weight:600;">'
                     '&#9679; logged in &middot; ' + _fmt_age(s.created_at) + '</span>')
        else:
            badge = '<span style="color:#facc15;">&#9675; not logged in</span>'
        cmd = "airouter-agent login " + p
        parts.append(
            '<div style="padding:14px 0; border-bottom:1px solid #1f1f1f; '
            'display:flex; align-items:center; gap:14px; flex-wrap:wrap;">'
            '<div style="min-width:100px; font-weight:600;">' + p + '</div>'
            '<div style="flex:1; min-width:200px; font-family:monospace; font-size:12px; '
            'color:#ccc; background:#0a0a0a; padding:8px 12px; border-radius:4px;">' + cmd + '</div>'
            '<button type="button" class="btn agent-run" data-provider="' + p + '" '
            'style="padding:6px 14px; font-size:12px; display:none;">Login</button>'
            '<button type="button" class="btn-secondary" data-copy="' + cmd + '" '
            'style="padding:6px 14px; font-size:12px;">copy</button>'
            '<div style="min-width:170px; font-size:12px; text-align:right;">' + badge + '</div>'
            '<pre class="agent-output" data-provider="' + p + '" style="display:none; width:100%; '
            'background:#0a0a0a; padding:10px 12px; border-radius:4px; color:#ccc; '
            'font-size:11px; line-height:1.5; overflow-x:auto; margin:6px 0 0;"></pre>'
            '</div>'
        )
    return "".join(parts)


@router.get("/agents", response_class=HTMLResponse)
def agents_page(user: User = Depends(current_user_web),
                db: Session = Depends(get_db)):
    devices = (db.query(Device)
               .filter(Device.user_id == user.id, Device.revoked_at.is_(None))
               .order_by(Device.last_seen_at.desc().nullslast())
               .all())
    sessions = (db.query(UserSession)
                .filter(UserSession.user_id == user.id)
                .all())
    sess_by_provider = {s.provider: s for s in sessions}

    body = (
        W.dashboard_nav("/dashboard/agents")
        + '<div class="container">'
        + '<h2>Agents</h2>'
        + '<p class="muted">One laptop, one terminal, one click per provider. '
        + 'The local agent opens Chrome on your machine and uploads the session to your account.</p>'
        + _status_card()
        + '<div class="card" style="margin-top:22px;">'
        + '<h3>Provider logins</h3>'
        + '<p class="muted" style="font-size:12px; margin-bottom:10px;">'
        + 'When the agent is running on your laptop, click <strong>Login</strong> below.</p>'
        + _providers_card(sess_by_provider)
        + '</div>'
        + '<div class="card" style="margin-top:22px;">'
        + '<h3>Connected devices</h3>'
        + _devices_card(devices)
        + '<div style="margin-top:14px;"><a class="btn btn-secondary" href="/dashboard/devices">Manage devices &rarr;</a></div>'
        + '</div>'
        + '<div class="card" style="margin-top:22px;">'
        + '<h3>Documentation</h3>'
        + '<p class="muted">Full install guide: <a href="https://github.com/arunramakantsingh-coder/AInterceptor/blob/fix/nonclaude-three-providers-20260917/docs/AGENT_INSTALL.md" target="_blank" rel="noopener">docs/AGENT_INSTALL.md</a></p>'
        + '</div>'
        + '</div>'
        + '<script src="/agents-static/agents.js" defer></script>'
    )
    return HTMLResponse(W.page("Agents", body, W.topbar(user.email)))
