from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from typer.testing import CliRunner

from simulator.cli.app import app


def _make_fake_rm(param_map: dict[str, dict[str, bool]] | None = None):
    param_map = param_map or {}

    def _find_action(obj_name: str, action_name: str):
        specs = param_map.get(action_name)
        if specs is None:
            return SimpleNamespace(parameters={})
        parameters = {}
        for name, spec in specs.items():
            if isinstance(spec, dict):
                parameters[name] = SimpleNamespace(**spec)
            else:
                parameters[name] = SimpleNamespace(required=spec)
        return SimpleNamespace(parameters=parameters)

    fake_rm = SimpleNamespace(find_action_for_object=_find_action)
    fake_rm._param_defs = {
        action: {
            name: (SimpleNamespace(**spec) if isinstance(spec, dict) else SimpleNamespace(required=spec))
            for name, spec in mapping.items()
        }
        for action, mapping in param_map.items()
    }
    return fake_rm


def _mock_cli_environment(monkeypatch, tmp_path: Path, fake_rm, history: SimpleNamespace | None = None):
    monkeypatch.setattr("simulator.cli.app._load_registries", lambda *args, **kwargs: fake_rm)

    if history is None:
        history = SimpleNamespace(
            simulation_id="test-run",
            get_successful_steps=lambda: [],
            get_failed_steps=lambda: [],
        )

    class FakeRunner:
        @staticmethod
        def save_history_to_yaml(history_obj, path: str) -> None:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("history", encoding="utf-8")

    fake_runner = FakeRunner()

    def _fake_run_simulation(*args, **kwargs):
        parameter_resolver = kwargs.get("parameter_resolver")
        actions = kwargs.get("actions")
        if actions is None and len(args) > 2:
            actions = args[2]
        if actions is None:
            actions = []
        if parameter_resolver:
            for spec in actions:
                action_name = spec.get("name")
                param_defs = getattr(fake_rm, "_param_defs", {}).get(action_name, {})
                for param_name, param_spec in param_defs.items():
                    if getattr(param_spec, "required", False) and param_name not in spec.get("parameters", {}):
                        value = parameter_resolver(action_name, param_name, param_spec)
                        spec.setdefault("parameters", {})[param_name] = value
        return history, fake_runner

    run_sim_mock = MagicMock(side_effect=_fake_run_simulation)
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

    return run_sim_mock


def test_simulate_accepts_actions_without_flag(monkeypatch, tmp_path):
    runner = CliRunner()

    fake_rm = _make_fake_rm()
    run_sim_mock = _mock_cli_environment(monkeypatch, tmp_path, fake_rm)

    result = runner.invoke(
        app,
        ["simulate", "--obj", "flashlight", "turn_on", "turn_off"],
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


def test_simulate_accepts_legacy_actions_flag(monkeypatch, tmp_path):
    runner = CliRunner()

    fake_rm = _make_fake_rm()
    run_sim_mock = _mock_cli_environment(monkeypatch, tmp_path, fake_rm)

    result = runner.invoke(
        app,
        ["simulate", "--obj", "flashlight", "--actions", "turn_on", "turn_off"],
    )

    assert result.exit_code == 0, result.stdout
    args = run_sim_mock.call_args.args
    assert args[3] is None
    action_specs = args[2]
    assert [action["name"] for action in action_specs] == ["turn_on", "turn_off"]


def test_simulate_prompts_for_missing_required_parameter(monkeypatch, tmp_path):
    runner = CliRunner()

    fake_rm = _make_fake_rm({"adjust_volume": {"to": {"required": True, "choices": ["mute", "low"]}}})
    run_sim_mock = _mock_cli_environment(monkeypatch, tmp_path, fake_rm)

    result = runner.invoke(
        app,
        ["simulate", "--obj", "tv", "adjust_volume"],
        input="2\n",
    )

    assert result.exit_code == 0, result.stdout
    action_specs = run_sim_mock.call_args.args[2]
    assert action_specs[0]["parameters"].get("to") == "low"


def test_simulate_inline_equals_assigns_parameter(monkeypatch, tmp_path):
    runner = CliRunner()

    fake_rm = _make_fake_rm(
        {
            "adjust_volume": {"to": True},
            "change_channel": {"to": True},
        }
    )
    run_sim_mock = _mock_cli_environment(monkeypatch, tmp_path, fake_rm)

    result = runner.invoke(
        app,
        [
            "simulate",
            "--obj",
            "tv",
            "turn_on",
            "adjust_volume=high",
            "change_channel=medium",
        ],
    )

    assert result.exit_code == 0, result.stdout

    action_specs = run_sim_mock.call_args.args[2]
    assert action_specs[1]["name"] == "adjust_volume"
    assert action_specs[1]["parameters"].get("to") == "high"
    assert action_specs[2]["name"] == "change_channel"
    assert action_specs[2]["parameters"].get("to") == "medium"


def test_simulate_honours_name_option_after_actions(monkeypatch, tmp_path):
    runner = CliRunner()

    fake_rm = _make_fake_rm()
    run_sim_mock = _mock_cli_environment(monkeypatch, tmp_path, fake_rm)

    result = runner.invoke(
        app,
        [
            "simulate",
            "--obj",
            "flashlight",
            "turn_on",
            "--name",
            "custom_run",
        ],
    )

    assert result.exit_code == 0, result.stdout
    args = run_sim_mock.call_args.args
    assert args[3] == "custom_run"


def test_simulate_rejects_params_option(monkeypatch, tmp_path):
    runner = CliRunner()

    fake_rm = _make_fake_rm()
    _mock_cli_environment(monkeypatch, tmp_path, fake_rm)

    result = runner.invoke(
        app,
        ["simulate", "--obj", "kettle", "pour_water", "--params", "to=medium"],
    )

    assert result.exit_code != 0
    # Check for "params" to avoid ANSI color code issues with "--params"
    assert "params" in result.output or "No such option" in result.output


def test_simulate_rejects_colon_syntax(monkeypatch, tmp_path):
    runner = CliRunner()

    fake_rm = _make_fake_rm()
    _mock_cli_environment(monkeypatch, tmp_path, fake_rm)

    result = runner.invoke(
        app,
        ["simulate", "--obj", "tv", "adjust_volume:to=high"],
    )

    assert result.exit_code != 0
    assert "Colon syntax" in result.output
