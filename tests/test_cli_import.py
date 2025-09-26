def test_cli_app_imports():
    from simulator.cli.app import app  # noqa: F401

    assert app is not None

