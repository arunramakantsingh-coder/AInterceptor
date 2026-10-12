"""atrace - read-only view of recent dispatcher path attempts."""
from __future__ import annotations
import argparse, sys
from app.runtime import path_trace


def _parse_since(v):
    v = v.strip().lower()
    try:
        if v.endswith("h"): return float(v[:-1]) * 3600
        if v.endswith("m"): return float(v[:-1]) * 60
        if v.endswith("s"): return float(v[:-1])
        return float(v)
    except Exception:
        raise SystemExit(f"--since: bad value {v!r}; use 30m, 2h, 600")


def main():
    ap = argparse.ArgumentParser(prog="atrace")
    ap.add_argument("provider", nargs="?", default=None)
    ap.add_argument("--path", choices=["a", "b", "claude"], default=None)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--since", default=None)
    ap.add_argument("--clear", action="store_true")
    a = ap.parse_args()

    if a.clear:
        try:
            if path_trace.LOG.exists():
                path_trace.LOG.unlink()
            print(f"[clear] removed {path_trace.LOG}")
        except Exception as e:
            print(f"[FAIL] {e}"); return 1
        return 0

    since = _parse_since(a.since) if a.since else None
    rows = path_trace.recent(provider=a.provider, path=a.path, n=a.n,
                              since_seconds=since)
    print()
    print(f"  path_trace: {path_trace.LOG}")
    print(f"  filter: provider={a.provider or '*'}  path={a.path or '*'}  "
          f"since={a.since or 'all'}  n={a.n}")
    print()
    print(path_trace.format_table(rows))
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
