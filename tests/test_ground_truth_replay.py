from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

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
    clarification_info: dict[str, int] | None = None,
    current_step: int | None = None,
) -> None:
    for ref in refs:
        if skip_hidden and hidden and ref in hidden:
            continue
        actual_attr = _prune(extract_attribute(actual_snapshot, ref))
        expected_attr = _prune(extract_attribute(expected_snapshot, ref))
        assert expected_attr is not None, f"Ground truth is missing attribute {ref}"

        # Enhanced error message with clarification context
        if actual_attr != expected_attr:
            error_msg = f"Mismatch for attribute {ref}: {actual_attr} != {expected_attr}"
            if clarification_info and ref in clarification_info:
                clarified_step = clarification_info[ref]
                error_msg += f"\n  (Note: '{ref}' was clarified at step {clarified_step}"
                if current_step is not None:
                    if current_step == clarified_step:
                        error_msg += ", mismatch emerged immediately upon clarification)"
                    else:
                        error_msg += f", mismatch detected {current_step - clarified_step} step(s) later)"
                else:
                    error_msg += ")"
            assert False, error_msg


@pytest.fixture(scope="module")
def registry_manager() -> RegistryManager:
    rm = RegistryManager()
    rm.register_defaults()
    kb_root = Path.cwd() / "kb"
    load_spaces(str(kb_root / "spaces"), rm)
    load_object_types(str(kb_root / "objects"), rm)
    load_actions(str(kb_root / "actions"), rm)
    return rm


def _apply_pre_step_interaction_answers(
    current,
    interaction_answers: dict,
    step_idx: int,
    hidden_refs: set[str],
    clarified_hidden: set[str],
    ever_clarified: set[str],
    clarified_at_step: dict[str, int],
    clarified_values: dict[str, Any],
) -> None:
    """Pre-apply interaction answers for this step to match ground truth."""
    for attr_ref, answer in interaction_answers.get(step_idx, []):
        try:
            target = AttributeTarget.from_string(attr_ref).resolve(current)
            target.current_value = answer
            target.last_known_value = answer
            target.last_trend_direction = None
            if attr_ref in hidden_refs and attr_ref not in clarified_hidden:
                clarified_hidden.add(attr_ref)
                ever_clarified.add(attr_ref)
                clarified_at_step[attr_ref] = step_idx
                clarified_values[attr_ref] = answer
        except Exception:
            continue


def _handle_clarification_loop(
    engine,
    current,
    action,
    parameters: dict,
    before_snapshot: dict,
    history,
    step_idx: int,
    step_action_name: str,
    hidden_refs: set[str],
    clarified_hidden: set[str],
    ever_clarified: set[str],
    actually_asked: set[str],
    clarified_at_step: dict[str, int],
    clarified_values: dict[str, Any],
):
    """Execute action with clarification loop, answering questions from ground truth."""
    result = engine.apply_action(current, action, parameters)
    attempts = 0
    asked_any = False

    while result.status == "rejected" and getattr(result, "clarifications", None):
        attempts += 1
        asked_any = False
        for question in result.clarifications:
            if question.startswith("[INFO]"):
                continue
            attr_ref = parse_attribute_from_question(question)
            if not attr_ref:
                continue

            # Track asked attributes
            actually_asked.add(attr_ref)

            # Warn if non-hidden attribute asked
            if attr_ref not in hidden_refs:
                import warnings

                warnings.warn(
                    f"Step {step_idx} ({step_action_name}): Simulator asked about '{attr_ref}' "
                    f"which is NOT marked in hidden_attributes. Either add it to metadata "
                    f"or check why the simulator needs it.",
                    UserWarning,
                )

            answer = attribute_value(before_snapshot, attr_ref)
            if answer is None:
                answer = lookup_interaction_answer(history, step_idx, attr_ref)
            if answer is None:
                continue
            try:
                target = AttributeTarget.from_string(attr_ref).resolve(current)
            except Exception:
                continue
            target.current_value = answer
            target.last_known_value = answer
            target.last_trend_direction = None
            asked_any = True
            if attr_ref in hidden_refs and attr_ref not in clarified_hidden:
                clarified_hidden.add(attr_ref)
                ever_clarified.add(attr_ref)
                clarified_at_step[attr_ref] = step_idx
                clarified_values[attr_ref] = answer
        if not asked_any or attempts > 10:
            break
        result = engine.apply_action(current, action, parameters)

    return result


