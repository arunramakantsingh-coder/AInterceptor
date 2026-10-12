# R-Module-Split

AIN (engine), CLI, Web (dashboard), and consumer /v1 communicate only
over HTTP. No cross-imports between the execution plane and its
frontends.

- CLI talks to http://127.0.0.1:8000/internal/*
- Web talks to /v1, /dashboard, /admin
- Business apps talk to /v1 (public) or MCP

Changing the CLI cannot break the engine. Changing the engine cannot
break the CLI as long as the HTTP contract holds.
