"""Periodic storageState exporter.

Playwright/Patchright storage_state() captures cookies + localStorage
but NOT IndexedDB. This module captures all three:
  1. cookies + localStorage via context.storage_state()
  2. IndexedDB per origin via page.evaluate() — same JS we use in the agent

Exports land in <export_dir>/<provider>.json every N seconds. The
persistent Chrome profile is the "hot" layer; these JSON files are the
"cold" backup that survives Chrome upgrades and profile corruption.
"""
from __future__ import annotations
import asyncio
import json
import pathlib
import time
from dataclasses import dataclass, field
from typing import Any


# ── IndexedDB dump (matches agent's logic) ────────────────────────────

IDB_DUMP_JS = r"""
async () => {
    if (!indexedDB.databases) return {};
    const dbs = await indexedDB.databases();
    const out = {};
    for (const info of dbs) {
        if (!info.name) continue;
        try {
            const db = await new Promise((resolve, reject) => {
                const req = indexedDB.open(info.name);
                req.onsuccess = () => resolve(req.result);
                req.onerror = () => reject(req.error);
            });
            const stores = Array.from(db.objectStoreNames);
            out[info.name] = {};
            for (const sn of stores) {
                try {
                    const tx = db.transaction(sn, 'readonly');
                    const store = tx.objectStore(sn);
                    const all = await new Promise((resolve, reject) => {
                        const req = store.getAll();
                        req.onsuccess = () => resolve(req.result);
                        req.onerror = () => reject(req.error);
                    });
                    out[info.name][sn] = all.map(v => {
                        try { return JSON.parse(JSON.stringify(v)); }
                        catch { return String(v); }
                    });
                } catch (e) { out[info.name][sn] = []; }
            }
            db.close();
        } catch (e) {}
    }
    return out;
}
""".strip()


@dataclass
class ExportStats:
    exports: int = 0
    failures: int = 0
    last_export_at: float = 0.0
    last_error: str | None = None
    providers: list[str] = field(default_factory=list)


class SessionExporter:
    """Dumps each tab's storage state (cookies + localStorage + IDB)."""

    def __init__(
        self,
        export_dir: pathlib.Path,
        interval_s: float = 300.0,
        logger=None,
    ) -> None:
        self.export_dir = pathlib.Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.interval_s = interval_s
        self.log = logger or (lambda msg: print(f"[exporter] {msg}", flush=True))
        self.stats = ExportStats()
        self._task: asyncio.Task | None = None
        self._stopping = False

    # ── one-shot export for a single tab ─────────────────────────────

    async def export_one(self, provider: str, context: Any, page: Any) -> bool:
        """Export one provider's state. Returns True on success."""
        try:
            state = await context.storage_state()
        except Exception as e:
            self.log(f"{provider}: storage_state failed: {e}")
            self.stats.failures += 1
            self.stats.last_error = str(e)
            return False

        # Add IndexedDB
        try:
            idb = await page.evaluate(IDB_DUMP_JS)
            if idb:
                state["_ainterceptor_idb"] = idb
        except Exception as e:
            self.log(f"{provider}: idb dump failed: {e}")
            # not fatal — cookies alone may be enough

        # Write atomically
        target = self.export_dir / f"{provider}.json"
        tmp = target.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
            tmp.replace(target)
        except Exception as e:
            self.log(f"{provider}: write failed: {e}")
            self.stats.failures += 1
            self.stats.last_error = str(e)
            return False

        self.stats.exports += 1
        self.stats.last_export_at = time.time()
        if provider not in self.stats.providers:
            self.stats.providers.append(provider)
        return True

    # ── export all tabs the supervisor owns ──────────────────────────

    async def export_all(self, supervisor: Any) -> int:
        """Iterate the supervisor's tabs and export each. Returns count."""
        ok = 0
        ctx = supervisor.state.context
        if ctx is None:
            return 0
        for provider, tab in list(supervisor.state.tabs.items()):
            if tab.page is None or tab.page.is_closed():
                continue
            if await self.export_one(provider, ctx, tab.page):
                ok += 1
        if ok:
            self.log(f"exported {ok} providers")
        return ok

    # ── background loop ──────────────────────────────────────────────

    def start(self, supervisor: Any) -> None:
        if self._task:
            return
        self._task = asyncio.create_task(self._loop(supervisor))
        self.log(f"background exporter started (every {int(self.interval_s)}s)")

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _loop(self, supervisor: Any) -> None:
        # first export happens quickly
        await asyncio.sleep(5)
        while not self._stopping:
            try:
                await self.export_all(supervisor)
            except Exception as e:
                self.log(f"loop error: {e}")
            await asyncio.sleep(self.interval_s)

    # ── introspection ────────────────────────────────────────────────

    def snapshot(self) -> dict:
        return {
            "exports": self.stats.exports,
            "failures": self.stats.failures,
            "last_export_in_s": int(time.time() - self.stats.last_export_at) if self.stats.last_export_at else None,
            "providers": list(self.stats.providers),
            "last_error": self.stats.last_error,
        }


# ── restore helper ────────────────────────────────────────────────────

def load_state(export_dir: pathlib.Path, provider: str) -> dict | None:
    """Load a previously exported storage state for a provider."""
    p = pathlib.Path(export_dir) / f"{provider}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_exports(export_dir: pathlib.Path) -> list[str]:
    """List all provider names that have an exported state file."""
    d = pathlib.Path(export_dir)
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json") if not p.name.endswith(".tmp"))
