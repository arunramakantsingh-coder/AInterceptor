#!/bin/bash
# Install AInterceptor git hooks into this clone.
set -e

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "[FAIL] not inside a git repo"; exit 1
}
cd "$ROOT"

SRC="$ROOT/scripts/hooks/post-commit"
DST="$ROOT/.git/hooks/post-commit"

if [ ! -f "$SRC" ]; then
    echo "[FAIL] $SRC not found"; exit 1
fi

if [ -L "$DST" ] || [ -e "$DST" ]; then
    echo "[i] $DST exists — backing up to ${DST}.bak"
    mv "$DST" "${DST}.bak"
fi

cp "$SRC" "$DST"
chmod +x "$DST"
echo "[OK] installed $DST"
echo "     disable per-commit:  AINT_SKIP_SYNC=1 git commit ..."
echo "     remove:              rm $DST"
