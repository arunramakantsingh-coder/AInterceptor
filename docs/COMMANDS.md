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
