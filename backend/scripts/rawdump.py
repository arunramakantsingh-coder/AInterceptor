"""arawdump <provider> "<prompt>" — capture + summarize raw response."""
from __future__ import annotations
import json, sys, urllib.request

INTERNAL = "http://127.0.0.1:8000"


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print('usage: arawdump <provider> "<prompt>"')
        return 1
    provider, prompt = args[0].lower(), args[1]
    req = urllib.request.Request(
        f"{INTERNAL}/internal/rawdump",
        data=json.dumps({"provider": provider, "prompt": prompt}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read())

    print()
    print(f"┌─ {d['provider']}  {d['timestamp']}")
    print(f"│ prompt:    {d['prompt']!r}")
    print(f"│ protocol:  {d['protocol']}")
    print(f"│ bytes:     {d['bytes']}   lines: {d['lines']}   event-lines: {d['event_lines']}")
    print(f"│ latency:   {d['latency_ms']} ms")
    print(f"├─ preview")
    for line in d.get("preview", []):
        print(f"│   {line[:110]}")
    print(f"└─ saved:    {d['saved']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
