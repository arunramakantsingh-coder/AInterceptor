import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend" / "app"

p = BE / "runtime" / "path_a.py"
src = p.read_text(encoding="utf-8")

# Extend _token_from_state to also scan _ainterceptor_idb
old = '''def _token_from_state(state: dict, candidates: tuple[str, ...] = ()) -> str | None:
    """Extract a JWT-ish token from storage_state localStorage.

    Playwright's storage_state format:
      {"cookies": [...], "origins": [{"origin": "...", "localStorage": [{"name","value"}]}]}
    """
    if not state:
        return None
    def looks_like_jwt(v: str) -> bool:
        if not isinstance(v, str) or len(v) < 40:
            return False
        parts = v.split(".")
        return len(parts) == 3 and parts[0].startswith("eyJ")
    # Prefer explicit candidates
    for origin in state.get("origins", []) or []:
        for entry in (origin.get("localStorage") or []):
            name = (entry.get("name") or "").lower()
            value = entry.get("value") or ""
            if name in candidates and looks_like_jwt(value):
                return value
    # Fallback: any JWT-ish value in localStorage
    for origin in state.get("origins", []) or []:
        for entry in (origin.get("localStorage") or []):
            value = entry.get("value") or ""
            if looks_like_jwt(value):
                return value
    return None'''

new = '''def _looks_like_jwt(v) -> bool:
    if not isinstance(v, str) or len(v) < 40:
        return False
    parts = v.split(".")
    return len(parts) == 3 and parts[0].startswith("eyJ")


def _scan_jwt(obj, depth: int = 0):
    """Recursively walk nested dicts/lists looking for a JWT-shaped string."""
    if depth > 8:
        return None
    if isinstance(obj, str):
        return obj if _looks_like_jwt(obj) else None
    if isinstance(obj, dict):
        for k, v in obj.items():
            r = _scan_jwt(v, depth + 1)
            if r:
                return r
    if isinstance(obj, list):
        for v in obj:
            r = _scan_jwt(v, depth + 1)
            if r:
                return r
    return None


def _token_from_state(state: dict, candidates: tuple[str, ...] = ()) -> str | None:
    """Extract a JWT-ish token from storage_state (localStorage + IndexedDB)."""
    if not state:
        return None

    # 1. Named localStorage candidates
    for origin in state.get("origins", []) or []:
        for entry in (origin.get("localStorage") or []):
            name = (entry.get("name") or "").lower()
            value = entry.get("value") or ""
            if name in candidates and _looks_like_jwt(value):
                return value

    # 2. Any JWT in localStorage
    for origin in state.get("origins", []) or []:
        for entry in (origin.get("localStorage") or []):
            value = entry.get("value") or ""
            if _looks_like_jwt(value):
                return value

    # 3. Scan the captured IndexedDB blob for any JWT
    idb = state.get("_ainterceptor_idb")
    if idb:
        found = _scan_jwt(idb)
        if found:
            return found

    return None'''

if old in src:
    src = src.replace(old, new, 1)
    p.write_text(src, encoding="utf-8", newline="\n")
    print("  [OK] path_a: JWT scanner covers IndexedDB")
else:
    print("  [!] token function pattern not matched")

import ast
try:
    ast.parse(p.read_text(encoding="utf-8"))
except SyntaxError as e:
    print("[FAIL]", e); sys.exit(1)
print("  [OK] syntax valid")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(path_a): scan _ainterceptor_idb for JWT"])
print((r.stdout.strip() or r.stderr.strip())[:300])