def _enforce_hidden_attributes_stay_unknown(
    actual_after: dict,
    step_idx: int,
    step_action_name: str,
    step_changes: list,
    hidden_refs: set[str],
    clarified_hidden: set[str],
    ever_clarified: set[str],
    clarified_at_step: dict[str, int],
    clarified_values: dict[str, Any],
) -> None:
    """Enforce hidden attributes stay 'unknown' until clarified (unless action sets them)."""
    expected_changes = {change.get("attribute") for change in step_changes if change.get("kind") == "value"}

    for attr_ref in hidden_refs - clarified_hidden:
        attr_value = attribute_value(actual_after, attr_ref)
        if attr_value is not None and attr_value != "unknown":
            # Check if action explicitly sets this
            if attr_ref in expected_changes:
                # Action sets it - treat as clarified
                clarified_hidden.add(attr_ref)
                ever_clarified.add(attr_ref)
                clarified_at_step[attr_ref] = step_idx
                clarified_values[attr_ref] = attr_value
            else:
                # Unexpected mutation of hidden attribute!
                raise AssertionError(
                    f"Step {step_idx} ({step_action_name}): Hidden attribute '{attr_ref}' "
                    f"changed to '{attr_value}' before being clarified. "
                    f"Hidden attributes must stay 'unknown' until explicitly asked "
                    f"or set by an action. This attribute was not in the action's "
                    f"expected changes: {expected_changes}"
                )


def _enforce_clarified_attributes_tracked(
    actual_after: dict,
    expected_after: dict,
    before_snapshot: dict,
    step_idx: int,
    step_action_name: str,
    clarified_hidden: set[str],
    clarified_at_step: dict[str, int],
    clarified_values: dict[str, Any],
) -> None:
    """Enforce once clarified, attributes stay tracked (allow 'unknown' only if trend is up/down)."""
    for attr_ref in clarified_hidden:
        attr_value = attribute_value(actual_after, attr_ref)
        expected_value = attribute_value(expected_after, attr_ref)

        if attr_value in (None, "unknown"):
            clarified_step = clarified_at_step.get(attr_ref, "?")
            original_value = clarified_values.get(attr_ref, "?")

            # Check if trend explains "unknown"
            before_value = attribute_value(before_snapshot, attr_ref)
            attr_snapshot_after = extract_attribute(expected_after, attr_ref)
            attr_snapshot_before = extract_attribute(before_snapshot, attr_ref)
            current_trend = attr_snapshot_after.get("trend") if attr_snapshot_after else None
            previous_trend = attr_snapshot_before.get("trend") if attr_snapshot_before else None

            # Trend up/down explains unknown
            if current_trend in ("up", "down") or (
                previous_trend in ("up", "down") and before_value in (None, "unknown")
            ):
                # Verify ground truth also expects unknown
                if expected_value not in (None, "unknown"):
                    raise AssertionError(
                        f"Step {step_idx} ({step_action_name}): '{attr_ref}' is 'unknown' due to "
                        f"trend (current='{current_trend}', previous='{previous_trend}'), "
                        f"but ground truth expects '{expected_value}'. Ground truth should show 'unknown'."
                    )
                # Keep tracking
                continue

            # Unexpected reversion
            if expected_value in (None, "unknown"):
                # Both unknown without trend
                raise AssertionError(
                    f"Step {step_idx} ({step_action_name}): Clarified attribute '{attr_ref}' "
                    f"is 'unknown' (was '{original_value}' at step {clarified_step}) "
                    f"without trend explanation (current='{current_trend}', previous='{previous_trend}'). "
                    f"This suggests a simulator bug that resets hidden attributes."
                )
            else:
                # Actual unknown, expected not
                raise AssertionError(
                    f"Step {step_idx} ({step_action_name}): Clarified attribute '{attr_ref}' "
                    f"is 'unknown' (was '{original_value}' at step {clarified_step}), "
                    f"but ground truth expects '{expected_value}'. Trend: current='{current_trend}', "
                    f"previous='{previous_trend}'. This suggests a simulator bug."
                )


