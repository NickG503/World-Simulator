from __future__ import annotations

from typing import List

from simulator.core.actions.conditions.base import Condition

from .base import Effect, StateChange


class ConditionalEffect(Effect):
    condition: Condition
    then_effect: Effect | List[Effect]
    else_effect: Effect | List[Effect] | None = None

    def _as_list(self, eff: Effect | List[Effect] | None) -> List[Effect]:
        if eff is None:
            return []
        return eff if isinstance(eff, list) else [eff]

    def apply(self, context: "ApplicationContext", instance: "ObjectInstance") -> List[StateChange]:  # noqa: F821
        condition_result = self.condition.evaluate(context)

        if condition_result:
            effects = self._as_list(self.then_effect)
            branch_info = StateChange(
                attribute="[CONDITIONAL_EVAL]",
                before="evaluating",
                after="TRUE → 'then' branch",
                kind="info",
            )
        else:
            # Check if else branch exists
            else_effects = self._as_list(self.else_effect)
            if not else_effects:
                # No else branch and condition is FALSE → This is a failure
                branch_info = StateChange(
                    attribute="[CONDITIONAL_EVAL_FAILED]",
                    before="evaluating",
                    after="FALSE (no 'else' branch defined)",
                    kind="error",
                )
                return [branch_info]
            else:
                # Else branch exists, execute it
                effects = else_effects
                branch_info = StateChange(
                    attribute="[CONDITIONAL_EVAL]",
                    before="evaluating",
                    after="FALSE → 'else' branch",
                    kind="info",
                )

        changes: List[StateChange] = [branch_info]
        for e in effects:
            changes.extend(e.apply(context, instance))
        return changes
