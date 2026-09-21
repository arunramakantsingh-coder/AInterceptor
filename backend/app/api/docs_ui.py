"""Dashboard: docs browser — render project markdown as HTML."""
from __future__ import annotations
import pathlib

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
import markdown as md

from app.db.models import User
from app.deps import current_user_web
from app.api import web_common as W

router = APIRouter(prefix="/docs", tags=["docs"])

ROOT = pathlib.Path(__file__).resolve().parents[3]

# Whitelisted directories relative to repo root
ALLOWED_DIRS = ("docs", "PROJECT", ".ai")
ALLOWED_ROOT_FILES = ("README.md",)

# Curated display order + friendly names
DISPLAY = [
    # (relative path,               category,          title)
    ("docs/COMMANDS.md",             "Reference",       "Command Reference"),
    ("docs/AGENT_INSTALL.md",        "Reference",       "Agent Install Guide"),

    ("PROJECT/ARCHITECTURE_VNC_LOGIN.md",  "Architecture", "VNC Login"),
    ("PROJECT/ARCHITECTURE_ACCOUNTS.md",   "Architecture", "Accounts & Devices"),
    ("PROJECT/AUTOMATION.md",        "Architecture",    "Automation Design"),
    ("PROJECT/WEB_UI.md",            "Architecture",    "Web UI Design"),
    ("PROJECT/CLI_COMMAND_REFERENCE.md",   "Architecture", "CLI Spec (future)"),

    (".ai/RULES.md",                 "Operations",      "Rules"),
    (".ai/PROGRESS.md",              "Operations",      "Progress"),
    (".ai/SESSION_LOG.md",           "Operations",      "Session Log"),
    (".ai/KNOWN_ISSUES.md",          "Operations",      "Known Issues"),
    (".ai/FUTURE_WORK.md",           "Operations",      "Future Work"),
    (".ai/STRATEGY.md",              "Operations",      "Strategy"),
    (".ai/HANDOFF.md",               "Operations",      "Session Handoff"),

    ("README.md",                    "Overview",        "Readme"),
]


def _resolve(rel: str) -> pathlib.Path:
    """Safe path resolution — no traversal outside whitelisted dirs."""
    p = (ROOT / rel).resolve()
    # must be under ROOT
    try:
        p.relative_to(ROOT)
    except ValueError:
        raise HTTPException(400, "invalid path")
    # must match whitelist
    rel_posix = p.relative_to(ROOT).as_posix()
    if rel_posix in ALLOWED_ROOT_FILES:
        return p
    parent = rel_posix.split("/", 1)[0]
    if parent not in ALLOWED_DIRS:
        raise HTTPException(403, "not allowed")
    if p.suffix.lower() != ".md":
        raise HTTPException(403, "not a markdown file")
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "not found")
    return p


def _render_markdown(text: str) -> str:
    # 'fenced_code' for triple-backtick blocks, 'tables' for github tables
    return md.markdown(text, extensions=["fenced_code", "tables", "sane_lists"])


# ── index ──────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
def docs_index(user: User = Depends(current_user_web)):
    # Group by category
    by_cat: dict[str, list[tuple[str, str]]] = {}
    for rel, cat, title in DISPLAY:
        path = ROOT / rel
        if not path.exists():
            continue
        by_cat.setdefault(cat, []).append((rel, title))

    blocks = []
    for cat in ("Reference", "Architecture", "Operations", "Overview"):
        items = by_cat.get(cat, [])
        if not items:
            continue
        rows = []
        for rel, title in items:
            path = ROOT / rel
            size = path.stat().st_size
            rows.append(
                '<a href="/docs/' + rel + '" '
                'style="display:flex; align-items:center; gap:12px; '
                'padding:12px 0; border-bottom:1px solid #1f1f1f; '
                'text-decoration:none; color:#e6e6e6;">'
                '<span style="flex:1;">' + W.esc(title) + '</span>'
                '<span class="muted" style="font-size:12px; font-family:monospace;">'
                + W.esc(rel) + '</span>'
                '<span class="muted" style="font-size:11px; min-width:70px; text-align:right;">'
                + f'{size//1024} KB' if size >= 1024 else f'{size} B'
                + '</span>'
                '<span style="color:#60a5fa;">&rarr;</span>'
                '</a>'
            )
        blocks.append(
            '<div class="card" style="margin-top:20px;">'
            '<h3>' + W.esc(cat) + '</h3>'
            + "".join(rows)
            + '</div>'
        )

    body = (
        W.dashboard_nav("/docs")
        + '<div class="container">'
        + '<h2>Documentation</h2>'
        + '<p class="muted">Live copy of every project doc. Updated on every commit via the post-commit hook.</p>'
        + "".join(blocks)
        + '</div>'
    )
    return HTMLResponse(W.page("Docs", body, W.topbar(user.email)))


# ── individual doc ─────────────────────────────────────────────────

@router.get("/{doc_path:path}", response_class=HTMLResponse)
def docs_view(doc_path: str, user: User = Depends(current_user_web)):
    p = _resolve(doc_path)
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(500, f"read failed: {e}")

    html_body = _render_markdown(text)
    rel = p.relative_to(ROOT).as_posix()
    mtime = p.stat().st_mtime
    from datetime import datetime, timezone
    stamp = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    body = (
        W.dashboard_nav("/docs")
        + '<div class="container docs-page">'
        + '<div class="row" style="justify-content:space-between; margin-bottom:18px;">'
        + '<div><h2 style="margin:0;">' + W.esc(p.name) + '</h2>'
        + '<p class="muted" style="margin-top:4px; font-size:12px;">'
        + W.esc(rel) + ' &middot; ' + stamp + '</p></div>'
        + '<a class="btn btn-secondary" href="/docs">&larr; all docs</a>'
        + '</div>'
        + '<div class="card docs-content">' + html_body + '</div>'
        + '</div>'
    )
    return HTMLResponse(W.page(p.name, body, W.topbar(user.email)))
