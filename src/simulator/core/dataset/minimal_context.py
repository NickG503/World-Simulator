from __future__ import annotations

"""
Minimal-context case generator for benchmark-style LLM testing.

Produces a compact, natural-language serialized case with:
- Minimal prompt
- Clarification question if unknown precondition
- Options (space levels) for the unknown attribute
- Expected outcomes per option by simulating the action with each option value
"""

from typing import Iterable, List, Optional, Set, Tuple

from simulator.core.engine.transition_engine import TransitionEngine
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.registries.registry_manager import RegistryManager
from simulator.core.actions.action import Action
from simulator.core.actions.conditions.base import Condition
from simulator.core.actions.conditions.attribute_conditions import AttributeCondition
from simulator.core.actions.conditions.logical_conditions import LogicalCondition, ImplicationCondition
from simulator.core.actions.effects.base import Effect
from simulator.core.actions.effects.attribute_effects import SetAttributeEffect
from simulator.core.actions.effects.trend_effects import TrendEffect
from simulator.core.actions.effects.conditional_effects import ConditionalEffect
from simulator.core.objects.part import AttributeTarget


def _walk_conditions(cond: Condition) -> Iterable[Condition]:
    yield cond
    if isinstance(cond, LogicalCondition):
        for c in cond.conditions:
            yield from _walk_conditions(c)
    if isinstance(cond, ImplicationCondition):
        yield from _walk_conditions(cond.if_condition)
        yield from _walk_conditions(cond.then_condition)


def _walk_effects(eff: Effect) -> Iterable[Effect]:
    yield eff
    if isinstance(eff, ConditionalEffect):
        # then and else can be a single effect or a list
        def _as_list(v):
            if v is None:
                return []
            return v if isinstance(v, list) else [v]

        for se in _as_list(eff.then_effect):
            yield from _walk_effects(se)
        for se in _as_list(eff.else_effect):
            yield from _walk_effects(se)


def get_relevant_attributes(action: Action) -> Set[str]:
    """Collect attribute paths referenced by preconditions and effects."""
    attrs: Set[str] = set()

    for cond in action.preconditions:
        for c in _walk_conditions(cond):
            if isinstance(c, AttributeCondition):
                attrs.add(c.target.to_string())

    for eff in action.effects:
        for e in _walk_effects(eff):
            if isinstance(e, SetAttributeEffect):
                attrs.add(e.target.to_string())
            elif isinstance(e, TrendEffect):
                attrs.add(f"{e.target.to_string()}.trend")

    return attrs


def _nl_action(action_name: str) -> str:
    return action_name.replace("_", " ")


def _format_changes(result) -> str:
    if not result.changes:
        if result.status == "ok":
            return "Action completed with no visible changes"
        return f"Action {result.status}: {result.reason or 'unknown'}"

    phrases: List[str] = []
    for ch in result.changes:
        attr = (ch.attribute or "").replace("_", " ")
        if ch.kind == "trend":
            if ch.after == "down":
                phrases.append(f"{attr} starts decreasing")
            elif ch.after == "up":
                phrases.append(f"{attr} starts increasing")
            elif ch.after == "none":
                phrases.append(f"{attr} stops changing")
            else:
                phrases.append(f"{attr} trend becomes {ch.after}")
        else:
            phrases.append(f"{attr} becomes {ch.after}")
    return ", ".join(phrases)


def _first_unknown_in_instance(paths: Iterable[str], instance: ObjectInstance) -> Optional[str]:
    for p in paths:
        # Ignore .trend paths for unknown checks
        base = p[:-6] if p.endswith(".trend") else p
        try:
            ai = AttributeTarget.from_string(base).resolve(instance)
        except Exception:
            continue
        if isinstance(ai.current_value, str) and ai.current_value == "unknown":
            return base
    return None


def generate_minimal_case_text(
    *,
    registries: RegistryManager,
    object_type: str,
    action_name: str,
    instance: ObjectInstance,
    case_id: Optional[str] = None,
) -> str:
    """Generate a minimal-context benchmark case as a single string block.

    Assumes 'instance' may have unknowns injected externally (e.g., via CLI).
    """
    action = registries.create_behavior_enhanced_action(object_type, action_name)
    if not action:
        raise KeyError(f"Action not found for {object_type}.{action_name}")

    engine = TransitionEngine(registries)
    # Attempt once to capture clarifications (if any)
    result = engine.apply_action(instance, action, {})

    relevant = sorted(get_relevant_attributes(action))

    # Decide which attribute to clarify
    clarify_attr: Optional[str] = None
    if result.clarifications:
        # Expect questions like "What is battery.level?"
        for q in result.clarifications:
            q = q.strip()
            if q.lower().startswith("what is ") and q.endswith("?"):
                clarify_attr = q[len("What is ") : -1].strip()
                break
    if not clarify_attr:
        clarify_attr = _first_unknown_in_instance(relevant, instance)

    # Compose prompt
    prompt = f"I have a {object_type}. I try to {_nl_action(action_name)}."

    lines: List[str] = []
    lines.append("=== BENCHMARK TEST CASE ===")
    lines.append(f"ID: {case_id or f'{object_type}_{action_name}_minimal'}")
    lines.append(f"PROMPT: \"{prompt}\"")

    if clarify_attr:
        # Determine options from the attribute's qualitative space
        ai = AttributeTarget.from_string(clarify_attr).resolve(instance)
        space = registries.spaces.get(ai.spec.space_id)
        nice_attr = clarify_attr.replace(".", " ")
        lines.append(f"CLARIFICATION_NEEDED: \"What is {nice_attr}?\"")
        quoted_options = ", ".join([f'\"{o}\"' for o in space.levels])
        lines.append(f"OPTIONS: [{quoted_options}]")

        # Simulate each option
        lines.append("")
        lines.append("EXPECTED_RESPONSES:")
        for opt in space.levels:
            # Copy instance and set the chosen option
            test_inst = instance.model_copy(deep=True)
            tai = AttributeTarget.from_string(clarify_attr).resolve(test_inst)
            tai.current_value = opt
            tai.confidence = 1.0
            r = engine.apply_action(test_inst, action, {})
            desc = _format_changes(r)
            lines.append(f"{opt}: \"{desc}\"")

        # LLM test: what do you need to know?
        lines.append("")
        lines.append("=== LLM TEST ===")
        lines.append(f"QUESTION: \"{prompt} What will happen?\"")
        lines.append(f"CLARIFICATION_NEEDED: \"What is {nice_attr}?\"")
    else:
        # No clarification needed; describe expected outcome directly
        desc = _format_changes(result)
        lines.append("")
        lines.append("EXPECTED:")
        lines.append(f"\"{desc}\"")

    return "\n".join(lines) + "\n"
