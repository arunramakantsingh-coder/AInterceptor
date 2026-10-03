def test_cli_package_importable():
    from cli.registry import load_providers

    assert load_providers()[1] == "claude"
