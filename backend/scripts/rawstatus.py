"""arawstatus — per-provider monitor of raw captures."""
from __future__ import annotations
import json, pathlib, sys

INDEX = pathlib.Path.home() / ".ainterceptor" / "raw" / "index.jsonl"


def _load():
    if not INDEX.exists():
        return []
    rows = []
    with INDEX.open() as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def _all_providers():
    try:
        from app.providers_list import ALL_PROVIDERS
        return sorted(set(ALL_PROVIDERS))
    except Exception:
        return ["chatgpt", "claude", "deepseek", "gemini"]


def main():
    rows = _load()

    # last-per-provider
    last = {}
    for r in rows:
        last[r.get("provider", "")] = r

    providers = _all_providers()
    print()
    print(f"  {'provider':12} {'last capture':22} {'protocol':10} {'latency':>10} {'bytes':>8}  status")
    print("  " + "─" * 82)
    for p in providers:
        r = last.get(p)
        if not r:
            print(f"  {p:12} {'—':22} {'—':10} {'—':>10} {'—':>8}  ⚪ no capture")
            continue
        ts = (r.get("timestamp") or "")[:19].replace("T", " ")
        proto = r.get("protocol", "—")
        lat = f"{r.get('latency_ms',0)} ms"
        b = f"{r.get('bytes',0)} B"
        status = "✅" if r.get("bytes", 0) > 0 else "⚠️"
        print(f"  {p:12} {ts:22} {proto:10} {lat:>10} {b:>8}  {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
