"""Serve .md docs from PROJECT/ and .ai/ as HTML on the admin dashboard.

Read-only, admin-only. No file writes. Minimal in-repo markdown renderer
that handles headers, lists, code fences, inline code, and paragraphs.
"""
from __future__ import annotations
import html, pathlib, re
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from app.db.models import User
from app.deps import current_user_web
from app.api import web_common as W

router = APIRouter(prefix="/dashboard", tags=["dashboard-docs"])

REPO = pathlib.Path(__file__).resolve().parents[3]
DOC_ROOTS = [REPO / "PROJECT", REPO / ".ai", REPO / "docs"]


def _safe_resolve(rel: str) -> pathlib.Path:
    rel = rel.strip("/").replace("\\", "/")
    for root in DOC_ROOTS:
        if not root.exists():
            continue
        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            continue
        if candidate.is_file() and candidate.suffix.lower() == ".md":
            return candidate
    raise HTTPException(404, "doc not found")


def _list_docs() -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {}
    for root in DOC_ROOTS:
        if not root.exists():
            continue
        for p in sorted(root.rglob("*.md")):
            rel = str(p.relative_to(REPO)).replace("\\", "/")
            title = p.stem.replace("_", " ")
            out.setdefault(root.name, []).append((rel, title))
    return out


def _md_to_html(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    in_code = False
    in_ul = False
    para: list[str] = []

    def flush_para():
        nonlocal para
        if para:
            text = " ".join(para).strip()
            if text:
                text = re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(text))
                text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
                out.append(f"<p>{text}</p>")
            para = []

    def close_ul():
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("```"):
            flush_para(); close_ul()
            out.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(html.escape(line))
            continue
        if not line.strip():
            flush_para(); close_ul(); continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush_para(); close_ul()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{html.escape(m.group(2))}</h{lvl}>")
            continue
        if re.match(r"^\s*[-*]\s+", line):
            flush_para()
            if not in_ul:
                out.append("<ul>"); in_ul = True
            text = re.sub(r"^\s*[-*]\s+", "", line)
            text = re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(text))
            out.append(f"<li>{text}</li>")
            continue
        para.append(line)

    flush_para(); close_ul()
    if in_code:
        out.append("</pre>")
    return "\n".join(out)


@router.get("/docs", response_class=HTMLResponse)
def docs_index(user: User = Depends(current_user_web)):
    grouped = _list_docs()
    rows = []
    for folder, items in grouped.items():
        rows.append(f'<h3 style="margin-top:24px;color:#e5e5e5;">{html.escape(folder)}</h3><ul>')
        for rel, title in items:
            rows.append(
                f'<li><a href="/dashboard/docs/{rel}" style="color:#60a5fa;">{html.escape(title)}</a>'
                f' <span style="color:#666;font-size:11px;">{html.escape(rel)}</span></li>'
            )
        rows.append('</ul>')
    body = (
        W.dashboard_nav("/dashboard/docs")
        + '<div class="container" style="max-width:900px;">'
        + '<h2>Project Docs</h2>'
        + '<p class="muted">Rendered from PROJECT/, .ai/, and docs/ in the repo. '
        + 'Edit the .md, commit, refresh — no restart needed.</p>'
        + "".join(rows)
        + '</div>'
    )
    return HTMLResponse(W.page("Docs", body, W.topbar(user.email)))


@router.get("/docs/{path:path}", response_class=HTMLResponse)
def docs_view(path: str, user: User = Depends(current_user_web)):
    f = _safe_resolve(path)
    md = f.read_text(encoding="utf-8", errors="replace")
    rendered = _md_to_html(md)
    rel = str(f.relative_to(REPO)).replace("\\", "/")
    body = (
        W.dashboard_nav("/dashboard/docs")
        + '<div class="container" style="max-width:900px;">'
        + f'<p><a href="/dashboard/docs" style="color:#60a5fa;">&larr; Docs</a>'
        + f' &nbsp; <span class="muted" style="font-size:12px;">{html.escape(rel)}</span></p>'
        + f'<div class="doc-body" style="line-height:1.6;color:#d4d4d4;">{rendered}</div>'
        + '</div>'
        + '<style>'
        + '.doc-body h1,.doc-body h2,.doc-body h3,.doc-body h4{color:#e5e5e5;margin-top:22px;margin-bottom:8px;}'
        + '.doc-body pre{background:#111;border:1px solid #222;border-radius:8px;'
        + 'padding:12px;overflow-x:auto;font-size:12px;line-height:1.5;color:#d4d4d4;}'
        + '.doc-body code{background:#1a1a1a;padding:1px 5px;border-radius:4px;font-size:12px;color:#f0abfc;}'
        + '.doc-body a{color:#60a5fa;text-decoration:none;}'
        + '.doc-body a:hover{text-decoration:underline;}'
        + '.doc-body ul{padding-left:22px;}'
        + '.doc-body li{margin:3px 0;}'
        + '.doc-body p{margin:10px 0;}'
        + '</style>'
    )
    return HTMLResponse(W.page(f.stem, body, W.topbar(user.email)))
