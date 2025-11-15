from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pytest

from simulator.core.engine.transition_engine import TransitionEngine
from simulator.core.objects.part import AttributeTarget
from simulator.core.registries import RegistryManager
from simulator.io.loaders.action_loader import load_actions
from simulator.io.loaders.object_loader import instantiate_default, load_object_types
from simulator.io.loaders.yaml_loader import load_spaces
from tests.utils.ground_truth import (
    apply_snapshot,
    attribute_value,
    capture_snapshot,
    extract_attribute,
    load_ground_truth,
    lookup_interaction_answer,
    mask_attributes,
    parse_attribute_from_question,
    tracked_attributes,
)

GROUND_TRUTH_DIR = Path(__file__).parent / "data" / "ground_truth"


def _ground_truth_files() -> Sequence[Path]:
    if not GROUND_TRUTH_DIR.exists():
        return []
    return sorted(GROUND_TRUTH_DIR.glob("*.yaml"))


def _prune(attr: dict | None) -> dict | None:
    if attr is None:
        return None
    keys = ("value", "trend", "last_known_value", "last_trend_direction")
    return {key: attr.get(key) for key in keys}


def _assert_tracked(
    actual_snapshot,
    expected_snapshot,
    refs: Sequence[str],
    *,
    hidden: set[str] | None = None,
    skip_hidden: bool = False,
) -> None:
    for ref in refs:
        if skip_hidden and hidden and ref in hidden:
            continue
        actual_attr = _prune(extract_attribute(actual_snapshot, ref))
        expected_attr = _prune(extract_attribute(expected_snapshot, ref))
        assert expected_attr is not None, f"Ground truth is missing attribute {ref}"
        assert actual_attr == expected_attr, f"Mismatch for attribute {ref}: {actual_attr} != {expected_attr}"


@pytest.fixture(scope="module")
def registry_manager() -> RegistryManager:
    rm = RegistryManager()
    rm.register_defaults()
    kb_root = Path.cwd() / "kb"
    load_spaces(str(kb_root / "spaces"), rm)
    load_object_types(str(kb_root / "objects"), rm)
    load_actions(str(kb_root / "actions"), rm)
    return rm


@pytest.mark.parametrize("history_path", _ground_truth_files(), ids=lambda p: p.stem)
def test_ground_truth_replay(history_path: Path, registry_manager: RegistryManager):
    history = load_ground_truth(history_path)
    rm = registry_manager
    obj_type = rm.objects.get(history.object_name)
    instance = instantiate_default(obj_type, rm)

    apply_snapshot(instance, history.initial_state)
    mask_attributes(instance, history.metadata.hidden_attributes)

    engine = TransitionEngine(rm)
    tracked_refs = tracked_attributes(history.metadata, history.final_state or history.initial_state)

    current = instance

    hidden_refs = set(history.metadata.hidden_attributes)

    for idx, step in enumerate(history.steps):
        before_snapshot, expected_after_snapshot = history.step_snapshots[idx]

        action = rm.create_behavior_enhanced_action(history.object_name, step.action_name)
        assert action is not None, f"Action {step.action_name} missing for {history.object_name}"
        parameters = dict(step.parameters)

        result = engine.apply_action(current, action, parameters)
        attempts = 0
        while result.status == "rejected" and getattr(result, "clarifications", None):
            attempts += 1
            asked_any = False
            for question in result.clarifications:
                if question.startswith("[INFO]"):
                    continue
                attr_ref = parse_attribute_from_question(question)
                if not attr_ref:
                    continue
                answer = attribute_value(before_snapshot, attr_ref)
                if answer is None:
                    answer = lookup_interaction_answer(history, idx, attr_ref)
                if answer is None:
                    continue
                try:
                    target = AttributeTarget.from_string(attr_ref).resolve(current)
                except Exception:
                    continue
                target.current_value = answer
                target.confidence = 1.0
                target.last_known_value = answer
                target.last_trend_direction = None
                asked_any = True
            if not asked_any or attempts > 10:
                break
            result = engine.apply_action(current, action, parameters)

        assert result.status == "ok", f"Action {step.action_name} failed: {result.reason}"
        assert result.after is not None
        current = result.after

        actual_after = capture_snapshot(current)
        _assert_tracked(actual_after, expected_after_snapshot, tracked_refs, hidden=hidden_refs, skip_hidden=True)

    final_snapshot = capture_snapshot(current)
    final_refs = sorted(set(tracked_refs) | hidden_refs)
    _assert_tracked(final_snapshot, history.final_state, final_refs, hidden=hidden_refs)
