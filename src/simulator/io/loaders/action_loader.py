from __future__ import annotations

import glob
import os
from typing import Any, Dict

import yaml
from pydantic import ValidationError

from simulator.core.actions.action import Action, ActionMetadata
from simulator.core.actions.file_spec import ActionFileSpec
from simulator.core.registries.registry_manager import RegistryManager
from simulator.io.loaders.errors import LoaderError


def _read_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_actions(path: str, registries: RegistryManager) -> None:
    if not os.path.exists(path):
        return
    files = sorted(glob.glob(os.path.join(path, "**", "*.yaml"), recursive=True))
    for fp in files:
        data = _read_yaml(fp)
        try:
            spec = ActionFileSpec.model_validate(data)
        except ValidationError as exc:
            raise LoaderError(fp, "Invalid action definition", cause=exc) from exc

        parameters = spec.build_parameters()
        preconditions = spec.build_preconditions()
        effects = spec.build_effects()

        metadata = ActionMetadata(description=spec.description) if spec.description else None

        action = Action(
            name=spec.action.strip(),
            object_type=spec.object_type.strip(),
            parameters=parameters,
            preconditions=preconditions,
            effects=effects,
            metadata=metadata,
        )

        # Register with object_type/name key
        key = f"{action.object_type}/{action.name}"
        try:
            registries.actions.register(key, action)
        except Exception as exc:
            raise LoaderError(fp, f"Failed to register action '{action.name}'", cause=exc) from exc
