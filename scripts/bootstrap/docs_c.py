import pathlib, subprocess

ROOT = pathlib.Path.cwd()
(PROJ := ROOT / "PROJECT").mkdir(exist_ok=True)

F = {}

F["PROJECT/ROUTING_POLICY.md"] = """# Routing Policy

How AInterceptor decides which provider handles a request.

## 1. Two Modes

Explicit: client sends model: "chatgpt". Router dispatches or returns 503
with health map if unhealthy.

Automatic: client sends model: "auto" | "reasoning" | "coding" | "fast" |
"long-context" | "vision". Router selects by capability + health.

## 2. Capability Registry

Provider capability scores (policy inputs, tunable in config):

| Provider | reasoning | coding | fast | long_context | vision | tools |
|---|---|---|---|---|---|---|
| Claude | 5 | 4 | 3 | 5 | yes | yes |
| ChatGPT | 5 | 5 | 4 | 4 | yes | yes |
| Gemini | 4 | 4 | 5 | 5 | yes | yes |
| DeepSeek | 4 | 5 | 4 | 3 | no | yes |
| Mistral | 3 | 4 | 4 | 3 | no | yes |
| Qwen | 3 | 4 | 4 | 4 | no | yes |
| Perplexity | 3 | 3 | 5 | 3 | yes | no |
| Grok | 4 | 4 | 4 | 4 | yes | yes |
| Poe | meta | meta | meta | meta | meta | meta |

## 3. Selection Algorithm

1. Filter by required capability.
2. Filter by health == ready.
3. Filter by session != expired.
4. Filter by user quota > 0.
5. Sort by score = capability_weight * health_score * cost_factor.
6. Try top. On failure, next. Max 3 fallbacks.
7. If none succeed, return 503 with diagnostic map.

## 4. Cost Model

Latency cost: Path A = 1, Path B = 5.
Rate cost: free = 0, subscription = 1, usage-based = variable.
User cost: personal = 0, shared = 1.
Router prefers lowest total cost subject to capability threshold.

## 5. Fallback Chain (config)

routing:
  reasoning:
    primary: claude
    secondary: chatgpt
    tertiary: gemini
    max_fallbacks: 2
  coding:
    primary: deepseek
    secondary: claude
    tertiary: chatgpt
  fast:
    primary: gemini
    secondary: chatgpt

Ordered. Try primary, then secondary, up to max_fallbacks.

## 6. Policy Rules (config)

policy:
  rules:
    - name: no-path-b-on-free-tier
      when: user.tier == "free"
      reject: provider.path == "B"
    - name: prefer-cheap-for-short-prompts
      when: request.tokens_estimate < 500
      order_by: cost_asc
    - name: cap-claude-for-low-quota
      when: user.claude_quota_pct < 20
      demote: claude by 2

Engine evaluates in order. First match applies.

## 7. Rate Limit Behavior

Per provider:
  rate-limit:
    rps: 0.5
    burst: 5
    cooldown: 60

On 429: mark rate_limited, cooldown_until = now + cooldown, fall through
to next provider. On cooldown expiry, health check restores.

## 8. Quota

Per user, per provider: messages/hour, tokens/day, concurrent requests
(default 3). Enforced BEFORE dispatch. Exceeding returns 429 with
Retry-After header.

## 9. Observability

Every decision emits:
{request_id, capability, candidates[], selected, reason,
 fallbacks_attempted, latency_ms, path: "A"|"B", outcome}

Feeds admin dashboard and evidence store.

## 10. CLI Configuration

AIRouter(config)# ai
AIRouter(config-ai)# routing
AIRouter(config-ai-routing)# reasoning
AIRouter(config-ai-routing-reasoning)# primary claude
AIRouter(config-ai-routing-reasoning)# secondary chatgpt
AIRouter(config-ai-routing-reasoning)# max-fallbacks 2

Full command tree in PROJECT/CLI_COMMAND_REFERENCE.md.
"""

F["PROJECT/CONFIGURATION_GUIDE.md"] = """# Configuration Guide

Cisco IOS semantics applied to AI providers.

## 1. Two Configurations

running-config: RAM, in-memory NOSState. Lifetime = process. No secrets.
startup-config: .ainterceptor/nvram/startup-config.json. Persistent. No secrets.

running = active. startup = boots.

## 2. Boot Behavior

On process start:
1. Load startup-config.json.
2. Apply to NOSState.
3. Initialize providers listed.
4. Print AIRouter> prompt.

Missing file: defaults + warning. Malformed: boot halts with clear error.

## 3. Saving

AIRouter# copy running-config startup-config
AIRouter# write memory            (alias)

Only way config survives restart.

## 4. Config Structure

{
  "version": "0.1.0",
  "hostname": "AIRouter",
  "config_register": "0x2102",
  "ai": {
    "providers": {
      "claude": {"enabled": true, "session": {"storage_state": "..."}},
      "chatgpt": {"enabled": true, "..." : "..."},
      "gemini": {"enabled": true, "..." : "..."},
      "deepseek": {"enabled": true, "..." : "..."}
    },
    "routing": {
      "reasoning": {"primary": "claude", "secondary": "chatgpt", "max_fallbacks": 2},
      "coding": {"primary": "deepseek", "secondary": "claude"}
    },
    "policy": {"rules": []}
  },
  "billing": {"enabled": false, "tiers": []}
}

NO cookies, tokens, secrets. Session files referenced by path only.

## 5. CLI Commands

View: show running-config, show startup-config, show boot, show version.
Edit: configure terminal -> hostname X -> ai -> provider claude -> enable.
Save: copy running-config startup-config | write memory.
Reset: erase startup-config | reload.

## 6. Mode Tree

EXEC -> enable -> PRIVILEGED -> configure terminal -> CONFIG ->
  ai -> CONFIG-AI -> provider <name> -> CONFIG-AI-PROVIDER-<name>
                  -> routing -> CONFIG-AI-ROUTING -> <capability>
                  -> policy -> CONFIG-AI-POLICY
  billing -> CONFIG-BILLING

Every mode: ? for help, exit to go up one, end to jump to PRIVILEGED.

## 7. Validation

Before copy running-config startup-config succeeds:
1. Schema validation.
2. Provider references exist.
3. Routing chains have no cycles.
4. Policy rules syntactically valid.
5. No secrets present (scan for cookie/token patterns).

Any failure: command errors, startup-config unchanged.

## 8. Versioning

startup-config.json has version field. On load: same = applied; older =
migration applied; newer = boot fails "config too new".
Config version and app version independent.

## 9. Secrets

.env (mounted read-only, never committed):
MASTER_KEY=<base64>, DATABASE_URL=postgresql://..., JWT_SECRET=<random>,
LOG_LEVEL=INFO.
Config references .env keys by name only.

## 10. Gitignore

.ainterceptor/nvram/startup-config.json
.ainterceptor/*/storage_state.json
.ainterceptor/**/chrome-profile-*/
.env
"""

for rel, txt in F.items():
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8", newline="\n")
    print(f"  [OK] {rel}  ({len(txt)} B)")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","docs(phase-1c): routing policy + configuration guide"])
print((r.stdout.strip() or r.stderr.strip())[:400])
print("DONE — script 3 of 4. Run script 4 next.")
