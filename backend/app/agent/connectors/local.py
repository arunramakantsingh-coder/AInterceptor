"""Local connector: filesystem + shell on the AInterceptor VM itself."""
from __future__ import annotations
import pathlib
import subprocess

MAX_BYTES = 200_000
MAX_GLOB = 500


class LocalConnector:
    def __init__(self, target):
        self.target = target

    # ── read ────────────────────────────────────────────────────
    def read(self, path: str) -> str:
        p = self._resolve(path)
        if not p.exists():
            return f"error: not found: {p}"
        if p.is_dir():
            # Return a directory listing instead of failing.
            items = sorted(p.iterdir())[:200]
            return "\n".join(str(x) + ("/" if x.is_dir() else "") for x in items)
        try:
            data = p.read_bytes()[:MAX_BYTES]
            truncated = " [truncated]" if p.stat().st_size > MAX_BYTES else ""
            return data.decode("utf-8", errors="replace") + truncated
        except Exception as e:
            return f"error reading {p}: {e}"

    # ── write ───────────────────────────────────────────────────
    def write(self, path: str, content: str) -> str:
        p = self._resolve(path)
        # Writes restricted to $HOME by default.
        home = pathlib.Path.home()
        if not str(p).startswith(str(home)):
            return f"error: writes outside $HOME are blocked by policy: {p}"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"wrote {len(content)} bytes to {p}"

    # ── glob ────────────────────────────────────────────────────
    def glob(self, pattern: str, root: str | None = None) -> list[str]:
        base = self._resolve(root or "~")
        if not base.exists() or not base.is_dir():
            return [f"error: not a directory: {base}"]
        try:
            hits = sorted(base.glob(pattern))[:MAX_GLOB]
        except Exception as e:
            return [f"error: {e}"]
        return [str(x) + ("/" if x.is_dir() else "") for x in hits]

    # ── shell ───────────────────────────────────────────────────
    def shell(self, cmd: str, timeout: int = 60) -> str:
        try:
            r = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=str(pathlib.Path.home()),
            )
        except subprocess.TimeoutExpired:
            return f"error: timeout after {timeout}s"
        except Exception as e:
            return f"error: {e}"
        out = r.stdout or ""
        if r.stderr:
            out += "\n[stderr]\n" + r.stderr
        if r.returncode != 0:
            out += f"\n[exit code: {r.returncode}]"
        return out[:MAX_BYTES] if out else "(no output)"

    # ── internals ───────────────────────────────────────────────
    def _resolve(self, path: str) -> pathlib.Path:
        p = pathlib.Path(path).expanduser()
        if not p.is_absolute():
            p = pathlib.Path.cwd() / p
        return p.resolve()
