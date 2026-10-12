"""Admin dashboard: raw capture monitor for all providers."""
from __future__ import annotations
import html, json, pathlib
from fastapi import APIRouter, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db.models import User
from app.deps import current_user_web
from app.api import web_common as W
from app.api.raw_routes import run_capture

router = APIRouter(prefix="/dashboard/monitoring", tags=["dashboard-monitoring"])
INDEX = pathlib.Path.home() / ".ainterceptor" / "raw" / "index.jsonl"


def _load_rows(limit: int = 200) -> list[dict]:
    if not INDEX.exists():
        return []
    rows = []
    with INDEX.open() as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows[-limit:]


def _all_providers() -> list[str]:
    try:
        from app.providers_list import ALL_PROVIDERS
        return sorted(set(ALL_PROVIDERS))
    except Exception:
        return ["chatgpt", "claude", "deepseek", "gemini"]


def _last_per_provider(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        p = r.get("provider", "")
        if p:
            out[p] = r
    return out


@router.get("/raw", response_class=HTMLResponse)
def raw_page(user: User = Depends(current_user_web), err: str = "", ok: str = ""):
    rows = _load_rows()
    last = _last_per_provider(rows)
    providers = _all_providers()

    banner = ""
    if err:
        banner = f'<div style="background:#7f1d1d;color:#fecaca;padding:10px;border-radius:6px;margin:10px 0;">Error: {html.escape(err)}</div>'
    elif ok:
        banner = f'<div style="background:#14532d;color:#bbf7d0;padding:10px;border-radius:6px;margin:10px 0;">OK: {html.escape(ok)}</div>'

    rows_html = []
    for p in providers:
        r = last.get(p)
        if r:
            proto = r.get("protocol", "—")
            lat = f"{r.get('latency_ms', 0)} ms"
            ts = (r.get("timestamp") or "")[:19].replace("T", " ")
            bytes_ = r.get("bytes", 0)
            status = "✅" if bytes_ > 0 else "⚠️"
            rows_html.append(
                f'<tr>'
                f'<td style="padding:6px 10px;"><b>{p}</b></td>'
                f'<td style="padding:6px 10px;">{html.escape(ts)}</td>'
                f'<td style="padding:6px 10px;">{html.escape(proto)}</td>'
                f'<td style="padding:6px 10px;">{lat}</td>'
                f'<td style="padding:6px 10px;">{bytes_} B</td>'
                f'<td style="padding:6px 10px;">{status}</td>'
                f'<td style="padding:6px 10px;">'
                f'<form method="post" action="/dashboard/monitoring/raw/capture/{p}" style="display:inline;">'
                f'<button type="submit" style="padding:3px 10px;cursor:pointer;">Capture</button>'
                f'</form></td>'
                f'</tr>'
            )
        else:
            rows_html.append(
                f'<tr>'
                f'<td style="padding:6px 10px;"><b>{p}</b></td>'
                f'<td style="padding:6px 10px;color:#666;">— no capture —</td>'
                f'<td></td><td></td><td></td>'
                f'<td style="padding:6px 10px;">⚪</td>'
                f'<td style="padding:6px 10px;">'
                f'<form method="post" action="/dashboard/monitoring/raw/capture/{p}" style="display:inline;">'
                f'<button type="submit" style="padding:3px 10px;cursor:pointer;">Capture</button>'
                f'</form></td>'
                f'</tr>'
            )

    recent_html = []
    for r in reversed(rows[-20:]):
        ts = (r.get("timestamp") or "")[:19].replace("T", " ")
        recent_html.append(
            f'<tr>'
            f'<td style="padding:4px 10px;">{html.escape(r.get("provider",""))}</td>'
            f'<td style="padding:4px 10px;">{html.escape(ts)}</td>'
            f'<td style="padding:4px 10px;">{r.get("bytes",0)} B</td>'
            f'<td style="padding:4px 10px;">{html.escape(r.get("protocol",""))}</td>'
            f'<td style="padding:4px 10px;">{r.get("latency_ms",0)} ms</td>'
            f'<td style="padding:4px 10px;font-size:11px;color:#666;">{html.escape(str(r.get("saved","")))}</td>'
            f'</tr>'
        )

    body = (
        W.dashboard_nav("/dashboard/monitoring/raw")
        + '<div class="container" style="max-width:1100px;">'
        + '<h2>Raw Capture Monitor</h2>'
        + '<p class="muted">Last capture per provider. Click Capture to fire a fresh probe. '
        + 'Cold calls can take 45–60s; warm calls ~10s. See <code>arawstatus</code> for CLI.</p>'
        + banner
        + '<h3 style="margin-top:24px;">Per-provider</h3>'
        + '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        + '<thead><tr style="text-align:left;border-bottom:1px solid #333;">'
        + '<th style="padding:6px 10px;">Provider</th>'
        + '<th style="padding:6px 10px;">Last capture</th>'
        + '<th style="padding:6px 10px;">Protocol</th>'
        + '<th style="padding:6px 10px;">Latency</th>'
        + '<th style="padding:6px 10px;">Bytes</th>'
        + '<th style="padding:6px 10px;">Status</th>'
        + '<th></th>'
        + '</tr></thead><tbody>'
        + "".join(rows_html)
        + '</tbody></table>'
        + '<h3 style="margin-top:32px;">Recent 20 captures</h3>'
        + '<table style="width:100%;border-collapse:collapse;font-size:12px;">'
        + '<thead><tr style="text-align:left;border-bottom:1px solid #333;">'
        + '<th style="padding:4px 10px;">Provider</th>'
        + '<th style="padding:4px 10px;">Time</th>'
        + '<th style="padding:4px 10px;">Bytes</th>'
        + '<th style="padding:4px 10px;">Protocol</th>'
        + '<th style="padding:4px 10px;">Latency</th>'
        + '<th style="padding:4px 10px;">File</th>'
        + '</tr></thead><tbody>'
        + "".join(recent_html)
        + '</tbody></table>'
        + '</div>'
    )
    return HTMLResponse(W.page("Raw Monitor", body, W.topbar(user.email)))


@router.post("/raw/capture/{provider}")
async def raw_capture(provider: str, prompt: str = Form("say PING"),
                      user: User = Depends(current_user_web)):
    try:
        await run_capture(provider, prompt)
        return RedirectResponse("/dashboard/monitoring/raw?ok=captured", status_code=303)
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        return RedirectResponse(f"/dashboard/monitoring/raw?err={msg[:200]}", status_code=303)
