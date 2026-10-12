"""Dashboard: sessions page — kill / refresh / last-used."""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, UserSession
from app.deps import current_user_web
from app.api import web_common as W

router = APIRouter(prefix="/dashboard", tags=["dashboard-sessions"])


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


def _render_row(r: UserSession) -> str:
    active = (r.status == "active")
    status_txt = ('<span style="color:#4ade80;">&#9679; active</span>'
                  if active else W.esc(r.status))
    created = r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "?"
    last_used = _fmt_age(r.last_used_at)
    form_action = "/dashboard/sessions/" + W.esc(r.provider) + "/delete"
    confirm = ("return confirm('Delete " + W.esc(r.provider) +
               " session? You will need to log in again.')")
    return (
        '<tr>'
        '<td style="padding:12px 8px;border-bottom:1px solid #1f1f1f;font-weight:600;">'
        + W.esc(r.provider) + '</td>'
        '<td style="padding:12px 8px;border-bottom:1px solid #1f1f1f;color:#aaa;">'
        + W.esc(r.alias) + '</td>'
        '<td style="padding:12px 8px;border-bottom:1px solid #1f1f1f;">'
        + status_txt + '</td>'
        '<td style="padding:12px 8px;border-bottom:1px solid #1f1f1f;color:#888;font-size:12px;">'
        + created + '</td>'
        '<td style="padding:12px 8px;border-bottom:1px solid #1f1f1f;color:#888;font-size:12px;">'
        + last_used + '</td>'
        '<td style="padding:12px 8px;border-bottom:1px solid #1f1f1f;text-align:right;white-space:nowrap;">'
        '<a class="btn btn-secondary" href="/dashboard/agents" '
        'style="padding:5px 12px;font-size:12px;margin-right:6px;">Refresh</a>'
        '<form method="POST" action="' + form_action + '" style="display:inline" '
        'onsubmit="' + confirm + '">'
        '<button type="submit" class="btn-secondary" '
        'style="padding:5px 12px;font-size:12px;color:#f87171;">Delete</button>'
        '</form>'
        '</td>'
        '</tr>'
    )


@router.get("/sessions", response_class=HTMLResponse)
def sessions_page(user: User = Depends(current_user_web),
                  db: Session = Depends(get_db)):
    rows = (db.query(UserSession)
            .filter(UserSession.user_id == user.id)
            .order_by(UserSession.created_at.desc())
            .all())

    if rows:
        trs = "".join(_render_row(r) for r in rows)
        table = (
            '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
            '<thead><tr style="text-align:left;color:#888;">'
            '<th style="padding:8px;">Provider</th>'
            '<th style="padding:8px;">Alias</th>'
            '<th style="padding:8px;">Status</th>'
            '<th style="padding:8px;">Created</th>'
            '<th style="padding:8px;">Last used</th>'
            '<th style="padding:8px;"></th>'
            '</tr></thead><tbody>' + trs + '</tbody></table>'
        )
    else:
        table = ('<p class="muted">No sessions yet. Visit '
                 '<a href="/dashboard/agents">Agents</a> to connect a provider.</p>')

    body = W.dashboard_nav("/dashboard/sessions") + (
        '<div class="container">'
        '<div class="row" style="justify-content:space-between;">'
        '<div><h2>Provider sessions</h2>'
        '<p class="muted">Each row is a logged-in provider stored for your account.</p></div>'
        '<a class="btn btn-secondary" href="/dashboard">&larr; back</a>'
        '</div>'
        '<div class="card" style="margin-top:20px;">' + table + '</div>'
        '</div>'
    )
    return HTMLResponse(W.page("Sessions", body, W.topbar(user.email)))


@router.post("/sessions/{provider}/delete")
def sessions_delete(provider: str,
                    user: User = Depends(current_user_web),
                    db: Session = Depends(get_db)):
    provider = provider.lower().strip()
    db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.provider == provider,
    ).delete()
    db.commit()
    return RedirectResponse(url="/dashboard/sessions", status_code=303)
