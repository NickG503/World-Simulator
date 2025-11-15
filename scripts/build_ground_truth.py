#!/usr/bin/env python3
"""Run a fully observable simulation and save an enriched ground-truth history.

This script executes a sequence of actions for an object, automatically answers
clarification prompts using predefined values, and writes the resulting history
into ``tests/data/ground_truth`` (or a custom destination) using the same format
consumed by the regression tests.

Example usage:

    python scripts/build_ground_truth.py \
        --object flashlight \
        --simulation-id flashlight_battery_trend_low \
        --output tests/data/ground_truth/flashlight_battery_trend_low.yaml \
        --hide battery.level \
        --answer battery.level=empty \
        replace_battery:to=low turn_on turn_off turn_on

Notes:
- Use ``action:param=value`` syntax for inline parameters. Separate multiple
  parameters with commas (e.g. ``stream_hd:wifi=on,quality=high``).
- Provide ``--answer attr=value`` for every clarification prompt the simulator
  will ask. The values are consumed in the order provided.
- ``--initial attr=value`` can be repeated to override default object values
  before the run begins.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

from simulator.core.engine.transition_engine import TransitionEngine
from simulator.core.objects.part import AttributeTarget
from simulator.core.registries import RegistryManager
from simulator.io.loaders.action_loader import load_actions
from simulator.io.loaders.object_loader import instantiate_default, load_object_types
from simulator.io.loaders.yaml_loader import load_spaces


def _parse_attr_assignment(text: str) -> tuple[str, str]:
    if "=" not in text:
        raise argparse.ArgumentTypeError(f"Expected attr=value assignment, got: {text}")
    attr, value = text.split("=", 1)
    attr = attr.strip()
    value = value.strip()
    if not attr or not value:
        raise argparse.ArgumentTypeError(f"Invalid assignment: {text}")
    return attr, value


def _parse_action(token: str) -> Dict[str, Any]:
    name, _, param_str = token.partition(":")
    name = name.strip()
    if not name:
        raise argparse.ArgumentTypeError(f"Invalid action token: {token}")
    params: Dict[str, str] = {}
    if param_str:
        for part in param_str.split(","):
            part = part.strip()
            if not part:
                continue
            key, value = _parse_attr_assignment(part)
            params[key] = value
    return {"name": name, "parameters": params}


def _capture_snapshot(instance) -> Dict[str, Any]:
    parts: Dict[str, Any] = {}
    for part_name, part in instance.parts.items():
        attrs: Dict[str, Any] = {}
        for attr_name, attr in part.attributes.items():
            attrs[attr_name] = {
                "value": attr.current_value,
                "trend": attr.trend,
                "confidence": attr.confidence,
                "last_known_value": attr.last_known_value,
                "last_trend_direction": attr.last_trend_direction,
                "space_id": attr.spec.space_id,
            }
        parts[part_name] = {"attributes": attrs}

    global_attrs: Dict[str, Any] = {}
    for attr_name, attr in instance.global_attributes.items():
        global_attrs[attr_name] = {
            "value": attr.current_value,
            "trend": attr.trend,
            "confidence": attr.confidence,
            "last_known_value": attr.last_known_value,
            "last_trend_direction": attr.last_trend_direction,
            "space_id": attr.spec.space_id,
        }

    return {"type": instance.type.name, "parts": parts, "global_attributes": global_attrs}


def _collect_paths(snapshot: Dict[str, Any], out: set[str]) -> None:
    for part_name, part in (snapshot.get("parts") or {}).items():
        for attr_name in (part.get("attributes") or {}).keys():
            out.add(f"{part_name}.{attr_name}")
    for attr_name in (snapshot.get("global_attributes") or {}).keys():
        out.add(attr_name)


def _base_attribute(reference: str) -> str:
    if reference.endswith(".trend"):
        return reference[: -len(".trend")]
    return reference


def _set_attribute(instance, reference: str, value: str) -> None:
    target = AttributeTarget.from_string(reference).resolve(instance)
    target.current_value = value
    target.confidence = 1.0
    target.last_known_value = value
    target.last_trend_direction = None


def _parse_question(question: str) -> str | None:
    text = question.strip()
    lower = text.lower()
    if lower.startswith("precondition: what is ") and text.endswith("?"):
        return text[len("Precondition: what is ") : -1].strip()
    if lower.startswith("postcondition: what is ") and text.endswith("?"):
        return text[len("Postcondition: what is ") : -1].strip()
    if lower.startswith("what is ") and text.endswith("?"):
        return text[len("What is ") : -1].strip()
    return None


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a ground-truth simulation history")
    parser.add_argument("actions", nargs="+", help="Action tokens (use name:param=value for parameters)")
    parser.add_argument("--object", required=True, help="Object type to simulate")
    parser.add_argument("--simulation-id", help="Identifier for the simulation run")
    parser.add_argument(
        "--output",
        type=Path,
        help="Destination YAML file (defaults to tests/data/ground_truth/<simulation_id>.yaml)",
    )
    parser.add_argument("--initial", action="append", default=[], help="attr=value overrides before simulation")
    parser.add_argument(
        "--answer",
        action="append",
        dest="answers",
        default=[],
        help="Provide an answer for a clarification prompt (attr=value). Use multiple times for repeated prompts.",
    )
    parser.add_argument(
        "--hide",
        action="append",
        default=[],
        help="Attribute references to mark as hidden when replaying this history",
    )
    parser.add_argument(
        "--track",
        action="append",
        default=[],
        help="Force specific attributes to appear in the tracked set",
    )
    return parser


def _load_registries() -> RegistryManager:
    rm = RegistryManager()
    rm.register_defaults()
    kb_root = Path.cwd() / "kb"
    load_spaces(str(kb_root / "spaces"), rm)
    load_object_types(str(kb_root / "objects"), rm)
    load_actions(str(kb_root / "actions"), rm)
    return rm


def _ensure_output_path(path: Path | None, simulation_id: str) -> Path:
    if path is not None:
        return path
    dest = Path("tests/data/ground_truth") / f"{simulation_id}.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


def _build_output_dict(
    *,
    args,
    steps: List[Dict[str, Any]],
    initial_snapshot: Dict[str, Any],
    interactions: List[Dict[str, Any]],
    tracked_paths: Iterable[str],
) -> Dict[str, Any]:
    hidden = set(args.hide or [])
    metadata = {
        "tracked_attributes": sorted(set(tracked_paths) - hidden),
        "hidden_attributes": sorted(hidden),
    }
    return {
        "history_version": 3,
        "simulation_id": args.simulation_id,
        "object_name": args.object,
        "started_at": date.today().isoformat(),
        "total_steps": len(steps),
        "initial_state": initial_snapshot,
        "steps": steps,
        "interactions": interactions,
        "metadata": metadata,
    }


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    if not args.actions:
        raise SystemExit("At least one action is required")

    if not args.simulation_id:
        action_label = args.actions[0].split(":", 1)[0]
        args.simulation_id = f"{args.object}_{action_label}"

    output_path = _ensure_output_path(args.output, args.simulation_id)

    rm = _load_registries()
    obj_type = rm.objects.get(args.object)
    instance = instantiate_default(obj_type, rm)

    for assignment in args.initial or []:
        ref, value = _parse_attr_assignment(assignment)
        _set_attribute(instance, ref, value)

    action_specs = [_parse_action(token) for token in args.actions]

    answers = defaultdict(list)
    for assignment in args.answers or []:
        ref, value = _parse_attr_assignment(assignment)
        answers[ref].append(value)

    engine = TransitionEngine(rm)
    steps: List[Dict[str, Any]] = []
    interactions: List[Dict[str, Any]] = []
    tracked_paths = set(args.track or [])

    initial_snapshot = _capture_snapshot(instance)
    _collect_paths(initial_snapshot, tracked_paths)

    current_instance = instance

    for index, spec in enumerate(action_specs):
        action = rm.create_behavior_enhanced_action(args.object, spec["name"])
        if not action:
            raise SystemExit(f"Action '{spec['name']}' not found for object '{args.object}'")

        result = engine.apply_action(current_instance, action, spec["parameters"])

        while result.status == "rejected" and getattr(result, "clarifications", None):
            answered_any = False
            for question in result.clarifications:
                if question.startswith("[INFO]"):
                    continue
                attr_ref = _parse_question(question)
                if not attr_ref:
                    continue
                queue = answers.get(attr_ref)
                if not queue:
                    raise SystemExit(f"No answer provided for attribute '{attr_ref}' (question: {question})")
                picked = queue.pop(0)
                _set_attribute(current_instance, attr_ref, picked)
                space_levels: List[str] = []
                try:
                    target = AttributeTarget.from_string(attr_ref).resolve(current_instance)
                    if target.spec.space_id:
                        space = rm.spaces.get(target.spec.space_id)
                        if space and getattr(space, "levels", None):
                            space_levels = list(space.levels)
                except Exception:
                    pass
                interactions.append(
                    {
                        "step": index,
                        "action": spec["name"],
                        "attribute": attr_ref,
                        "question": question,
                        "answer": picked,
                        "options": space_levels,
                    }
                )
                tracked_paths.add(attr_ref)
                answered_any = True
            if not answered_any:
                raise SystemExit(
                    f"Clarifications for action '{spec['name']}' could not be answered: {result.clarifications}"
                )
            result = engine.apply_action(current_instance, action, spec["parameters"])

        if result.status != "ok" or not result.after:
            raise SystemExit(f"Action '{spec['name']}' failed: {result.reason}")

        current_instance = result.after
        for change in result.changes:
            attr_name = change.attribute or ""
            if attr_name and not attr_name.startswith("["):
                tracked_paths.add(_base_attribute(attr_name))

        visible_changes = []
        for c in result.changes:
            attr_name = c.attribute or ""
            if c.kind == "info" or attr_name.startswith("["):
                continue
            visible_changes.append(
                {
                    "attribute": c.attribute,
                    "before": c.before,
                    "after": c.after,
                    "kind": c.kind,
                }
            )

        steps.append(
            {
                "step_number": index,
                "action_name": spec["name"],
                "parameters": spec["parameters"],
                "status": result.status,
                "error": result.reason,
                "changes": visible_changes,
            }
        )

    history_dict = _build_output_dict(
        args=args,
        steps=steps,
        initial_snapshot=initial_snapshot,
        interactions=interactions,
        tracked_paths=tracked_paths,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as handle:
        yaml.safe_dump(history_dict, handle, sort_keys=False)

    print(f"Saved ground truth to {output_path}")


if __name__ == "__main__":
    main()
