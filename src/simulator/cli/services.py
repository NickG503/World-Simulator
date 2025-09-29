from __future__ import annotations

"""Higher-level helpers used by CLI commands."""

from typing import Dict, Iterable

from simulator.core.engine.transition_engine import TransitionEngine
from simulator.core.objects.object_type import ObjectType
from simulator.core.prompt import UnknownValueResolver
from simulator.io.loaders.object_loader import instantiate_default
from simulator.core.registries.registry_manager import RegistryManager


def resolve_action(
    registries: RegistryManager,
    object_name: str,
    action_name: str,
):
    obj = registries.objects.get(object_name)
    action = registries.create_behavior_enhanced_action(object_name, action_name)
    return obj, action


def apply_action(
    registries: RegistryManager,
    object_name: str,
    action_name: str,
    parameters: Dict[str, str],
    console,
    interactive: bool = True,
):
    obj_type, action = resolve_action(registries, object_name, action_name)
    if not action:
        return obj_type, action, None, None

    instance = instantiate_default(obj_type, registries)
    resolver = UnknownValueResolver(registries, console)
    resolver.resolve_unknowns(instance, interactive=interactive)

    engine = TransitionEngine(registries)
    result = engine.apply_action(instance, action, parameters)
    return obj_type, action, instance, result


def run_simulation(
    registries: RegistryManager,
    object_type: str,
    actions: Iterable[dict],
    simulation_id: str | None,
    verbose: bool,
    *,
    interactive: bool = False,
    unknown_paths: list[str] | None = None,
):
    from simulator.core.simulation_runner import create_simulation_runner

    runner = create_simulation_runner(registries)
    history = runner.run_simulation(
        object_type,
        list(actions),
        simulation_id,
        verbose=verbose,
        interactive=interactive,
        unknown_paths=unknown_paths,
    )
    return history, runner


__all__ = [
    "apply_action",
    "run_simulation",
    "resolve_action",
]
