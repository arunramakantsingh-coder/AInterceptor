# Configuration Guide

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
