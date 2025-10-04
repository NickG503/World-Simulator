from __future__ import annotations

"""Sequential dataset builder for multi-action minimal stories.

Builds a single text block that:
- Lists a minimal story of attempted actions
- If an unknown-dependent precondition appears, captures a clarification question and options
- Provides expected outcomes per option by simulating from the start up to the failing action
"""

import re
from typing import Dict, List, Optional, Tuple

from simulator.core.engine.transition_engine import TransitionEngine
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.registries.registry_manager import RegistryManager
from simulator.core.actions.action import Action
from simulator.core.dataset.minimal_context import _nl_action, _format_changes
from simulator.core.objects.part import AttributeTarget


_ATTR_PATH_PATTERN = re.compile(r"([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)")


def _humanize_attribute_paths(text: Optional[str]) -> str:
    if not text:
        return ""

    def _repl(match: re.Match[str]) -> str:
        attr = match.group(0)
        parts = [segment.replace("_", " ") for segment in attr.split(".")]
        return " ".join(parts)

    return _ATTR_PATH_PATTERN.sub(_repl, text)


def _extract_attr_from_question(q: str) -> Optional[str]:
    qs = q.strip()
    if qs.lower().startswith("what is ") and qs.endswith("?"):
        return qs[len("What is "):-1].strip()
    return None


def _apply_action(engine: TransitionEngine, inst: ObjectInstance, act: Action) -> Tuple[ObjectInstance, str, Optional[List[str]]]:
    res = engine.apply_action(inst, act, {})
    clar = getattr(res, "clarifications", None)
    return (res.after if res.after else inst, res.status, clar)


def build_sequential_dataset_text(
    *,
    registries: RegistryManager,
    object_type: str,
    actions: List[Dict],  # {name: str, parameters?: dict}
    instance: ObjectInstance,
    case_id: Optional[str] = None,
) -> str:
    action_names = [a.get("name") for a in actions]
    # Build a single, fluent line with sequential connectors
    if action_names:
        parts: List[str] = []
        for i, name in enumerate(action_names):
            if i == 0:
                parts.append(f"I try to {_nl_action(name)}")
            else:
                parts.append(f"and then I try to {_nl_action(name)}")
        story_text = f"I have a {object_type}. " + ", ".join(parts) + "."
    else:
        story_text = f"I have a {object_type}."

    engine = TransitionEngine(registries)
    # walk from the start to find first unknown-dependent failure
    cur = instance.model_copy(deep=True)
    failing_index = None
    failing_attr: Optional[str] = None
    for idx, spec in enumerate(actions):
        act = registries.create_behavior_enhanced_action(object_type, spec.get("name"))
        if not act:
            continue
        res = engine.apply_action(cur, act, spec.get("parameters") or {})
        if res.status != "ok":
            clar = getattr(res, "clarifications", None) or []
            for q in clar:
                failing_attr = _extract_attr_from_question(q)
                if failing_attr:
                    failing_index = idx
                    break
            if failing_index is not None:
                break
        else:
            if res.after:
                cur = res.after

    lines: List[str] = []
    lines.append("=== DATASET CASE ===")
    lines.append(f"ID: {case_id or f'{object_type}_sequence'}")
    lines.append("STORY:")
    lines.append(story_text)

    if failing_index is not None and failing_attr is not None:
        # Prepare options from space
        ai = AttributeTarget.from_string(failing_attr).resolve(instance)
        space = registries.spaces.get(ai.spec.space_id)
        nice_attr = _humanize_attribute_paths(failing_attr)
        lines.append("")
        lines.append(f"QUESTION: \"Given the story, what will happen?\"")
        lines.append(f"CLARIFICATION_NEEDED: \"What is {nice_attr}?\"")
        quoted_options = ", ".join([f'\"{o}\"' for o in space.levels])
        lines.append(f"OPTIONS: [{quoted_options}]")

        # For each option, simulate from the start up to failing action with that value injected
        lines.append("")
        lines.append("EXPECTED_RESPONSES:")
        for opt in space.levels:
            # fresh start
            cur2 = instance.model_copy(deep=True)
            # Apply actions before failing step
            for j in range(failing_index):
                a = registries.create_behavior_enhanced_action(object_type, actions[j].get("name"))
                if not a:
                    continue
                rj = engine.apply_action(cur2, a, actions[j].get("parameters") or {})
                if rj.after:
                    cur2 = rj.after
            # Inject the chosen option
            tai = AttributeTarget.from_string(failing_attr).resolve(cur2)
            tai.current_value = opt
            tai.confidence = 1.0
            # Apply the failing step
            a_fail = registries.create_behavior_enhanced_action(object_type, actions[failing_index].get("name"))
            rf = engine.apply_action(cur2, a_fail, actions[failing_index].get("parameters") or {})
            desc = _format_changes(rf)
            lines.append(f"{opt}: \"{desc}\"")
    else:
        # No clarifications needed across the sequence
        lines.append("")
        lines.append(f"QUESTION: \"Given the story, what will happen?\"")
        lines.append("EXPECTED: \"The action sequence completes without clarifications.\"")

    return "\n".join(lines) + "\n"


def build_interactive_dataset_text(history) -> str:
    """Build a dataset block from an interactive run, including Q/A and results.

    Expects a SimulationHistory with steps and optional 'interactions' list.
    """
    lines: List[str] = []
    lines.append("=== DATASET RUN ===")
    lines.append(f"ID: {history.simulation_id}")
    # Minimal story of attempted actions
    # Build a single, fluent line with sequential connectors
    action_names: List[str] = [st.action_name for st in history.steps]
    if action_names:
        parts2: List[str] = []
        for i, name in enumerate(action_names):
            if i == 0:
                parts2.append(f"I try to {_nl_action(name)}")
            else:
                parts2.append(f"and then I try to {_nl_action(name)}")
        story_line = f"I have a {history.object_type}. " + ", ".join(parts2) + "."
    else:
        story_line = f"I have a {history.object_type}."
    lines.append("STORY:")
    lines.append(story_line)

    # Insert clarifications with answers
    if getattr(history, "interactions", None):
        lines.append("")
        lines.append("CLARIFICATIONS:")
        for ev in history.interactions:
            q = _humanize_attribute_paths(ev.get("question"))
            a = ev.get("answer")
            step = ev.get("step")
            act = _nl_action(ev.get("action", ""))
            lines.append(f"- step {step} ({act}): Q: \"{q}\" A: \"{a}\"")

    # Summarize per-step results
    lines.append("")
    lines.append("RESULTS:")
    for st in history.steps:
        human_action = _nl_action(st.action_name)
        if st.status != "ok":
            message = _humanize_attribute_paths(st.error_message)
            lines.append(f"- {human_action}: FAILED — {message or 'unknown error'}")
        elif st.changes:
            # reuse formatter from minimal context
            class _Tmp:
                changes = st.changes
                status = st.status
                reason = st.error_message
            lines.append(f"- {human_action}: {_format_changes(_Tmp)}")
        else:
            lines.append(f"- {human_action}: no visible changes")

    return "\n".join(lines) + "\n"
