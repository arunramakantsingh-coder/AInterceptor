# dsh profile — AIN integration

This is the profile overlay for the DeepSeek Harness (dsh) Web UI
when it is used as a client of AInterceptor's /v1 endpoint.

## What it does

1. Routes the AIP (DeepSeek, Claude, Gemini) through AInterceptor
   at http://127.0.0.1:8000/v1 — see the llm-pi-ai block.

2. Disables dsh's native tools (bash, pwsh, fs, str-replace-editor).
   Reason: two tool systems confuse the model. AIN owns the tool
   catalog in agent mode; every action must go through AIN's
   dispatcher so it is multi-target, credential-vaulted, and
   audited. See the "disable: dsh native tools" block.

3. Keeps the meta-tools (goal, jobs, todo, subagent, workflow,
   present, cordis), the web tool, and ask_user. AIN does not
   yet have equivalents for those.

## Install

    cp deploy/dsh-profile/cordis.patch.yml \\
       ~/.dsh/profiles/web/cordis.patch.yml

    # restart dsh to pick up the change
    pkill -f "dsh.*web"
    cd ~/deepseek-harness
    nohup npx -y @deepseek-ai/dsh@0.2.0-rc.2 --profile web \\
      --no-open --port 3080 \\
      --trusted-host ainterceptor.taila2310c.ts.net:8443 \\
      --trusted-host 127.0.0.1:3080 \\
      > ~/deepseek-harness/dsh-web.log 2>&1 &

## Verify

In the harness, ask: "List every tool you have available."
Expected reply: AIN's catalog only —
  list_targets, read, write, glob, list_capabilities,
  tailscale_status, probe_port, scan_lan, shell

If dsh native tools appear (bash, pwsh, edit, str_replace),
the disable block did not apply. Restore the backup
(cordis.patch.yml.bak-*) and check the plugin ids.

## Reference

- AIN's tool catalog: backend/app/agent/tools.py
- AIN's chat_routes override: backend/app/api/chat_routes.py
  (search for _AIN_TOOLS)
