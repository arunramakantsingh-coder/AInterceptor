import os
os.environ.setdefault("MASTER_KEY", __import__("base64").b64encode(os.urandom(32)).decode())
os.environ.setdefault("JWT_SECRET", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from backend.app.runtime import path_b as pb


def test_provider_registry_has_all_four():
    for p in ("claude", "chatgpt", "gemini", "deepseek"):
        assert p in pb.PARSERS
        assert p in pb.RESPONSE_MARKERS
        assert p in pb.COMPOSER_SELECTORS


def test_response_markers_are_lists_of_strings():
    for p, markers in pb.RESPONSE_MARKERS.items():
        assert isinstance(markers, tuple)
        for m in markers:
            assert isinstance(m, str) and m


def test_cdp_capture_construction():
    class FakePage:
        context = None
    cap = pb.CDPCapture(FakePage(), ("foo", "bar"))
    assert cap.markers == ("foo", "bar")


def test_cdp_capture_request_filter():
    class FakePage:
        context = None
    cap = pb.CDPCapture(FakePage(), ("/api/v0/chat/completion",))

    # Irrelevant POST — ignored
    cap._on_request({
        "requestId": "r1",
        "request": {"method": "POST", "url": "https://example.com/other"},
    })
    assert "r1" not in cap._candidates

    # GET — ignored (even if URL matches)
    cap._on_request({
        "requestId": "r2",
        "request": {"method": "GET", "url": "https://chat.deepseek.com/api/v0/chat/completion"},
    })
    assert "r2" not in cap._candidates

    # Matching POST — captured
    cap._on_request({
        "requestId": "r3",
        "request": {"method": "POST", "url": "https://chat.deepseek.com/api/v0/chat/completion"},
    })
    assert "r3" in cap._candidates


def test_parser_adapter_is_monotone():
    a = pb.ParserAdapter()

    class Wrapped(pb.ParserAdapter):
        def _parse(self, raw):
            # simulate a parser that returns progressively longer text
            return raw.decode("utf-8", errors="replace")

    w = Wrapped()
    a_text = w.feed(b"hello")
    b_text = w.feed(b" world")
    c_text = w.feed(b"!")
    assert a_text == "hello"
    assert b_text == "hello world"
    assert c_text == "hello world!"


def test_parser_adapter_never_shrinks():
    class Shrinking(pb.ParserAdapter):
        def _parse(self, raw):
            return "x"        # always returns shorter than accumulated

    p = Shrinking()
    p.feed(b"hello world")     # first parse returns "x"
    p.feed(b"more data")
    # last text should stay at "x" (the maximum seen)
    assert p.current() == "x"


def test_parser_adapter_survives_parse_error():
    class Broken(pb.ParserAdapter):
        def _parse(self, raw):
            raise RuntimeError("boom")

    p = Broken()
    out = p.feed(b"hello")
    assert out == ""
    assert p.current() == ""


def test_claude_adapter_imports():
    a = pb.ClaudeAdapter()
    assert hasattr(a, "feed")


def test_submit_via_page_fetch_only_for_claude():
    import asyncio
    class FakePage:
        async def evaluate(self, js, prompt):
            return True
    # chatgpt returns False (not implemented for fetch)
    assert asyncio.run(pb._submit_via_page_fetch(FakePage(), "chatgpt", "hi")) is False
    # claude returns True when the page's evaluate succeeds
    assert asyncio.run(pb._submit_via_page_fetch(FakePage(), "claude", "hi")) is True


def test_find_composer_returns_none_when_empty():
    import asyncio
    class FakeLocator:
        async def count(self):
            return 0
    class FakePage:
        def locator(self, sel):
            return FakeLocator()
    assert asyncio.run(pb._find_composer(FakePage(), ("textarea",))) is None
