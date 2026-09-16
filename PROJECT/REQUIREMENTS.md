# REQUIREMENTS.md

## Scope
AInterceptor is a web-application AI router. It communicates with supported AI providers through their public web-application communication layer and does not use provider inference APIs as the primary integration mechanism.

The provider-rendered webpage/DOM is not the response contract. Browser automation may establish, authenticate, maintain, or recover a provider web session, while the Interceptor controls/observes the underlying web communication transport and normalizes its events.

## Functional Requirements

| ID | Requirement | Milestone |
|---|---|---|
| FR-001 | Establish and maintain a controlled provider web session using an approved browser/runtime mechanism. | M1 |
| FR-002 | Intercept the provider web application's communication path at the transport/event layer. | M1 |
| FR-003 | Capture streaming provider events without making rendered DOM scraping the core extraction mechanism. | M1 |
| FR-004 | Normalize provider transport events into the shared AInterceptor event/chunk contract. | M1 |
| FR-005 | Detect invalid/expired sessions before dispatch and expose a typed recovery state. | M1 |
| FR-006 | Provide provider-specific adapters/runtime implementations behind a shared interface. | M1–M3 |
| FR-007 | Support session harvesting where required and, only where explicitly validated, a direct transport fast path using session state. | M2 |
| FR-008 | Support multiple provider runtimes without cross-provider adapter imports. | M3 |
| FR-009 | Route requests by declared provider/model capability and policy. | M4 |
| FR-010 | Support fallback and provider health/rate-limit state. | M4 |
| FR-011 | Expose an OpenAI-compatible `/v1/chat/completions` gateway. | M5 |
| FR-012 | Provide a Developer control plane integrated with GitHub-backed project state, validation, checkpoints, roadmap, defects and architecture decisions. | M6 |
| FR-013 | Preserve normalized streaming semantics through the Gateway without requiring provider-specific transport knowledge in the Orchestrator. | M4–M5 |

## Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-001 | Scripts are idempotent and safe to re-run where applicable. |
| NFR-002 | Credentials, cookies, tokens and session state are never committed or emitted in plaintext logs. |
| NFR-003 | Validation produces explicit PASS/FAIL evidence. |
| NFR-004 | Repository-changing agent instructions follow the pasteable-script policy. |
| NFR-005 | No secrets are stored in Git. |
| NFR-006 | Provider adapters are isolated behind a shared typed contract. |
| NFR-007 | Interceptor owns provider transport/session mechanics; Orchestrator owns routing/policy and must not contain provider transport logic. |
| NFR-008 | Provider communication events are normalized before crossing the Interceptor/Orchestrator boundary. |
| NFR-009 | Browser automation and DOM interaction are implementation mechanisms, not the provider response contract. |
| NFR-010 | Provider-specific transport behavior is covered by synthetic fixtures and contract tests before live validation. |
| NFR-011 | Destructive Git operations require explicit authorization, validation and audit evidence. |

## Exclusions / Boundaries

- Provider inference APIs are not the primary integration mechanism.
- Provider-rendered DOM scraping is not the core response extraction mechanism.
- Commercial resale is outside the current legal/product boundary.
- No provider transport implementation may bypass the Interceptor boundary to call the public Gateway directly.

## Reconciliation Notes

- The original requirements described "Provider Web UIs" and SSE/WebSocket normalization, but did not explicitly establish transport interception as the authoritative extraction boundary. This is now explicit.
- The original phase numbering conflicted with the roadmap's governance-dashboard numbering. Delivery milestones are therefore tracked as M0/M0.1/M1–M6 in the reconciled roadmap.
- The existing provider contract and governance wording are not silently treated as reconciled implementation facts; interface changes require an ADR and implementation validation before being adopted.
