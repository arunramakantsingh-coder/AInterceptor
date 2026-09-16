from pathlib import Path

p = Path(r"TEST\cli\test_cli_m0.py")
text = p.read_text(encoding="utf-8")

text = text.replace(
'''    assert [p.name for p in providers] == [
        "claude",
        "chatgpt",
        "gemini",
        "grok",
    ]''',
'''    assert [p.name for p in providers] == [
        "chatgpt",
        "claude",
        "gemini",
        "grok",
    ]'''
)

text = text.replace(
'''def test_numeric_provider_selection():
    shell = Shell()
    assert shell.select_provider(1) is True
    assert shell.provider.name == "claude"
''',
'''def test_numeric_provider_selection():
    shell = Shell()

    assert shell.select_provider(1) is True
    assert shell.provider.name == "chatgpt"

    shell.provider = None

    assert shell.select_provider(2) is True
    assert shell.provider.name == "claude"
'''
)

p.write_text(text, encoding="utf-8")
print("Updated CLI tests for requested provider numbering.")
