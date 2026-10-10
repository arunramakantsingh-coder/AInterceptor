# Provider Runtime Contract

Every provider runtime implements this interface. No exceptions.
Claude is the reference; all others conform.

## 1. Interface

    class ProviderRuntime(Protocol):
        provider: str
        transport: str              # sse | ws | fetch | json
        async def start(self) -> None: ...
        async def close(self) -> None: ...
        def health(self) -> HealthState: ...
        async def ensure_session(self) -> None: ...
        def is_login_page(self) -> bool: ...
        async def submit(self, prompt: str, attachments: list = []) -> None: ...
        async def stream(self) -> AsyncIterator[StreamEvent]: ...
        def normalize(self, events: list[StreamEvent]) -> str: ...
        async def recover(self, reason: str) -> bool: ...

## 2. StreamEvent Contract

Shape already in backend/app/interception/contracts.py:
StreamEvent(provider, request_id, event_type, sequence, delta,
finish_reason, metadata).
EventType: SESSION_CREATED, SESSION_READY, REQUEST_INTERCEPTED,
REQUEST_FORWARDED, STREAM_STARTED, STREAM_DELTA, STREAM_COMPLETED,
STREAM_FAILED, SESSION_EXPIRED, SESSION_RECOVERY_REQUIRED.

## 3. Required Behaviors

Lifecycle: start() idempotent. close() releases browser + children.
health() returns one of: ready | degraded | rate_limited |
session_expired | browser_dead | provider_drift.

Session: ensure_session() verifies storage state + auth. is_login_page()
returns True on login wall. Never logs or serializes storage state.

Input: submit() finds composer, types, triggers send. Fails loudly if
composer not found. Robust to multiple candidate selectors.

Transport: stream() yields StreamEvents as bytes arrive over CDP.
Emit STREAM_STARTED before first delta. Emit exactly one COMPLETED or
FAILED. Handle partial frames. Never emit duplicate delta for same bytes.

Parsing: provider-specific. Claude: SSE content_block_delta. DeepSeek:
cumulative snapshots + APPEND, RESPONSE fragments. ChatGPT: SSE
/message/content/parts/0. Gemini: wrb.fr frames. Parse own protocol only.

Normalization: monotone output. Exclude reasoning/THINK fragments.
Exclude metadata and tool call envelopes.

Recovery: recover(reason) called when health != ready. Return True/False.
Never swallow errors silently.

## 4. Path A vs Path B

Each runtime declares:
    PATH_A_SUPPORTED = True/False
    PATH_B_SUPPORTED = True/False
    PREFERRED_PATH = "A" | "B"
Orchestrator consults flags, falls back automatically.

## 5. Isolated Sessions

Each runtime owns: its own browser context (Path B), its own storage
state file (per user, per provider), its own CDP session. No runtime
reads another provider's session.

## 6. Testing Requirements

test_parse_<provider>.py: offline parser tests against fixtures.
test_runtime_<provider>.py: lifecycle + submit + stream (mocked).
test_<provider>_e2e.py: optional live round-trip (skip in CI).
Parser tests pass in CI. E2E is opt-in via AINTERCEPTOR_LIVE_TESTS=1.

## 7. Anti-Patterns

Never: DOM scraping as response transport; hardcoding internal endpoints
across runtimes; sharing storage state; serializing cookies into logs;
using existing_chrome_cdp(); modifying Claude for another provider.

## 8. Adding a New Provider

1. backend/app/interception/<provider>.py
2. backend/app/providers/<provider>/__init__.py
3. Register in backend/app/interception/registry.py
4. Add fixture in backend/tests/fixtures/
5. Add test in tests/test_<provider>_parse.py
6. Document in PROJECT/PROVIDER_EVIDENCE_MODEL.md
7. Add to CLI provider list
8. Add to BLUEPRINT.md provider table

No provider merges without all eight.
