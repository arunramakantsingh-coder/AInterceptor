# DECISIONS.md

| ADR | Title | Status | Date |
|---|---|---|---|
| 0001 | Playwright + network interception as Phase 1 mechanism | Accepted | 2026-09-15 |
| 0002 | Rollback = revert commit, never force-push | Accepted | 2026-09-15 |
| 0003 | Every repo change is a single pasteable script | Accepted | 2026-09-15 |
| 0004 | Milestone commits via script only | Accepted | 2026-09-15 |
| 0005 | Python over PowerShell for bootstrap scripts | Accepted | 2026-09-15 |
| 0006 | Transport/event interception is the authoritative provider extraction boundary | Accepted | 2026-09-16 |

## ADR-0006 — Transport/event interception is the authoritative provider extraction boundary

### Decision
AInterceptor shall integrate with supported AI providers through the provider public web-application communication layer. The authoritative response extraction mechanism is interception and normalization of the underlying communication transport/events. Browser automation may be used for session establishment, authentication, maintenance and recovery, but rendered webpage/DOM extraction is not the core response contract.

### Consequences
- Provider runtimes own session and transport mechanics.
- Streaming is handled incrementally at the transport/event boundary.
- Provider-specific event formats are normalized before crossing into the Orchestrator.
- The Orchestrator remains independent of provider transport details.
- A page-side `fetch()` implementation that buffers a complete response is transitional PoC behavior and is not sufficient evidence of M1 architectural compliance.

### Boundary
No provider inference API is to be introduced as a shortcut to replace the web-layer interception mechanism without a new explicit ADR and review.
