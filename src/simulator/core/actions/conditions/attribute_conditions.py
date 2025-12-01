from __future__ import annotations

from typing import List, Literal, Union

from simulator.core.objects import AttributeTarget

from .base import Condition

ComparisonOperator = Literal["equals", "not_equals", "in", "not_in", "lt", "lte", "gt", "gte"]


class AttributeCondition(Condition):
    """Check an attribute value."""

    target: AttributeTarget
    operator: ComparisonOperator
    value: Union[str, List[str], "ParameterReference"]  # noqa: F821

    def evaluate(self, context: "EvaluationContext") -> bool:  # noqa: F821
        from simulator.core.actions.parameter import ParameterReference
        from simulator.core.engine.context import EvaluationContext  # local import

        assert isinstance(context, EvaluationContext)

        # Resolve value
        if isinstance(self.value, ParameterReference):
            rhs = context.parameters.get(self.value.name)
        else:
            rhs = self.value

        # Read current value
        lhs = context.read_attribute(self.target)

        # Unknown values should not satisfy preconditions or postconditions
        # during action execution (context.action is set), to force
        # clarification. For post-action validation (e.g., constraints) the
        # operator check below should run so we can reason about the last
        # known value.
        if isinstance(lhs, str) and lhs == "unknown":
            if context.action is not None:
                return False

        if self.operator == "equals":
            return lhs == rhs
        elif self.operator == "not_equals":
            return lhs != rhs
        elif self.operator == "in":
            # Check if lhs is in the list rhs
            if isinstance(rhs, list):
                return lhs in rhs
            return lhs == rhs
        elif self.operator == "not_in":
            # Check if lhs is NOT in the list rhs
            if isinstance(rhs, list):
                return lhs not in rhs
            return lhs != rhs
        elif self.operator in ("lt", "lte", "gt", "gte"):
            # Order-aware comparisons using the attribute's qualitative space
            # Resolve space via registries using target
            ai = self.target.resolve(context.instance)
            space = context.registries.spaces.get(ai.spec.space_id)
            try:
                li = space.levels.index(lhs)
                ri = space.levels.index(str(rhs))
            except ValueError:
                raise ValueError(f"Values '{lhs}' or '{rhs}' not in space '{space.id}' levels {space.levels}")
            if self.operator == "lt":
                return li < ri
            if self.operator == "lte":
                return li <= ri
            if self.operator == "gt":
                return li > ri
            if self.operator == "gte":
                return li >= ri
            return False
        else:
            raise ValueError(f"Unknown operator: {self.operator}")

    def describe(self) -> str:
        """Human-readable description of this condition."""
        op_map = {
            "equals": "==",
            "not_equals": "!=",
            "in": "in",
            "not_in": "not in",
            "lt": "<",
            "lte": "<=",
            "gt": ">",
            "gte": ">=",
        }
        op_symbol = op_map.get(self.operator, self.operator)
        if hasattr(self.value, "name"):
            value_str = self.value.name
        elif isinstance(self.value, list):
            value_str = "{" + ", ".join(self.value) + "}"
        else:
            value_str = str(self.value)
        return f"{self.target.to_string()} {op_symbol} {value_str}"


def _rebuild_models():
    from simulator.core.actions.parameter import ParameterReference  # noqa: F401

    AttributeCondition.model_rebuild()


_rebuild_models()
