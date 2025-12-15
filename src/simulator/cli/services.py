from __future__ import annotations

"""Higher-level helpers used by CLI commands.

Simplified for tree-based simulation: No interactive prompts.
"""

from typing import Dict

from simulator.core.engine.transition_engine import TransitionEngine
from simulator.core.registries.registry_manager import RegistryManager
from simulator.io.loaders.object_loader import instantiate_default


def resolve_action(
    registries: RegistryManager,
    object_name: str,
    action_name: str,
):
    """Resolve an action for an object type."""
    obj = registries.objects.get(object_name)
    action = registries.create_behavior_enhanced_action(object_name, action_name)
    return obj, action


def apply_action(
    registries: RegistryManager,
    object_name: str,
    action_name: str,
    parameters: Dict[str, str],
    console,
    interactive: bool = False,  # Ignored, kept for API compatibility
):
    """Apply a single action to an object instance."""
    obj_type, action = resolve_action(registries, object_name, action_name)
    if not action:
        return obj_type, action, None, None

    instance = instantiate_default(obj_type, registries)

    engine = TransitionEngine(registries)
    result = engine.apply_action(instance, action, parameters)
    return obj_type, action, instance, result


__all__ = [
    "apply_action",
    "resolve_action",
]
