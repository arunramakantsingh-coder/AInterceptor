# Agent Login — User Install Guide

For users who log into an AI provider on their own machine and push the
resulting session to the AInterceptor VM. No VNC required.

## What this does

1. Opens real Chrome on the user's machine
2. User logs into the provider normally
3. Agent captures storage_state (cookies + localStorage + IndexedDB)
4. Agent POSTs it to /api/sessions/upload
5. Server encrypts + stores it, then CDP-injects it into the live tab
   on the VM. No daemon restart needed.

## Prerequisites

- Python 3.10+
- Real Chrome installed (not Chromium)
- Network access to the AInterceptor VM (Tailscale recommended)

## Step 1 - Install the agent

    cd agent
    pip install -e .
    python -m playwright install chromium

## Step 2 - Get an API key from the admin

Admin runs:

    akeys create <your-name> --save
    akeys current

Admin sends the full token (sk-aint-...) via a private channel.
Do NOT paste it into chat or screenshots.

## Step 3 - Configure the agent

    airouter-agent config --server http://100.82.62.82:8000 --token sk-aint-XXXX

Verify: cat ~/.airouter/config.json

## Step 4 - Log into a provider

    airouter-agent login claude

What happens:

1. Real Chrome opens on your machine
2. Log in normally
3. Agent detects login, uploads state
4. Console prints: Session for claude uploaded successfully.

Supported providers: claude, chatgpt, gemini, deepseek.

## Step 5 - Verify (admin side)

    aprobe
    atest <provider>

## Troubleshooting

| Symptom | Fix |
|---|---|
| missing server or token | Re-run step 3 |
| playwright not installed | pip install playwright && python -m playwright install chromium |
| upload failed: 401 | Token revoked or wrong |
| upload failed: 400 | Provider not valid, or state file malformed |
| login never detected | Provider changed URL; see agent/airouter_agent/login.py |

## Security

- Token is a bearer credential. Treat like a password.
- Server encrypts session blob at rest.
- Revoke with: akeys revoke <id>
