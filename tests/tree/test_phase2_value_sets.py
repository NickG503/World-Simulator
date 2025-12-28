"""
Tests for Phase 2 value set support.

Tests cover:
- AttributeSnapshot value sets
- BranchCondition value sets
- Value sets from trends
- WorldSnapshot value sets
- Visualization with value sets
"""

from simulator.core.simulation_runner import (
    AttributeSnapshot,
    ObjectStateSnapshot,
    PartStateSnapshot,
)
from simulator.core.tree.models import BranchCondition, WorldSnapshot


class TestAttributeSnapshotValueSets:
    """Tests for AttributeSnapshot value set support."""

    def test_single_value(self):
        """AttributeSnapshot handles single value."""
        attr = AttributeSnapshot(value="high", trend=None)

        assert attr.value == "high"
        assert attr.is_value_set() is False
        assert attr.get_single_value() == "high"
        assert attr.get_value_as_set() == {"high"}
        assert attr.is_unknown() is False

    def test_value_set(self):
        """AttributeSnapshot handles value sets (list)."""
        attr = AttributeSnapshot(value=["low", "medium"], trend=None)

        assert attr.value == ["low", "medium"]
        assert attr.is_value_set() is True
        assert attr.get_single_value() == "low"  # First element
        assert attr.get_value_as_set() == {"low", "medium"}
        assert attr.is_unknown() is True  # Multiple values = unknown

    def test_none_value(self):
        """AttributeSnapshot handles None value."""
        attr = AttributeSnapshot(value=None, trend=None)

        assert attr.value is None
        assert attr.is_value_set() is False
        assert attr.get_single_value() is None
        assert attr.get_value_as_set() == set()
        assert attr.is_unknown() is True

    def test_unknown_string_value(self):
        """AttributeSnapshot recognizes 'unknown' string."""
        attr = AttributeSnapshot(value="unknown", trend=None)

        assert attr.is_unknown() is True

    def test_single_element_list(self):
        """Single-element list is considered known."""
        attr = AttributeSnapshot(value=["high"], trend=None)

        assert attr.is_value_set() is True
        assert attr.is_unknown() is False  # Single element = known


class TestBranchConditionValueSets:
    """Tests for BranchCondition value set support."""

    def test_branch_condition_single_value(self):
        """BranchCondition with single value."""
        cond = BranchCondition(
            attribute="battery.level",
            operator="equals",
            value="high",
            source="precondition",
            branch_type="success",
        )

        assert cond.is_value_set() is False
        assert cond.get_value_display() == "high"
        assert cond.matches_value("high") is True
        assert cond.matches_value("low") is False

    def test_branch_condition_value_set(self):
        """BranchCondition with value set (list)."""
        cond = BranchCondition(
            attribute="battery.level",
            operator="in",
            value=["low", "empty"],
            source="postcondition",
            branch_type="else",
        )

        assert cond.is_value_set() is True
        assert cond.get_value_display() == "{low, empty}"
        assert cond.matches_value("low") is True
        assert cond.matches_value("empty") is True
        assert cond.matches_value("high") is False

    def test_branch_condition_describe_set(self):
        """BranchCondition describe() handles value sets."""
        cond = BranchCondition(
            attribute="battery.level",
            operator="in",
            value=["low", "empty"],
            source="postcondition",
            branch_type="else",
        )

        desc = cond.describe()
        assert "battery.level" in desc
        assert "{low, empty}" in desc


class TestValueSetFromTrend:
    """Tests for computing value sets from trends."""

    def test_trend_down_from_high(self, registry_manager):
        """Trend down from high gives values at or below."""
        from simulator.core.tree.snapshot_utils import compute_value_set_from_trend

        values = compute_value_set_from_trend("high", "down", "generic_level", registry_manager)

        # generic_level: ["empty", "low", "medium", "high", "full"]
        # down from high: empty, low, medium, high
        assert "empty" in values
        assert "low" in values
        assert "medium" in values
        assert "high" in values
        assert "full" not in values

    def test_trend_down_from_medium(self, registry_manager):
        """Trend down from medium gives values at or below."""
        from simulator.core.tree.snapshot_utils import compute_value_set_from_trend

        values = compute_value_set_from_trend("medium", "down", "generic_level", registry_manager)

        # down from medium: empty, low, medium
        assert "empty" in values
        assert "low" in values
        assert "medium" in values
        assert "high" not in values
        assert "full" not in values

    def test_trend_up_from_low(self, registry_manager):
        """Trend up from low gives values at or above."""
        from simulator.core.tree.snapshot_utils import compute_value_set_from_trend

        values = compute_value_set_from_trend("low", "up", "generic_level", registry_manager)

        # up from low: low, medium, high, full
        assert "empty" not in values
        assert "low" in values
        assert "medium" in values
        assert "high" in values
        assert "full" in values

    def test_trend_none(self, registry_manager):
        """No trend keeps current value only."""
        from simulator.core.tree.snapshot_utils import compute_value_set_from_trend

        values = compute_value_set_from_trend("medium", "none", "generic_level", registry_manager)

        assert values == ["medium"]

    def test_trend_invalid_value(self, registry_manager):
        """Invalid current value returns itself."""
        from simulator.core.tree.snapshot_utils import compute_value_set_from_trend

        values = compute_value_set_from_trend("invalid", "down", "generic_level", registry_manager)

        assert values == ["invalid"]

    def test_trend_invalid_space(self, registry_manager):
        """Invalid space returns current value."""
        from simulator.core.tree.snapshot_utils import compute_value_set_from_trend

        values = compute_value_set_from_trend("medium", "down", "nonexistent_space", registry_manager)

        assert values == ["medium"]


