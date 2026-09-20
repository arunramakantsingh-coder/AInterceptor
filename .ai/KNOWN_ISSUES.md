# Known Issues

| ID | Severity | Area | Summary | Status |
|---|---|---|---|---|
| B001 | Closed | chatgpt | NOT a parser bug — chatgpt tab was anonymous. Probe + agent login both fixed. 2026-09-21 | Resolved |
| B002 | Low | sessions | Fake cookie uploaded during testing sits as `claude/default/active` — delete with `asessions delete claude` | Open |
| B003 | Low | claude | `claude login` uses Windows-only `ctypes.windll` — VNC/agent path works instead | Won't fix (superseded) |
| B004 | Low | config | `AINTERCEPTOR_PROBER_ENABLED=1` in `.env` — background prober sends "ping" and pollutes chat history | Should be 0 |
| B005 | Low | providers | `perplexity` listed but no runtime file; `character` has runtime but not registered | Open |
