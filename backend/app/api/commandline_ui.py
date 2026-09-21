"""Dashboard: /dashboard/commandline — full CLI reference, rendered."""
from __future__ import annotations
import pathlib

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
import markdown as md

from app.db.models import User
from app.deps import current_user_web
from app.api import web_common as W

router = APIRouter(prefix="/dashboard", tags=["commandline"])

ROOT = pathlib.Path(__file__).resolve().parents[3]
DOC = ROOT / "docs" / "COMMANDS.md"


def _render(text: str) -> str:
    return md.markdown(text, extensions=["fenced_code", "tables", "sane_lists"])


@router.get("/commandline", response_class=HTMLResponse)
def commandline_page(user: User = Depends(current_user_web)):
    if not DOC.exists():
        raise HTTPException(404, "docs/COMMANDS.md not found on disk")
    text = DOC.read_text(encoding="utf-8")
    html_body = _render(text)
    from datetime import datetime, timezone
    stamp = datetime.fromtimestamp(DOC.stat().st_mtime, tz=timezone.utc)\
        .strftime("%Y-%m-%d %H:%M UTC")

    body = (
        W.dashboard_nav("/dashboard/commandline")
        + '<div class="container docs-page">'
        + '<div class="row" style="justify-content:space-between; margin-bottom:18px;">'
        + '<div>'
        + '<h2 style="margin:0;">Command Line Reference</h2>'
        + '<p class="muted" style="margin-top:4px; font-size:12px;">'
        + 'Every CLI command AInterceptor exposes. Source: <code>docs/COMMANDS.md</code>'
        + ' &middot; ' + stamp + '</p></div>'
        + '<a class="btn btn-secondary" href="/dashboard">&larr; back</a>'
        + '</div>'
        + '<div class="card docs-content">' + html_body + '</div>'
        + '</div>'
    )
    return HTMLResponse(W.page("Command Line", body, W.topbar(user.email)))
