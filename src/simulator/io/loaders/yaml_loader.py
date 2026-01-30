from __future__ import annotations

import glob
import os

from pydantic import ValidationError

from simulator.core.attributes.file_spec import QualitativeSpaceFileSpec
from simulator.core.registries.registry_manager import RegistryManager
from simulator.io.loaders.common import read_yaml
from simulator.io.loaders.errors import LoaderError


def load_spaces(path: str, registries: RegistryManager) -> None:
    """Load qualitative spaces from YAML files in a directory tree.

    Expected format:
    spaces:
      - id: binary_state
        name: Binary State
        levels: [off, on]
    """
    if not os.path.exists(path):
        return
    files = sorted(glob.glob(os.path.join(path, "**", "*.yaml"), recursive=True))
    for fp in files:
        data = read_yaml(fp)
        try:
            spec = QualitativeSpaceFileSpec.model_validate(data)
        except ValidationError as exc:
            raise LoaderError(fp, "Invalid qualitative space definition", cause=exc) from exc
        for entry in spec.spaces:
            try:
                space = entry.build()
            except ValidationError as exc:
                raise LoaderError(fp, "Invalid qualitative space entry", cause=exc) from exc
            if space.id in registries.spaces.spaces:
                continue
            try:
                registries.spaces.register(space)
            except Exception as exc:
                raise LoaderError(fp, f"Failed to register qualitative space '{space.id}'", cause=exc) from exc
