"""Dashboard: usage page — /v1 call history from usage_events."""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, ApiKey, UsageEvent
from app.deps import current_user_web
from app.api import web_common as W

router = APIRouter(prefix="/dashboard", tags=["dashboard-usage"])


def _fmt_ts(ts):
    if not ts:
        return "?"
    try:
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)[:19]


@router.get("/usage", response_class=HTMLResponse)
def usage_page(user: User = Depends(current_user_web),
               db: Session = Depends(get_db)):
    # Load events for this user's keys (join via ApiKey.user_id is not
    # stored on events — they store user_id directly)
    events = (db.query(UsageEvent)
              .filter(UsageEvent.user_id == user.id)
              .order_by(UsageEvent.created_at.desc())
              .limit(200)
              .all())

    total = len(events)
    ok = sum(1 for e in events if e.status == "ok")
    err = total - ok
    avg_lat = (
        int(sum(e.latency_ms or 0 for e in events) / total)
        if total else 0
    )
    tokens_in = sum(e.tokens_in or 0 for e in events)
    tokens_out = sum(e.tokens_out or 0 for e in events)

    # Summary cards
    cards = (
        '<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(160px,1fr));'
        ' margin-top:20px;">'
        '<div class="card"><div class="muted" style="font-size:12px;">Calls</div>'
        f'<div style="font-size:28px; font-weight:700; margin-top:6px;">{total}</div></div>'
        '<div class="card"><div class="muted" style="font-size:12px;">OK</div>'
        f'<div style="font-size:28px; font-weight:700; margin-top:6px; color:#4ade80;">{ok}</div></div>'
        '<div class="card"><div class="muted" style="font-size:12px;">Errors</div>'
        f'<div style="font-size:28px; font-weight:700; margin-top:6px; color:#f87171;">{err}</div></div>'
        '<div class="card"><div class="muted" style="font-size:12px;">Avg latency</div>'
        f'<div style="font-size:28px; font-weight:700; margin-top:6px;">{avg_lat}<span style="font-size:14px;">ms</span></div></div>'
        '<div class="card"><div class="muted" style="font-size:12px;">Tokens in</div>'
        f'<div style="font-size:28px; font-weight:700; margin-top:6px;">{tokens_in}</div></div>'
        '<div class="card"><div class="muted" style="font-size:12px;">Tokens out</div>'
        f'<div style="font-size:28px; font-weight:700; margin-top:6px;">{tokens_out}</div></div>'
        '</div>'
    )

    # Table
    if not events:
        table = ('<p class="muted">No calls yet. Send a request to '
                 '<code>/v1/chat/completions</code> with an API key from your '
                 '<a href="/dashboard/keys">keys page</a>.</p>')
    else:
        rows = []
        for e in events[:100]:
            status_color = "#4ade80" if e.status == "ok" else "#f87171"
            rows.append(
                '<tr>'
                '<td style="padding:8px;border-bottom:1px solid #1f1f1f;color:#888;font-size:12px;white-space:nowrap;">'
                + _fmt_ts(e.created_at) + '</td>'
                '<td style="padding:8px;border-bottom:1px solid #1f1f1f;">'
                + W.esc(e.provider or "?") + '</td>'
                '<td style="padding:8px;border-bottom:1px solid #1f1f1f;color:#aaa;font-size:12px;">'
                + W.esc(e.model or "?") + '</td>'
                '<td style="padding:8px;border-bottom:1px solid #1f1f1f;text-align:right;">'
                + str(e.tokens_in or 0) + '</td>'
                '<td style="padding:8px;border-bottom:1px solid #1f1f1f;text-align:right;">'
                + str(e.tokens_out or 0) + '</td>'
                '<td style="padding:8px;border-bottom:1px solid #1f1f1f;text-align:right;color:#888;font-size:12px;">'
                + str(e.latency_ms or 0) + 'ms</td>'
                '<td style="padding:8px;border-bottom:1px solid #1f1f1f;">'
                '<span style="color:' + status_color + '; font-size:12px;">'
                + W.esc(e.status or "?") + '</span></td>'
                '<td style="padding:8px;border-bottom:1px solid #1f1f1f;color:#888;font-size:12px;">'
                + W.esc(e.path or "?") + '</td>'
                '</tr>'
            )
        table = (
            '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
            '<thead><tr style="text-align:left;color:#888;">'
            '<th style="padding:8px;">Time</th>'
            '<th style="padding:8px;">Provider</th>'
            '<th style="padding:8px;">Model</th>'
            '<th style="padding:8px;text-align:right;">In</th>'
            '<th style="padding:8px;text-align:right;">Out</th>'
            '<th style="padding:8px;text-align:right;">Latency</th>'
            '<th style="padding:8px;">Status</th>'
            '<th style="padding:8px;">Path</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table>'
        )

    body = (
        W.dashboard_nav("/dashboard/usage")
        + '<div class="container">'
        + '<h2>Usage</h2>'
        + '<p class="muted">Recent calls to <code>/v1/chat/completions</code>.</p>'
        + cards
        + '<div class="card" style="margin-top:20px;">'
        + '<h3>Last 100 calls</h3>'
        + table
        + '</div>'
        + '</div>'
    )
    return HTMLResponse(W.page("Usage", body, W.topbar(user.email)))
