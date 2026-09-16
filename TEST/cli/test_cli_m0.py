from cli.registry import load_providers
from cli.shell import Shell


def test_provider_registry_order():
    providers = load_providers()
    assert [p.name for p in providers] == [
        "chatgpt",
        "claude",
        "gemini",
        "grok",
    ]


def test_claude_is_configured():
    claude = next(p for p in load_providers() if p.name == "claude")
    assert claude.configured is True


def test_numeric_provider_selection():
    shell = Shell()

    assert shell.select_provider(1) is True
    assert shell.provider.name == "chatgpt"

    shell.provider = None

    assert shell.select_provider(2) is True
    assert shell.provider.name == "claude"


def test_partial_command_resolution():
    shell = Shell()

    assert shell.resolve_command(
        "prov",
        ["help", "providers", "status"],
    ) == "providers"

    assert shell.resolve_command(
        "sta",
        ["help", "providers", "status"],
    ) == "status"
