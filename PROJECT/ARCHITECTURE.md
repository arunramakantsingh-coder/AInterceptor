# ARCHITECTURE.md

## 1. System Boundary

AInterceptor is a web-layer AI router. The supported provider is reached through its public web application and its web-application communication path. Provider inference APIs are not the primary integration boundary.

The provider-rendered webpage/DOM is not the response contract. Browser automation is an enabling mechanism for session establishment, authentication, maintenance and recovery. The authoritative extraction boundary is the intercepted provider communication transport and its normalized events.

## 2. Logical Architecture

```text
AInterceptor UI / Client
        |
        v
Application Gateway
        |
        v
Orchestrator
(routing / policy / capability / fallback / rate limits)
        |
        | typed normalized request/event interfaces
        v
Interceptor
(session / transport / interception / streaming / normalization)
        |
        v
Provider Web Runtime
        |
        v
Provider public web communication
```

### Interceptor subsystem

Owns:
- provider web-session lifecycle
- browser/runtime lifecycle where required
- authentication/session establishment and recovery
- communication transport interception
- request/response/event capture
- SSE/WebSocket or equivalent streaming handling
- provider-specific event parsing
- normalization into shared AInterceptor events/chunks

Must not own:
- provider routing policy
- global fallback decisions
- public Gateway API
- cross-provider business logic

Primary locations: `backend/app/interception/`, `backend/app/providers/`.

### Orchestrator subsystem

Owns:
- provider/model capability selection
- routing policy
- fallback
- provider health and rate-limit policy
- request lifecycle orchestration
- normalized response aggregation/merge where explicitly required

Must not contain provider-specific transport or session mechanics.

Primary locations: `backend/app/orchestrator/`, with the public API boundary in `backend/app/gateway/`.

### Gateway

The Gateway is the public application/API face. It validates caller authorization, validates the request contract, delegates to the Orchestrator and emits the AInterceptor response contract. It does not call provider transports directly.

## 3. Data Contracts

### Session

```text
Session {
  provider,
  session_id,
  storage_reference,
  status,
  expires_at,
  last_validated_at,
  recovery_state
}
```

Secrets/cookies/tokens are kept outside Git and must not be exposed in normal logs.

### Normalized stream event

```text
StreamEvent {
  provider,
  request_id,
  event_type,
  sequence,
  delta,
  finish_reason,
  metadata
}
```

Minimum event lifecycle includes concepts equivalent to:
`SESSION_CREATED`, `SESSION_READY`, `REQUEST_INTERCEPTED`, `REQUEST_FORWARDED`, `STREAM_STARTED`, `STREAM_DELTA`, `STREAM_COMPLETED`, `STREAM_FAILED`, `SESSION_EXPIRED`, `SESSION_RECOVERY_REQUIRED`.

### Provider health

```text
ProviderHealth {
  provider,
  status,
  last_success,
  error_rate,
  latency_ms,
  rate_limit_state
}
```

## 4. Interfaces

Public/application interfaces:

- `/v1/chat/completions` — OpenAI-compatible gateway contract, introduced at M5.
- `/health/providers` — provider health/status contract.
- `/api/github/*` — authenticated Developer control-plane integration.

Internal interfaces:

- Gateway -> Orchestrator: normalized request contract.
- Orchestrator -> Interceptor: typed provider execution contract.
- Interceptor -> Orchestrator: normalized stream/event contract.

Provider-specific transport details must not cross these boundaries.

## 5. Trust and Security

- Browser/runtime execution is sandboxed where technically supported.
- Session state is stored in an encrypted/protected vault or equivalent secure store.
- Session files are git-ignored and never committed.
- GitHub integration uses an appropriate authenticated flow; privileged credentials must remain server-side.
- Logs use redaction and must not contain provider cookies, access tokens, CSRF tokens or equivalent secrets.
- Destructive Developer/Git actions require authorization, explicit confirmation, audit evidence and validation.

## 6. Implementation Reconciliation

The current Claude interceptor is an early PoC and does not yet satisfy this architecture: it performs provider calls through page-side `fetch()` and buffers the entire response before parsing. That implementation must therefore be treated as transitional PoC code, not as the final Interceptor transport contract. M0.1 establishes the target boundary; M1 must validate a real transport/event interception path before the implementation is considered compliant.
