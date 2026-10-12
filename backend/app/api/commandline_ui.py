"""Dashboard: /dashboard/commandline — interactive CLI reference.

Reads the same command tree the ashell uses (backend/app/api/command_tree.py).
"""
from __future__ import annotations
import html

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.db.models import User
from app.deps import current_user_web
from app.api import web_common as W
from app.api.command_tree import COMMAND_TREE


router = APIRouter(prefix="/dashboard", tags=["commandline"])

CATEGORY_ORDER = [
    "Status & Health", "Daemon Lifecycle", "Chat", "Providers", "Sessions",
    "Configuration", "API Keys", "Logs & Evidence", "Bootstrap & Git",
    "Automation", "Agent (laptop)", "Shell",
    "Tokens (planned)", "Routing (planned)", "Rate Limits (planned)",
]


def _esc(s):
    return html.escape(s or "", quote=True)


def _cat_id(cat):
    return ("cat-" + cat.lower()
            .replace(" ", "-").replace("&", "and")
            .replace("(", "").replace(")", ""))


def _card(name, node):
    built = node.get("built", True)
    badge = "" if built else '<span class="cmd-badge">not yet built</span>'
    subs = node.get("subcommands") or {}

    subs_html = ""
    if subs:
        rows = []
        for sn in sorted(subs):
            sv = subs[sn]
            sbadge = "" if sv.get("built", True) else ' <span class="cmd-badge">planned</span>'
            ex = (sv.get("examples") or [""])[0]
            rows.append(
                '<div class="cmd-sub">'
                '<code class="cmd-sub-name">' + _esc(name + " " + sn) + '</code>'
                + sbadge +
                '<div class="cmd-sub-desc">' + _esc(sv.get("desc", "")) + '</div>'
                + ('<div class="cmd-example"><code>' + _esc(ex) + '</code>'
                   '<button class="cmd-copy" data-copy="' + _esc(ex) + '">copy</button></div>'
                   if sv.get("examples") else "")
                + '</div>'
            )
        subs_html = '<div class="cmd-subs">' + "".join(rows) + '</div>'

    examples_html = ""
    if node.get("examples"):
        parts = []
        for e in node["examples"]:
            parts.append(
                '<div class="cmd-example"><code>' + _esc(e) + '</code>'
                '<button class="cmd-copy" data-copy="' + _esc(e) + '">copy</button></div>'
            )
        examples_html = '<div class="cmd-examples">' + "".join(parts) + '</div>'

    note_html = ""
    if node.get("note"):
        note_html = '<div class="cmd-note">' + _esc(node["note"]) + '</div>'

    blob_parts = [name, node.get("desc", ""), node.get("syntax", "")]
    blob_parts += (node.get("examples") or [])
    blob_parts += list(subs.keys())
    blob = " ".join(blob_parts).lower()

    return (
        '<div class="cmd-card" id="' + _esc(name) + '" '
        'data-name="' + _esc(name) + '" '
        'data-search="' + _esc(blob) + '">'
        '<div class="cmd-head" onclick="cmdToggle(this.parentNode)">'
        '<code class="cmd-name">' + _esc(name) + '</code>' + badge +
        '<span class="cmd-syntax">' + _esc(node.get("syntax", name)) + '</span>'
        '<span class="cmd-arrow">&#9656;</span></div>'
        '<div class="cmd-desc">' + _esc(node.get("desc", "")) + '</div>'
        '<div class="cmd-body" hidden>'
        + examples_html + subs_html + note_html +
        '</div></div>'
    )


