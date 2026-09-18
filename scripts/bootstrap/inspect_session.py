import pathlib, subprocess, sys, json, base64, os

ROOT = pathlib.Path.cwd()

# ── 1. Inspect what the agent actually uploaded ──
# Fetch via API and decrypt with the server's MASTER_KEY
print("==> Inspecting uploaded DeepSeek storage_state")
env = {}
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
master = base64.b64decode(env["MASTER_KEY"])

# Use docker to decrypt via the container's own code
script = '''
import os, json, base64
from app.db.session import SessionLocal
from app.db.models import UserSession
from app.crypto.aes import decrypt_for_user
db = SessionLocal()
rows = db.query(UserSession).all()
for r in rows:
    try:
        raw = decrypt_for_user(r.user_id, r.encrypted_blob, r.nonce)
        st = json.loads(raw)
        print(f"provider={r.provider} alias={r.alias}")
        print(f"  cookies   : {len(st.get('cookies', []))}")
        print(f"  origins   : {len(st.get('origins', []))}")
        for o in st.get("origins", []):
            print(f"    origin={o.get('origin')}  localStorage_items={len(o.get('localStorage', []))}")
            for item in o.get("localStorage", [])[:10]:
                nm = item.get("name", "")
                vl = item.get("value", "")
                print(f"      {nm:<30} = {vl[:60]}{'...' if len(vl) > 60 else ''}")
    except Exception as e:
        print(f"decrypt failed for {r.id}: {e}")
'''
cmd = ["docker", "compose", "exec", "-T", "api", "python", "-c", script]
r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr[-500:])
