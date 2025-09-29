from pathlib import Path


def test_resolve_history_path_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from simulator.cli.paths import default_history_path, resolve_history_path, histories_dir

    expected = default_history_path("sim123", "flashlight")
    resolved = resolve_history_path(None, "sim123", "flashlight")

    assert resolved == expected
    assert Path(resolved).parent == histories_dir()


def test_resolve_history_path_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from simulator.cli.paths import resolve_history_path, histories_dir

    result = resolve_history_path("flashlight_cycle.yaml", "sim123", "flashlight")
    assert Path(result) == histories_dir() / "flashlight_cycle.yaml"


def test_resolve_history_path_filename_nested_goes_to_histories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from simulator.cli.paths import resolve_history_path, histories_dir

    result = resolve_history_path("custom/flashlight_cycle.yaml", "sim123", "flashlight")
    assert Path(result) == histories_dir() / "flashlight_cycle.yaml"


def test_resolve_dataset_path_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from simulator.cli.paths import default_dataset_path, resolve_dataset_path, datasets_dir

    expected = default_dataset_path("sim123", "flashlight")
    resolved = resolve_dataset_path(None, "sim123", "flashlight")

    assert resolved == expected
    assert Path(resolved).parent == datasets_dir()


def test_resolve_dataset_path_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from simulator.cli.paths import resolve_dataset_path, datasets_dir

    result = resolve_dataset_path("flashlight_run.txt", "sim123", "flashlight")
    assert Path(result) == datasets_dir() / "flashlight_run.txt"


def test_resolve_dataset_path_nested(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from simulator.cli.paths import resolve_dataset_path

    result = resolve_dataset_path("custom/ds.txt", "sim123", "flashlight")
    assert Path(result) == Path("outputs/datasets/ds.txt")
