from __future__ import annotations
import glob
import os
from typing import Dict, Any
import yaml
from simulator.core.attributes import QualitativeSpace
from simulator.core.registries.registry_manager import RegistryManager


def _read_yaml_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


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
        data = _read_yaml_file(fp)
        for entry in data.get("spaces", []) or []:
            space = QualitativeSpace(**entry)
            # Avoid duplicate registrations if defaults already loaded
            if space.id in registries.spaces.spaces:
                continue
            registries.spaces.register(space)
