"""Append-only JSONL trace of dispatcher path attempts.

Never raises into the caller. Read via `atrace`.
"""
from __future__ import annotations
import json, pathlib, time

ROOT = pathlib.Path.home() / ".ainterceptor"
LOG = ROOT / "path_attempts.jsonl"
MAX_LINES = 1000


def append(provider, path, ok, latency_ms, error=None):
    try:
        ROOT.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": time.time(),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "provider": provider,
            "path": path,
            "ok": bool(ok),
            "latency_ms": int(latency_ms or 0),
        }
        if error:
            row["error"] = str(error)[:240]
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if LOG.stat().st_size > 500_000:
            lines = LOG.read_text().splitlines()
            if len(lines) > MAX_LINES:
                LOG.write_text("\n".join(lines[-MAX_LINES:]) + "\n")
    except Exception:
        pass


def recent(provider=None, path=None, n=20, since_seconds=None):
    if not LOG.exists():
        return []
    cutoff = (time.time() - since_seconds) if since_seconds else 0
    out = []
    try:
        for line in LOG.read_text().splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if provider and r.get("provider") != provider:
                continue
            if path and str(r.get("path", "")).upper() != path.upper():
                continue
            if cutoff and r.get("ts", 0) < cutoff:
                continue
            out.append(r)
    except Exception:
        return []
    return out[-n:]


def format_table(rows):
    if not rows:
        return "  (no attempts recorded)"
    lines = [
        "  when                provider    path    result       ms  error",
        "  " + "-" * 88,
    ]
    for r in rows:
        when = str(r.get("iso", "?"))[:19]
        p = str(r.get("provider", "?"))[:10]
        pa = str(r.get("path", "?"))[:6]
        ok = "OK" if r.get("ok") else "FAIL"
        ms = int(r.get("latency_ms", 0) or 0)
        err = str(r.get("error") or "")[:40]
        lines.append(f"  {when:<19} {p:<11} {pa:<7} {ok:<6} {ms:>6d}  {err}")
    return "\n".join(lines)
