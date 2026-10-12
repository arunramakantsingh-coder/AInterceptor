# AInterceptor — Command Line Reference

Complete list of every command AInterceptor exposes on the VM.
Regenerate whenever new commands land.

Live view: https://ainterceptor.taila2310c.ts.net/dashboard/commandline

---

## How to read this

- All commands run on the **Debian VM** (`ssh arun@100.82.62.82`)
- Every command is a thin wrapper around `python -m scripts.<module>` in `~/bin/`
- Symbols: `[option]` optional · `|` pick one · `<value>` required

---

## 1. Status & Health

### astatus
System state: daemon PID, CDP port, Xvfb, x11vnc, active providers, open tabs.

    astatus

### ahealth
Pretty-print of `/health` — supervisor, exporter, prober, circuits.

    ahealth

### aversion
Versions of AInterceptor, Python, Chrome, xdotool, and current `.env` flags.

    aversion

### aprobe [provider]
Read-only provider health. Sends **no** messages.

    aprobe                  # all active providers
    aprobe claude           # one provider

| State | Meaning |
|---|---|
| REACHABLE | Tab open, past login wall, chat input present |
| LOGIN_REQUIRED | URL matches login markers, or anonymous body detected |
| CLOUDFLARE | Cloudflare challenge page |
| SESSION_EXPIRED | Tab open, no chat input, not a login URL |
| NO_TAB | No matching tab in Chrome |
| DOWN | Page evaluate threw |

### atest <provider>
Round-trip test. Sends a real message and waits for a reply.
**Pollutes chat history** — use sparingly.

    atest deepseek

---

## 2. Daemon Lifecycle

### astart [--fg]
Start daemon if not already running. Idempotent.

    astart                  # background
    astart --fg             # foreground, Ctrl+C to stop

### arestart [--fg]
Stop + start. Use this to pick up `.env` or code changes.

    arestart
    arestart --fg

### astop
Stop daemon + Chrome, wait for both to exit, clear Singleton locks.

    astop

---

## 3. Chat

Enter a REPL session with one provider. `/exit` to leave.

    chatgpt
    claude
    deepseek
    gemini

Uses the **live VM Chrome**. If a tab shows a login wall, run `alogin <provider>` first.

---

## 4. Provider Management

### aproviders
List all 20 configured providers with status.

### aproviders enable <name>
Add to `.env` active list. Applies on next `arestart`.

### aproviders disable <name>
Remove from active list.

### aproviders info <name>
Host, home URL, login markers.

### aproviders status <name>
5-layer diagnostic: listed / registry / runtime file / active / session.

### aproviders validate <name>
status + live probe.

### aproviders add <name>
Interactive wizard: URL, host, login markers, capabilities, activate.

Non-interactive:

    aproviders add newprovider \
      --url https://newprovider.com/chat \
      --host newprovider.com \
      --login-markers /auth,/signin \
      --no-activate \
      --yes

### aproviders remove <name>
Deactivates. Does not delete runtime files.

### aproviders test <name>
Alias for `aprobe <name>`.

---

## 5. Sessions (VNC and Agent)

### alogin <provider>
Agent-first login. Prints the exact command to run on the user's laptop and
polls for the upload.

    alogin claude                 # agent-first (default)
    alogin claude --vnc           # VNC fallback (admin only)

### alogout <provider>
Clear that provider's cookies from VM Chrome.

### ashow / ahide
Move all Chrome windows on-screen (for VNC) / off-screen.

