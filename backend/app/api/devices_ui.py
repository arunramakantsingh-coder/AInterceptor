"""Dashboard: devices page — list + inline connect-code generator."""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, Device, DeviceCode
from app.deps import current_user_web
from app.api import web_common as W
from app.api.device_routes import generate_device_code, CODE_TTL

router = APIRouter(prefix="/dashboard", tags=["dashboard-devices2"])

DEFAULT_SERVER = "https://ainterceptor.taila2310c.ts.net"


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


def _devices_table(devices):
    if not devices:
        return '<p class="muted">No devices yet. Generate a code below to connect one.</p>'
    rows = []
    for d in devices:
        rows.append(
            '<tr>'
            '<td style="padding:12px 8px;border-bottom:1px solid #1f1f1f;font-weight:600;">'
            + W.esc(d.name) + '</td>'
            '<td style="padding:12px 8px;border-bottom:1px solid #1f1f1f;color:#aaa;">'
            + W.esc(d.os or "—") + '</td>'
            '<td style="padding:12px 8px;border-bottom:1px solid #1f1f1f;color:#888;font-size:12px;">'
            + _fmt_age(d.last_seen_at) + '</td>'
            '<td style="padding:12px 8px;border-bottom:1px solid #1f1f1f;text-align:right;">'
            '<form method="POST" action="/dashboard/devices/' + W.esc(d.id) + '/revoke" '
            'style="display:inline" '
            'onsubmit="return confirm(\'Revoke this device?\')">'
            '<button type="submit" class="btn-secondary" '
            'style="padding:5px 12px;font-size:12px;color:#f87171;">Revoke</button>'
            '</form></td></tr>'
        )
    return (
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<thead><tr style="text-align:left;color:#888;">'
        '<th style="padding:8px;">Name</th>'
        '<th style="padding:8px;">OS</th>'
        '<th style="padding:8px;">Last seen</th>'
        '<th style="padding:8px;"></th>'
        '</tr></thead><tbody>' + "".join(rows) + '</tbody></table>'
    )


def _pending_code(db, user):
    now = datetime.now(timezone.utc)
    return (db.query(DeviceCode)
            .filter(DeviceCode.user_id == user.id,
                    DeviceCode.consumed_at.is_(None),
                    DeviceCode.expires_at > now)
            .order_by(DeviceCode.created_at.desc())
            .first())


def _connect_block(code_row):
    if not code_row:
        return (
            '<div class="card" style="margin-top:20px;">'
            '<h3>Connect a new device</h3>'
            '<p class="muted" style="font-size:13px; margin-bottom:14px;">'
            'Generate a one-time code. Then run the shown command on your laptop.</p>'
            '<form method="POST" action="/dashboard/devices/generate">'
            '<button type="submit">Generate device code</button>'
            '</form></div>'
        )
    code = code_row.code
    exp_iso = code_row.expires_at.isoformat()
    cmd = "airouter-agent connect --server " + DEFAULT_SERVER + " --code " + code
    return (
        '<div class="card" style="margin-top:20px; border-color:#1d4ed8;">'
        '<h3 style="color:#60a5fa;">Your device code</h3>'
        '<p class="muted" style="font-size:13px; margin-bottom:12px;">'
        'Run this on your laptop:</p>'
        '<div style="background:#0a0a0a; padding:14px; border-radius:6px;'
        ' font-family:monospace; font-size:12px; color:#ccc; overflow-x:auto;'
        ' margin-bottom:12px;">' + W.esc(cmd) + '</div>'
        '<div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px;">'
        '<button type="button" class="btn" style="padding:7px 14px; font-size:12px;"'
        ' data-copy="' + W.esc(cmd) + '">Copy full command</button>'
        '<span class="muted" style="font-size:12px; align-self:center;">or code:</span>'
        '<code style="font-size:14px; font-weight:700; letter-spacing:2px;">' + W.esc(code) + '</code>'
        '<button type="button" class="btn-secondary" style="padding:5px 12px; font-size:12px;"'
        ' data-copy="' + W.esc(code) + '">copy</button></div>'
        '<p class="muted" style="font-size:12px;">Waiting &middot; expires in '
        '<span id="countdown">--</span></p>'
        '<script>'
        'const expires = new Date("' + exp_iso + '");'
        'const cd = document.getElementById("countdown");'
        'function tick(){var s=Math.max(0,Math.round((expires-new Date())/1000));'
        'var m=Math.floor(s/60),r=s%60;cd.textContent=m+":"+String(r).padStart(2,"0");'
        'if(s===0)cd.textContent="expired";}'
        'setInterval(tick,1000);tick();'
        'const poll=setInterval(async()=>{try{'
        'const r=await fetch("/dashboard/devices/status?code=' + code + '");'
        'const d=await r.json();if(d.consumed){clearInterval(poll);location.reload();}}'
        'catch(e){}},2500);'
        '</script></div>'
    )


@router.get("/devices", response_class=HTMLResponse)
def devices_page(user: User = Depends(current_user_web),
                 db: Session = Depends(get_db)):
    devices = (db.query(Device)
               .filter(Device.user_id == user.id, Device.revoked_at.is_(None))
               .order_by(Device.last_seen_at.desc().nullslast())
               .all())
    code_row = _pending_code(db, user)
    body = (
        W.dashboard_nav("/dashboard/devices")
        + '<div class="container">'
        + '<h2>Devices</h2>'
        + '<p class="muted">Laptops that can upload sessions on your behalf.</p>'
        + '<div class="card" style="margin-top:20px;">'
        + '<h3>Connected devices</h3>'
        + _devices_table(devices)
        + '</div>'
        + _connect_block(code_row)
        + '</div>'
        + '<script src="/agents-static/agents.js" defer></script>'
    )
    return HTMLResponse(W.page("Devices", body, W.topbar(user.email)))


@router.post("/devices/generate")
def devices_generate(user: User = Depends(current_user_web),
                     db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    db.query(DeviceCode).filter(
        DeviceCode.user_id == user.id,
        DeviceCode.consumed_at.is_(None),
    ).delete()
    code = generate_device_code()
    db.add(DeviceCode(code=code, user_id=user.id, expires_at=now + CODE_TTL))
    db.commit()
    return RedirectResponse(url="/dashboard/devices", status_code=303)


@router.get("/devices/status")
def devices_status(code: str,
                   user: User = Depends(current_user_web),
                   db: Session = Depends(get_db)):
    row = db.get(DeviceCode, code)
    if not row or row.user_id != user.id:
        return {"consumed": False}
    return {"consumed": row.consumed_at is not None}


@router.post("/devices/{device_id}/revoke")
def devices_revoke(device_id: str,
                   user: User = Depends(current_user_web),
                   db: Session = Depends(get_db)):
    d = db.get(Device, device_id)
    if d and d.user_id == user.id and d.revoked_at is None:
        d.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return RedirectResponse(url="/dashboard/devices", status_code=303)