def _validate_metadata_consistency(
    hidden_refs: set[str],
    actually_asked: set[str],
    clarified_hidden: set[str],
    ever_clarified: set[str],
    history,
) -> None:
    """Validate metadata matches simulator behavior (warns if hidden attrs never asked)."""
    import warnings

    # Warn: hidden attrs never asked
    never_asked = hidden_refs - actually_asked - clarified_hidden
    if never_asked:
        warnings.warn(
            f"The following attributes are marked as hidden but were never asked about "
            f"by the simulator: {sorted(never_asked)}. Either they're incorrectly marked "
            f"as hidden, or the simulator doesn't need them anymore.",
            UserWarning,
        )

    # Error: interaction answers never used
    for attr_ref in hidden_refs:
        expected_answers = [
            (step_idx, answer)
            for step_idx, answers in history.interaction_answers.items()
            for ref, answer in answers
            if ref == attr_ref
        ]
        if expected_answers and attr_ref not in ever_clarified:
            steps_with_answers = [step_idx for step_idx, _ in expected_answers]
            raise AssertionError(
                f"Attribute '{attr_ref}' has interaction answers at step(s) {steps_with_answers} "
                f"but was never clarified during replay. This suggests the simulator didn't "
                f"ask about it when expected, or the answers weren't applied correctly."
            )


@pytest.mark.parametrize("history_path", _ground_truth_files(), ids=lambda p: p.stem)
def test_ground_truth_replay(history_path: Path, registry_manager: RegistryManager):
    """Replay ground truth history and validate all state changes, hidden attribute handling, and metadata."""
    # Initialize
    history = load_ground_truth(history_path)
    rm = registry_manager
    obj_type = rm.objects.get(history.object_name)
    instance = instantiate_default(obj_type, rm)

    apply_snapshot(instance, history.initial_state)
    mask_attributes(instance, history.metadata.hidden_attributes)

    engine = TransitionEngine(rm)
    tracked_refs = set(tracked_attributes(history.metadata, history.final_state or history.initial_state))

    current = instance

    # Tracking state
    hidden_refs = set(history.metadata.hidden_attributes)
    clarified_hidden: set[str] = set()
    clarified_at_step: dict[str, int] = {}
    clarified_values: dict[str, Any] = {}
    actually_asked: set[str] = set()
    ever_clarified: set[str] = set()

    # Replay steps
    for idx, step in enumerate(history.steps):
        before_snapshot, expected_after_snapshot = history.step_snapshots[idx]

        # Pre-step: apply interaction answers
        _apply_pre_step_interaction_answers(
            current,
            history.interaction_answers,
            idx,
            hidden_refs,
            clarified_hidden,
            ever_clarified,
            clarified_at_step,
            clarified_values,
        )

        # Execute action with clarifications
        action = rm.create_behavior_enhanced_action(history.object_name, step.action_name)
        assert action is not None, f"Action {step.action_name} missing for {history.object_name}"
        parameters = dict(step.parameters)

        result = _handle_clarification_loop(
            engine,
            current,
            action,
            parameters,
            before_snapshot,
            history,
            idx,
            step.action_name,
            hidden_refs,
            clarified_hidden,
            ever_clarified,
            actually_asked,
            clarified_at_step,
            clarified_values,
        )

        # Update state
        assert result.status == "ok", f"Action {step.action_name} failed: {result.reason}"
        assert result.after is not None
        current = result.after

        # Post-action: enforce constraints
        actual_after = capture_snapshot(current)

        _enforce_hidden_attributes_stay_unknown(
            actual_after,
            idx,
            step.action_name,
            step.changes,
            hidden_refs,
            clarified_hidden,
            ever_clarified,
            clarified_at_step,
            clarified_values,
        )

        _enforce_clarified_attributes_tracked(
            actual_after,
            expected_after_snapshot,
            before_snapshot,
            idx,
            step.action_name,
            clarified_hidden,
            clarified_at_step,
            clarified_values,
        )

        # Verify step expectations
        active_hidden = hidden_refs - clarified_hidden
        tracked_and_clarified = sorted(tracked_refs | clarified_hidden)
        _assert_tracked(
            actual_after,
            expected_after_snapshot,
            tracked_and_clarified,
            hidden=active_hidden,
            skip_hidden=True,
            clarification_info=clarified_at_step,
            current_step=idx,
        )

    # Validate metadata
    _validate_metadata_consistency(
        hidden_refs,
        actually_asked,
        clarified_hidden,
        ever_clarified,
        history,
    )

    # Verify final state
    final_snapshot = capture_snapshot(current)
    active_hidden = hidden_refs - clarified_hidden
    final_refs = sorted(tracked_refs | hidden_refs)
    _assert_tracked(
        final_snapshot,
        history.final_state,
        final_refs,
        hidden=active_hidden,
        clarification_info=clarified_at_step,
        current_step=None,
    )
