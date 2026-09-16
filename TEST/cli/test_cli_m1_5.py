import asyncio

from app.interception.claude import ClaudeRuntime


def test_claude_runtime_uses_cdp_env_without_storage_state(monkeypatch):
    monkeypatch.setenv("AINTERCEPTOR_CLAUDE_CDP_URL", "http://127.0.0.1:9222")
    runtime = ClaudeRuntime()
    assert runtime.cdp_url == "http://127.0.0.1:9222"
    assert runtime.session_path is None


def test_claude_runtime_can_be_configured_for_storage_state():
    runtime = ClaudeRuntime(session_path="somewhere/storage_state.json")
    assert runtime.session_path == "somewhere/storage_state.json"
    assert runtime.cdp_url is None


def test_claude_runtime_close_does_not_require_owned_browser():
    runtime = ClaudeRuntime(cdp_url="http://127.0.0.1:9222")
    runtime._owns_browser = False
    runtime._owns_context = False
    asyncio.run(runtime.close())
