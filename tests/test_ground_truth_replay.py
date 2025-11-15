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


@pytest.mark.parametrize("history_path", _ground_truth_files(), ids=lambda p: p.stem)
def test_ground_truth_replay(history_path: Path, registry_manager: RegistryManager):
    history = load_ground_truth(history_path)
    rm = registry_manager
    obj_type = rm.objects.get(history.object_name)
    instance = instantiate_default(obj_type, rm)

    apply_snapshot(instance, history.initial_state)
    mask_attributes(instance, history.metadata.hidden_attributes)

    engine = TransitionEngine(rm)
    tracked_refs = set(tracked_attributes(history.metadata, history.final_state or history.initial_state))

    current = instance

    hidden_refs = set(history.metadata.hidden_attributes)
    clarified_hidden: set[str] = set()

    # Enhanced tracking for better diagnostics and validation
    clarified_at_step: dict[str, int] = {}  # attr_ref -> step index when clarified
    clarified_values: dict[str, Any] = {}  # attr_ref -> value when first clarified
    actually_asked: set[str] = set()  # attrs simulator actually asked about
    ever_clarified: set[str] = set()  # attrs that were clarified at any point (even if later unclarified)

    for idx, step in enumerate(history.steps):
        before_snapshot, expected_after_snapshot = history.step_snapshots[idx]

        # Apply any interaction answers for this step to the instance
        # This ensures the instance state matches ground truth expectations even if not explicitly asked
        for attr_ref, answer in history.interaction_answers.get(idx, []):
            try:
                target = AttributeTarget.from_string(attr_ref).resolve(current)
                target.current_value = answer
                target.last_known_value = answer
                target.last_trend_direction = None
                if attr_ref in hidden_refs and attr_ref not in clarified_hidden:
                    clarified_hidden.add(attr_ref)
                    ever_clarified.add(attr_ref)
                    clarified_at_step[attr_ref] = idx
                    clarified_values[attr_ref] = answer
            except Exception:
                continue

        action = rm.create_behavior_enhanced_action(history.object_name, step.action_name)
        assert action is not None, f"Action {step.action_name} missing for {history.object_name}"
        parameters = dict(step.parameters)

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

                # Track that simulator actually asked about this attribute
                actually_asked.add(attr_ref)

                # Validate: warn if simulator asks about non-hidden attribute
                if attr_ref not in hidden_refs:
                    import warnings

                    warnings.warn(
                        f"Step {idx} ({step.action_name}): Simulator asked about '{attr_ref}' "
                        f"which is NOT marked in hidden_attributes. Either add it to metadata "
                        f"or check why the simulator needs it.",
                        UserWarning,
                    )

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
                target.last_known_value = answer
                target.last_trend_direction = None
                asked_any = True
                if attr_ref in hidden_refs and attr_ref not in clarified_hidden:
                    clarified_hidden.add(attr_ref)
                    ever_clarified.add(attr_ref)
                    clarified_at_step[attr_ref] = idx
                    clarified_values[attr_ref] = answer
            if not asked_any or attempts > 10:
                break
            result = engine.apply_action(current, action, parameters)

        assert result.status == "ok", f"Action {step.action_name} failed: {result.reason}"
        assert result.after is not None
        current = result.after

        actual_after = capture_snapshot(current)

        # ENFORCEMENT 1: Hidden attributes MUST stay "unknown" until clarified
        # UNLESS the action explicitly sets them (which counts as revealing the value)
        # This catches pre-clarification drift where actions mutate hidden attrs unexpectedly
        expected_changes = {change.get("attribute") for change in step.changes if change.get("kind") == "value"}

        for attr_ref in hidden_refs - clarified_hidden:
            attr_value = attribute_value(actual_after, attr_ref)
            if attr_value is not None and attr_value != "unknown":
                # Check if this change was expected (action sets this attribute)
                if attr_ref in expected_changes:
                    # Action legitimately sets this hidden attribute - treat as clarified
                    clarified_hidden.add(attr_ref)
                    ever_clarified.add(attr_ref)
                    clarified_at_step[attr_ref] = idx
                    clarified_values[attr_ref] = attr_value
                else:
                    # Unexpected mutation of hidden attribute!
                    raise AssertionError(
                        f"Step {idx} ({step.action_name}): Hidden attribute '{attr_ref}' "
                        f"changed to '{attr_value}' before being clarified. "
                        f"Hidden attributes must stay 'unknown' until explicitly asked "
                        f"or set by an action. This attribute was not in the action's "
                        f"expected changes: {expected_changes}"
                    )

        # ENFORCEMENT 2: Once clarified, ALWAYS track (even if value becomes "unknown")
        # EXCEPTION: If trend is/was up/down, value being "unknown" is expected until re-clarified
        # This catches accidental resets or re-masking bugs
        for attr_ref in clarified_hidden:
            attr_value = attribute_value(actual_after, attr_ref)
            expected_value = attribute_value(expected_after_snapshot, attr_ref)

            if attr_value in (None, "unknown"):
                clarified_step = clarified_at_step.get(attr_ref, "?")
                original_value = clarified_values.get(attr_ref, "?")

                # Check if there's a trend (current or previous) that explains the "unknown" value
                before_value = attribute_value(before_snapshot, attr_ref)
                attr_snapshot_after = extract_attribute(expected_after_snapshot, attr_ref)
                attr_snapshot_before = extract_attribute(before_snapshot, attr_ref)
                current_trend = attr_snapshot_after.get("trend") if attr_snapshot_after else None
                previous_trend = attr_snapshot_before.get("trend") if attr_snapshot_before else None

                # If trend is currently up/down, OR was up/down and value was already unknown
                if current_trend in ("up", "down") or (
                    previous_trend in ("up", "down") and before_value in (None, "unknown")
                ):
                    # Trend explains the "unknown" value - verify ground truth matches
                    if expected_value not in (None, "unknown"):
                        raise AssertionError(
                            f"Step {idx} ({step.action_name}): '{attr_ref}' is 'unknown' due to "
                            f"trend (current='{current_trend}', previous='{previous_trend}'), "
                            f"but ground truth expects '{expected_value}'. Ground truth should show 'unknown'."
                        )
                    # Continue tracking - attribute stays in clarified_hidden!
                    continue

                # No trend excuse - this is an unexpected reversion
                if expected_value in (None, "unknown"):
                    # Both actual and expected are unknown (no trend explanation)
                    raise AssertionError(
                        f"Step {idx} ({step.action_name}): Clarified attribute '{attr_ref}' "
                        f"is 'unknown' (was '{original_value}' at step {clarified_step}) "
                        f"without trend explanation (current='{current_trend}', previous='{previous_trend}'). "
                        f"This suggests a simulator bug that resets hidden attributes."
                    )
                else:
                    # Actual is unknown but expected is not (no trend explanation)
                    raise AssertionError(
                        f"Step {idx} ({step.action_name}): Clarified attribute '{attr_ref}' "
                        f"is 'unknown' (was '{original_value}' at step {clarified_step}), "
                        f"but ground truth expects '{expected_value}'. Trend: current='{current_trend}', "
                        f"previous='{previous_trend}'. This suggests a simulator bug."
                    )

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

    # VALIDATION: Check for metadata inconsistencies and missing clarifications
    import warnings

    # Check: attributes marked hidden but never asked about
    never_asked = hidden_refs - actually_asked - clarified_hidden
    if never_asked:
        warnings.warn(
            f"The following attributes are marked as hidden but were never asked about "
            f"by the simulator: {sorted(never_asked)}. Either they're incorrectly marked "
            f"as hidden, or the simulator doesn't need them anymore.",
            UserWarning,
        )

    # Check: attributes with interaction answers but never clarified
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

    # Final assertion: use the final active_hidden state, not the original hidden_refs
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
