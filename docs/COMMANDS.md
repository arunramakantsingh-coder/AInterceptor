# AInterceptor — Command Reference

Auto-generated summary. Source of truth for day-to-day use.
Regenerate with:  aref

## CLI commands (on the VM)

### Status & health

| Command | Purpose |
|---|---|
| `astatus` | System state: daemon, CDP, Xvfb, x11vnc, active providers, tabs |
| `ahealth` | Pretty-print /health (supervisor, exporter, prober) |
| `aversion` | Versions of AInterceptor, Python, Chrome, xdotool |
| `aprobe` | Read-only provider health; `aprobe <p>` for one |
| `atest` | Round-trip test with a real message (pollutes chat) |

### Daemon lifecycle

| Command | Purpose |
|---|---|
| `astart` | Start daemon in background if not running |
| `astart --fg` | Start in foreground (blocks, shows logs) |
| `arestart` | Stop + start in background |
| `arestart --fg` | Stop + start in foreground |
| `astop` | Stop daemon + Chrome, wait, clear Singleton locks |

### Chat

| Command | Purpose |
|---|---|
| `chatgpt` | Enter ChatGPT CLI REPL |
| `claude` | Enter Claude CLI REPL |
| `deepseek` | Enter DeepSeek CLI REPL |
| `gemini` | Enter Gemini CLI REPL |

### Provider management

| Command | Purpose |
|---|---|
| `aproviders` | List all 20 providers with ACTIVE / inactive |
| `aproviders enable <n>` | Add to .env active list |
| `aproviders disable <n>` | Remove from .env active list |
| `aproviders info <n>` | Host, URL, login markers |
| `aproviders status <n>` | 5-layer diagnostic: listed/registry/runtime/active/session |
| `aproviders validate <n>` | status + live probe |
| `aproviders add <n>` | Interactive wizard to add a new provider |
| `aproviders remove <n>` | Deactivate (does not delete files) |
| `aproviders test <n>` | Alias for `aprobe <n>` |

### Sessions (VNC / agent)

| Command | Purpose |
|---|---|
| `alogin <p>` | Agent-first login; prints agent command, waits |
| `alogin <p> --vnc` | VNC fallback (admin) |
| `alogout <p>` | Clear that provider's cookies only |
| `ashow` | Move Chrome windows on-screen (VNC) |
| `ahide` | Move Chrome windows off-screen |
| `asessions` | List your DB-stored sessions |
| `asessions --all` | Admin view: all users' sessions |
| `asessions export <p> [path]` | Copy local storage_state file |
| `asessions delete <p>` | Remove a session row from DB |

### Configuration

| Command | Purpose |
|---|---|
| `aconfig show` | Print AINTERCEPTOR_* keys with descriptions |
| `aconfig list` | List known config keys |
| `aconfig get <key>` | Print one value |
| `aconfig set <k> <v>` | Write a value (restart to apply) |
| `aconfig-reset <key>` | Reset one key to default |

### API keys

| Command | Purpose |
|---|---|
| `akeys list` | All keys with status |
| `akeys create <n>` | Mint a key |
| `akeys create <n> --save` | Mint + write to ~/.ainterceptor/admin_api_key.txt |
| `akeys current` | Show prefix of loaded key (never the token) |
| `akeys revoke <id>` | Revoke by ID |

### Logs & evidence

| Command | Purpose |
|---|---|
| `alogs [daemon|chrome|x11vnc]` | Tail the named log (default: daemon) |
| `aevidence` | List recent validation logs |
| `aevidence show <name>` | Show one |
| `aevidence clear [days]` | Prune logs older than N days |

### Bootstrap & git

| Command | Purpose |
|---|---|
| `abootstrap` | Create admin user + first API key |
| `asave "message"` | git add -A && commit && push origin <branch> |

### Automation (R1/R6/R7)

| Command | Purpose |
|---|---|
| `asession` | Interactive: append a decision to .ai/SESSION_LOG.md |
| `asession --quick "title" "chosen" "why"` | Non-interactive append |
| `aprogress` | Regenerate .ai/PROGRESS.md from git log |
| `aprogress --show` | Print only (no write) |
| `aprogress --commits N` | Look at last N commits |
| `sync_docs --last-commit [--dry]` | Parse commit tags, update docs |
| `sync_docs --commit <sha>` | Process a specific commit |

