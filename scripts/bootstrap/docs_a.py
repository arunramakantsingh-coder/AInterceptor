import pathlib, subprocess, datetime

ROOT = pathlib.Path.cwd()
(PROJ := ROOT / "PROJECT").mkdir(exist_ok=True)
(AI := ROOT / ".ai").mkdir(exist_ok=True)

F = {}

F["AGENTS.md"] = """# AGENTS.md — AInterceptor

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
"""

F["BLUEPRINT.md"] = """# BLUEPRINT.md — AInterceptor

**A Cisco-style AI Network Operating System.**
One endpoint. Many AI web interfaces. Zero provider APIs.

## Two Products
### Webapp (end users)
User opens our web UI, logs in, chats with any connected AI provider.
Can fan out one prompt to many providers, compare side by side, pick best.

### API (developers)
External apps authenticate with an AInterceptor key and call an
OpenAI-compatible endpoint. Router selects provider by capability,
enforces policy, returns result. Used by CareerOS.

Both share: session store, provider runtimes, routing engine, auth, billing.

## Core Concept
AInterceptor does NOT use provider APIs. It drives the real provider web
UI in an authenticated browser and captures network transport (SSE/WS)
at the browser's CDP boundary — Layer 6.

Provider Web App -> Browser -> CDP Network -> AInterceptor Transport
Capture -> Provider Parser -> StreamEvent -> Orchestrator -> Client.

## Architecture (summary)
Management Plane: CLI (Cisco-style), Web UI, SSH (admin), API.
Control Plane: config engine, NVRAM, policy, billing.
Orchestrator: routing, capability, fallback, rate limits.
Interceptor: provider runtimes, session lifecycle, transport capture.
Browser Runtime: Chromium (headless), CDP sessions, storage state.

## Supported Providers
Claude, DeepSeek, ChatGPT, Gemini, Mistral, Qwen, HuggingChat,
Perplexity, Grok, Poe.

Path A = direct HTTPS with harvested cookies (fast).
Path B = headless Chromium driving real UI (universal).
ChatGPT needs B. Others prefer A, fall back to B.

## Login Model
Default: airouter-agent on user's own machine opens real Chrome,
user logs in, agent captures storage state, uploads.
Power-user: manual cookie export.
Server never opens a browser for login.

## Deployment
Docker-first, Linux runtime, Postgres.
No Xvfb, no VNC, no visible Chrome on the server.

## Roadmap (summary)
1: API product + agent (ChatGPT E2E)
2: DeepSeek + Claude + Gemini via API
3: Orchestrator (capability, fallback, load balance)
4: Webapp (chat + comparison)
5: Billing, quotas, teams
6: Policy-based routing, cost optimization
7: Public launch, multi-tenant, Kubernetes

Full detail in PROJECT/ROADMAP.md.
"""

F[".ai/CONTEXT.md"] = """# .ai/CONTEXT.md — AInterceptor
Project: AInterceptor — Cisco-style AI Network Operating System
Codename: AINT
Phase: 1 (API product + agent)

One-line orientation: drives real authenticated AI web UIs at the
browser's CDP network boundary, exposes them as an OpenAI-compatible
API and (later) a multi-AI web UI. Claude is the reference. Docker-first.

Read order for fresh agents:
AGENTS.md, PROJECT_GOVERNANCE_STANDARD_v1.1.md, BLUEPRINT.md,
PROJECT/AIOS_ARCHITECTURE.md, PROJECT/PROVIDER_RUNTIME_CONTRACT.md,
PROJECT/ROUTING_POLICY.md, PROJECT/ROADMAP.md, .ai/CURRENT_TASK.md,
.ai/KNOWN_ISSUES.md.
"""

F[".ai/CURRENT_TASK.md"] = """# .ai/CURRENT_TASK.md
Phase: 1 — API product + agent
Focus: documentation refresh, then Docker + API + agent implementation
Next: review design docs, approve, then build docker/ + backend/app/api/

Reality Check:
- Working: Claude + DeepSeek on Windows
- Not yet: Docker, API, agent, multi-tenant
- Do NOT modify Claude

Recently completed:
- Phase 2 (DeepSeek via daemon) working on Windows
- Provider registry with per-provider CDP
- DeepSeek parser byte-exact
- Documentation refresh (this commit)
"""

F[".ai/KNOWN_ISSUES.md"] = """# .ai/KNOWN_ISSUES.md

| ID | Sev | Area | Summary | Status |
|---|---|---|---|---|
| K001 | Low | Docs | README listed Phase 1+ cmds before they existed | Resolved |
| K002 | Low | Validation | datetime.utcnow deprecation | Resolved |
| K003 | High | Dashboard | next@15.0.3 CVE | Resolved |
| K004 | Med | Runtime | Claude CDP attach hangs if Chrome dead | Open |
| K005 | Med | Runtime | Non-Claude parser drops fragments on partial frames | Partial |
| K006 | Low | Repo | _bundle.zip, .bak, test_input.txt tracked | Open |
| K007 | Med | Repo | .evidence/raw/*.raw tracked | Open |
| K008 | Info | Process | Silent "pattern not matched" commits | Resolved |
| K009 | Low | Config | Two pytest.ini files, ambiguous | Open |
| K010 | Info | Governance | Research register not linked from AGENTS.md | Open |
"""

for rel, txt in F.items():
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8", newline="\n")
    print(f"  [OK] {rel}  ({len(txt)} B)")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","docs(phase-1a): AGENTS, BLUEPRINT, .ai context refresh"])
print((r.stdout.strip() or r.stderr.strip())[:400])
print("DONE — script 1 of 4. Run script 2 next.")
