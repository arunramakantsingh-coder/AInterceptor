# AGENTS.md — AInterceptor

Operational rules for AI agents and human contributors. Read this first.

Then: PROJECT_GOVERNANCE_STANDARD_v1.1.md, BLUEPRINT.md,
PROJECT/AIOS_ARCHITECTURE.md, PROJECT/ROADMAP.md, .ai/CURRENT_TASK.md.

## Project Identity
- Name: AInterceptor | Codename: AINT
- Vision: Cisco-style AI Network Operating System
- Products: Webapp (multi-AI chat) + API (OpenRouter-style gateway)
- Stack: Python 3.12, FastAPI, Postgres, Playwright, Docker
- Host: Windows dev, Linux deploy via Docker

## Iron Rules
1. Never modify Claude. It is the reference implementation. Frozen.
2. Never force-push. Rollback = revert commit.
3. Never commit secrets (cookies, tokens, storage_state, keys).
4. Every change is a single pasteable script (Governance §18, §19).
5. Verify before claiming. Observed, not assumed.
6. Milestones commit only via scripts/milestone_commit.ps1.
7. No implementation before the framework exists.
8. One provider per directory. No cross-imports between adapters.
9. Every phase ships its UI surface or its API contract.
10. Project rules may be stricter, never weaker.

## Two Subsystems (Governance §20)
- Interceptor: web-layer interception. backend/app/interception/, providers/.
- Orchestrator: routing, capability, merging, Gateway API. backend/app/orchestrator/, gateway/.
Every change declares its subsystem. No cross-imports except via typed interfaces in interception/contracts.py.

## Repository Map
AGENTS.md, BLUEPRINT.md, README.md, PROJECT_GOVERNANCE*.md,
PROJECT/ (docs), .ai/ (agent memory), backend/ (Python),
cli/ (Cisco shell), docker/ (Dockerfile, compose), agent/ (user-side),
tests/ (integration + parser + e2e).

## Cisco-Style CLI
AInterceptor-BOOT> airouter
AIRouter> enable
AIRouter# configure terminal
AIRouter(config)# ai
AIRouter(config-ai)# provider claude
AIRouter(config-ai-provider-claude)# login
AIRouter# copy running-config startup-config
AIRouter# chat claude

running-config = in-memory. startup-config = .ainterceptor/nvram/startup-config.json.
copy running-config startup-config = persist. See PROJECT/CONFIGURATION_GUIDE.md.

## Deployment
Phase 1: Docker Compose (Windows dev, Linux deploy).
Chrome runs inside the container, headless. Never visible to users.
See PROJECT/DEPLOYMENT_GUIDE.md.

## When in Doubt
Re-read PROJECT_GOVERNANCE_STANDARD_v1.1.md. Safer rule wins. Update docs with code.
Repository is durable memory. Chat history is not.