### asessions
List your (admin's) sessions from the DB.

### asessions --all
Admin view — every user's sessions with owning email.

### asessions export <provider> [path]
Copy local `~/.ainterceptor/exports/<provider>.json`.

### asessions delete <provider>
Remove a session row from the DB.

---

## 6. Configuration

### aconfig show
Print every `AINTERCEPTOR_*` key with description.

### aconfig list
List known config keys.

### aconfig get <key>
Print one value.

### aconfig set <key> <value>
Write a value. Restart daemon to apply.

### aconfig-reset <key>
Restore default.

---

## 7. API Keys

### akeys list
All keys with status, prefix, name.

### akeys create <name> [--save]
Mint a new key. `--save` writes to `~/.ainterceptor/admin_api_key.txt`.

### akeys current
Show prefix of the loaded key (never the token).

### akeys revoke <id>
Revoke by ID.

---

## 8. Logs & Evidence

### alogs [daemon|chrome|x11vnc]
Tail the named log.

### aevidence
List recent validation logs (`.evidence/`).

### aevidence show <name>
Show one.

### aevidence clear [days]
Prune logs older than N days.

---

## 9. Bootstrap & Git

### abootstrap
Create admin user + first API key (idempotent).

### asave "message"
`git add -A && git commit && git push`.

---

## 10. Automation (R1/R6/R7)

### asession [--quick "title" "chosen" "why"]
Append a decision to `.ai/SESSION_LOG.md`.

### aprogress [--show] [--commits N]
Regenerate `.ai/PROGRESS.md` from git log.

### sync_docs --last-commit [--dry]
Parse commit tags (`[feature:...]`, `[fix:...]`, `[roadmap:...]`, `[bug:...]`,
`[closes:...]`, `[release:...]`) and update ROADMAP / BUGS / FUTURE / CHANGELOG.
Runs automatically via `.git/hooks/post-commit`.

---

## 11. Agent (User's Laptop)

### airouter-agent connect --server URL --code XXXX-XXXX
Exchange a device code for a token.

### airouter-agent login <provider>
Open real Chrome, wait for user login, upload storage_state.

### airouter-agent serve [--port 45231]
Local helper the dashboard calls to run logins with one click.

### airouter-agent status
Show server, token prefix, hostname, reachability.

### airouter-agent config --server URL --token TOK
Store server + token manually.

---

## 12. Web Pages

| URL | Purpose |
|---|---|
| /auth/login | Email+password + Google OAuth |
| /auth/signup | Sign up |
| /login | VNC admin landing |
| /login/<provider> | VNC per-provider (admin) |
| /dashboard | Overview |
| /dashboard/commandline | This page |
| /dashboard/agents | One-click provider login |
| /dashboard/sessions | Kill / refresh / last-used |
| /dashboard/devices | Devices + inline connect-code |
| /dashboard/providers | 20-provider catalog |
| /dashboard/usage | /v1 call history |
| /dashboard/keys | API keys |
| /dashboard/settings | Account |
| /docs | Full docs browser |

---

## 13. API Endpoints

| Endpoint | Purpose |
|---|---|
| POST /v1/chat/completions | OpenAI-compatible. stream=true (SSE) or stream=false (JSON). |
| POST /api/keys | Mint API key |
| GET /api/keys | List keys |
| DELETE /api/keys/{id} | Revoke key |
| POST /api/sessions/upload | Agent upload |
| GET /api/sessions | List sessions |
| DELETE /api/sessions/{id} | Delete session |
| POST /api/devices/exchange | Exchange device code |
| GET /auth/google | Start Google OAuth |
| GET /auth/google/callback | OAuth callback |
| GET /health | Health snapshot |

---

## 14. Environment (.env on VM)

| Key | Purpose |
|---|---|
| AINTERCEPTOR_ACTIVE_PROVIDERS | Comma-separated list of live providers |
| AINTERCEPTOR_PROBER_ENABLED | 0/1 — background prober (default 0) |
| AINTERCEPTOR_ADMIN_EMAIL | Which user may toggle providers and CDP-inject |
| AINTERCEPTOR_WEB_LOGIN_PASSWORD | Admin password for /login/<provider> |
| AINTERCEPTOR_WEB_COOKIE_SECRET | HMAC secret for VNC session cookie |
| AINTERCEPTOR_VNC_PASSWORD | x11vnc password |
| AINTERCEPTOR_GOOGLE_CLIENT_ID | Google OAuth client ID |
| AINTERCEPTOR_GOOGLE_CLIENT_SECRET | Google OAuth client secret |
| AINTERCEPTOR_PUBLIC_URL | Public HTTPS origin (Funnel) |
| AINTERCEPTOR_HOST | uvicorn bind address |

---

## 15. Quick Troubleshooting

| Symptom | Command |
|---|---|
| Is the daemon up? | astatus |
| Is provider X logged in? | aprobe <X> |
| Is provider X actually replying? | atest <X> |
| Which sessions does the DB have? | asessions --all |
| Which API keys exist? | akeys list |
| What did the daemon just do? | alogs daemon |
| Why did my last commit miss docs? | sync_docs --last-commit --dry |
| Restart cleanly | arestart |

---

## 16. Command structure at a glance

    STATUS             LIFECYCLE        CHAT
      astatus            astart           chatgpt
      ahealth            arestart         claude
      aversion           astop            deepseek
      aprobe                              gemini
      atest

    PROVIDERS          SESSIONS         CONFIG
      aproviders         alogin <p>       aconfig show
      aproviders enable  alogout <p>      aconfig list
      aproviders disable ashow            aconfig get <k>
      aproviders info    ahide            aconfig set <k> <v>
      aproviders status  asessions        aconfig-reset <k>
      aproviders validate asessions --all
      aproviders add     asessions export
      aproviders remove  asessions delete
      aproviders test

    KEYS               LOGS/AUDIT       AUTOMATION
      akeys list         alogs <t>        asession
      akeys create       aevidence        aprogress
      akeys current      aevidence show   sync_docs
      akeys revoke       aevidence clear

    BOOTSTRAP          GIT              AGENT (laptop)
      abootstrap         asave "msg"      airouter-agent connect
                                          airouter-agent login <p>
                                          airouter-agent serve
                                          airouter-agent status
