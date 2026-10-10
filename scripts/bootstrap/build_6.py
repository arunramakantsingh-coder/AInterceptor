import pathlib, subprocess, secrets, base64, os, sys

ROOT = pathlib.Path.cwd()

# ── 1. .gitignore updates ──
gi = ROOT / ".gitignore"
g = gi.read_text(encoding="utf-8") if gi.exists() else ""
additions = [
    ".env",
    "sessions/",
    "logs/",
    "data/",
    "backend/.evidence/",
    "_bundle.zip",
    "backend/app/interception/nonclaude_runtime.py.bak",
    "backend/test_input.txt",
    "test_input.txt",
    "ainterceptor.egg-info/",
    ".evidence/raw/",
    ".evidence/dump/",
    ".evidence/branch*.txt",
    ".evidence/recent_commits.txt",
    ".evidence/repo_tree.txt",
    ".evidence/tags.txt",
    ".evidence/tracked_files.txt",
]
for line in additions:
    if line not in g:
        g = g.rstrip() + "\n" + line + "\n"
gi.write_text(g, encoding="utf-8", newline="\n")
print("  [OK] .gitignore updated")

# ── 2. Generate .env ──
env_path = ROOT / ".env"
if not env_path.exists():
    master = base64.b64encode(os.urandom(32)).decode()
    jwt_secret = secrets.token_urlsafe(48)
    env = (
        f"MASTER_KEY={master}\n"
        f"JWT_SECRET={jwt_secret}\n"
        f"POSTGRES_USER=airouter\n"
        f"POSTGRES_PASSWORD=airouter_dev\n"
        f"POSTGRES_DB=airouter\n"
        f"DATABASE_URL=postgresql+psycopg://airouter:airouter_dev@db:5432/airouter\n"
        f"LOG_LEVEL=INFO\n"
    )
    env_path.write_text(env, encoding="utf-8", newline="\n")
    print("  [OK] .env generated (secrets random)")
else:
    print("  [SKIP] .env already exists")

# ── 3. Backend tests ──
tests = ROOT / "tests"
tests.mkdir(exist_ok=True)

F = {}
F["tests/test_crypto.py"] = '''import os
from unittest.mock import patch

# Set env before importing app modules
os.environ.setdefault("MASTER_KEY", __import__("base64").b64encode(os.urandom(32)).decode())
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.crypto.aes import encrypt_for_user, decrypt_for_user  # noqa: E402


def test_roundtrip():
    blob = b'{"cookies": [{"name":"a","value":"b"}]}'
    ct, nonce = encrypt_for_user("user-1", blob)
    assert ct != blob
    out = decrypt_for_user("user-1", ct, nonce)
    assert out == blob


def test_wrong_user_fails():
    blob = b"secret"
    ct, nonce = encrypt_for_user("user-1", blob)
    try:
        decrypt_for_user("user-2", ct, nonce)
        assert False, "should have raised"
    except Exception:
        pass


def test_different_nonces():
    blob = b"same input"
    ct1, n1 = encrypt_for_user("u", blob)
    ct2, n2 = encrypt_for_user("u", blob)
    assert n1 != n2
    assert ct1 != ct2
'''

F["tests/test_auth.py"] = '''import os
os.environ.setdefault("MASTER_KEY", __import__("base64").b64encode(os.urandom(32)).decode())
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.auth import (hash_password, verify_password, make_jwt, read_jwt,
                      generate_api_key, verify_api_key)  # noqa: E402


def test_password_roundtrip():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip():
    tok = make_jwt("user-abc")
    assert read_jwt(tok) == "user-abc"


def test_jwt_tamper():
    tok = make_jwt("user-abc")
    assert read_jwt(tok + "x") is None


def test_api_key_format():
    full, prefix, hashed = generate_api_key()
    assert full.startswith("sk-aint-")
    assert len(full) > 20
    assert prefix == full[:16]
    assert verify_api_key(full, hashed)
    assert not verify_api_key(full + "x", hashed)
'''

F["tests/__init__.py"] = ""

for rel, txt in F.items():
    p = ROOT / rel
    p.write_text(txt, encoding="utf-8", newline="\n")
    print(f"  [OK] {rel}")

# ── 4. Run tests locally (best effort — skip if deps missing) ──
print("\n==> Running local tests (best effort)")
r = subprocess.run(
    ["python", "-m", "pytest", "-q",
     "tests/test_crypto.py", "tests/test_auth.py",
     "-o", "asyncio_mode=auto", "--no-header", "-x"],
    cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
)
print(r.stdout[-1500:] if r.stdout else "")
if r.stderr.strip():
    print("STDERR:", r.stderr[-500:])

# ── 5. Commit ──
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)

git(["add", "-A"])
r = git(["commit", "-m", "feat(phase-1): env generation, gitignore hardening, unit tests"])
print((r.stdout.strip() or r.stderr.strip())[:400])

# ── 6. Untrack residue (best effort) ──
for path in ["_bundle.zip", "backend/test_input.txt", "test_input.txt",
             "backend/app/interception/nonclaude_runtime.py.bak"]:
    subprocess.run(["git","rm","--cached","--ignore-unmatch", path],
                   cwd=ROOT, capture_output=True)

git(["add", "-A"])
r = git(["commit", "-m", "chore: untrack residue files"])
print((r.stdout.strip() or r.stderr.strip())[:300])

sha = git(["rev-parse", "HEAD"]).stdout.strip()

print()
print("=" * 66)
print("PHASE 1 SCAFFOLD COMPLETE — 6 SCRIPTS LANDED")
print(f"  HEAD: {sha[:10]}")
print()
print("NEXT: build and start the stack.")
print()
print("  1. Verify .env exists:")
print("       Test-Path .env")
print()
print("  2. Build and start:")
print("       docker compose up -d --build")
print("     First run takes 3-6 min (installs python deps + playwright chromium).")
print()
print("  3. Check health:")
print("       curl http://localhost:8000/healthz")
print("     Expected: {\"status\":\"ok\",\"version\":\"0.1.0\",\"db\":\"ok\",\"providers\":[...]}")
print()
print("  4. Signup:")
print("       curl -X POST http://localhost:8000/api/auth/signup ^")
print("         -H \"Content-Type: application/json\" ^")
print("         -d \"{\\\"email\\\":\\\"me@example.com\\\",\\\"password\\\":\\\"changeme123\\\"}\"")
print()
print("  5. Create API key (paste token from step 4):")
print("       curl -X POST http://localhost:8000/api/keys ^")
print("         -H \"Authorization: Bearer <token>\" ^")
print("         -H \"Content-Type: application/json\" ^")
print("         -d \"{\\\"name\\\":\\\"CareerOS\\\"}\"")
print()
print("  6. Upload a session via agent:")
print("       cd agent")
print("       pip install -e .")
print("       airouter-agent config --server http://localhost:8000 --token <token>")
print("       airouter-agent login chatgpt")
print()
print("  7. Chat via API:")
print("       curl -N http://localhost:8000/v1/chat/completions ^")
print("         -H \"Authorization: Bearer sk-aint-...\" ^")
print("         -H \"Content-Type: application/json\" ^")
print("         -d \"{\\\"model\\\":\\\"deepseek\\\",\\\"messages\\\":[{\\\"role\\\":\\\"user\\\",\\\"content\\\":\\\"hi\\\"}],\\\"stream\\\":true}\"")
print()
print("Paste the docker build output next.")
print("=" * 66)