@router.get("/commandline", response_class=HTMLResponse)
def commandline_page(user: User = Depends(current_user_web)):
    by_cat = {}
    for name, node in COMMAND_TREE.items():
        by_cat.setdefault(node.get("category", "Other"), []).append(name)

    seen = set(CATEGORY_ORDER)
    tail = sorted(c for c in by_cat if c not in seen)
    order = [c for c in CATEGORY_ORDER if c in by_cat] + tail

    sections = []
    for cat in order:
        names = sorted(by_cat[cat])
        cards = "".join(_card(n, COMMAND_TREE[n]) for n in names)
        sections.append(
            '<section class="cmd-section" id="' + _esc(_cat_id(cat)) + '">'
            '<h3 class="cmd-cat-title">' + _esc(cat)
            + ' <span class="cmd-cat-count">(' + str(len(names)) + ')</span></h3>'
            + cards + '</section>'
        )

    total = len(COMMAND_TREE)
    built = sum(1 for n in COMMAND_TREE.values() if n.get("built", True))
    cat_links = "".join(
        '<a class="cmd-jump" href="#' + _esc(_cat_id(c)) + '">' + _esc(c) + '</a>'
        for c in order
    )

    CSS = (
        ".cmd-shell{max-width:1100px;margin:0 auto;padding:28px 24px}"
        ".cmd-shell h2{margin:0 0 6px}"
        ".cmd-meta{color:#888;font-size:13px;margin-bottom:22px}"
        ".cmd-search-wrap{position:sticky;top:0;z-index:10;background:#0a0a0a;"
        "padding:12px 0;margin-bottom:18px;border-bottom:1px solid #1a1a1a}"
        ".cmd-search{width:100%;padding:12px 16px;font-size:15px;font-family:inherit;"
        "background:#111;color:#fff;border:1px solid #333;border-radius:8px;outline:none}"
        ".cmd-search:focus{border-color:#1d4ed8}"
        ".cmd-search-hint{color:#666;font-size:12px;margin-top:6px}"
        ".cmd-jumps{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:22px}"
        ".cmd-jump{font-size:11px;color:#888;padding:4px 10px;border:1px solid #222;"
        "border-radius:12px;text-decoration:none}"
        ".cmd-jump:hover{color:#fff;border-color:#444}"
        ".cmd-section{margin-bottom:34px;scroll-margin-top:80px}"
        ".cmd-cat-title{font-size:15px;color:#bbb;border-bottom:1px solid #1f1f1f;"
        "padding-bottom:8px;margin-bottom:12px}"
        ".cmd-cat-count{color:#555;font-weight:400;font-size:13px}"
        ".cmd-card{border:1px solid #1f1f1f;border-radius:8px;background:#0d0d0d;"
        "margin-bottom:8px;scroll-margin-top:80px}"
        ".cmd-card:hover{border-color:#333}"
        ".cmd-card.cmd-highlight{border-color:#1d4ed8;box-shadow:0 0 0 2px rgba(29,78,216,.2)}"
        ".cmd-head{display:flex;align-items:center;gap:12px;padding:12px 16px;"
        "cursor:pointer;user-select:none}"
        ".cmd-name{font-family:ui-monospace,monospace;font-size:14px;color:#e6e6e6;font-weight:600}"
        ".cmd-syntax{color:#666;font-family:ui-monospace,monospace;font-size:12px;"
        "flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"
        ".cmd-arrow{color:#555;transition:transform .15s}"
        ".cmd-card.cmd-open .cmd-arrow{transform:rotate(90deg)}"
        ".cmd-badge{font-size:10px;text-transform:uppercase;padding:2px 6px;"
        "border-radius:4px;font-weight:700;letter-spacing:.5px;"
        "background:#422006;color:#fbbf24}"
        ".cmd-desc{padding:0 16px 14px;color:#999;font-size:13px;line-height:1.5}"
        ".cmd-body{padding:0 16px 16px;border-top:1px solid #1a1a1a;margin-top:2px}"
        ".cmd-examples{margin-top:12px}"
        ".cmd-example{display:flex;align-items:center;gap:8px;background:#0a0a0a;"
        "border:1px solid #1a1a1a;border-radius:6px;padding:8px 12px;margin-bottom:6px}"
        ".cmd-example code{flex:1;font-family:ui-monospace,monospace;font-size:12.5px;"
        "color:#93c5fd;overflow-x:auto;white-space:pre}"
        ".cmd-copy{background:#1a1a1a;color:#bbb;border:0;border-radius:4px;"
        "padding:3px 10px;font-size:11px;cursor:pointer;font-family:inherit}"
        ".cmd-copy:hover{background:#222;color:#fff}"
        ".cmd-subs{margin-top:12px}"
        ".cmd-sub{padding:10px 0 10px 14px;border-left:2px solid #1f1f1f;margin-bottom:6px}"
        ".cmd-sub-name{font-family:ui-monospace,monospace;font-size:13px;color:#ccc;font-weight:500}"
        ".cmd-sub-desc{color:#888;font-size:12.5px;margin-top:3px}"
        ".cmd-note{margin-top:12px;padding:10px 12px;background:#1c1917;border-left:3px solid #7c2d12;"
        "color:#fbbf24;font-size:12.5px;border-radius:0 4px 4px 0}"
        ".cmd-empty{color:#666;text-align:center;padding:40px 0}"
        ".cmd-hidden{display:none}"
    )

    body_html = (
        '<div class="cmd-shell">'
        '<h2>Command Line Reference</h2>'
        '<div class="cmd-meta">'
        + str(total) + ' commands across ' + str(len(order)) + ' categories &middot; '
        + str(built) + ' built, ' + str(total - built) + ' planned &mdash; '
        'same tree as <code>ashell</code>.</div>'
        '        \'<link rel="stylesheet" href="/dashboard/commandline.css">\''
        '        \'<div class="cmd-console">\''
        '        \'<div class="cmd-console-bar">\''
        '        \'<span class="cmd-console-prompt">AIRouter&gt;</span>\''
        '        \'<input id="cmd-input" class="cmd-console-input" autocomplete="off" \''
        '        \'spellcheck="false" placeholder="type a command, Tab to complete, ? for syntax">\''
        '        \'</div>\''
        '        \'<pre id="cmd-out" class="cmd-console-out"></pre>\''
        '        \'<div class="cmd-console-hint">\''
        '        \'<kbd>Tab</kbd> completes commands, subcommands and values &middot; \''
        '        \'<kbd>?</kbd> shows the valid next tokens &middot; \''
        '        \'<kbd>Enter</kbd> filters the cards below &middot; \''
        '        \'<kbd>Esc</kbd> clears\''
        '        \'</div>\''
        '        \'</div>\''
        '        \'<div class="cmd-chips" id="cmd-chips"></div>\''
        '        \'<script id="cmd-tree" type="application/json">{"astatus":{"desc":"Daemon PID, CDP port, Xvfb, x11vnc, active providers, open tabs","syntax":"astatus"},"ahealth":{"desc":"Pretty-print of /health \\u2014 supervisor, exporter, prober, circuits","syntax":"ahealth"},"aversion":{"desc":"Versions of AInterceptor, Python, Chrome, xdotool, current .env flags","syntax":"aversion"},"aprobe":{"desc":"Read-only provider health. Sends NO messages.","syntax":"aprobe [provider ...]","args":{"provider":{"type":"provider","desc":"provider name"}}},"atest":{"desc":"Round-trip test \\u2014 sends a real message and waits for reply. Pollutes chat history.","syntax":"atest <provider>","args":{"provider":{"type":"provider","desc":"provider name"}}},"astart":{"desc":"Start daemon if not running. Idempotent.","syntax":"astart [--fg]"},"arestart":{"desc":"Stop + start. Use after .env or code changes.","syntax":"arestart [--fg]"},"astop":{"desc":"Stop daemon + Chrome, clear Singleton locks","syntax":"astop"},"chatgpt":{"desc":"Enter ChatGPT REPL (/exit to leave)","syntax":"chatgpt"},"claude":{"desc":"Enter Claude REPL","syntax":"claude"},"deepseek":{"desc":"Enter DeepSeek REPL","syntax":"deepseek"},"gemini":{"desc":"Enter Gemini REPL","syntax":"gemini"},"aproviders":{"desc":"Manage the 20 configured providers","syntax":"aproviders <subcommand>","subcommands":{"list":{"desc":"List all 20 providers with status"},"enable":{"desc":"Add provider to .env active list (applies on arestart)","args":{"provider":{"type":"provider","desc":"provider name"}}},"disable":{"desc":"Remove provider from active list","args":{"provider":{"type":"provider","desc":"provider name"}}},"info":{"desc":"Host, home URL, login markers","args":{"provider":{"type":"provider","desc":"provider name"}}},"status":{"desc":"5-layer diagnostic: listed / registry / runtime file / active / session","args":{"provider":{"type":"provider","desc":"provider name"}}},"validate":{"desc":"status + live probe (opens tab, checks DOM)","args":{"provider":{"type":"provider","desc":"provider name"}}},"add":{"desc":"Interactive wizard to add a new provider"},"remove":{"desc":"Deactivate (does not delete runtime files)","args":{"provider":{"type":"provider","desc":"provider name"}}},"test":{"desc":"Alias for aprobe <name>","args":{"provider":{"type":"provider","desc":"provider name"}}}}},"alogin":{"desc":"Agent-first login. Prints agent command, waits for upload.","syntax":"alogin <provider> [--vnc]","args":{"provider":{"type":"provider","desc":"provider name"}}},"alogout":{"desc":"Clear that provider\'s cookies from VM Chrome (siblings untouched)","syntax":"alogout <provider>","args":{"provider":{"type":"provider","desc":"provider name"}}},"ashow":{"desc":"Move all Chrome windows on-screen (for VNC)","syntax":"ashow"},"ahide":{"desc":"Move all Chrome windows off-screen","syntax":"ahide"},"asessions":{"desc":"Manage DB-stored provider sessions","syntax":"asessions <subcommand>","args":{"provider":{"type":"provider","desc":"provider name"}},"subcommands":{"list":{"desc":"List YOUR (admin\'s) sessions"},"all":{"desc":"Admin view \\u2014 every user\'s sessions with owning email"},"export":{"desc":"Copy local storage_state file for a provider"},"delete":{"desc":"Remove a session row from the DB"}}},"aconfig":{"desc":"Read/write .env keys","syntax":"aconfig <subcommand>","subcommands":{"show":{"desc":"Print every AINTERCEPTOR_* key with description"},"list":{"desc":"List known config keys"},"get":{"desc":"Print one value"},"set":{"desc":"Write a value. Restart daemon to apply."}}},"aconfig-reset":{"desc":"Restore a config key to its default value","syntax":"aconfig-reset <key>"},"akeys":{"desc":"Manage user API keys (sk-aint-*)","syntax":"akeys <subcommand>","args":{"sub":{"type":"choice","choices":["list","create","current","revoke","rotate"],"desc":"subcommand"}},"subcommands":{"list":{"desc":"All keys with status, prefix, name"},"create":{"desc":"Mint a new key. --save writes to ~/.ainterceptor/admin_api_key.txt"},"current":{"desc":"Show prefix of the loaded key (never the token)"},"revoke":{"desc":"Revoke by ID"},"rotate":{"desc":"Issue replacement, revoke old after grace period"},"reveal":{"desc":"Show plaintext (one-time)"}}},"atoken":{"desc":"Short-lived bearer tokens for scripts and CI jobs","syntax":"atoken <subcommand>","subcommands":{"create":{"desc":"Mint a token with TTL"},"list":{"desc":"Active tokens"},"revoke":{"desc":"Revoke a token"}}},"aroute":{"desc":"Per-capability routing table (needs routing engine)","syntax":"aroute <subcommand>","subcommands":{"show":{"desc":"Show current routing table"},"set":{"desc":"Set primary/secondary/tertiary per capability"},"fallback":{"desc":"Provider-level fallback chain"}}},"arate":{"desc":"Per-provider rate limits and cooldowns","syntax":"arate <subcommand>","subcommands":{"show":{"desc":"Current limits per provider"},"set":{"desc":"Set requests per second"},"cooldown":{"desc":"Set 429 cooldown in seconds"}}},"alogs":{"desc":"Tail a named log file","syntax":"alogs [daemon|chrome|x11vnc]","args":{"name":{"type":"choice","choices":["daemon","chrome","x11vnc"],"desc":"log name"}}},"aevidence":{"desc":"Browse validation evidence logs","syntax":"aevidence <subcommand>","subcommands":{"list":{"desc":"List recent validation logs"},"show":{"desc":"Show one log"},"clear":{"desc":"Prune logs older than N days"}}},"abootstrap":{"desc":"Create admin user + first API key (idempotent)","syntax":"abootstrap"},"asave":{"desc":"git add -A && commit && push","syntax":"asave \\"<message>\\""},"asession":{"desc":"Append a decision to .ai/SESSION_LOG.md (R6)","syntax":"asession [--quick \\"title\\" \\"chosen\\" \\"why\\"]"},"aprogress":{"desc":"Regenerate .ai/PROGRESS.md from git log (R1)","syntax":"aprogress [--show] [--commits N]"},"sync_docs":{"desc":"Parse commit tags, update ROADMAP / BUGS / FUTURE / CHANGELOG","syntax":"sync_docs --last-commit [--dry] | --commit <sha>"},"airouter-agent":{"desc":"User-side agent \\u2014 runs on the user\'s laptop, not the VM","syntax":"airouter-agent <subcommand>","subcommands":{"connect":{"desc":"Exchange a device code for a persistent token"},"login":{"desc":"Open real Chrome, wait for user login, upload storage_state"},"serve":{"desc":"Local helper (port 45231) the dashboard calls for one-click logins"},"status":{"desc":"Show server, token prefix, hostname, reachability","args":{"provider":{"type":"provider","desc":"provider name"}}},"config":{"desc":"Store server + token manually"}}},"ashell":{"desc":"Interactive Cisco-style shell with ? help and Tab completion","syntax":"ashell"}}</script>\''
        '        \'<script id="cmd-providers" type="application/json">["character","chatgpt","claude","copilot","deepseek","doubao","gemini","glm","grok","huggingchat","kimi","lechat","meta","mistral","perplexity","phind","poe","qwen","yi","you"]</script>\''
        '        \'<script src="/dashboard/commandline.js" defer></script>\''
        '<div class="cmd-search-wrap">'
        '<input id="cmd-search" class="cmd-search" type="text" '
        'placeholder="Search commands, examples, subcommands… (try aproviders, login, key)" '
        'autocomplete="off" spellcheck="false">'
        '<div class="cmd-search-hint" id="cmd-count">&nbsp;</div>'
        '</div>'
        '<div class="cmd-jumps">' + cat_links + '</div>'
        '<div id="cmd-sections">' + "".join(sections) + '</div>'
        '<div id="cmd-empty" class="cmd-empty cmd-hidden">No commands match your search.</div>'
        '</div>'
    )

    JS = (
        "(function(){"
        "var input=document.getElementById('cmd-search');"
        "var count=document.getElementById('cmd-count');"
        "var empty=document.getElementById('cmd-empty');"
        "var sections=document.querySelectorAll('.cmd-section');"
        "var cards=Array.prototype.slice.call(document.querySelectorAll('.cmd-card'));"
        "var chips=document.getElementById('cmd-chips');"
        "var activeCat=null;"
        "cards.forEach(function(c){"
        "c._name=(c.getAttribute('data-name')||'').toLowerCase();"
        "c._blob=(c.getAttribute('data-search')||'').toLowerCase();"
        "var s=c.closest('.cmd-section');c._cat=s?s.id:'';});"
        "function score(c,q){"
        "if(c._name===q)return 100;"
        "if(c._name.indexOf(q)===0)return 80;"
        "if(c._name.indexOf(q)!==-1)return 60;"
        "var i=c._blob.indexOf(q);"
        "return i===-1?-1:20+Math.max(0,10-Math.floor(i/40));}"
        "function setCat(cat){activeCat=cat;"
        "Array.prototype.slice.call(chips.querySelectorAll('.cmd-chip')).forEach(function(b){"
        "b.classList.toggle('cmd-chip-on',(b.getAttribute('data-cat')||'')===(cat||''));});"
        "filter();}"
        "function filter(){"
        "var q=(input.value||'').toLowerCase().trim();var vis=0;"
        "var scored=cards.map(function(c){return [c,q?score(c,q):1];})"
        ".filter(function(p){return p[1]>=0;});"
        "scored.sort(function(a,b){return b[1]-a[1];});"
        "cards.forEach(function(c){c.classList.add('cmd-hidden');});"
        "sections.forEach(function(sec){sec.classList.add('cmd-hidden');});"
        "var host=document.getElementById('cmd-sections');"
        "scored.forEach(function(p){"
        "var c=p[0];"
        "if(activeCat&&c._cat!==activeCat)return;"
        "c.classList.remove('cmd-hidden');vis++;"
        "var sec=c.closest('.cmd-section');if(sec)sec.classList.remove('cmd-hidden');"
        "if(q&&c._name.indexOf(q)!==-1){c.classList.add('cmd-open');"
        "var b=c.querySelector('.cmd-body');if(b)b.hidden=false;}"
        "if(q&&host&&sec)host.appendChild(sec);});"
        "empty.classList.toggle('cmd-hidden',vis!==0);"
        "count.textContent=q?(vis+' of '+cards.length+' commands match (ranked)'"
        "+(activeCat?' in '+activeCat:''))"
        ":(cards.length+' commands \u00b7 type to filter; Tab-complete in the console above');}"
        "input.addEventListener('input',filter);"
        "if(chips){"
        "var all=document.createElement('button');"
        "all.className='cmd-chip cmd-chip-on';all.textContent='All';"
        "all.setAttribute('data-cat','');"
        "all.addEventListener('click',function(){setCat(null);});"
        "chips.appendChild(all);"
        "sections.forEach(function(sec){"
        "var t=sec.querySelector('.cmd-cat-title');if(!t)return;"
        r"var nm=t.textContent.replace(/\(\d+\)/,'').trim();"
        "var b=document.createElement('button');"
        "b.className='cmd-chip';b.textContent=nm;b.setAttribute('data-cat',sec.id);"
        "b.addEventListener('click',function(){setCat(sec.id);});chips.appendChild(b);});}"
        "document.addEventListener('click',function(ev){"
        "var t=ev.target;if(t&&t.classList.contains('cmd-copy')){"
        "var x=t.getAttribute('data-copy')||'';"
        "if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(x);}"
        "else{var ta=document.createElement('textarea');ta.value=x;"
        "ta.style.position='fixed';ta.style.left='-9999px';document.body.appendChild(ta);"
        "ta.select();try{document.execCommand('copy');}catch(e){}document.body.removeChild(ta);}"
        "var o=t.textContent;t.textContent='copied';setTimeout(function(){t.textContent=o;},1200);}});"
        "function fromHash(){var h=(location.hash||'').replace(/^#/,'');if(!h)return;"
        "var e=document.getElementById(h);"
        "if(e&&e.classList.contains('cmd-card')){e.classList.add('cmd-open');"
        "var b=e.querySelector('.cmd-body');if(b)b.hidden=false;"
        "e.scrollIntoView({behavior:'smooth',block:'center'});"
        "e.classList.add('cmd-highlight');"
        "setTimeout(function(){e.classList.remove('cmd-highlight');},2000);}}"
        "window.addEventListener('hashchange',fromHash);fromHash();"
        "document.addEventListener('keydown',function(ev){"
        "if(ev.key==='/'&&document.activeElement!==input){ev.preventDefault();"
        "input.focus();input.select();}});"
        "filter();"
        "})();"
        "function cmdToggle(card){card.classList.toggle('cmd-open');"
        "var b=card.querySelector('.cmd-body');"
        "if(b)b.hidden=!card.classList.contains('cmd-open');}"
    )

    full = (
        W.dashboard_nav("/dashboard/commandline")
        + "<style>" + CSS + "</style>"
        + body_html
        + "<script>" + JS + "</script>"
    )
    return HTMLResponse(W.page("Command Line", full, W.topbar(user.email)))


# ── static assets for the interactive console ───────────────────────

import pathlib as _pl
from fastapi.responses import PlainTextResponse as _PTR

_ASSET_DIR = _pl.Path(__file__).resolve().parent / "static"


@router.get("/commandline.css")
def _cli_css():
    return _PTR((_ASSET_DIR / "cli_console.css").read_text(encoding="utf-8"),
                media_type="text/css")


@router.get("/commandline.js")
def _cli_js():
    return _PTR((_ASSET_DIR / "cli_console.js").read_text(encoding="utf-8"),
                media_type="application/javascript")
