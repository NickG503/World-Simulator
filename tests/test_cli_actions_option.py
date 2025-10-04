from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from typer.testing import CliRunner

from simulator.cli.app import _expand_actions_args, app


def test_expand_actions_args_single_flag_multiple_values():
    raw = ["--obj", "flashlight", "--actions", "turn_on", "turn_off", "--name", "demo"]
    expanded = _expand_actions_args(raw)
    assert expanded == [
        "--obj",
        "flashlight",
        "--actions",
        "turn_on",
        "--actions",
        "turn_off",
        "--name",
        "demo",
    ]


def test_simulate_accepts_single_flag_multi_actions(monkeypatch, tmp_path):
    runner = CliRunner()

    fake_rm = object()
    monkeypatch.setattr("simulator.cli.app._load_registries", lambda *args, **kwargs: fake_rm)

    fake_history = SimpleNamespace(
        simulation_id="test-run",
        get_successful_steps=lambda: [],
        get_failed_steps=lambda: [],
    )

    class FakeRunner:
        saved_history_path: str | None = None

        @staticmethod
        def save_history_to_yaml(history, path: str) -> None:
            FakeRunner.saved_history_path = path
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("history", encoding="utf-8")

    fake_runner = FakeRunner()

    run_sim_mock = MagicMock(return_value=(fake_history, fake_runner))
    monkeypatch.setattr("simulator.cli.app.run_simulation", run_sim_mock)
    monkeypatch.setattr(
        "simulator.cli.app.resolve_history_path",
        lambda simulation_id: str(tmp_path / f"{simulation_id}.yaml"),
    )
    monkeypatch.setattr(
        "simulator.cli.app.resolve_result_path",
        lambda simulation_id: str(tmp_path / f"{simulation_id}.txt"),
    )
    monkeypatch.setattr("simulator.cli.app.build_interactive_dataset_text", lambda history: "dataset text")

    result = runner.invoke(
        app,
        ["simulate", "--obj", "flashlight", "--actions", "turn_on", "turn_off"],
    )

    assert result.exit_code == 0, result.stdout

    args = run_sim_mock.call_args.args
    assert args[0] is fake_rm
    assert args[1] == "flashlight"
    action_specs = args[2]
    assert [action["name"] for action in action_specs] == ["turn_on", "turn_off"]
    assert all(action["parameters"] == {} for action in action_specs)
    assert args[3] is None

    result_path = tmp_path / "test-run.txt"
    assert result_path.exists()
    assert result_path.read_text(encoding="utf-8") == "dataset text"


def test_simulate_reports_failed_actions(monkeypatch, tmp_path):
    runner = CliRunner()

    fake_rm = object()
    monkeypatch.setattr("simulator.cli.app._load_registries", lambda *args, **kwargs: fake_rm)

    failure_step = SimpleNamespace(
        action_name="adjust_volume",
        error_message="Precondition failed: screen.power should be off, but got on",
    )

    fake_history = SimpleNamespace(
        simulation_id="failed-run",
        get_successful_steps=lambda: [],
        get_failed_steps=lambda: [failure_step],
    )

    class FakeRunner:
        @staticmethod
        def save_history_to_yaml(history, path: str) -> None:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("history", encoding="utf-8")

    fake_runner = FakeRunner()

    run_sim_mock = MagicMock(return_value=(fake_history, fake_runner))
    monkeypatch.setattr("simulator.cli.app.run_simulation", run_sim_mock)
    monkeypatch.setattr(
        "simulator.cli.app.resolve_history_path",
        lambda simulation_id: str(tmp_path / f"{simulation_id}.yaml"),
    )
    monkeypatch.setattr(
        "simulator.cli.app.resolve_result_path",
        lambda simulation_id: str(tmp_path / f"{simulation_id}.txt"),
    )
    monkeypatch.setattr("simulator.cli.app.build_interactive_dataset_text", lambda history: "dataset text")

    result = runner.invoke(
        app,
        [
            "simulate",
            "--obj",
            "tv",
            "--actions",
            "adjust_volume",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "Failed actions detected" in result.stdout
    assert "adjust volume" in result.stdout
    assert "screen power should be off" in result.stdout
