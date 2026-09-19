"""Test every active provider end-to-end.

Usage:
    python scripts/test_all_providers.py            # test active providers
    python scripts/test_all_providers.py --all      # test every provider
    python scripts/test_all_providers.py claude gemini  # test specific ones

Runs each provider through the local API, streams the reply, prints
PASS/FAIL with the actual text received.
"""
from __future__ import annotations
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = os.environ.get("AINTERCEPTOR_BASE", "http://127.0.0.1:8000")
PROMPT = "Reply with exactly one word: ok"


def _token() -> str:
    envf = ROOT / ".env.test"
    if not envf.exists():
        print("[FAIL] .env.test not found"); sys.exit(1)
    for line in envf.read_text(encoding="utf-8").splitlines():
        if line.startswith("API_KEY="):
            return line[8:].strip()
    print("[FAIL] API_KEY not found in .env.test"); sys.exit(1)


def _active_providers() -> list[str]:
    # Prefer the daemon's own view
    try:
        with urllib.request.urlopen(f"{BASE}/health", timeout=5) as r:
            data = json.loads(r.read())
            return data.get("providers_active") or []
    except Exception:
        # Fall back to env
        env = os.environ.get("AINTERCEPTOR_ACTIVE_PROVIDERS", "claude,chatgpt,gemini,deepseek")
        return [p.strip() for p in env.split(",") if p.strip()]


def _all_providers() -> list[str]:
    try:
        with urllib.request.urlopen(f"{BASE}/admin/providers",
                                    headers={"Authorization": f"Bearer {_bearer()}"},
                                    timeout=5) as r:
            return [row["provider"] for row in json.loads(r.read())["all"]]
    except Exception:
        return []


def _bearer() -> str:
    envf = ROOT / ".env.test"
    for line in envf.read_text(encoding="utf-8").splitlines():
        if line.startswith("TOKEN="):
            return line[6:].strip()
    return ""


def test_one(provider: str) -> tuple[bool, str]:
    body = json.dumps({
        "model": provider,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": True,
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    collected = ""
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            buf = b""
            for chunk in resp:
                buf += chunk
                while b"\n\n" in buf:
                    ev, buf = buf.split(b"\n\n", 1)
                    for ln in ev.split(b"\n"):
                        if not ln.startswith(b"data: "):
                            continue
                        payload = ln[6:].decode("utf-8", "replace")
                        if payload == "[DONE]":
                            continue
                        try:
                            obj = json.loads(payload)
                        except Exception:
                            continue
                        if "error" in obj:
                            return False, f"error: {obj['error'].get('message')}"
                        for ch in obj.get("choices", []):
                            d = ch.get("delta") or {}
                            if d.get("content"):
                                collected += d["content"]
        if collected.strip():
            return True, collected.strip()
        return False, "empty reply"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        providers = args
    elif "--all" in sys.argv:
        providers = _all_providers()
    else:
        providers = _active_providers()

    if not providers:
        print("no providers to test"); return 1

    print(f"Testing {len(providers)} provider(s): {providers}\n")
    passed = failed = 0
    for p in providers:
        print(f"  [{p:<12}] ", end="", flush=True)
        ok, detail = test_one(p)
        if ok:
            passed += 1
            print(f"PASS  {detail!r}")
        else:
            failed += 1
            print(f"FAIL  {detail}")
    print(f"\nResult: {passed} passed, {failed} failed, {len(providers)} total")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
