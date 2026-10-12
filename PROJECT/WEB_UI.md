# AInterceptor — Web UI Design

## Page tree
Public:    /auth/login  /auth/signup  /login  /login/<provider>
Dashboard: /dashboard  /keys  /sessions  /devices  /agents(new)
           /providers(new)  /usage(new)  /settings(new)
Admin:     /dashboard/admin/{overview,sessions,devices,logs}
Future:    /routing  /billing  /docs

## S1 — Nav refactor (this session)
- Reorder nav: Overview | Agents | Sessions | Devices | Providers | Usage | API keys | Settings
- Move connect into /dashboard/devices (route stays for backward compat)
- Add /dashboard/agents placeholder

## S2 — /dashboard/agents
- Detected devices list
- Per-device install commands (OS-tabbed)
- Inline device-code generator
- Per-provider [Login] buttons with copy
- Provider status: uploaded Nm ago / not logged in

## S3 — /dashboard/sessions enhancement
- Columns: provider | alias | status | source | device | created
- Actions: delete (kill), refresh, export
- Bulk: delete expired

## Build order
S1 (nav) -> S2 (agents) -> S3 (sessions)
S4 (providers) -> S5 (usage) -> S6 (settings) -> S7 (admin)
