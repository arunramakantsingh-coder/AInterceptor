"""Dashboard: agents page — laptop setup + per-provider login commands."""
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

PUBLIC_URL = "https://ainterceptor.taila2310c.ts.net"
PROVIDERS = ["chatgpt", "claude", "deepseek", "gemini"]


def _fmt_age(ts) -> str:
    if not ts:
        return "never"
    try:
        delta = datetime.now(timezone.utc) - ts
        s = int(delta.total_seconds())
    except Exception:
        return str(ts)[:19]
    if s < 60:    return f"{s}s ago"
    if s < 3600:  return f"{s//60}m ago"
    if s < 86400: return f"{s//3600}h ago"
    return f"{s//86400}d ago"


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

    # Devices block
    if devices:
        rows = []
        for d in devices:
            rows.append(
                '<div style="padding:12px 0; border-bottom:1px solid #1f1f1f;">'
                f'<div style="font-weight:600;">{W.esc(d.name)}</div>'
                f'<div class="muted" style="font-size:12px; margin-top:2px;">'
                f'{W.esc(d.os or "unknown OS")} · last seen {_fmt_age(d.last_seen_at)}'
                '</div></div>'
            )
        devices_html = "".join(rows)
    else:
        devices_html = ('<p class="muted">No devices connected yet. '
                        'Click <strong>Connect a new device</strong> below to get '
                        'a code, then run the command on your laptop.</p>')

    # Connect block (inline code generator — placeholder button for now)
    connect_html = (
        '<div style="margin-top:14px;">'
        '<a class="btn" href="/dashboard/devices">Connect a new device →</a>'
        '<p class="muted" style="font-size:12px; margin-top:8px;">'
        'Generate a device code on the devices page; run the shown command '
        'once on your laptop.</p></div>'
    )

    # Per-provider login commands
    prov_html_rows = []
    for p in PROVIDERS:
        s = sess_by_provider.get(p)
        if s and s.status == "active":
            badge = (f'<span style="color:#4ade80; font-weight:600;">'
                     f'● logged in · {_fmt_age(s.created_at)}</span>')
        else:
            badge = '<span style="color:#facc15;">○ not logged in</span>'
        cmd = f"airouter-agent login {p}"
        prov_html_rows.append(
            '<div style="padding:14px 0; border-bottom:1px solid #1f1f1f; '
            'display:flex; align-items:center; gap:14px;">'
            f'<div style="min-width:100px; font-weight:600;">{p}</div>'
            f'<div style="flex:1; font-family:monospace; font-size:12px; '
            f'color:#ccc; background:#0a0a0a; padding:8px 12px; border-radius:4px;">'
            f'{W.esc(cmd)}</div>'
            f'<button type="button" class="btn-secondary" '
            f'style="padding:5px 12px; font-size:12px;" '
            f'onclick="navigator.clipboard.writeText(\'{W.esc(cmd)}\'); '
            f'this.textContent=\'copied\'; setTimeout(()=>this.textContent=\'copy\',1200);">'
            f'copy</button>'
            f'<div style="min-width:180px; font-size:12px; text-align:right;">{badge}</div>'
            '</div>'
        )
    providers_html = "".join(prov_html_rows)

    body = W.dashboard_nav("/dashboard/agents") + f'''
<div class="container">
  <h2>Agents &amp; devices</h2>
  <p class="muted">Set up a laptop once, then log into any provider with a single command.</p>

  <div class="card" style="margin-top:22px;">
    <h3>Your connected devices</h3>
    {devices_html}
    {connect_html}
  </div>

  <div class="card" style="margin-top:22px;">
    <h3>Provider logins</h3>
    <p class="muted" style="font-size:12px; margin-bottom:10px;">
      Run the command on any of your connected devices. The session uploads
      to your account automatically.
    </p>
    {providers_html}
  </div>

  <div class="card" style="margin-top:22px;">
    <h3>Full documentation</h3>
    <p class="muted">See the <a href="https://github.com/arunramakantsingh-coder/AInterceptor/blob/fix/nonclaude-three-providers-20260917/docs/AGENT_INSTALL.md">agent install guide</a> for details.</p>
  </div>
</div>
'''
    return HTMLResponse(W.page("Agents", body, W.topbar(user.email)))
