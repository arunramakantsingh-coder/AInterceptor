"""Simple sliding-window rate limiter, per (provider, key)."""
from __future__ import annotations
import time
from collections import defaultdict, deque


DEFAULT_RPS = 0.5           # 1 request every 2 seconds
DEFAULT_BURST = 5           # allow up to N in a burst
DEFAULT_COOLDOWN_S = 60.0   # after 429, block for this long


class RateLimitExceeded(Exception):
    pass


class RateLimiter:
    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._cooldowns: dict[str, float] = {}
        self._rps: dict[str, float] = {}
        self._burst: dict[str, int] = {}

    def configure(self, provider: str, rps: float = DEFAULT_RPS,
                  burst: int = DEFAULT_BURST) -> None:
        self._rps[provider] = rps
        self._burst[provider] = burst

    def cooldown(self, provider: str, key: str = "default",
                 seconds: float = DEFAULT_COOLDOWN_S) -> None:
        self._cooldowns[f"{provider}:{key}"] = time.time() + seconds

    def _key(self, provider: str, key: str) -> str:
        return f"{provider}:{key}"

    def allows(self, provider: str, key: str = "default",
               now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        k = self._key(provider, key)

        if now < self._cooldowns.get(k, 0):
            return False

        rps = self._rps.get(provider, DEFAULT_RPS)
        burst = self._burst.get(provider, DEFAULT_BURST)
        window = self._windows[k]
        cutoff = now - 1.0
        while window and window[0] < cutoff:
            window.popleft()

        # burst: allow up to N in the last second
        if len(window) >= burst:
            return False
        # rps smoothing: space by 1/rps
        if window and (now - window[-1]) < (1.0 / rps):
            return False
        return True

    def record(self, provider: str, key: str = "default") -> None:
        self._windows[self._key(provider, key)].append(time.time())

    def retry_after_s(self, provider: str, key: str = "default") -> float:
        now = time.time()
        k = self._key(provider, key)
        cd = self._cooldowns.get(k, 0)
        if now < cd:
            return cd - now
        rps = self._rps.get(provider, DEFAULT_RPS)
        window = self._windows[k]
        if window and (now - window[-1]) < (1.0 / rps):
            return (1.0 / rps) - (now - window[-1])
        return 0.0

    def snapshot(self) -> dict:
        return {
            "cooldowns": {k: max(0, int(v - time.time()))
                          for k, v in self._cooldowns.items() if v > time.time()},
            "windows": {k: len(v) for k, v in self._windows.items()},
        }


_limiter: RateLimiter | None = None


def get_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter
