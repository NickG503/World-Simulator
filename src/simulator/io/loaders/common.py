"""Common utilities for loaders."""

from __future__ import annotations

from typing import Any, Dict

import yaml


def read_yaml(path: str) -> Dict[str, Any]:
    """Read and parse a YAML file.

    Args:
        path: Path to the YAML file

    Returns:
        Parsed YAML content as a dictionary
    """
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
