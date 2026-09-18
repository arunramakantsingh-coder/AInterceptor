import asyncio
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
