"""AInterceptor API-key CLI. Talks to the daemon over HTTP.

Usage:  python -m scripts.keys_cli <list|create|revoke|rotate> [args]
"""
from __future__ import annotations
import argparse, json, pathlib, sys
import urllib.request, urllib.error

KEY_FILE = pathlib.Path.home() / ".ainterceptor" / "admin_api_key.txt"
BASE     = "http://127.0.0.1:8000"


def _token() -> str:
    if not KEY_FILE.exists():
        print(f"[FAIL] no admin key at {KEY_FILE}")
        print("       run: python -m scripts.bootstrap_admin")
        sys.exit(2)
    return KEY_FILE.read_text().strip()


def _req(method: str, path: str, body: dict | None = None):
    url = BASE + path
    headers = {"Authorization": f"Bearer {_token()}",
               "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "replace")}
    except Exception as e:
        return 0, {"error": str(e)}


def cmd_list() -> int:
    code, body = _req("GET", "/api/keys")
    if code != 200:
        print(f"[FAIL] {code} {body}"); return 1
    if not body:
        print("  (no keys)")
        return 0
    print(f"  {'ID':36s}  {'PREFIX':16s}  {'NAME':20s}  STATUS")
    for k in body:
        status = "REVOKED" if k.get("revoked_at") else "active"
        print(f"  {k['id']:36s}  {k['prefix']:16s}  {k['name']:20s}  {status}")
    return 0


def cmd_create(name: str, save: bool = False) -> int:
    code, body = _req("POST", "/api/keys", {"name": name})
    if code != 200:
        print(f"[FAIL] {code} {body}"); return 1
    print("=" * 60)
    print(" NEW API KEY (shown once — save it now)")
    print("=" * 60)
    print(f"  id:     {body['id']}")
    print(f"  name:   {body['name']}")
    print(f"  prefix: {body['prefix']}")
    print(f"  token:  {body['key']}")
    print("=" * 60)
    if save:
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        KEY_FILE.write_text(body["key"] + "\n", encoding="utf-8")
        try:
            KEY_FILE.chmod(0o600)
        except Exception:
            pass
        print(f"[OK] saved to {KEY_FILE} (chmod 600)")
    else:
        print("  (not saved — rerun with --save to write automatically)")
    return 0


def cmd_current() -> int:
    if not KEY_FILE.exists():
        print(f"[FAIL] no key at {KEY_FILE}")
        return 1
    tok = KEY_FILE.read_text().strip()
    print(f"  file:    {KEY_FILE}")
    print(f"  prefix:  {tok[:16]}")
    print(f"  length:  {len(tok)}")
    code, _ = _req("GET", "/api/keys")
    if code != 200:
        print(f"  status:  [warn] daemon returned {code}")
        return 0
    print(f"  daemon:  reachable")
    return 0


def cmd_revoke(key_id: str) -> int:
    code, body = _req("DELETE", f"/api/keys/{key_id}")
    if code != 200:
        print(f"[FAIL] {code} {body}"); return 1
    print(f"[OK] revoked {key_id}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="akeys")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=lambda _: cmd_list())
    pc = sub.add_parser("create"); pc.add_argument("name"); pc.add_argument("--save", action="store_true"); pc.set_defaults(fn=lambda a: cmd_create(a.name, a.save))
    pr = sub.add_parser("revoke"); pr.add_argument("id"); pr.set_defaults(fn=lambda a: cmd_revoke(a.id))
    sub.add_parser("current").set_defaults(fn=lambda _: cmd_current())
    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
