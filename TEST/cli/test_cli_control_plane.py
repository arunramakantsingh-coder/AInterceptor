from cli.nos import Mode, NOSState, model_definitions
from cli.registry import PROVIDER_ORDER
from cli.renderer import banner, help_view, model_help, providers_status
from cli.shell import AIRouterShell


def test_airouter_banner_identifies_nos():
    text = banner()
    assert "A I R O U T E R" in text
    assert "AI ROUTER OPERATING SYSTEM" in text


def test_provider_registry_includes_deepseek():
    assert PROVIDER_ORDER == ("chatgpt", "claude", "gemini", "deepseek")


def test_shell_starts_in_boot_mode():
    shell = AIRouterShell()
    assert shell.state.mode == Mode.BOOT
    shell.dispatch("airouter")
    assert shell.state.mode == Mode.USER_EXEC


def test_bootai_keeps_console_in_boot_mode():
    shell = AIRouterShell()
    shell.dispatch("bootai")
    assert shell.state.mode == Mode.BOOT


def test_exec_mode_transitions_with_unique_abbreviations():
    shell = AIRouterShell()
    shell.state = NOSState(mode=Mode.USER_EXEC)
    shell._set_mode(Mode.USER_EXEC)
    shell.dispatch("en")
    assert shell.state.mode == Mode.PRIVILEGED_EXEC
    shell.dispatch("conf t")
    assert shell.state.mode == Mode.CONFIG
    shell.dispatch("ai")
    assert shell.state.mode == Mode.CONFIG_AI
    shell.dispatch("prov cl")
    assert shell.state.mode == Mode.CONFIG_AI_PROVIDER
    assert shell.state.provider == "claude"


def test_show_command_accepts_abbreviation():
    shell = AIRouterShell()
    shell.state = NOSState(mode=Mode.USER_EXEC)
    shell._set_mode(Mode.USER_EXEC)
    shell.dispatch("show v")


def test_show_run_renders_running_configuration():
    shell = AIRouterShell()
    shell.state = NOSState(mode=Mode.PRIVILEGED_EXEC)
    shell._set_mode(Mode.PRIVILEGED_EXEC)
    shell.state.selected_model = "claude-opus-4-8"
    shell.state.config["providers"] = {"claude": True, "chatgpt": False}
    output = shell._show(["run"])
    assert "model claude-opus-4-8" in output
    assert "provider claude" in output
    assert "enable" in output
    assert "provider chatgpt" in output
    assert "disable" in output


def test_model_catalog_is_available_to_context_help():
    assert model_definitions()
    assert "claude-opus-4-8" in model_help("claude")
    assert "gemini-3.6-flash" in model_help("gemini")
    assert "deepseek-flash" in model_help("deepseek")


def test_provider_runtime_modules_import():
    from app.interception.chatgpt import ChatGPTRuntime
    from app.interception.deepseek import DeepSeekRuntime
    from app.interception.gemini import GeminiRuntime

    assert ChatGPTRuntime().provider == "chatgpt"
    assert GeminiRuntime().provider == "gemini"
    assert DeepSeekRuntime().provider == "deepseek"


def test_help_is_mode_specific():
    assert "enable" in help_view("user-exec")
    assert "configure terminal" in help_view("privileged-exec")
    assert "provider <name>" in help_view("config-ai")


def test_provider_status_is_rendered():
    text = providers_status()
    assert "[1] ChatGPT Web" in text
    assert "[2] Claude Web" in text
    assert "RUNTIME AVAILABLE" in text
