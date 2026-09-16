from pathlib import Path

# ----------------------------------------------------------------------
# 1. Fix provider ordering: ChatGPT=1, Claude=2, Gemini=3, Grok=4
# ----------------------------------------------------------------------

p = Path("cli/registry.py")
text = p.read_text(encoding="utf-8")

old = '''    # Stable operator-facing order.
    preferred = {"claude": 1, "chatgpt": 2, "gemini": 3, "grok": 4}
    return sorted(providers, key=lambda p: preferred.get(p.name, 99))
'''

new = '''    # Stable operator-facing order.
    preferred = {"chatgpt": 1, "claude": 2, "gemini": 3, "grok": 4}
    return sorted(providers, key=lambda p: preferred.get(p.name, 99))
'''

if old not in text:
    raise SystemExit("registry.py expected ordering block not found")

p.write_text(text.replace(old, new), encoding="utf-8")


# ----------------------------------------------------------------------
# 2. Make PromptSession lazy.
#    Shell construction must work in unit-test/non-console environments.
# ----------------------------------------------------------------------

p = Path("cli/shell.py")
text = p.read_text(encoding="utf-8")

old = '''        self.session = PromptSession(
            history=FileHistory(
                os.path.join(history_dir, "cli-history")
            ),
            completer=AInterceptorCompleter(self),
            complete_while_typing=False,
        )
'''

new = '''        self._history_file = os.path.join(
            history_dir,
            "cli-history",
        )

        # Created only when run() actually owns an interactive terminal.
        # This keeps Shell unit-testable in pytest/CI/non-console contexts.
        self.session = None
'''

if old not in text:
    raise SystemExit("shell.py PromptSession initialization block not found")

text = text.replace(old, new)

old = '''    def run(self) -> None:
        banner()
'''

new = '''    def _create_prompt_session(self) -> PromptSession:
        return PromptSession(
            history=FileHistory(self._history_file),
            completer=AInterceptorCompleter(self),
            complete_while_typing=False,
        )

    def run(self) -> None:
        self.session = self._create_prompt_session()

        banner()
'''

if old not in text:
    raise SystemExit("shell.py run() insertion point not found")

text = text.replace(old, new)

p.write_text(text, encoding="utf-8")


# ----------------------------------------------------------------------
# 3. Update CLI tests to match requested operator numbering.
# ----------------------------------------------------------------------

p = Path("TEST/cli/test_cli_m0.py")
text = p.read_text(encoding="utf-8")

old = '''def test_provider_registry_order():
    providers = load_providers()
    assert [p.name for p in providers] == [
        "claude",
        "chatgpt",
        "gemini",
        "grok",
    ]
'''

new = '''def test_provider_registry_order():
    providers = load_providers()
    assert [p.name for p in providers] == [
        "chatgpt",
        "claude",
        "gemini",
        "grok",
    ]
'''

if old not in text:
    raise SystemExit("CLI provider-order test block not found")

old = '''def test_numeric_provider_selection():
    shell = Shell()
    assert shell.select_provider(1) is True
    assert shell.provider.name == "claude"
'''

new = '''def test_numeric_provider_selection():
    shell = Shell()

    assert shell.select_provider(1) is True
    assert shell.provider.name == "chatgpt"

    shell.provider = None

    assert shell.select_provider(2) is True
    assert shell.provider.name == "claude"
'''

if old not in text:
    raise SystemExit("CLI numeric-selection test block not found")

p.write_text(text, encoding="utf-8")


# ----------------------------------------------------------------------
# 4. Validate.
# ----------------------------------------------------------------------

print("Applied CLI M0.1 testability/provider-order fixes.")
