from pathlib import Path


def test_default_history_path(tmp_path, monkeypatch):
    """Test default history path generation."""
    monkeypatch.chdir(tmp_path)
    from simulator.cli.paths import default_history_path, histories_dir

    result = default_history_path("sim123")

    assert Path(result).parent == histories_dir()
    assert Path(result).name == "sim123.yaml"


def test_resolve_history_path_simple(tmp_path, monkeypatch):
    """Test resolve history path with simple name."""
    monkeypatch.chdir(tmp_path)
    from simulator.cli.paths import histories_dir, resolve_history_path

    result = resolve_history_path("flashlight_cycle")
    assert Path(result) == histories_dir() / "flashlight_cycle.yaml"


def test_resolve_history_path_with_extension(tmp_path, monkeypatch):
    """Test resolve history path when name already has .yaml extension."""
    monkeypatch.chdir(tmp_path)
    from simulator.cli.paths import histories_dir, resolve_history_path

    result = resolve_history_path("flashlight_cycle.yaml")
    assert Path(result) == histories_dir() / "flashlight_cycle.yaml"


def test_resolve_history_path_nested(tmp_path, monkeypatch):
    """Test resolve history path extracts basename from nested path."""
    monkeypatch.chdir(tmp_path)
    from simulator.cli.paths import histories_dir, resolve_history_path

    result = resolve_history_path("custom/flashlight_cycle.yaml")
    assert Path(result) == histories_dir() / "flashlight_cycle.yaml"


def test_default_result_path(tmp_path, monkeypatch):
    """Test default result path generation."""
    monkeypatch.chdir(tmp_path)
    from simulator.cli.paths import default_result_path, results_dir

    result = default_result_path("sim123")

    assert Path(result).parent == results_dir()
    assert Path(result).name == "sim123.txt"


def test_resolve_result_path(tmp_path, monkeypatch):
    """Test resolve result path."""
    monkeypatch.chdir(tmp_path)
    from simulator.cli.paths import resolve_result_path, results_dir

    result = resolve_result_path("flashlight_run")
    assert Path(result) == results_dir() / "flashlight_run.txt"
