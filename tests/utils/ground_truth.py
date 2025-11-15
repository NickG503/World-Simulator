"""Helpers for working with ground-truth trajectory YAML files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import yaml

from simulator.core.engine.transition_engine import DiffEntry
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.objects.part import AttributeTarget
from simulator.core.simulation_runner import (
    AttributeSnapshot,
    ObjectStateSnapshot,
    PartStateSnapshot,
    _apply_changes_to_snapshot,
)


@dataclass
class GroundTruthMetadata:
    tracked_attributes: List[str]
    hidden_attributes: List[str]


@dataclass
class GroundTruthStep:
    action_name: str
    parameters: Dict[str, str]
    status: str
    changes: List[Dict[str, Any]]


@dataclass
class GroundTruthHistory:
    simulation_id: str
    object_name: str
    steps: List[GroundTruthStep]
    initial_state: Dict[str, Any]
    interactions: List[Dict[str, Any]]
    metadata: GroundTruthMetadata
    step_snapshots: List[Tuple[Dict[str, Any], Dict[str, Any]]]
    final_state: Dict[str, Any]
    interaction_answers: Dict[int, List[tuple[str, str]]]


def _coerce_snapshot(snapshot: Dict[str, Any]) -> ObjectStateSnapshot:
    if not snapshot:
        return ObjectStateSnapshot(type="unknown", parts={}, global_attributes={})
    return ObjectStateSnapshot.model_validate(snapshot)


def _coerce_changes(changes: List[Dict[str, Any]]) -> List[DiffEntry]:
    entries: List[DiffEntry] = []
    for raw in changes:
        if not raw:
            continue
        entries.append(
            DiffEntry(
                attribute=raw.get("attribute", ""),
                before=raw.get("before"),
                after=raw.get("after"),
                kind=raw.get("kind", "value"),
            )
        )
    return entries


def _ensure_snapshot_attr(snapshot: ObjectStateSnapshot, reference: str) -> AttributeSnapshot:
    parts = reference.split(".")
    if len(parts) == 1:
        attr = parts[0]
        if attr not in snapshot.global_attributes:
            snapshot.global_attributes[attr] = AttributeSnapshot(value=None, trend=None, confidence=1.0)
        return snapshot.global_attributes[attr]
    if len(parts) >= 2:
        part = parts[0]
        attr = parts[1]
        if part not in snapshot.parts:
            snapshot.parts[part] = PartStateSnapshot()
        part_snapshot = snapshot.parts[part]
        if attr not in part_snapshot.attributes:
            part_snapshot.attributes[attr] = AttributeSnapshot(value=None, trend=None, confidence=1.0)
        return part_snapshot.attributes[attr]
    raise ValueError(f"Invalid attribute reference: {reference}")


def _apply_answers_to_snapshot(snapshot: ObjectStateSnapshot, answers: List[tuple[str, str]]) -> None:
    for reference, value in answers:
        attr_snapshot = _ensure_snapshot_attr(snapshot, reference)
        attr_snapshot.value = value
        attr_snapshot.last_known_value = value
        attr_snapshot.last_trend_direction = None
        attr_snapshot.trend = attr_snapshot.trend or "none"
        attr_snapshot.confidence = 1.0


def _reconstruct_snapshots(
    initial_state: Dict[str, Any],
    steps: List[GroundTruthStep],
    interaction_answers: Dict[int, List[tuple[str, str]]],
) -> tuple[List[Tuple[Dict[str, Any], Dict[str, Any]]], Dict[str, Any]]:
    cursor = _coerce_snapshot(initial_state)
    pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for idx, step in enumerate(steps):
        if interaction_answers:
            _apply_answers_to_snapshot(cursor, interaction_answers.get(idx, []))
        before = cursor.model_dump()
        cursor = _apply_changes_to_snapshot(cursor, _coerce_changes(step.changes))
        after = cursor.model_dump()
        pairs.append((before, after))
    final_state = pairs[-1][1] if pairs else cursor.model_dump()
    return pairs, final_state


def _build_interaction_map(interactions: List[Dict[str, Any]]) -> Dict[int, List[tuple[str, str]]]:
    mapping: Dict[int, List[tuple[str, str]]] = {}
    for entry in interactions:
        step = entry.get("step")
        attr = entry.get("attribute")
        answer = entry.get("answer")
        if step is None or attr is None or answer is None:
            continue
        mapping.setdefault(int(step), []).append((attr, answer))
    return mapping


def load_ground_truth(path: Path) -> GroundTruthHistory:
    raw = yaml.safe_load(path.read_text())
    metadata = raw.get("metadata", {}) or {}
    meta = GroundTruthMetadata(
        tracked_attributes=list(metadata.get("tracked_attributes", [])),
        hidden_attributes=list(metadata.get("hidden_attributes", [])),
    )

    steps = [
        GroundTruthStep(
            action_name=step.get("action_name") or step.get("action"),
            parameters=dict(step.get("parameters", {})),
            status=step.get("status", "ok"),
            changes=list(step.get("changes", [])),
        )
        for step in raw.get("steps", [])
    ]

    interactions = list(raw.get("interactions", []))
    interaction_map = _build_interaction_map(interactions)
    snapshot_pairs, final_state = _reconstruct_snapshots(raw.get("initial_state", {}), steps, interaction_map)

    return GroundTruthHistory(
        simulation_id=raw.get("simulation_id", ""),
        object_name=raw.get("object_name", raw.get("object_type", "")),
        steps=steps,
        initial_state=raw.get("initial_state", {}),
        interactions=interactions,
        metadata=meta,
        step_snapshots=snapshot_pairs,
        final_state=final_state,
        interaction_answers=interaction_map,
    )


def apply_snapshot(instance: ObjectInstance, snapshot: Mapping[str, Any]) -> None:
    for part_name, part in (snapshot.get("parts") or {}).items():
        if part_name not in instance.parts:
            continue
        part_instance = instance.parts[part_name]
        attributes = part.get("attributes") or {}
        for attr_name, attr_snapshot in attributes.items():
            if attr_name not in part_instance.attributes:
                continue
            attr = part_instance.attributes[attr_name]
            attr.current_value = attr_snapshot.get("value")
            attr.trend = attr_snapshot.get("trend")
            attr.confidence = attr_snapshot.get("confidence", 1.0)
            attr.last_known_value = attr_snapshot.get("last_known_value")
            attr.last_trend_direction = attr_snapshot.get("last_trend_direction")
    for attr_name, attr_snapshot in (snapshot.get("global_attributes") or {}).items():
        if attr_name not in instance.global_attributes:
            continue
        attr = instance.global_attributes[attr_name]
        attr.current_value = attr_snapshot.get("value")
        attr.trend = attr_snapshot.get("trend")
        attr.confidence = attr_snapshot.get("confidence", 1.0)
        attr.last_known_value = attr_snapshot.get("last_known_value")
        attr.last_trend_direction = attr_snapshot.get("last_trend_direction")


def mask_attributes(instance: ObjectInstance, attr_refs: Iterable[str]) -> None:
    for ref in attr_refs:
        try:
            target = AttributeTarget.from_string(ref).resolve(instance)
        except Exception:
            continue
        target.current_value = "unknown"
        target.confidence = 0.0
        target.last_trend_direction = None


def capture_snapshot(instance: ObjectInstance) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "type": instance.type.name,
        "parts": {},
        "global_attributes": {},
    }
    for part_name, part_instance in instance.parts.items():
        snap_attrs: Dict[str, Any] = {}
        for attr_name, attr in part_instance.attributes.items():
            snap_attrs[attr_name] = {
                "value": attr.current_value,
                "trend": attr.trend,
                "confidence": attr.confidence,
                "last_known_value": attr.last_known_value,
                "last_trend_direction": attr.last_trend_direction,
                "space_id": attr.spec.space_id,
            }
        snapshot["parts"][part_name] = {"attributes": snap_attrs}
    for attr_name, attr in instance.global_attributes.items():
        snapshot["global_attributes"][attr_name] = {
            "value": attr.current_value,
            "trend": attr.trend,
            "confidence": attr.confidence,
            "last_known_value": attr.last_known_value,
            "last_trend_direction": attr.last_trend_direction,
            "space_id": attr.spec.space_id,
        }
    return snapshot


def extract_attribute(snapshot: Mapping[str, Any], reference: str) -> Dict[str, Any] | None:
    parts = reference.split(".")
    if len(parts) == 1:
        return (snapshot.get("global_attributes") or {}).get(reference)
    if len(parts) == 2:
        part = (snapshot.get("parts") or {}).get(parts[0]) or {}
        return (part.get("attributes") or {}).get(parts[1])
    return None


def tracked_attributes(meta: GroundTruthMetadata, fallback_snapshot: Mapping[str, Any]) -> Sequence[str]:
    if meta.tracked_attributes:
        return meta.tracked_attributes
    refs: List[str] = []
    for part_name, part in (fallback_snapshot.get("parts") or {}).items():
        for attr_name in (part.get("attributes") or {}).keys():
            refs.append(f"{part_name}.{attr_name}")
    for attr_name in (fallback_snapshot.get("global_attributes") or {}).keys():
        refs.append(attr_name)
    return refs


def attribute_value(snapshot: Mapping[str, Any], reference: str) -> Any:
    attr = extract_attribute(snapshot, reference)
    if attr is None:
        return None
    value = attr.get("value")
    if value in (None, "unknown"):
        return None
    return value


def lookup_interaction_answer(history: GroundTruthHistory, step_index: int, reference: str) -> str | None:
    candidates = history.interaction_answers.get(step_index, [])
    for attr, answer in candidates:
        if attr == reference:
            return answer
    return None


def parse_attribute_from_question(question: str) -> str | None:
    text = question.strip()
    lowered = text.lower()
    if lowered.startswith("precondition: what is ") and text.endswith("?"):
        return text[len("Precondition: what is ") : -1].strip()
    if lowered.startswith("postcondition: what is ") and text.endswith("?"):
        return text[len("Postcondition: what is ") : -1].strip()
    if lowered.startswith("what is ") and text.endswith("?"):
        return text[len("What is ") : -1].strip()
    return None
