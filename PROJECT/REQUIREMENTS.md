# REQUIREMENTS.md

## Functional
FR-001 Submit prompt to provider web UI, stream response. (Phase 1)
FR-002 Normalize SSE/WebSocket to chunks. (1)
FR-003 Detect session expiry pre-dispatch. (1)
FR-004 Playwright session harvesting. (2)
FR-005 Direct HTTP with harvested tokens. (2)
FR-006 Adapters for ChatGPT/DeepSeek/Qwen. (3)
FR-007 Routing with fallback. (4)
FR-008 Rate-limit tracking + 429 cooldown. (4)
FR-009 OpenAI-compatible /v1/chat/completions. (5)
FR-010 Governance dashboard. (6)

## Non-Functional
NFR-001 Idempotent scripts.
NFR-002 No plaintext credentials.
NFR-003 PASS/FAIL output.
NFR-004 Pasteable-script policy.
NFR-005 No secrets in git.
NFR-006 Isolated adapters, shared interface.

## Exclusions
Official APIs. Commercial resale.
