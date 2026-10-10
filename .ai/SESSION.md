## 2026-09-16 — Phase 1 complete (v0.1.0)
- Dashboard: 8 routes live (commits, versions, compare, roadmap, bugs, providers, status, rollback).
- M1.5 provider health + status panel added.
- Section 21 UI-first rule adopted.
- Tagged v0.1.0.


## 2026-09-15 — Bootstrap
- Fresh restart. Python bootstrap. B001 resolved via ADR-0005.

## 2026-09-21 — VNC login page + chatgpt fix

- Implemented `/login/<provider>` branded page with admin password gate
- noVNC assets served from /opt/noVNC via FastAPI static mount
- WebSocket proxy /login/<provider>/ws forwards to 127.0.0.1:5900
- Subprotocol echo required for noVNC handshake (was hardcoded "binary")
- Login flow: browser → password → iframe → Chrome on Xvfb → user logs in → session persists
- Result: chatgpt session now authenticated, `atest chatgpt` PASS
- B001 closed — root cause was auth, not parser
