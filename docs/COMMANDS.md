# AInterceptor — Command Reference

Living document. Updated with every feature. Source of truth for the
future CLI user guide.

## Host

Debian 13 VM. User `arun`. Tailscale IP `100.82.62.82`.
Repo at `~/ainterceptor`.

## Daemon

| Command | Purpose |
|---|---|
| `cd ~/ainterceptor && ./run-linux.sh` | Start daemon (foreground) |
| `Ctrl+C` | Stop daemon |
| `pkill -f "app.runtime.daemon"` | Force-stop daemon |

## Monitoring

| Command | Purpose |
|---|---|
| `astatus` | System state (daemon, CDP, Xvfb, x11vnc, tabs) |
| `aprobe` | Read-only health of all active providers |
| `aprobe claude` | Read-only health of one provider |

## Prober toggle

| Command | Effect |
|---|---|
| `aprobe-off` | Disable background prober (default) |
| `aprobe-on` | Enable (invasive — sends pings) |
| `cd ~/ainterceptor && ./run-linux.sh` | Apply change (restart) |

## Chat

| Command | Purpose |
|---|---|
| `chatgpt` / `claude` / `deepseek` / `gemini` | Enter chat REPL |
| `/exit` inside chat | Leave chat |

## VNC (admin login flow)

| Command | Purpose |
|---|---|
| `x11vnc -display :99 -forever -shared -rfbauth ~/.vnc/passwd -rfbport 5900 -bg -o ~/.vnc/x11vnc.log` | Start x11vnc |
| `pkill -f x11vnc` | Stop |
| (Windows) VNC viewer → `100.82.62.82:5900` | Connect |

## Git

| Command | Purpose |
|---|---|
| `git log --oneline -5` | Recent commits |
| `git status --short` | Working tree state |
| `git push origin fix/nonclaude-three-providers-20260917` | Push |

## Planned (script 2)

- `alogin <provider>` — bring Chrome on-screen, wait for login, save state
- `alogout <provider>` — clear that provider's cookies
- `atest <provider>` — send "hi", verify reply
- `ashow` / `ahide` — window position toggle


---

## Agent-based login (user-side)

See docs/AGENT_INSTALL.md for the full guide.

| Command | Purpose |
|---|---|
| akeys list | Show all API keys + status |
| akeys create <name> --save | Mint a key, save locally |
| akeys current | Show prefix of loaded key |
| akeys revoke <id> | Revoke a key |

Admin sends the token once privately. User runs airouter-agent config
then airouter-agent login <provider>. Server CDP-injects the session.


---

## Batch 1 admin commands (fully implemented)

### Sessions (DB-backed)

