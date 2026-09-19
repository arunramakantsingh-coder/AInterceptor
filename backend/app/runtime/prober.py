"""Background health prober.

Every N seconds, for each provider, probe every available path with a
cheap request. Record latency + success/failure on the circuit breaker.
Store recent probe results for /health and CLI show.
"""
from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


# probes are cheap — a single-character prompt with 5s timeout
PROBE_PROMPT = "ping"
PROBE_TIMEOUT_S = 15.0


@dataclass
class ProbeResult:
    provider: str
    path: str
    ok: bool
    latency_ms: int
    ts: float
    error: str | None = None


@dataclass
class ProberStats:
    total_probes: int = 0
    failures: int = 0
    last_run_at: float = 0.0
    history: list[ProbeResult] = field(default_factory=list)   # last 200


class HealthProber:
    def __init__(
        self,
        circuits: Any,                     # CircuitRegistry
        providers: list[str],
        path_a_providers: list[str],
        path_b_providers: list[str],
        dispatcher_fn=None,                # async fn(provider, path) -> bool
        interval_s: float = 60.0,
        logger=None,
    ) -> None:
        self.circuits = circuits
        self.providers = providers
        self.path_a = set(path_a_providers)
        self.path_b = set(path_b_providers)
        self.dispatcher_fn = dispatcher_fn
        self.interval_s = interval_s
        self.log = logger or (lambda m: print(f"[prober] {m}", flush=True))
        self.stats = ProberStats()
        self._task: asyncio.Task | None = None
        self._stopping = False

    # ── one probe ─────────────────────────────────────────────────────

    async def probe_one(self, provider: str, path: str) -> ProbeResult:
        if self.dispatcher_fn is None:
            # no dispatcher — cannot actually probe
            return ProbeResult(provider, path, True, 0, time.time())
        t0 = time.monotonic()
        err = None
        ok = False
        try:
            ok = await asyncio.wait_for(
                self.dispatcher_fn(provider, path),
                timeout=PROBE_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            err = "timeout"
        except Exception as e:
            err = str(e)[:200]
        latency = int((time.monotonic() - t0) * 1000)
        return ProbeResult(provider, path, ok, latency, time.time(), err)

    # ── one full sweep ────────────────────────────────────────────────

    async def sweep(self) -> list[ProbeResult]:
        # Defense-in-depth: intersect with active providers
        try:
            from app.control_plane.state import get_state
            active = set(get_state().list_active())
            providers = [p for p in self.providers if p in active]
        except Exception:
            providers = list(self.providers)
        results: list[ProbeResult] = []
        for provider in providers:
            for path in ("A", "B"):
                if path == "A" and provider not in self.path_a:
                    continue
                if path == "B" and provider not in self.path_b:
                    continue
                r = await self.probe_one(provider, path)
                results.append(r)
                self.stats.total_probes += 1
                if not r.ok:
                    self.stats.failures += 1
                    self.circuits.get(provider, path).record_failure(r.latency_ms)
                else:
                    self.circuits.get(provider, path).record_success(r.latency_ms)
                self.log(f"{provider}:{path} {'ok' if r.ok else 'FAIL'} {r.latency_ms}ms"
                         + (f" ({r.error})" if r.error else ""))
        self.stats.last_run_at = time.time()
        self.stats.history.extend(results)
        self.stats.history = self.stats.history[-200:]
        return results

    # ── background loop ───────────────────────────────────────────────

    def start(self) -> None:
        if self._task:
            return
        self._task = asyncio.create_task(self._loop())
        self.log(f"background prober started (every {int(self.interval_s)}s)")

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _loop(self) -> None:
        await asyncio.sleep(10)      # let the daemon warm up first
        while not self._stopping:
            try:
                await self.sweep()
            except Exception as e:
                self.log(f"loop error: {e}")
            await asyncio.sleep(self.interval_s)

    # ── introspection ─────────────────────────────────────────────────

    def snapshot(self) -> dict:
        recent = self.stats.history[-20:]
        per_provider: dict[str, dict] = {}
        for provider in self.providers:
            per_provider[provider] = {}
            for path in ("A", "B"):
                circ = self.circuits.get(provider, path).to_dict()
                # latest probe for this provider x path
                last = next((r for r in reversed(self.stats.history)
                             if r.provider == provider and r.path == path), None)
                per_provider[provider][path] = {
                    **circ,
                    "last_probe_ms": last.latency_ms if last else None,
                    "last_probe_ok": last.ok if last else None,
                    "last_probe_age_s": int(time.time() - last.ts) if last else None,
                }
        return {
            "total_probes": self.stats.total_probes,
            "failures": self.stats.failures,
            "last_run_in_s": (int(time.time() - self.stats.last_run_at)
                              if self.stats.last_run_at else None),
            "providers": per_provider,
        }
