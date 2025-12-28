"""
Utility functions for cloning and modifying object instances.
"""

from typing import Dict, List

from simulator.core.attributes import AttributePath
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.tree.models import WorldSnapshot


def set_attribute_value(instance: ObjectInstance, attr_path: str, value: str) -> None:
    """Set an attribute to a single value."""
    AttributePath.parse(attr_path).set_value_in_instance(instance, value)


def update_snapshot_attribute(snapshot: WorldSnapshot, attr_path: str, values: List[str]) -> None:
    """Update snapshot attribute, preserving existing value sets from trends."""
    attr = AttributePath.parse(attr_path).resolve_from_snapshot(snapshot)
    if attr and not isinstance(attr.value, list):
        attr.value = values[0] if len(values) == 1 else values


def clone_instance_with_values(instance: ObjectInstance, attr_path: str, values: List[str]) -> ObjectInstance:
    """Clone an instance and constrain an attribute to specific value(s)."""
    new_instance = instance.deep_copy()
    if values:
        AttributePath.parse(attr_path).set_value_in_instance(new_instance, values[0])
    return new_instance


def clone_instance_with_multi_values(instance: ObjectInstance, attr_values: Dict[str, List[str]]) -> ObjectInstance:
    """Clone an instance and constrain multiple attributes to specific values.

    Args:
        instance: Original instance to clone
        attr_values: Dict mapping attr_path -> list of possible values

    Returns:
        Cloned instance with first value set for each attribute
    """
    new_instance = instance.deep_copy()
    for attr_path, values in attr_values.items():
        if values:
            AttributePath.parse(attr_path).set_value_in_instance(new_instance, values[0])
    return new_instance