| Command | Purpose |
|---|---|
| `asessions` | List **your** (admin's) sessions |
| `asessions --all` | **Admin view**: every session across all users, with owning email |
| `asessions export <p> [path]` | Copy local export file for a provider |
| `asessions delete <p>` | Delete a provider's session row from the DB |

### Health / diagnostic

| Command | Purpose |
|---|---|
| `ahealth` | Pretty-print `/health` (supervisor, exporter, prober, circuits) |
| `aversion` | Show AInterceptor / Python / Playwright / Chrome / xdotool versions |
| `alogs [daemon|chrome|x11vnc]` | Tail the named log (default: daemon) |
| `astatus` | System state: daemon, CDP, Xvfb, x11vnc, active providers, tabs |
| `aprobe [<provider>]` | Read-only probe of all active (or one) providers |
| `atest <provider>` | Full round-trip: sends `[AINT TEST]`, verifies reply |

### Lifecycle

| Command | Purpose |
|---|---|
| `astart` | Start daemon in background if not running (idempotent) |
| `astart --fg` | Start daemon in foreground (blocks, shows logs live) |
| `arestart` | Stop + start in background |
| `arestart --fg` | Stop + start in foreground |
| `astop` | Stop daemon + Chrome, wait for exit, clear Singleton locks |

### Config

| Command | Purpose |
|---|---|
| `aconfig show` | Print all `AINTERCEPTOR_*` keys with descriptions |
| `aconfig list` | List known config keys |
| `aconfig get <key>` | Print one key's value |
| `aconfig set <key> <value>` | Write a key (restart daemon to apply) |
| `aconfig-reset <key>` | Reset one key to its default |

### Keys

| Command | Purpose |
|---|---|
| `akeys list` | List all API keys with status (active/revoked) |
| `akeys create <name> [--save]` | Mint a new key; `--save` writes to `~/.ainterceptor/admin_api_key.txt` |
| `akeys current` | Show prefix + length of the loaded key (never the token) |
| `akeys revoke <id>` | Revoke a key by ID |

### Provider management

| Command | Purpose |
|---|---|
| `aproviders` | List all 20 providers with ACTIVE / inactive state |
| `aproviders enable <name>` | Add to `.env` active list (restart to apply) |
| `aproviders disable <name>` | Remove from active list |
| `aproviders info <name>` | Host, URL, login markers |
| `aproviders test <name>` | Alias for `aprobe <name>` |

### Session (VNC-based login)

| Command | Purpose |
|---|---|
| `alogin <provider>` | Move Chrome on-screen (VNC), wait for login, save storage_state |
| `alogout <provider>` | Clear that provider's cookies only (siblings untouched) |
| `ashow` | Move Chrome windows on-screen (for VNC) |
| `ahide` | Move Chrome windows off-screen |

### Agent-based login (user-side)

See `docs/AGENT_INSTALL.md`.

| Command | Purpose |
|---|---|
| `airouter-agent config --server ... --token ...` | Point agent at VM |
| `airouter-agent login <provider>` | Open Chrome on user's machine; upload state to VM |

### Bootstrap / git

| Command | Purpose |
|---|---|
| `abootstrap` | Create admin user + first API key (idempotent) |
| `asave "message"` | `git add -A && git commit && git push origin <branch>` |

### Chat

| Command | Purpose |
|---|---|
| `chatgpt` / `claude` / `deepseek` / `gemini` | Enter chat REPL (uses `chat_any`) |
| `/exit` inside chat | Leave |

### Environment

All commands assume:
- Debian VM, user `arun`, repo at `~/ainterceptor`
- venv at `~/ainterceptor/.venv`
- `~/bin` on PATH
- `x11vnc` on `:5900` (for VNC login)
- Xvfb on `:99`


---

## Provider wizard (Batch 2)

### Diagnostic

| Command | Purpose |
|---|---|
| `aproviders status <name>` | Show 5-layer state: listed / registry / runtime file / active / session |
| `aproviders validate <name>` | status + probe (tab reachable, login state) |

`status` output shows exactly which layer is missing and prints the next
command to fix it.

### Add a new provider

Interactive (prompts for URL, tab prefix, login markers, selectors, activation):

    aproviders add <name>

Non-interactive (for scripts/agents):

    aproviders add <name> \
      --url https://<name>.example/ \
      --tab-prefix <name>.example \
      --login-markers /login,/signin \
      --composer-selectors 'div[contenteditable="true"],textarea' \
      --no-activate \
      --yes

`add` performs three edits:
1. Append `<name>` to `backend/app/providers_list.py` (ALL_PROVIDERS)
2. Insert a `ProviderEntry` into `backend/app/interception/registry.py`
3. Scaffold `backend/app/interception/<name>.py` with a working skeleton
   and `# TODO` markers

It does NOT delete or overwrite anything. If the file exists, it skips.

After add:

    arestart                  # apply new registry
    alogin <name>             # log in via VNC
    aproviders validate <name>

### Remove a provider

    aproviders remove <name>

Deactivates only (removes from `AINTERCEPTOR_ACTIVE_PROVIDERS`). Does NOT
delete files. Manual cleanup commands printed at the end.
