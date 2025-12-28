"""
Tests for Phase 2 comparison and logical operators.

Tests cover:
- Comparison operators (>=, <=, >, <)
- AND conditions
- OR conditions
"""

from simulator.core.tree.models import BranchCondition


class TestComparisonOperators:
    """Tests for comparison operators (>=, <=, >, <) in conditions."""

    def test_gte_operator_expands_to_value_set(self):
        """The >= operator should expand to all values at or above the threshold."""
        from simulator.core.attributes.qualitative_space import QualitativeSpace

        space = QualitativeSpace(
            id="battery_level",
            name="Battery Level",
            levels=["empty", "low", "medium", "high", "full"],
        )

        # battery.level >= low means {low, medium, high, full}
        result = space.get_values_for_comparison("low", "gte")
        assert result == ["low", "medium", "high", "full"]

    def test_lte_operator_expands_to_value_set(self):
        """The <= operator should expand to all values at or below the threshold."""
        from simulator.core.attributes.qualitative_space import QualitativeSpace

        space = QualitativeSpace(
            id="battery_level",
            name="Battery Level",
            levels=["empty", "low", "medium", "high", "full"],
        )

        # battery.level <= medium means {empty, low, medium}
        result = space.get_values_for_comparison("medium", "lte")
        assert result == ["empty", "low", "medium"]

    def test_gt_operator_excludes_threshold(self):
        """The > operator should expand to values strictly above the threshold."""
        from simulator.core.attributes.qualitative_space import QualitativeSpace

        space = QualitativeSpace(
            id="battery_level",
            name="Battery Level",
            levels=["empty", "low", "medium", "high", "full"],
        )

        # battery.level > medium means {high, full}
        result = space.get_values_for_comparison("medium", "gt")
        assert result == ["high", "full"]

    def test_lt_operator_excludes_threshold(self):
        """The < operator should expand to values strictly below the threshold."""
        from simulator.core.attributes.qualitative_space import QualitativeSpace

        space = QualitativeSpace(
            id="battery_level",
            name="Battery Level",
            levels=["empty", "low", "medium", "high", "full"],
        )

        # battery.level < medium means {empty, low}
        result = space.get_values_for_comparison("medium", "lt")
        assert result == ["empty", "low"]

    def test_edge_case_gte_at_first_level(self):
        """gte at the first level should return all levels."""
        from simulator.core.attributes.qualitative_space import QualitativeSpace

        space = QualitativeSpace(
            id="battery_level",
            name="Battery Level",
            levels=["empty", "low", "medium", "high", "full"],
        )

        result = space.get_values_for_comparison("empty", "gte")
        assert result == ["empty", "low", "medium", "high", "full"]

    def test_edge_case_lt_at_first_level(self):
        """lt at the first level should return empty list."""
        from simulator.core.attributes.qualitative_space import QualitativeSpace

        space = QualitativeSpace(
            id="battery_level",
            name="Battery Level",
            levels=["empty", "low", "medium", "high", "full"],
        )

        result = space.get_values_for_comparison("empty", "lt")
        assert result == []


class TestAndCondition:
    """Tests for AND compound conditions."""

    def test_and_condition_creation(self):
        """AndCondition can be created with multiple sub-conditions."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import AndCondition
        from simulator.core.objects import AttributeTarget

        cond1 = AttributeCondition(
            target=AttributeTarget.from_string("battery.level"),
            operator="not_equals",
            value="empty",
        )
        cond2 = AttributeCondition(
            target=AttributeTarget.from_string("switch.position"),
            operator="equals",
            value="off",
        )

        and_cond = AndCondition(conditions=[cond1, cond2])

        assert len(and_cond.conditions) == 2
        assert and_cond.describe() == "(battery.level != empty AND switch.position == off)"

    def test_and_condition_get_checked_attributes(self):
        """AndCondition.get_checked_attributes returns all attribute paths."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import AndCondition
        from simulator.core.objects import AttributeTarget

        cond1 = AttributeCondition(
            target=AttributeTarget.from_string("battery.level"),
            operator="not_equals",
            value="empty",
        )
        cond2 = AttributeCondition(
            target=AttributeTarget.from_string("switch.position"),
            operator="equals",
            value="off",
        )

        and_cond = AndCondition(conditions=[cond1, cond2])
        attrs = and_cond.get_checked_attributes()

        assert "battery.level" in attrs
        assert "switch.position" in attrs

    def test_and_condition_parsing_from_yaml(self):
        """AND conditions can be parsed from YAML spec."""
        from simulator.core.actions.specs import build_condition, parse_condition_spec

        yaml_data = {
            "type": "and",
            "conditions": [
                {"type": "attribute_check", "target": "battery.level", "operator": "not_equals", "value": "empty"},
                {"type": "attribute_check", "target": "switch.position", "operator": "equals", "value": "off"},
            ],
        }

        spec = parse_condition_spec(yaml_data)
        condition = build_condition(spec)

        from simulator.core.actions.conditions.logical_conditions import AndCondition

        assert isinstance(condition, AndCondition)
        assert len(condition.conditions) == 2

    def test_branch_condition_compound_type(self):
        """BranchCondition supports compound_type for AND conditions."""
        sub1 = BranchCondition(
            attribute="battery.level",
            operator="in",
            value=["low", "medium", "high", "full"],
            source="precondition",
            branch_type="success",
        )
        sub2 = BranchCondition(
            attribute="switch.position",
            operator="equals",
            value="off",
            source="precondition",
            branch_type="success",
        )

        compound = BranchCondition(
            attribute="",
            operator="",
            value="",
            source="precondition",
            branch_type="success",
            compound_type="and",
            sub_conditions=[sub1, sub2],
        )

        assert compound.is_compound()
        assert compound.compound_type == "and"
        assert len(compound.sub_conditions) == 2
        # Check the description contains the expected parts
        desc = compound.describe()
        assert "battery.level" in desc
        assert "switch.position" in desc
        assert "AND" in desc


class TestOrCondition:
    """Tests for OR compound conditions."""

    def test_or_condition_creation(self):
        """OrCondition can be created with multiple sub-conditions."""
        from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
        from simulator.core.actions.conditions.logical_conditions import OrCondition
        from simulator.core.objects import AttributeTarget

        cond1 = AttributeCondition(
            target=AttributeTarget.from_string("battery.level"),
            operator="equals",
            value="full",
        )
        cond2 = AttributeCondition(
            target=AttributeTarget.from_string("switch.position"),
            operator="equals",
            value="on",
        )

        or_cond = OrCondition(conditions=[cond1, cond2])

        assert len(or_cond.conditions) == 2
        assert or_cond.describe() == "(battery.level == full OR switch.position == on)"

    def test_or_condition_parsing_from_yaml(self):
        """OR conditions can be parsed from YAML spec."""
        from simulator.core.actions.specs import build_condition, parse_condition_spec

        yaml_data = {
            "type": "or",
            "conditions": [
                {"type": "attribute_check", "target": "battery.level", "operator": "equals", "value": "full"},
                {"type": "attribute_check", "target": "switch.position", "operator": "equals", "value": "on"},
            ],
        }

        spec = parse_condition_spec(yaml_data)
        condition = build_condition(spec)

        from simulator.core.actions.conditions.logical_conditions import OrCondition

        assert isinstance(condition, OrCondition)
        assert len(condition.conditions) == 2
