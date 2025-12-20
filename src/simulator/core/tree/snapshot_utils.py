"""Snapshot utilities for tree simulation."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, List, Optional, Tuple, Union

from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.registries.registry_manager import RegistryManager
from simulator.core.simulation_runner import (
    AttributeSnapshot,
    ObjectStateSnapshot,
    PartStateSnapshot,
)
from simulator.core.tree.models import WorldSnapshot
from simulator.core.types import ChangeDict


def capture_snapshot(
    obj_instance: ObjectInstance,
    registry_manager: RegistryManager,
    parent_snapshot: Optional[WorldSnapshot] = None,
) -> WorldSnapshot:
    """
    Capture the current object state as a WorldSnapshot.

    When an attribute has an active trend (not "none"), its value becomes a
    value SET representing all possible values the trend could produce.
    - trend "down" from "medium" → ["empty", "low", "medium"]
    - trend "up" from "low" → ["low", "medium", "high", "full"]

    Value sets are preserved from parent snapshot if the action only clears
    the trend without setting a new specific value.

    Args:
        obj_instance: The object instance to snapshot
        registry_manager: Registry for accessing spaces
        parent_snapshot: Optional parent snapshot for value set preservation

    Returns:
        WorldSnapshot representing the current state
    """
    parts: Dict[str, PartStateSnapshot] = {}

    for part_name, part_instance in obj_instance.parts.items():
        attrs: Dict[str, AttributeSnapshot] = {}
        for attr_name, attr_instance in part_instance.attributes.items():
            attr_path = f"{part_name}.{attr_name}"
            value = compute_value_with_trend(attr_instance, attr_path, registry_manager, parent_snapshot)
            attrs[attr_name] = AttributeSnapshot(
                value=value,
                trend=attr_instance.trend,
                last_known_value=attr_instance.last_known_value,
                last_trend_direction=attr_instance.last_trend_direction,
                space_id=attr_instance.spec.space_id,
            )
        parts[part_name] = PartStateSnapshot(attributes=attrs)

    global_attrs: Dict[str, AttributeSnapshot] = {}
    for attr_name, attr_instance in obj_instance.global_attributes.items():
        value = compute_value_with_trend(attr_instance, attr_name, registry_manager, parent_snapshot)
        global_attrs[attr_name] = AttributeSnapshot(
            value=value,
            trend=attr_instance.trend,
            last_known_value=attr_instance.last_known_value,
            last_trend_direction=attr_instance.last_trend_direction,
            space_id=attr_instance.spec.space_id,
        )

    object_state = ObjectStateSnapshot(
        type=obj_instance.type.name,
        parts=parts,
        global_attributes=global_attrs,
    )

    return WorldSnapshot(object_state=object_state)


def compute_value_with_trend(
    attr_instance,
    attr_path: str,
    registry_manager: RegistryManager,
    parent_snapshot: Optional[WorldSnapshot] = None,
) -> Union[str, List[str]]:
    """
    Compute the value for an attribute, considering its trend and parent value set.

    - If the attribute has an active trend (up/down), returns a value set
    - If parent had a value set and this action didn't set a new concrete value,
      preserve the value set
    - Otherwise returns the single current value

    Args:
        attr_instance: The attribute instance
        attr_path: Path like "battery.level"
        registry_manager: For accessing spaces
        parent_snapshot: Optional parent snapshot

    Returns:
        Single value or list of possible values
    """
    current_value = attr_instance.current_value
    trend = attr_instance.trend
    space_id = attr_instance.spec.space_id

    # If there's an active trend, compute value set
    if trend and trend != "none" and current_value != "unknown":
        if space_id:
            value_set = compute_value_set_from_trend(current_value, trend, space_id, registry_manager)
            if len(value_set) > 1:
                return value_set

    # If parent had a value set, only preserve it if NO explicit value was set
    if parent_snapshot:
        parent_value = parent_snapshot.get_attribute_value(attr_path)
        if isinstance(parent_value, list) and len(parent_value) > 1:
            parent_attr = parent_snapshot._get_attribute_snapshot(attr_path)
            parent_last_known = parent_attr.last_known_value if parent_attr else None
            if attr_instance.last_known_value == parent_last_known:
                return parent_value

    return current_value


def compute_value_set_from_trend(
    current_value: str,
    trend: str,
    space_id: str,
    registry_manager: RegistryManager,
) -> List[str]:
    """
    Compute possible values based on trend direction.

    Args:
        current_value: Current known value (e.g., "medium")
        trend: Trend direction ("up" or "down")
        space_id: ID of the qualitative space
        registry_manager: For accessing space definitions

    Returns:
        List of possible values based on trend.
        - trend "down" from "medium" → ["empty", "low", "medium"]
        - trend "up" from "medium" → ["medium", "high", "full"]
    """
    try:
        space = registry_manager.spaces.get(space_id)
        if not space:
            return [current_value]

        levels = list(space.levels)
        if current_value not in levels:
            return [current_value]

        current_idx = levels.index(current_value)

        if trend == "down":
            return levels[: current_idx + 1]
        elif trend == "up":
            return levels[current_idx:]
        else:
            return [current_value]
    except Exception:
        return [current_value]


def snapshot_with_constrained_values(
    snapshot: WorldSnapshot,
    attr_path: str,
    values: List[str],
    registry_manager: RegistryManager,
    enforce_constraints: bool = True,
) -> Tuple[WorldSnapshot, List[ChangeDict]]:
    """Create a copy of snapshot with constrained values, enforcing constraints.

    Returns:
        Tuple of (modified snapshot, list of constraint-induced changes)
    """
    from simulator.core.tree.constraints import enforce_constraints as do_enforce

    new_snapshot = deepcopy(snapshot)

    parts = attr_path.split(".")
    if len(parts) == 2:
        part_name, attr_name = parts
        if part_name in new_snapshot.object_state.parts:
            attr = new_snapshot.object_state.parts[part_name].attributes.get(attr_name)
            if attr:
                attr.value = values[0] if len(values) == 1 else values
    elif len(parts) == 1:
        attr = new_snapshot.object_state.global_attributes.get(parts[0])
        if attr:
            attr.value = values[0] if len(values) == 1 else values

    constraint_changes: List[ChangeDict] = []
    if enforce_constraints:
        object_type_name = new_snapshot.object_state.type
        new_snapshot, constraint_changes = do_enforce(new_snapshot, object_type_name, registry_manager)

    return new_snapshot, constraint_changes


def capture_snapshot_with_values(
    instance: ObjectInstance,
    attr_path: str,
    values: List[str],
    registry_manager: RegistryManager,
    parent_snapshot: Optional[WorldSnapshot] = None,
) -> WorldSnapshot:
    """
    Capture a snapshot, preserving trend-based value sets.

    The `values` parameter is used for branch condition tracking, but the
    snapshot's actual value is computed by `capture_snapshot` which considers
    trends. If a trend produces a value SET, we preserve it rather than
    overriding with a single value.

    Args:
        instance: Object instance to snapshot
        attr_path: Attribute path being branched on
        values: Branch constraint values
        registry_manager: For space access
        parent_snapshot: Optional parent for value set preservation

    Returns:
        WorldSnapshot with appropriate values
    """
    snapshot = capture_snapshot(instance, registry_manager, parent_snapshot)

    parts = attr_path.split(".")
    if len(parts) == 2:
        part_name, attr_name = parts
        if part_name in snapshot.object_state.parts:
            attr = snapshot.object_state.parts[part_name].attributes.get(attr_name)
            if attr:
                current_is_set = isinstance(attr.value, list)
                if not current_is_set:
                    attr.value = values[0] if len(values) == 1 else values
    elif len(parts) == 1:
        attr = snapshot.object_state.global_attributes.get(parts[0])
        if attr:
            current_is_set = isinstance(attr.value, list)
            if not current_is_set:
                attr.value = values[0] if len(values) == 1 else values

    return snapshot


def update_snapshot_attribute(snapshot: WorldSnapshot, attr_path: str, values: List[str]) -> None:
    """
    Update an attribute's value in a snapshot (in place).

    Args:
        snapshot: Snapshot to modify
        attr_path: Attribute path
        values: New value(s)
    """
    parts = attr_path.split(".")
    if len(parts) == 2:
        part_name, attr_name = parts
        if part_name in snapshot.object_state.parts:
            attr = snapshot.object_state.parts[part_name].attributes.get(attr_name)
            if attr:
                attr.value = values[0] if len(values) == 1 else values
    elif len(parts) == 1:
        attr = snapshot.object_state.global_attributes.get(parts[0])
        if attr:
            attr.value = values[0] if len(values) == 1 else values


def get_all_space_values(space_id: str, registry_manager: RegistryManager) -> List[str]:
    """Get all values in a space, ordered."""
    try:
        space = registry_manager.spaces.get(space_id)
        return list(space.levels) if space else []
    except Exception:
        return []


def get_attribute_space_id(instance: ObjectInstance, attr_path: str) -> Optional[str]:
    """
    Get the space ID for an attribute.

    Args:
        instance: Object instance
        attr_path: Attribute path like "battery.level"

    Returns:
        Space ID or None if not found
    """
    try:
        parts = attr_path.split(".")
        if len(parts) == 2:
            part_name, attr_name = parts
            part_inst = instance.parts.get(part_name)
            if part_inst:
                attr_inst = part_inst.attributes.get(attr_name)
                if attr_inst:
                    return attr_inst.spec.space_id
        elif len(parts) == 1:
            attr_inst = instance.global_attributes.get(parts[0])
            if attr_inst:
                return attr_inst.spec.space_id
    except Exception:
        pass
    return None
