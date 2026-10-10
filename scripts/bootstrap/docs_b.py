import pathlib, subprocess

ROOT = pathlib.Path.cwd()
(PROJ := ROOT / "PROJECT").mkdir(exist_ok=True)

F = {}

F["PROJECT/AIOS_ARCHITECTURE.md"] = """# AIOS Architecture

AInterceptor is an AI Network Operating System — Cisco IOS applied to AI providers.

## 1. Design Philosophy

An OS has: boot sequence, running-config, startup-config, control plane,
data plane, management plane, defined state transitions. AInterceptor
adopts all six.

## 2. Planes

Management Plane: CLI (Cisco-style), Web UI, API, SSH (admin only).
Control Plane: config engine, policy engine, billing engine, health.
Data Plane: request -> orchestrator -> provider -> response.
Provider Plane: one runtime per provider. Claude is reference.
Storage Plane: Postgres + encrypted session blobs + NVRAM + evidence.

## 3. Boot Sequence

power/start -> AInterceptor-BOOT -> load startup-config.json ->
init NVRAM -> init provider registry -> init session store ->
init DB -> self-tests -> AIRouter> prompt.

Boot is config-driven, not env-var driven. Env vars are for secrets only.

## 4. Configuration Model

| Cisco | AInterceptor |
|---|---|
| running config | in-memory NOSState |
| startup config | .ainterceptor/nvram/startup-config.json |
| copy run start | same |
| show running-config | same |
| reload | same |
| boot register | 0x2102 |

Config contains NO secrets. Secrets in .env, referenced by name.

## 5. Provider Runtime Contract

Every runtime implements:
lifecycle (start/close/health), auth (is_login_page, ensure_session),
session (path, load/save), input (find_composer, submit),
transport (capture_start, capture_stream, capture_stop),
parsing (parse, detect_terminal), normalization (to_normalized_reply),
recovery (on_session_expired, on_rate_limit, on_transport_drift).

Full spec: PROJECT/PROVIDER_RUNTIME_CONTRACT.md.

## 6. Transport Model

Path A (direct HTTPS with harvested session): ~500ms overhead, ~1MB RAM.
Breaks if provider needs browser-generated tokens.

Path B (headless Chromium, real UI): ~3s overhead, ~100MB RAM.
Universal, resilient.

Orchestrator tries A first, falls back to B per provider policy.

## 7. Session Lifecycle

login via agent -> storage_state.json -> HKDF(master_key,user_id) +
AES-GCM -> stored in user_sessions -> at request time: decrypt -> load ->
session valid weeks -> expiry -> 401/403 -> status='expired' -> user
re-logins.

## 8. Multi-Tenancy

Phase 1: 1 user, 1 Chromium, 1 storage file.
Phase 2: 2-10, per-user storage files.
Phase 3: 10-100, per-user contexts.
Phase 4+: 100+, context pool + queue.

Schema and interface identical across phases. Only scheduler changes.

## 9. Failure Model

States: ready | degraded | rate_limited | session_expired |
browser_dead | provider_drift.
Orchestrator routes around non-ready providers.

## 10. Evidence Model

Every request emits: provider, runtime_version, browser_version,
contract_version, timestamp, request_signature (hash), transport,
event_sequence, terminal_state, parser_result (hash), error_class.

Never raw cookies, tokens, prompts, or full payloads.

## 11. Roadmap Alignment

Phase 1: boot + config + ChatGPT via API.
Phase 2: DeepSeek, Claude, Gemini via API.
Phase 3: Orchestrator (policy, capability, fallback).
Phase 4: Webapp (chat UI, comparison).
Phase 5: Billing, quotas.
Phase 6: Policy-based routing, cost optimization.
Phase 7: Multi-tenant scale, Kubernetes.
"""

F["PROJECT/PROVIDER_RUNTIME_CONTRACT.md"] = """# Provider Runtime Contract

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
"""

for rel, txt in F.items():
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8", newline="\n")
    print(f"  [OK] {rel}  ({len(txt)} B)")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","docs(phase-1b): AIOS architecture + provider runtime contract"])
print((r.stdout.strip() or r.stderr.strip())[:400])
print("DONE — script 2 of 4. Run script 3 next.")
