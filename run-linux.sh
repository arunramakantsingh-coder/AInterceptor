#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

# Activate venv
source .venv/bin/activate

# Load .env
set -a
source .env
set +a

# Ensure Xvfb :99
if ! pgrep -x Xvfb >/dev/null; then
  echo "[launcher] starting Xvfb :99"
  Xvfb :99 -screen 0 1400x900x24 -nolisten tcp &
  sleep 2
fi
export DISPLAY=:99

# Run the daemon
export PYTHONPATH=backend
echo "[launcher] starting AInterceptor daemon"
exec python -m app.runtime.daemon
