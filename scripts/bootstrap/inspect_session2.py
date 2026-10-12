import subprocess, pathlib
ROOT = pathlib.Path.cwd()

script = '''
import sys
sys.path.insert(0, "/app/backend")
import os, json
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
            items = o.get("localStorage", [])
            print(f"    origin={o.get('origin')}  items={len(items)}")
            for item in items[:15]:
                nm = item.get("name", "")
                vl = item.get("value", "")
                print(f"      {nm:<40} = {vl[:80]}{'...' if len(vl) > 80 else ''}")
    except Exception as e:
        print(f"decrypt failed for {r.id}: {e}")
'''

cmd = ["docker", "compose", "exec", "-T", "api", "python", "-c", script]
r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr[-800:])
