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
    assert "- step 1 (turn on): Q: \"What is battery level?\"" in text
    assert "battery.level" not in text


def test_history_yaml_omits_completed_at(tmp_path: Path):
    object_type = "flashlight"
    before = _empty_snapshot(object_type)
    after = _empty_snapshot(object_type)
    changes = [
        DiffEntry(attribute="battery.level", before="medium", after="empty", kind="value")
    ]
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
