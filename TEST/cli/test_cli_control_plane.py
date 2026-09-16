from cli.registry import PROVIDER_ORDER
from cli.renderer import banner, global_help, provider_help, providers_status
from cli.shell import CLIState, CommandDispatcher


def test_banner_identifies_control_plane():
    text = banner()
    assert "A I N T E R C E P T O R" in text
    assert "Web AI Provider Control Plane" in text


def test_provider_number_navigation():
    state = CLIState()
    dispatcher = CommandDispatcher(state)
    result = dispatcher.dispatch("2")
    assert result == f"Context changed to {PROVIDER_ORDER[1]}"
    assert state.provider == "claude"


def test_global_and_provider_help_are_contextual():
    state = CLIState()
    dispatcher = CommandDispatcher(state)
    assert "use <provider>" in global_help()
    dispatcher.dispatch("use claude")
    assert "chat [prompt]" in provider_help()


def test_provider_status_is_rendered():
    text = providers_status()
    assert "[1] ChatGPT Web" in text
    assert "[2] Claude Web" in text
    assert "READY" in text
