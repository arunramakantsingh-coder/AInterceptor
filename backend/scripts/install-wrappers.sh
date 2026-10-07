#!/bin/bash
# install-wrappers.sh — regenerate ~/bin/a* shims from a single source.
# Run once after a fresh VM build or after changing a wrapper's template.
#
# Each shim is: cd repo, activate venv, PYTHONPATH=backend,
#               exec python -m scripts.ops <cmd> "$@"
#
# "$@" is REQUIRED. Without it, flags like --fg never reach Python.
set -euo pipefail

REPO="$HOME/ainterceptor"
BIN="$HOME/bin"
mkdir -p "$BIN"

# Every CLI command that maps to scripts.ops <cmd>
COMMANDS=(
  astart arestart astop areload
  astatus ahealth aversion aprobe atest
  amonitor atrace adispatch aint apath alive
  aproviders alogin alogout ashow ahide asessions
  aconfig aconfig-reset
  akeys
  alogs aevidence
  abootstrap asave
  asession aprogress sync_docs
  ashell
  arawdump arawstatus
)

for cmd in "${COMMANDS[@]}"; do
  f="$BIN/$cmd"
  cat > "$f" <<EOF
#!/bin/bash
cd \$HOME/ainterceptor
source .venv/bin/activate
export PYTHONPATH=backend
exec python -m scripts.ops $cmd "\$@"
EOF
  chmod +x "$f"
done

# Non-ops wrappers (different entry points)
cat > "$BIN/adev" << 'EOF'
#!/bin/bash
cd $HOME/ainterceptor && source .venv/bin/activate 2>/dev/null
export AINTERCEPTOR_DEV_RELOAD=1
exec bash run-linux.sh
EOF
chmod +x "$BIN/adev"

cat > "$BIN/arawdump" << 'EOF'
#!/bin/bash
cd $HOME/ainterceptor && source .venv/bin/activate 2>/dev/null
exec python backend/scripts/rawdump.py "$@"
EOF
chmod +x "$BIN/arawdump"

cat > "$BIN/arawstatus" << 'EOF'
#!/bin/bash
cd $HOME/ainterceptor && source .venv/bin/activate 2>/dev/null
exec python backend/scripts/rawstatus.py "$@"
EOF
chmod +x "$BIN/arawstatus"

echo "[ok] installed $(ls $BIN/a* 2>/dev/null | wc -l) wrappers into $BIN"
