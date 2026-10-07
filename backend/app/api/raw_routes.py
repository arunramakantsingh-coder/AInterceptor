"""Internal-only raw capture route. Loopback-only."""
from __future__ import annotations
import json, pathlib, time, uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.runtime.path_b import _get_runtime
from app.interception.web_runtime_base import NetworkCapture

router = APIRouter(prefix="/internal", tags=["internal"])
RAW_DIR = pathlib.Path.home() / ".ainterceptor" / "raw"
INDEX = RAW_DIR / "index.jsonl"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def _is_loopback(request: Request) -> bool:
    c = request.client
    if c is None or c.host not in ("127.0.0.1", "::1", "localhost"):
        return False
    for h in ("x-forwarded-for", "x-real-ip", "x-forwarded-host", "forwarded"):
        if request.headers.get(h):
            return False
    host = (request.headers.get("host") or "").lower()
    return host.startswith(("127.0.0.1", "localhost", "[::1]"))


def _detect_protocol(body: bytes) -> str:
    if not body:
        return "empty"
    text = body[:4000].decode("utf-8", errors="replace")
    if "event:" in text and "data:" in text:
        return "SSE"
    if text.lstrip().startswith(")]}'"):
        return "SSE (XSSI)"
    s = text.lstrip()
    if s.startswith("{") or s.startswith("["):
        return "JSON"
    if "<!doctype" in text[:200].lower():
        return "HTML"
    return "unknown"


class RawIn(BaseModel):
    provider: str
    prompt: str


async def run_capture(provider: str, prompt: str) -> dict:
    """Shared capture logic. Called by the loopback route and the
    dashboard trigger. Returns the summary dict written to the index."""
    t0 = time.monotonic()
    rt = await _get_runtime(provider)
    from app.interception.contracts import ProviderExecutionRequest
    req = ProviderExecutionRequest(
        provider=provider,
        request_id=f"raw-{uuid.uuid4().hex[:8]}",
        messages=[{"role": "user", "content": prompt}],
    )
    async for _ in rt.execute(req):
        pass

    latency_ms = int((time.monotonic() - t0) * 1000)
    # Each runtime records its own last raw body during execute().
    # No monkey-patching, no cross-provider coupling — Claude uses
    # ClaudeCDPTransport, WebRuntimeBase uses NetworkCapture, but both
    # set self._last_raw_body. Read from the runtime.
    raw = getattr(rt, "_last_raw_body", b"") or b""
    if not raw:
        raise HTTPException(503, f"{provider}: no body captured")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = RAW_DIR / f"{provider}-{ts}.sse"
    path.write_bytes(raw)

    text = raw.decode("utf-8", errors="replace")
    events = [ln for ln in text.splitlines() if ln.startswith(("event:", "data:"))]

    summary = {
        "provider": provider,
        "prompt": prompt,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "protocol": _detect_protocol(raw),
        "bytes": len(raw),
        "lines": len(text.splitlines()),
        "event_lines": len(events),
        "preview": events[:6],
        "saved": str(path),
        "latency_ms": latency_ms,
    }
    with INDEX.open("a") as fh:
        fh.write(json.dumps(summary) + "\n")
    return summary


@router.post("/rawdump")
async def rawdump(body: RawIn, request: Request):
    if not _is_loopback(request):
        raise HTTPException(403, "internal route: loopback only")
    return await run_capture(body.provider, body.prompt)
