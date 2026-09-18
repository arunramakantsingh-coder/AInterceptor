# AIOS Architecture

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
