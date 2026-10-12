import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend" / "app"

(BE / "runtime" / "session_exporter.py").write_text('''"""Periodic storageState exporter.

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
''', encoding="utf-8", newline="\n")
print("  [OK] backend/app/runtime/session_exporter.py")

# ── unit tests (no real browser) ──
(ROOT / "tests" / "test_session_exporter.py").write_text('''import asyncio
import json
import os
import pathlib
import tempfile

os.environ.setdefault("MASTER_KEY", __import__("base64").b64encode(os.urandom(32)).decode())
os.environ.setdefault("JWT_SECRET", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from backend.app.runtime import session_exporter as se


class FakePage:
    def __init__(self, idb=None, fail=False):
        self._idb = idb or {}
        self._fail = fail
    async def evaluate(self, js):
        if self._fail:
            raise RuntimeError("evaluate failed")
        return self._idb
    def is_closed(self):
        return False


class FakeContext:
    def __init__(self, state=None, fail=False):
        self._state = state or {"cookies": [{"name": "a", "value": "b"}], "origins": []}
        self._fail = fail
    async def storage_state(self):
        if self._fail:
            raise RuntimeError("storage_state failed")
        return self._state


class FakeTab:
    def __init__(self, page):
        self.page = page


class FakeSupervisor:
    def __init__(self, context, tabs):
        class S: pass
        self.state = S()
        self.state.context = context
        self.state.tabs = tabs


def test_construction(tmp_path):
    e = se.SessionExporter(export_dir=tmp_path / "exports", interval_s=10, logger=lambda m: None)
    assert e.export_dir.exists()
    snap = e.snapshot()
    assert snap["exports"] == 0
    assert snap["providers"] == []


@pytest.mark.asyncio
async def test_export_one_success(tmp_path):
    e = se.SessionExporter(export_dir=tmp_path / "exports", logger=lambda m: None)
    ctx = FakeContext(state={"cookies": [{"name": "x", "value": "y"}], "origins": []})
    page = FakePage(idb={"db1": {"store1": [{"k": "v"}]}})
    ok = await e.export_one("claude", ctx, page)
    assert ok
    target = e.export_dir / "claude.json"
    assert target.exists()
    data = json.loads(target.read_text())
    assert data["cookies"][0]["name"] == "x"
    assert "_ainterceptor_idb" in data
    assert "db1" in data["_ainterceptor_idb"]


@pytest.mark.asyncio
async def test_export_one_storage_state_fails(tmp_path):
    e = se.SessionExporter(export_dir=tmp_path / "exports", logger=lambda m: None)
    ctx = FakeContext(fail=True)
    page = FakePage()
    ok = await e.export_one("claude", ctx, page)
    assert not ok
    assert e.stats.failures == 1
    assert e.stats.last_error is not None


@pytest.mark.asyncio
async def test_export_one_idb_fails_but_still_saves(tmp_path):
    e = se.SessionExporter(export_dir=tmp_path / "exports", logger=lambda m: None)
    ctx = FakeContext(state={"cookies": [{"name": "x", "value": "y"}], "origins": []})
    page = FakePage(fail=True)   # idb dump raises
    ok = await e.export_one("claude", ctx, page)
    # cookies-only export still succeeds
    assert ok
    target = e.export_dir / "claude.json"
    data = json.loads(target.read_text())
    assert data["cookies"][0]["name"] == "x"
    assert "_ainterceptor_idb" not in data


@pytest.mark.asyncio
async def test_export_all_iterates_tabs(tmp_path):
    e = se.SessionExporter(export_dir=tmp_path / "exports", logger=lambda m: None)
    ctx = FakeContext()
    tabs = {
        "claude":   FakeTab(FakePage()),
        "chatgpt":  FakeTab(FakePage()),
        "deepseek": FakeTab(FakePage()),
    }
    sup = FakeSupervisor(ctx, tabs)
    n = await e.export_all(sup)
    assert n == 3
    assert (e.export_dir / "claude.json").exists()
    assert (e.export_dir / "chatgpt.json").exists()
    assert (e.export_dir / "deepseek.json").exists()
    assert sorted(e.stats.providers) == ["chatgpt", "claude", "deepseek"]


def test_load_state(tmp_path):
    e = se.SessionExporter(export_dir=tmp_path / "exports", logger=lambda m: None)
    assert se.load_state(e.export_dir, "claude") is None
    (e.export_dir / "claude.json").write_text('{"cookies": [{"name": "a", "value": "b"}]}')
    st = se.load_state(e.export_dir, "claude")
    assert st is not None
    assert st["cookies"][0]["name"] == "a"


def test_list_exports(tmp_path):
    e = se.SessionExporter(export_dir=tmp_path / "exports", logger=lambda m: None)
    assert se.list_exports(e.export_dir) == []
    (e.export_dir / "claude.json").write_text("{}")
    (e.export_dir / "chatgpt.json").write_text("{}")
    (e.export_dir / "deepseek.json.tmp").write_text("{}")   # tmp ignored
    assert se.list_exports(e.export_dir) == ["chatgpt", "claude"]


def test_snapshot_shape(tmp_path):
    e = se.SessionExporter(export_dir=tmp_path / "exports", logger=lambda m: None)
    s = e.snapshot()
    assert set(s.keys()) == {"exports", "failures", "last_export_in_s", "providers", "last_error"}
''', encoding="utf-8", newline="\n")
print("  [OK] tests/test_session_exporter.py")

# ── syntax + tests ──
import ast
for f in ["backend/app/runtime/session_exporter.py", "tests/test_session_exporter.py"]:
    try: ast.parse((ROOT / f).read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[FAIL] {f}: {e}"); sys.exit(1)
print("  [OK] syntax valid")

PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable

print("\n==> running session exporter tests")
r = subprocess.run([str(PY), "-m", "pytest", "-q",
                    "tests/test_session_exporter.py", "-o", "asyncio_mode=auto"],
                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
print(r.stdout[-1500:] if r.stdout else "")
if r.stderr.strip(): print("STDERR:", r.stderr[-400:])
if r.returncode != 0:
    print("[FAIL] tests did not pass"); sys.exit(1)

# ── commit ──
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","feat(runtime): periodic session exporter (cookies + localStorage + IDB) (Step 4)"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("=" * 60)
print("STEP 4 COMPLETE — exporter + 8 unit tests")
print("=" * 60)
