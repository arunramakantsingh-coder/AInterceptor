"""Agent-first login: instruct user, wait for airouter-agent upload."""
from __future__ import annotations
import asyncio
import json
import pathlib
import sys
import time
import urllib.request
import urllib.error

_HERE = pathlib.Path(__file__).resolve()
ROOT = _HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from scripts.admin_cli import PROVIDER_HOSTS

KEY_FILE = pathlib.Path.home() / ".ainterceptor" / "admin_api_key.txt"
SERVER_DEFAULT = "http://100.82.62.82:8000"


def _token():
    if KEY_FILE.exists():
        return KEY_FILE.read_text().strip()
    return None


def _list_sessions(server, token):
    req = urllib.request.Request(
        f"{server.rstrip('/')}/api/sessions",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read() or b"[]")
    except Exception:
        return None


async def agent_login(provider, server=SERVER_DEFAULT, token=None, timeout_s=300):
    provider = provider.lower()
    if provider not in PROVIDER_HOSTS:
        print(f"[FAIL] unknown provider: {provider}")
        print(f"       known: {', '.join(sorted(PROVIDER_HOSTS))}")
        return 1

    token = token or _token()
    if not token:
        print("[FAIL] no admin key found at")
        print(f"       {KEY_FILE}")
        print("       run:  abootstrap")
        return 1

    print()
    print("=" * 62)
    print(f" AGENT LOGIN — {provider}")
    print("=" * 62)
    print()
    print(" Run these commands on YOUR laptop (not this VM):")
    print()
    print("   cd agent")
    print("   pip install -e .")
    print(f"   airouter-agent config --server {server} \\")
    print("       --token <YOUR_KEY>")
    print(f"   airouter-agent login {provider}")
    print()
    print(" The key is stored on this VM at:")
    print(f"   {KEY_FILE}")
    print(" (share it with the user through a private channel)")
    print()
    print(f" Waiting up to {timeout_s}s for the upload to arrive...")
    print()

    t0 = time.monotonic()
    last_beat = t0
    while time.monotonic() - t0 < timeout_s:
        await asyncio.sleep(5)
        sessions = _list_sessions(server, token)
        if sessions:
            match = next(
                (s for s in sessions
                 if s.get("provider") == provider
                 and s.get("status") == "active"),
                None,
            )
            if match:
                took = int(time.monotonic() - t0)
                print(f"[OK] {provider} session uploaded ({took}s)")
                print(f"     created: {match.get('created_at')}")
                print()
                print(" Next:")
                print(f"   aprobe {provider}")
                print(f"   atest  {provider}")
                return 0
        now = time.monotonic()
        if now - last_beat >= 30:
            print(f"     ...waiting ({int(now - t0)}s)")
            last_beat = now

    print()
    print(f"[FAIL] no upload for {provider} within {timeout_s}s")
    print()
    print(" Troubleshooting:")
    print(f"   - did the user run 'airouter-agent login {provider}'?")
    print("   - daemon up?          astatus")
    print("   - existing sessions?  asessions")
    print("   - daemon log?         alogs daemon")
    return 1


def main():
    import argparse
    p = argparse.ArgumentParser(prog="alogin")
    p.add_argument("provider")
    p.add_argument("--server", default=SERVER_DEFAULT)
    p.add_argument("--token")
    p.add_argument("--timeout", type=int, default=300)
    args = p.parse_args()
    return asyncio.run(
        agent_login(args.provider, args.server, args.token, args.timeout)
    )


if __name__ == "__main__":
    sys.exit(main())
