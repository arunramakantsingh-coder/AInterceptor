import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend" / "app"

p = BE / "runtime" / "path_a.py"
src = p.read_text(encoding="utf-8")

# Add token extraction helper after _headers_from_state
helper = '''

def _token_from_state(state: dict, candidates: tuple[str, ...] = ()) -> str | None:
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
    return None

'''

if "_token_from_state" not in src:
    src = src.replace(
        "def _headers_from_state(state: dict, extra: dict | None = None) -> dict:",
        helper.strip() + "\n\n" + "def _headers_from_state(state: dict, extra: dict | None = None) -> dict:",
        1,
    )
    print("  [OK] _token_from_state helper added")

# Rewrite _stream_deepseek to use Authorization header
old = '''    _dbg("deepseek POST -> chat.deepseek.com/api/v0/chat/completion")
    _dbg("deepseek cookies:", list(cookies.keys()))
    _dbg("deepseek body:", body)'''
new = '''    token = _token_from_state(state, candidates=("usertoken", "user_token", "__user_token__", "token"))
    if token:
        headers["Authorization"] = f"Bearer {token}"
        _dbg("deepseek Bearer token found (len=%d)" % len(token))
    else:
        _dbg("deepseek Bearer token NOT FOUND in storage_state — will try cookies only")
    _dbg("deepseek POST -> chat.deepseek.com/api/v0/chat/completion")
    _dbg("deepseek cookies:", list(cookies.keys()))
    _dbg("deepseek body:", body)'''

if old in src:
    src = src.replace(old, new, 1)
    print("  [OK] _stream_deepseek sends Authorization: Bearer")
else:
    print("  [!] deepseek streamer pattern not matched")

p.write_text(src, encoding="utf-8", newline="\n")

# Also add x-ds-* headers some DeepSeek versions require
if "x-ds-" not in src:
    print("  [i] no x-ds-* headers needed for now")

# Syntax check
import ast
try:
    ast.parse(src)
except SyntaxError as e:
    print("[FAIL]", e); sys.exit(1)
print("  [OK] syntax valid")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(path_a): send Authorization: Bearer from storage_state localStorage"])
print((r.stdout.strip() or r.stderr.strip())[:300])

print()
print("=" * 60)
print("NEXT:")
print("  docker compose up -d --build api")
print("  (2 min)")
print()
print("Then re-run the curl and check logs:")
print("  curl.exe -N -X POST http://localhost:8000/v1/chat/completions \\")
print("    -H \"Authorization: Bearer $APIKEY\" \\")
print("    -H \"Content-Type: application/json\" \\")
print("    --data-binary \"@body.json\"")
print("  docker compose logs --tail=80 api | Select-String 'path_a|path_b'")
print("=" * 60)