class TestWorldSnapshotValueSets:
    """Tests for WorldSnapshot handling value sets."""

    def test_get_attribute_value_with_set(self):
        """WorldSnapshot returns value set from attribute."""
        obj_state = ObjectStateSnapshot(
            type="test",
            parts={
                "battery": PartStateSnapshot(
                    attributes={"level": AttributeSnapshot(value=["low", "medium"], trend="down")}
                )
            },
            global_attributes={},
        )
        snapshot = WorldSnapshot(object_state=obj_state)

        value = snapshot.get_attribute_value("battery.level")
        assert value == ["low", "medium"]

    def test_is_attribute_known_with_set(self):
        """WorldSnapshot detects value sets as unknown."""
        obj_state = ObjectStateSnapshot(
            type="test",
            parts={
                "battery": PartStateSnapshot(
                    attributes={"level": AttributeSnapshot(value=["low", "medium"], trend=None)}
                )
            },
            global_attributes={},
        )
        snapshot = WorldSnapshot(object_state=obj_state)

        # Multiple values = unknown
        assert snapshot.is_attribute_known("battery.level") is False

    def test_is_attribute_value_set(self):
        """WorldSnapshot can check if value is a set."""
        obj_state = ObjectStateSnapshot(
            type="test",
            parts={
                "battery": PartStateSnapshot(
                    attributes={"level": AttributeSnapshot(value=["low", "medium"], trend=None)}
                )
            },
            global_attributes={},
        )
        snapshot = WorldSnapshot(object_state=obj_state)

        assert snapshot.is_attribute_value_set("battery.level") is True


class TestVisualizationValueSets:
    """Tests for visualization with value sets."""

    def test_visualization_handles_value_sets(self, registry_manager, tmp_path):
        """Visualization correctly displays value sets."""
        from simulator.visualizer.generator import generate_html

        # Create tree data with value sets
        tree_data = {
            "simulation_id": "test_value_sets",
            "object_type": "flashlight",
            "object_name": "flashlight",
            "created_at": "2025-01-01",
            "root_id": "state0",
            "current_path": ["state0", "state1"],
            "nodes": {
                "state0": {
                    "id": "state0",
                    "snapshot": {
                        "object_state": {
                            "type": "flashlight",
                            "parts": {
                                "battery": {
                                    "attributes": {
                                        "level": {
                                            "value": ["low", "medium"],  # Value set
                                            "trend": "down",
                                        }
                                    }
                                }
                            },
                            "global_attributes": {},
                        },
                        "timestamp": "2025-01-01",
                    },
                    "parent_id": None,
                    "children_ids": ["state1"],
                    "action_name": None,
                    "action_parameters": {},
                    "action_status": "ok",
                    "changes": [],
                },
                "state1": {
                    "id": "state1",
                    "snapshot": {
                        "object_state": {
                            "type": "flashlight",
                            "parts": {"battery": {"attributes": {"level": {"value": "low", "trend": None}}}},
                            "global_attributes": {},
                        },
                        "timestamp": "2025-01-01",
                    },
                    "parent_id": "state0",
                    "children_ids": [],
                    "action_name": "turn_on",
                    "action_parameters": {},
                    "action_status": "ok",
                    "branch_condition": {
                        "attribute": "battery.level",
                        "operator": "in",
                        "value": ["low", "medium"],
                        "source": "postcondition",
                        "branch_type": "else",
                    },
                    "changes": [],
                },
            },
        }

        output_path = tmp_path / "test_value_sets.html"
        html = generate_html(tree_data, str(output_path))

        assert output_path.exists()
        assert "formatValue" in html  # JS function for formatting
        assert "value-set" in html  # CSS class for value sets
