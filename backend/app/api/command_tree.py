"""Canonical command tree for AInterceptor.

Single source of truth consumed by:
  - backend/scripts/ashell.py       (interactive shell)
  - backend/app/api/commandline_ui  (web reference page)

Add a command here once; both consumers pick it up.
"""
from __future__ import annotations

# Node shape:
#   { "category": str, "desc": str, "syntax": str,
#     "examples": [str], "built": bool,
#     "subcommands": { name: <same shape, minus category> } }

COMMAND_TREE: dict[str, dict] = {

    # ── Status & Health ──────────────────────────────────────────
    "astatus": {
        "category": "Status & Health",
        "desc": "Daemon PID, CDP port, Xvfb, x11vnc, active providers, open tabs",
        "syntax": "astatus",
        "examples": ["astatus"],
        "built": True,
    },
    "ahealth": {
        "category": "Status & Health",
        "desc": "Pretty-print of /health — supervisor, exporter, prober, circuits",
        "syntax": "ahealth",
        "examples": ["ahealth"],
        "built": True,
    },
    "aversion": {
        "category": "Status & Health",
        "desc": "Versions of AInterceptor, Python, Chrome, xdotool, current .env flags",
        "syntax": "aversion",
        "examples": ["aversion"],
        "built": True,
    },
    "aprobe": {
        "category": "Status & Health",
        "desc": "Read-only provider health. Sends NO messages.",
        "syntax": "aprobe [provider ...]",
        "examples": ["aprobe", "aprobe claude", "aprobe claude chatgpt"],
        "built": True,
    },
    "atest": {
        "category": "Status & Health",
        "desc": "Round-trip test — sends a real message and waits for reply. Pollutes chat history.",
        "syntax": "atest <provider>",
        "examples": ["atest deepseek"],
        "built": True,
    },

    # ── Daemon Lifecycle ─────────────────────────────────────────
    "astart": {
        "category": "Daemon Lifecycle",
        "desc": "Start daemon if not running. Idempotent.",
        "syntax": "astart [--fg]",
        "examples": ["astart", "astart --fg"],
        "built": True,
    },
    "arestart": {
        "category": "Daemon Lifecycle",
        "desc": "Stop + start. Use after .env or code changes.",
        "syntax": "arestart [--fg]",
        "examples": ["arestart", "arestart --fg"],
        "built": True,
    },
    "astop": {
        "category": "Daemon Lifecycle",
        "desc": "Stop daemon + Chrome, clear Singleton locks",
        "syntax": "astop",
        "examples": ["astop"],
        "built": True,
    },

    # ── Chat ─────────────────────────────────────────────────────
    "chatgpt":  {"category": "Chat", "desc": "Enter ChatGPT REPL (/exit to leave)",
                 "syntax": "chatgpt", "examples": ["chatgpt"], "built": True},
    "claude":   {"category": "Chat", "desc": "Enter Claude REPL",
                 "syntax": "claude", "examples": ["claude"], "built": True},
    "deepseek": {"category": "Chat", "desc": "Enter DeepSeek REPL",
                 "syntax": "deepseek", "examples": ["deepseek"], "built": True},
    "gemini":   {"category": "Chat", "desc": "Enter Gemini REPL",
                 "syntax": "gemini", "examples": ["gemini"], "built": True},

    # ── Providers ────────────────────────────────────────────────
    "aproviders": {
        "category": "Providers",
        "desc": "Manage the 20 configured providers",
        "syntax": "aproviders <subcommand>",
        "built": True,
        "subcommands": {
            "list":     {"desc": "List all 20 providers with status",
                         "syntax": "aproviders list",
                         "examples": ["aproviders"], "built": True},
            "enable":   {"desc": "Add provider to .env active list (applies on arestart)",
                         "syntax": "aproviders enable <name>",
                         "examples": ["aproviders enable mistral"], "built": True},
            "disable":  {"desc": "Remove provider from active list",
                         "syntax": "aproviders disable <name>",
                         "examples": ["aproviders disable mistral"], "built": True},
            "info":     {"desc": "Host, home URL, login markers",
                         "syntax": "aproviders info <name>",
                         "examples": ["aproviders info claude"], "built": True},
            "status":   {"desc": "5-layer diagnostic: listed / registry / runtime file / active / session",
                         "syntax": "aproviders status <name>",
                         "examples": ["aproviders status perplexity"], "built": True},
            "validate": {"desc": "status + live probe (opens tab, checks DOM)",
                         "syntax": "aproviders validate <name>",
                         "examples": ["aproviders validate claude"], "built": True},
            "add":      {"desc": "Interactive wizard to add a new provider",
                         "syntax": "aproviders add <name> [--url --host --login-markers --no-activate --yes]",
                         "examples": ["aproviders add newprovider",
                                      "aproviders add np --url https://np.com/chat --host np.com --yes"],
                         "built": True},
            "remove":   {"desc": "Deactivate (does not delete runtime files)",
                         "syntax": "aproviders remove <name>",
                         "examples": ["aproviders remove newprovider"], "built": True},
            "test":     {"desc": "Alias for aprobe <name>",
                         "syntax": "aproviders test <name>",
                         "examples": ["aproviders test deepseek"], "built": True},
        },
    },

    # ── Sessions ─────────────────────────────────────────────────
    "alogin": {
        "category": "Sessions",
        "desc": "Agent-first login. Prints agent command, waits for upload.",
        "syntax": "alogin <provider> [--vnc]",
        "examples": ["alogin claude", "alogin claude --vnc"],
        "built": True,
    },
    "alogout": {
        "category": "Sessions",
        "desc": "Clear that provider's cookies from VM Chrome (siblings untouched)",
        "syntax": "alogout <provider>",
        "examples": ["alogout claude"],
        "built": True,
    },
    "ashow": {"category": "Sessions", "desc": "Move all Chrome windows on-screen (for VNC)",
              "syntax": "ashow", "examples": ["ashow"], "built": True},
    "ahide": {"category": "Sessions", "desc": "Move all Chrome windows off-screen",
              "syntax": "ahide", "examples": ["ahide"], "built": True},
    "asessions": {
        "category": "Sessions",
        "desc": "Manage DB-stored provider sessions",
        "syntax": "asessions <subcommand>",
        "built": True,
        "subcommands": {
            "list":   {"desc": "List YOUR (admin's) sessions",
                       "syntax": "asessions", "examples": ["asessions"], "built": True},
            "all":    {"desc": "Admin view — every user's sessions with owning email",
                       "syntax": "asessions --all", "examples": ["asessions --all"], "built": True},
            "export": {"desc": "Copy local storage_state file for a provider",
                       "syntax": "asessions export <provider> [path]",
                       "examples": ["asessions export claude ~/claude.json"], "built": True},
            "delete": {"desc": "Remove a session row from the DB",
                       "syntax": "asessions delete <provider>",
                       "examples": ["asessions delete claude"], "built": True},
        },
    },

    # ── Configuration ────────────────────────────────────────────
    "aconfig": {
        "category": "Configuration",
        "desc": "Read/write .env keys",
        "syntax": "aconfig <subcommand>",
        "built": True,
        "subcommands": {
            "show": {"desc": "Print every AINTERCEPTOR_* key with description",
                     "syntax": "aconfig show", "examples": ["aconfig show"], "built": True},
            "list": {"desc": "List known config keys",
                     "syntax": "aconfig list", "examples": ["aconfig list"], "built": True},
            "get":  {"desc": "Print one value",
                     "syntax": "aconfig get <key>",
                     "examples": ["aconfig get AINTERCEPTOR_ADMIN_EMAIL"], "built": True},
            "set":  {"desc": "Write a value. Restart daemon to apply.",
                     "syntax": "aconfig set <key> <value>",
                     "examples": ["aconfig set AINTERCEPTOR_ADMIN_EMAIL you@example.com"],
                     "built": True},
        },
    },
    "aconfig-reset": {
        "category": "Configuration",
        "desc": "Restore a config key to its default value",
        "syntax": "aconfig-reset <key>",
        "examples": ["aconfig-reset AINTERCEPTOR_ACTIVE_PROVIDERS"],
        "built": True,
    },

    # ── API Keys ─────────────────────────────────────────────────
    "akeys": {
        "category": "API Keys",
        "desc": "Manage user API keys (sk-aint-*)",
        "syntax": "akeys <subcommand>",
        "built": True,
        "subcommands": {
            "list":    {"desc": "All keys with status, prefix, name",
                        "syntax": "akeys list", "examples": ["akeys list"], "built": True},
            "create":  {"desc": "Mint a new key. --save writes to ~/.ainterceptor/admin_api_key.txt",
                        "syntax": "akeys create <name> [--save]",
                        "examples": ["akeys create careeros-prod --save"], "built": True},
            "current": {"desc": "Show prefix of the loaded key (never the token)",
                        "syntax": "akeys current", "examples": ["akeys current"], "built": True},
            "revoke":  {"desc": "Revoke by ID",
                        "syntax": "akeys revoke <id>",
                        "examples": ["akeys revoke 39fdbee8-..."], "built": True},
            "rotate":  {"desc": "Issue replacement, revoke old after grace period",
                        "syntax": "akeys rotate <id>",
                        "examples": ["akeys rotate 39fdbee8-..."], "built": False},
            "reveal":  {"desc": "Show plaintext (one-time)",
                        "syntax": "akeys reveal <id>",
                        "examples": [], "built": False,
                        "note": "Cannot be built — keys are stored as one-way hashes."},
        },
    },

    # ── Tokens (planned) ─────────────────────────────────────────
    "atoken": {
        "category": "Tokens (planned)",
        "desc": "Short-lived bearer tokens for scripts and CI jobs",
        "syntax": "atoken <subcommand>",
        "built": False,
        "subcommands": {
            "create": {"desc": "Mint a token with TTL",
                       "syntax": "atoken create --ttl 1h",
                       "examples": ["atoken create --ttl 1h"], "built": False},
            "list":   {"desc": "Active tokens",
                       "syntax": "atoken list", "examples": ["atoken list"], "built": False},
            "revoke": {"desc": "Revoke a token",
                       "syntax": "atoken revoke <id>",
                       "examples": [], "built": False},
        },
    },

    # ── Routing (planned) ────────────────────────────────────────
    "aroute": {
        "category": "Routing (planned)",
        "desc": "Per-capability routing table (needs routing engine)",
        "syntax": "aroute <subcommand>",
        "built": False,
        "subcommands": {
            "show":     {"desc": "Show current routing table",
                         "syntax": "aroute show", "examples": ["aroute show"], "built": False},
            "set":      {"desc": "Set primary/secondary/tertiary per capability",
                         "syntax": "aroute set <capability> <provider-chain>",
                         "examples": ["aroute set reasoning claude,chatgpt,gemini"], "built": False},
            "fallback": {"desc": "Provider-level fallback chain",
                         "syntax": "aroute fallback <provider> <next>",
                         "examples": ["aroute fallback claude chatgpt"], "built": False},
        },
    },

    # ── Rate Limits (planned) ────────────────────────────────────
    "arate": {
        "category": "Rate Limits (planned)",
        "desc": "Per-provider rate limits and cooldowns",
        "syntax": "arate <subcommand>",
        "built": False,
        "subcommands": {
            "show":     {"desc": "Current limits per provider",
                         "syntax": "arate show", "examples": ["arate show"], "built": False},
            "set":      {"desc": "Set requests per second",
                         "syntax": "arate set <provider> <rps>",
                         "examples": ["arate set claude 0.5"], "built": False},
            "cooldown": {"desc": "Set 429 cooldown in seconds",
                         "syntax": "arate cooldown <provider> <seconds>",
                         "examples": ["arate cooldown claude 60"], "built": False},
        },
    },

    # ── Logs & Evidence ──────────────────────────────────────────
    "alogs": {
        "category": "Logs & Evidence",
        "desc": "Tail a named log file",
        "syntax": "alogs [daemon|chrome|x11vnc]",
        "examples": ["alogs daemon", "alogs chrome"],
        "built": True,
    },
    "aevidence": {
        "category": "Logs & Evidence",
        "desc": "Browse validation evidence logs",
        "syntax": "aevidence <subcommand>",
        "built": True,
        "subcommands": {
            "list":  {"desc": "List recent validation logs",
                      "syntax": "aevidence", "examples": ["aevidence"], "built": True},
            "show":  {"desc": "Show one log",
                      "syntax": "aevidence show <name>",
                      "examples": ["aevidence show phase_1_....log"], "built": True},
            "clear": {"desc": "Prune logs older than N days",
                      "syntax": "aevidence clear [days]",
                      "examples": ["aevidence clear 30"], "built": True},
        },
    },

    # ── Bootstrap & Git ──────────────────────────────────────────
    "abootstrap": {
        "category": "Bootstrap & Git",
        "desc": "Create admin user + first API key (idempotent)",
        "syntax": "abootstrap",
        "examples": ["abootstrap"],
        "built": True,
    },
    "asave": {
        "category": "Bootstrap & Git",
        "desc": "git add -A && commit && push",
        "syntax": 'asave "<message>"',
        "examples": ['asave "feat: add thing"'],
        "built": True,
    },

    # ── Automation ───────────────────────────────────────────────
    "asession": {
        "category": "Automation",
        "desc": "Append a decision to .ai/SESSION_LOG.md (R6)",
        "syntax": 'asession [--quick "title" "chosen" "why"]',
        "examples": ["asession", 'asession --quick "Adopt X" "yes" "because Y"'],
        "built": True,
    },
    "aprogress": {
        "category": "Automation",
        "desc": "Regenerate .ai/PROGRESS.md from git log (R1)",
        "syntax": "aprogress [--show] [--commits N]",
        "examples": ["aprogress", "aprogress --show --commits 20"],
        "built": True,
    },
    "sync_docs": {
        "category": "Automation",
        "desc": "Parse commit tags, update ROADMAP / BUGS / FUTURE / CHANGELOG",
        "syntax": "sync_docs --last-commit [--dry] | --commit <sha>",
        "examples": ["sync_docs --last-commit", "sync_docs --last-commit --dry"],
        "built": True,
    },

    # ── Agent (laptop) ───────────────────────────────────────────
    "airouter-agent": {
        "category": "Agent (laptop)",
        "desc": "User-side agent — runs on the user's laptop, not the VM",
        "syntax": "airouter-agent <subcommand>",
        "built": True,
        "subcommands": {
            "connect": {"desc": "Exchange a device code for a persistent token",
                        "syntax": "airouter-agent connect --server URL --code XXXX-XXXX",
                        "examples": ["airouter-agent connect --server https://ainterceptor.taila2310c.ts.net --code HK4P-QR7W"],
                        "built": True},
            "login":   {"desc": "Open real Chrome, wait for user login, upload storage_state",
                        "syntax": "airouter-agent login <provider>",
                        "examples": ["airouter-agent login claude"], "built": True},
            "serve":   {"desc": "Local helper (port 45231) the dashboard calls for one-click logins",
                        "syntax": "airouter-agent serve [--port 45231]",
                        "examples": ["airouter-agent serve"], "built": True},
            "status":  {"desc": "Show server, token prefix, hostname, reachability",
                        "syntax": "airouter-agent status",
                        "examples": ["airouter-agent status"], "built": True},
            "config":  {"desc": "Store server + token manually",
                        "syntax": "airouter-agent config --server URL --token TOK",
                        "examples": [], "built": True},
        },
    },

    # ── Shell ────────────────────────────────────────────────────
    "ashell": {
        "category": "Shell",
        "desc": "Interactive Cisco-style shell with ? help and Tab completion",
        "syntax": "ashell",
        "examples": ["ashell"],
        "built": True,
    },
}


def categories() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name, node in COMMAND_TREE.items():
        out.setdefault(node.get("category", "Other"), []).append(name)
    return {k: sorted(v) for k, v in sorted(out.items())}
