import os
os.environ.setdefault("MASTER_KEY", __import__("base64").b64encode(os.urandom(32)).decode())
os.environ.setdefault("JWT_SECRET", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pathlib
import pytest
from backend.app.runtime import browser_supervisor as bs


def test_provider_urls_present():
    assert "claude" in bs.PROVIDER_URLS
    assert "chatgpt" in bs.PROVIDER_URLS
    assert "gemini" in bs.PROVIDER_URLS
    assert "deepseek" in bs.PROVIDER_URLS
    assert len(bs.PROVIDER_URLS) == 10


def test_chrome_args_off_screen():
    args = bs._chrome_args(pathlib.Path("/tmp/p"), off_screen=True)
    assert any("--window-position=-32000,-32000" in a for a in args)
    assert any("--remote-allow-origins=*" in a for a in args)
    assert any("--disable-blink-features=AutomationControlled" in a for a in args)


def test_chrome_args_on_screen():
    args = bs._chrome_args(pathlib.Path("/tmp/p"), off_screen=False)
    assert any("--window-position=100,100" in a for a in args)


def test_supervisor_construction():
    s = bs.BrowserSupervisor(profile_dir=pathlib.Path("/tmp/test-profile"),
                             providers=["claude", "deepseek"])
    assert s.providers == ["claude", "deepseek"]
    assert s.state.ready is False
    snap = s.snapshot()
    assert snap["ready"] is False
    assert snap["tabs"] == []
    assert snap["alive"] is False


def test_supervisor_default_providers():
    s = bs.BrowserSupervisor(profile_dir=pathlib.Path("/tmp/test-profile"))
    assert len(s.providers) == 10
    assert "claude" in s.providers


@pytest.mark.asyncio
async def test_get_tab_unknown_provider():
    s = bs.BrowserSupervisor(profile_dir=pathlib.Path("/tmp/test-profile"))
    with pytest.raises(KeyError):
        await s.get_tab("does-not-exist")


def test_push_chrome_off_screen_noop_non_windows():
    import sys
    if not sys.platform.startswith("win"):
        assert bs.push_chrome_off_screen() == 0
    else:
        # On Windows it returns an int >= 0
        n = bs.push_chrome_off_screen()
        assert isinstance(n, int)
