"""CLI helper: python scripts/login.py <provider>

Calls the running daemon's /api/login/<provider> endpoint, which brings
the daemon's Chrome on-screen. Log in to the provider in the browser,
the daemon detects success and saves the session.
"""
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request


def _token() -> str:
    env_file = pathlib.Path(".env.test")
    if not env_file.exists():
        print("[FAIL] .env.test not found — run the signup script first")
        sys.exit(1)
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("TOKEN="):
            return line[6:].strip()
    print("[FAIL] TOKEN not found in .env.test")
    sys.exit(1)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/login.py <provider>")
        print("providers: claude chatgpt gemini deepseek mistral qwen huggingchat perplexity grok poe")
        return 1
    provider = sys.argv[1].lower()
    base = os.environ.get("AINTERCEPTOR_BASE", "http://127.0.0.1:8000")
    token = _token()

    print(f"[..] requesting login for {provider}")
    print(f"     the daemon's Chrome will appear on screen shortly")
    print(f"     log in normally, then wait for confirmation")
    print()

    req = urllib.request.Request(
        f"{base}/api/login/{provider}",
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=360) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"[FAIL] HTTP {e.code}: {e.read().decode('utf-8','replace')[:400]}")
        return 1
    except Exception as e:
        print(f"[FAIL] {e}")
        return 1

    if not body.get("ok"):
        print(f"[FAIL] {body.get('error')}")
        return 1

    print()
    print(f"[OK] {provider} session saved")
    print(f"     cookies         : {body.get('cookies')}")
    print(f"     indexeddb dbs   : {body.get('idb_databases')}")
    print(f"     took            : {body.get('took_s')}s")
    print(f"     saved at        : {body.get('saved_path')}")
    print()
    print("Chrome is now off-screen again. Log in to other providers with:")
    print(f"  python scripts/login.py <provider>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
