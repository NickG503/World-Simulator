"""
Shared fixtures for tree simulation tests.
"""

import pytest

from simulator.cli.paths import kb_actions_path, kb_objects_path, kb_spaces_path
from simulator.core.registries import RegistryManager
from simulator.io.loaders.action_loader import load_actions
from simulator.io.loaders.object_loader import load_object_types
from simulator.io.loaders.yaml_loader import load_spaces


def _load_test_registries() -> RegistryManager:
    """Load all registries for testing."""
    rm = RegistryManager()
    load_spaces(kb_spaces_path(None), rm)
    rm.register_defaults()
    load_object_types(kb_objects_path(None), rm)
    load_actions(kb_actions_path(None), rm)
    return rm


@pytest.fixture(scope="module")
def registry_manager() -> RegistryManager:
    """Load registries once for all tests in the module."""
    return _load_test_registries()
