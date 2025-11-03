from __future__ import annotations

from pathlib import Path

from simulator.core.dataset.sequential_dataset import build_interactive_dataset_text
from simulator.core.engine.transition_engine import DiffEntry
from simulator.core.registries import RegistryManager
from simulator.core.simulation_runner import (
    ObjectStateSnapshot,
    SimulationHistory,
    SimulationRunner,
    SimulationStep,
)


def _empty_snapshot(object_type: str) -> ObjectStateSnapshot:
    return ObjectStateSnapshot(type=object_type, parts={}, global_attributes={})


def _make_history(object_type: str, steps: list[SimulationStep]) -> SimulationHistory:
    return SimulationHistory(
        simulation_id="test-run",
        object_type=object_type,
        object_name=object_type,
        started_at="2025-10-04",
        total_steps=len(steps),
        steps=steps,
        initial_state=steps[0].object_state_before if steps else None,
        interactions=[
            {
                "step": steps[0].step_number + 1,
                "action": steps[0].action_name,
                "question": "What is battery.level?",
                "answer": "on",
            }
        ],
    )


def test_build_interactive_dataset_text_humanizes_actions_and_attributes():
    object_type = "flashlight"
    before = _empty_snapshot(object_type)
    after = _empty_snapshot(object_type)
    step = SimulationStep(
        step_number=0,
        action_name="turn_on",
        object_name=object_type,
        parameters={},
        status="rejected",
        error_message="Precondition failed: battery.level should not be empty, but got empty",
        object_state_before=before,
        object_state_after=after,
        changes=[],
    )

    history = _make_history(object_type, [step])
    text = build_interactive_dataset_text(history)

    assert "- turn on: FAILED — Precondition failed: battery level should not be empty, but got empty" in text
    assert '- step 1 (turn on): Q: "What is battery level?"' in text
    assert "battery.level" not in text


def test_history_yaml_omits_completed_at(tmp_path: Path):
    object_type = "flashlight"
    before = _empty_snapshot(object_type)
    after = _empty_snapshot(object_type)
    changes = [DiffEntry(attribute="battery.level", before="medium", after="empty", kind="value")]
    step = SimulationStep(
        step_number=0,
        action_name="drain_battery",
        object_name=object_type,
        parameters={},
        status="ok",
        error_message=None,
        object_state_before=before,
        object_state_after=after,
        changes=changes,
    )

    history = SimulationHistory(
        simulation_id="test-run",
        object_type=object_type,
        object_name=object_type,
        started_at="2025-10-04",
        total_steps=1,
        steps=[step],
        interactions=[],
    )

    runner = SimulationRunner(RegistryManager())
    file_path = tmp_path / "history.yaml"
    runner.save_history_to_yaml(history, str(file_path))

    content = file_path.read_text(encoding="utf-8")
    assert "started_at" in content
    assert "completed_at" not in content
    assert "history_version: 3" in content
    assert "initial_state:" in content
    assert "object_state_before" not in content
    assert "object_state_after" not in content


def test_load_history_v3_reconstructs_states(tmp_path: Path):
    yaml_content = """
history_version: 3
simulation_id: sample
object_type: tv
object_name: tv
started_at: '2025-10-01'
total_steps: 1
initial_state:
  type: tv
  parts:
    screen:
      attributes:
        power:
          value: 'off'
          trend: 'none'
          confidence: 1.0
  global_attributes: {}
steps:
  - step: 0
    action: turn_on
    status: ok
    changes:
      - attribute: screen.power
        before: 'off'
        after: 'on'
        kind: value
"""

    file_path = tmp_path / "history.yaml"
    file_path.write_text(yaml_content, encoding="utf-8")

    runner = SimulationRunner(RegistryManager())
    history = runner.load_history_from_yaml(str(file_path))

    assert history.initial_state is not None
    initial_screen = history.initial_state.parts["screen"].attributes["power"].value
    assert initial_screen == "off"

    state_after = history.get_state_at_step(0)
    assert state_after is not None
    assert state_after.parts["screen"].attributes["power"].value == "on"
