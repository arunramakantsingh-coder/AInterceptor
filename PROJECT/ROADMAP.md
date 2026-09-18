# ROADMAP.md

## Current State

**M0.1 — Architecture & Requirements Reconciliation: COMPLETE**

The repository baseline has been reconciled around the web-layer interception boundary. The next implementation milestone is **M1 — Single Provider Interception PoC**.

## Delivery Milestones

| Milestone | Name | Status |
|---|---|---|
| M0 | Framework & Governance Bootstrap | COMPLETE |
| M0.1 | Architecture & Requirements Reconciliation | COMPLETE |
| M1 | Single Provider Interception PoC | IN PROGRESS — M1.5 runtime/CLI integration |
| M2 | Session Harvesting + Direct Transport Fast Path | PENDING |
| M3 | Multi-Provider Interceptor Adapters | PENDING |
| M4 | Orchestrator Engine — capability routing, fallback, rate limits, merge | PENDING |
| M5 | Gateway API — OpenAI-compatible `/v1/chat/completions` | PENDING |
| M6 | Developer Control Plane / Governance Dashboard | PENDING |

## M0.1 Acceptance Record

| Gate | Status |
|---|---|
| Existing requirements reviewed | PASS |
| Existing architecture reviewed | PASS |
| Existing roadmap reviewed | PASS |
| Existing governance reviewed | PASS |
| Existing AI current-task/handoff/known-issues reviewed | PASS |
| Existing Interceptor implementation inspected | PASS |
| Web-layer transport boundary made explicit | PASS |
| DOM scraping excluded as core response contract | PASS |
| Interceptor / Orchestrator responsibility boundary defined | PASS |
| Delivery numbering reconciled to M0/M0.1/M1–M6 | PASS |
| Provider API shortcut excluded as primary integration path | PASS |
| Transitional Claude PoC gap documented | PASS |
| Implementation changes introduced | NO — documentation-only milestone |
| Final milestone checkpoint commit | PENDING — must follow project milestone commit procedure |

## M1 Definition of Done

- One supported provider web session can be established and validated.
- AInterceptor controls/observes the provider web application's communication path at the transport/event layer.
- Streaming events are captured incrementally rather than buffered as a completed DOM/page result.
- Provider events are normalized into the shared AInterceptor event/chunk contract.
- Session expiry/failure is represented explicitly.
- Positive, negative and edge-path tests pass using synthetic fixtures where live provider access is not required.
- `/intercept` UI shows normalized live interception events/chunks.
- Security review confirms no credentials or session secrets enter Git or ordinary logs.
- Git diff, validation, checkpoint and roadmap evidence are recorded.

## M1.5 Progress Record

- Claude live SSE schema handling updated for `content_block_delta`, `message_delta`, and `message_stop`.
- Claude runtime supports CDP attach mode through `AINTERCEPTOR_CLAUDE_CDP_URL` without requiring a storage-state file.
- CDP-attached Chromium is treated as externally owned and is not closed by `ClaudeRuntime.close()`.
- CLI package boundary and Claude chat wiring added; provider order remains ChatGPT, Claude, Gemini, Grok.
- CLI test package and synthetic Claude SSE/runtime configuration tests added.
- Full local/live validation remains to be performed after pulling this branch.

## Phase 2 — Interceptor (DeepSeek PoC) — COMPLETE

- Date: 2026-09-18
- Provider: DeepSeek Web (CDP 9223)
- Byte-exact match with browser: verified
- Parser: RESPONSE-only, per-fragment content, idempotent append
- Runtime: DOM ground-truth on finalize, registry-enforced CDP
- Tests: 19/19 passing
- Commit: 4b3e2cf
