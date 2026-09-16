# DECISIONS.md

| ADR | Title | Status | Date |
|---|---|---|---|
| 0001 | Playwright + network interception as Phase 1 mechanism | Accepted | 2026-09-15 |
| 0002 | Rollback = revert commit, never force-push | Accepted | 2026-09-15 |
| 0003 | Every repo change is a single pasteable script | Accepted | 2026-09-15 |
| 0004 | Milestone commits via script only | Accepted | 2026-09-15 |
| 0005 | Python over PowerShell for bootstrap scripts | Accepted | 2026-09-15 |
| 0006 | Transport/event interception is the authoritative provider extraction boundary | Accepted | 2026-09-16 |
| 0007 | Provider runtime boundary is separate from the legacy adapter facade | Accepted | 2026-09-16 |

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

## ADR-0007 — Provider runtime boundary is separate from the legacy adapter facade

### Context
The current `ProviderAdapter` protocol contains four callable methods while
project governance refers to a five-method adapter interface. The source does
not identify a fifth method. M1 therefore must not invent or silently add one.

M1 requires a stronger typed execution boundary between the Orchestrator and
the provider-specific Interceptor runtime.

### Decision
Do not alter the frozen `ProviderAdapter` method count in M1.2.

Introduce `ProviderRuntime` as the authoritative M1 execution boundary:

1. `start()` establishes or validates the provider web session/runtime.
2. `execute(request)` receives `ProviderExecutionRequest` and asynchronously
   emits normalized `StreamEvent` values.
3. `close()` releases provider-local runtime resources.

Provider-specific browser, transport and session details remain private to
the runtime implementation. The legacy `ProviderAdapter` remains a
compatibility facade until a separate ADR reconciles the governance method
count.

### Consequences
- M1 has a stable typed runtime boundary without an arbitrary adapter change.
- Claude can be refactored behind the runtime without leaking Playwright
  objects into the Orchestrator.
- Transport compliance remains a separate M1.3 implementation task.

### Non-goals
- No live provider invocation.
- No provider inference API integration.
- No DOM-based response extraction.
- No routing/fallback logic.