### Agent (user's laptop)

| Command | Purpose |
|---|---|
| `airouter-agent connect --server URL --code XXXX-XXXX` | Exchange a device code for a persistent token |
| `airouter-agent login <provider>` | Open real Chrome, log in, upload session |
| `airouter-agent serve [--port 45231]` | Local helper the web UI calls to run commands |
| `airouter-agent status` | Show server, token prefix, hostname |
| `airouter-agent config --server URL --token TOK` | Store server + token manually |

## Web pages

| URL | Purpose |
|---|---|
| `/auth/login` | Email+password, Google button |
| `/auth/signup` | Sign up |
| `/login` | VNC admin landing |
| `/login/<provider>` | VNC per-provider (admin) |
| `/dashboard` | Overview: cards, recent activity, quick start |
| `/dashboard/agents` | One-click provider login via local helper |
| `/dashboard/sessions` | Kill / refresh / last-used |
| `/dashboard/devices` | List, revoke, inline connect-code generator |
| `/dashboard/providers` | 20-provider catalog, admin enable/disable |
| `/dashboard/usage` | Call history + summary cards |
| `/dashboard/keys` | Create / list / revoke API keys |
| `/dashboard/settings` | Account, password, danger zone |

## API endpoints

| Endpoint | Purpose |
|---|---|
| `POST /v1/chat/completions` | OpenAI-compatible; `stream=true` (SSE) or `stream=false` (JSON); auth: sk-aint-* |
| `POST /api/keys` | Mint an API key (auth: JWT or sk-aint-*) |
| `GET  /api/keys` | List keys |
| `DELETE /api/keys/{id}` | Revoke a key |
| `POST /api/sessions/upload` | Agent upload (auth: sk-dev-* or sk-aint-*) |
| `GET  /api/sessions` | List sessions for the caller |
| `DELETE /api/sessions/{id}` | Delete a session |
| `POST /api/devices/exchange` | Exchange a device code → sk-dev-* token |
| `GET  /auth/google` | Start Google OAuth |
| `GET  /auth/google/callback` | OAuth callback |
| `GET  /health` | Supervisor, exporter, prober, circuits snapshot |

## Environment (.env on VM)

| Key | Purpose |
|---|---|
| `AINTERCEPTOR_ACTIVE_PROVIDERS` | Comma-separated list of live providers |
| `AINTERCEPTOR_PROBER_ENABLED` | 0/1 — background prober (invasive; default 0) |
| `AINTERCEPTOR_ADMIN_EMAIL` | Which user may enable/disable providers, CDP-inject |
| `AINTERCEPTOR_WEB_LOGIN_PASSWORD` | Admin password for `/login/<provider>` |
| `AINTERCEPTOR_WEB_COOKIE_SECRET` | HMAC secret for the VNC session cookie |
| `AINTERCEPTOR_VNC_PASSWORD` | x11vnc password (embedded in iframe) |
| `AINTERCEPTOR_GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `AINTERCEPTOR_GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `AINTERCEPTOR_PUBLIC_URL` | Public HTTPS origin (Funnel) |
| `AINTERCEPTOR_HOST` | uvicorn bind address (0.0.0.0) |

## Docs index

| Doc | Purpose |
|---|---|
| `docs/COMMANDS.md` | this file |
| `docs/AGENT_INSTALL.md` | user-side agent install guide |
| `PROJECT/CLI_COMMAND_REFERENCE.md` | future Cisco-style interactive CLI spec |
| `.ai/RULES.md` | project rules R1-R7 |
| `.ai/SESSION_LOG.md` | decision log |
| `.ai/PROGRESS.md` | milestone progress |
| `.ai/FUTURE_WORK.md` | parking lot |
| `.ai/STRATEGY.md` | scaling + OpenRouter comparison |
| `PROJECT/AUTOMATION.md` | automation design (hooks, sync_docs) |
| `PROJECT/WEB_UI.md` | web UI design |
| `PROJECT/ARCHITECTURE_VNC_LOGIN.md` | VNC login architecture |
| `PROJECT/ARCHITECTURE_ACCOUNTS.md` | accounts + device flow |
