from cli.registry import load_providers


def test_provider_order():
    assert load_providers() == ["chatgpt", "claude", "gemini", "grok"]


def test_provider_selection_order_is_stable():
    providers = load_providers()
    assert providers[0] == "chatgpt"
    assert providers[1] == "claude"
    assert providers[2] == "gemini"
    assert providers[3] == "grok"
