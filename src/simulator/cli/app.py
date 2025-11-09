from __future__ import annotations

import logging
import re
from typing import Dict, Optional

import typer
from rich.console import Console
from rich.table import Table
from typer.core import TyperCommand

from simulator.cli.formatters import (
    build_changes_table,
    build_object_definition_table,
    format_constraint,
)
from simulator.cli.load_helpers import load_or_exit
from simulator.cli.paths import (
    kb_actions_path,
    kb_objects_path,
    kb_spaces_path,
    resolve_history_path,
    resolve_result_path,
)
from simulator.cli.services import apply_action, run_simulation
from simulator.core.dataset.sequential_dataset import build_interactive_dataset_text
from simulator.core.engine.transition_engine import TransitionResult
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.registries import RegistryManager
from simulator.core.registries.validators import RegistryValidator
from simulator.io.loaders.action_loader import load_actions
from simulator.io.loaders.object_loader import load_object_types
from simulator.io.loaders.yaml_loader import load_spaces

app = typer.Typer(help="Simulator CLI: validate knowledge base, inspect objects, and run actions.")
console = Console()


_ATTR_PATH_PATTERN = re.compile(r"([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)")


def _humanize_attr_paths(text: str | None) -> str:
    if not text:
        return ""

    def _repl(match: re.Match[str]) -> str:
        parts = [segment.replace("_", " ") for segment in match.group(0).split(".")]
        return " ".join(parts)

    return _ATTR_PATH_PATTERN.sub(_repl, text)


_KNOWN_VALUE_OPTIONS = {"--obj", "--name", "--objs-path", "--acts-path"}
_KNOWN_BOOL_OPTIONS = {"--verbose-load"}


def _normalize_action_tokens(raw_args: list[str]) -> list[str]:
    """Allow positional actions while remaining compatible with legacy --actions usage."""
    option_tokens: list[str] = []
    action_tokens: list[str] = []

    length = len(raw_args)
    i = 0
    while i < length:
        token = raw_args[i]

        if token == "--":
            option_tokens.extend(raw_args[i:])
            break

        if token == "--actions":
            i += 1
            continue

        if token.startswith("--actions="):
            _, value = token.split("=", 1)
            if value:
                action_tokens.append(value)
            i += 1
            continue

        opt_name, eq, opt_value = token.partition("=")
        if opt_name in _KNOWN_VALUE_OPTIONS:
            if eq:
                option_tokens.append(token)
            else:
                option_tokens.append(token)
                if i + 1 < length:
                    option_tokens.append(raw_args[i + 1])
                    i += 1
            i += 1
            continue

        if opt_name in _KNOWN_BOOL_OPTIONS:
            option_tokens.append(opt_name)
            i += 1
            continue

        action_tokens.append(token)
        i += 1

    return option_tokens + action_tokens


def _infer_inline_param_name(rm: RegistryManager, object_name: str, action_name: str) -> tuple[str | None, str | None]:
    """Infer which parameter should receive an inline value for an action.

    Returns (parameter_name, error_message).
    """

    try:
        action_spec = rm.find_action_for_object(object_name, action_name)
    except Exception:  # pragma: no cover - defensive guard
        action_spec = None

    if not action_spec:
        return None, f"[red]Unknown action[/red]: {action_name}"

    params = getattr(action_spec, "parameters", {}) or {}
    if not params:
        return None, f"[red]Action '{action_name}' does not accept parameters[/red]"

    required = [name for name, spec in params.items() if getattr(spec, "required", False)]

    if len(params) == 1:
        return next(iter(params.keys())), None

    if len(required) == 1:
        return required[0], None

    return None, (
        f"[red]Action '{action_name}' has multiple parameters[/red]. Use the explicit syntax 'action:param=value'."
    )


class _SimulateCommand(TyperCommand):
    def parse_args(self, ctx, args):
        return super().parse_args(ctx, _normalize_action_tokens(list(args)))


def _load_registries(
    objs: str | None,
    acts: str | None,
    *,
    verbose_load: bool = False,
) -> RegistryManager:
    rm = RegistryManager()
    load_or_exit(load_spaces, kb_spaces_path(None), rm, console=console, verbose_errors=verbose_load)
    rm.register_defaults()
    load_or_exit(load_object_types, kb_objects_path(objs), rm, console=console, verbose_errors=verbose_load)
    load_or_exit(load_actions, kb_actions_path(acts), rm, console=console, verbose_errors=verbose_load)
    return rm


def _render_constraints(obj) -> None:
    if not obj.constraints:
        return
    console.print(f"\n[bold]Constraints ({len(obj.constraints)}):[/bold]")
    for idx, constraint in enumerate(obj.constraints, start=1):
        console.print(f"  {idx}. {format_constraint(constraint)}")


def _render_changes(result: TransitionResult) -> None:
    if result.changes:
        console.print(build_changes_table(result))
    elif result.status == "ok":
        console.print("\n[dim]No changes made[/dim]")
    if getattr(result, "clarifications", None):
        console.print(f"\n[yellow]Clarifications needed ({len(result.clarifications)}):[/yellow]")
        for q in result.clarifications:
            console.print(f"  • {q}")


def _render_instance_state(title: str, instance: ObjectInstance) -> None:
    table = Table(title=title)
    table.add_column("Attribute")
    table.add_column("Value")
    table.add_column("Trend")

    for part_name, part in instance.parts.items():
        for attr_name, attr in part.attributes.items():
            table.add_row(
                f"{part_name}.{attr_name}",
                str(attr.current_value),
                str(attr.trend or "none"),
            )

    for attr_name, attr in instance.global_attributes.items():
        table.add_row(
            attr_name,
            str(attr.current_value),
            str(attr.trend or "none"),
        )

    console.print(table)


def _render_snapshot(title: str, snapshot) -> None:
    table = Table(title=title)
    table.add_column("Attribute")
    table.add_column("Value")
    table.add_column("Trend")

    for part_name, part in snapshot.parts.items():
        for attr_name, attr in part.attributes.items():
            table.add_row(
                f"{part_name}.{attr_name}",
                str(attr.value),
                str(attr.trend or "none"),
            )

    for attr_name, attr in snapshot.global_attributes.items():
        table.add_row(
            attr_name,
            str(attr.value),
            str(attr.trend or "none"),
        )

    console.print(table)


@app.command()
def validate(
    objs: str | None = typer.Argument(None, help="Path to kb/objects folder"),
    acts: str | None = typer.Option(None, help="Path to kb/actions folder"),
    verbose: bool = typer.Option(False, "--verbose-load", help="Display full validation trace on loader errors"),
) -> None:
    rm = _load_registries(objs, acts, verbose_load=verbose)

    console.print(f"[green]OK[/green] Loaded {len(list(rm.objects.all()))} object type(s)")
    console.print(f"[green]OK[/green] Loaded {len(rm.actions.items)} action(s)")

    errors = RegistryValidator(rm).validate_all()
    if errors:
        console.print("[red]Validation errors detected:[/red]")
        for error in errors:
            console.print(f" - {error}")
        raise typer.Exit(code=1)

    console.print("[green]All validations passed[/green]")


@app.command("show")
def show_object(
    what: str = typer.Argument(..., help="What to show: 'object' or 'behaviors'"),
    name: str = typer.Argument(..., help="Object type name"),
    path: str | None = typer.Option(None, help="Path to kb/objects folder"),
    verbose: bool = typer.Option(False, "--verbose-load", help="Display full validation trace on loader errors"),
) -> None:
    rm = RegistryManager()
    load_or_exit(load_spaces, kb_spaces_path(None), rm, console=console, verbose_errors=verbose)
    rm.register_defaults()
    load_or_exit(load_object_types, kb_objects_path(path), rm, console=console, verbose_errors=verbose)

    try:
        obj = rm.objects.get(name)
    except KeyError:
        console.print(f"[red]Object type not found[/red]: {name}")
        raise typer.Exit(code=2)

    if what == "behaviors":
        behaviours = sorted(obj.behaviors.keys())
        console.print(f"\n[bold]Behaviors for {name}:[/bold]")
        if behaviours:
            for behaviour in behaviours:
                console.print(f"  ✓ {behaviour}")
        else:
            console.print("  [dim]No behaviors defined[/dim]")
        return

    if what != "object":
        console.print("[red]Supported options[/red]: 'object', 'behaviors'")
        raise typer.Exit(code=2)

    console.print(f"[bold]{obj.name}[/bold] (Object Type)")
    attr_count = sum(len(part.attributes) for part in obj.parts.values()) + len(obj.global_attributes)
    console.print(f"Parts: {len(obj.parts)}, Attributes: {attr_count}, Constraints: {len(obj.constraints)}")
    console.print(build_object_definition_table(obj, rm))
    _render_constraints(obj)


@app.command()
def apply(
    object_name: str = typer.Argument(..., help="Object type name"),
    action_name: str = typer.Argument(..., help="Action name"),
    params: list[str] = typer.Option([], "--param", "-p", help="key=value pairs"),
    full: bool = typer.Option(False, "--full", help="Show full object states"),
    no_interactive: bool = typer.Option(False, "--no-interactive", help="Skip prompts for unknown values"),
    objs: str | None = typer.Option(None, help="Path to kb/objects folder"),
    acts: str | None = typer.Option(None, help="Path to kb/actions folder"),
    verbose: bool = typer.Option(False, "--verbose-load", help="Display full validation trace on loader errors"),
) -> None:
    rm = _load_registries(objs, acts, verbose_load=verbose)

    param_map: Dict[str, str] = {}
    for item in params:
        if "=" not in item:
            console.print(f"[red]Bad --param[/red] (expected key=value): {item}")
            raise typer.Exit(code=2)
        key, value = item.split("=", 1)
        param_map[key.strip()] = value.strip()

    obj_type, action, instance, result = apply_action(
        rm,
        object_name,
        action_name,
        param_map,
        console,
        interactive=not no_interactive,
    )

    if action is None or result is None or instance is None:
        console.print(f"[red]No action found[/red] for {object_name}.{action_name}")
        raise typer.Exit(code=1)

    if action_name in obj_type.behaviors:
        console.print(f"[cyan]Using object-specific behavior for[/cyan] {object_name}.{action_name}")
    else:
        console.print(f"[yellow]Using generic behavior for[/yellow] {object_name}.{action_name}")

    if full:
        console.print("\n[bold]Full Result[/bold]:")
        console.print_json(data=result.model_dump())
    else:
        status_color = "green" if result.status == "ok" else "red" if result.status == "rejected" else "yellow"
        console.print(f"\n[bold]Status:[/bold] [{status_color}]{result.status}[/{status_color}]")
        if result.reason:
            console.print(f"[bold]Reason:[/bold] {result.reason}")

    if result.violations:
        console.print(f"\n[red bold]⚠️  Constraint Violations ({len(result.violations)}):[/red bold]")
        for violation in result.violations:
            console.print(f"  • {violation}")

    _render_changes(result)

    if full and instance is not None:
        _render_instance_state("Resulting state", instance)


@app.command(cls=_SimulateCommand)
def simulate(
    obj: str = typer.Option(..., "--obj", help="Object type to simulate"),
    actions: list[str] = typer.Argument(..., help="Actions to execute (use action=value for inline parameters)"),
    run_name: str | None = typer.Option(
        None, "--name", help="Name for history and result files (auto-generated if not provided)"
    ),
    objs: str | None = typer.Option(None, "--objs-path", help="Path to kb/objects folder"),
    acts: str | None = typer.Option(None, "--acts-path", help="Path to kb/actions folder"),
    verbose_load: bool = typer.Option(False, "--verbose-load", help="Display full validation trace on loader errors"),
) -> None:
    rm = _load_registries(objs, acts, verbose_load=verbose_load)

    action_specs: list[dict] = []
    for action_str in actions:
        if ":" in action_str:
            console.print("[red]Colon syntax is no longer supported.[/red] Use 'action=value' for inline parameters.")
            raise typer.Exit(code=2)

        if "=" in action_str:
            action_name_raw, inline_value = action_str.split("=", 1)
            action_name = action_name_raw.strip()
            value = inline_value.strip()
            if not value:
                console.print(f"[red]Bad action value[/red]: expected 'action=value', got '{action_str}'")
                raise typer.Exit(code=2)

            param_name, error_message = _infer_inline_param_name(rm, obj, action_name)
            if error_message:
                console.print(error_message)
                raise typer.Exit(code=2)

            action_specs.append({"name": action_name, "parameters": {param_name: value}})
        else:
            action_specs.append({"name": action_str.strip(), "parameters": {}})

    def _resolve_parameter(action_name: str, param_name: str, param_spec) -> str:
        choices = getattr(param_spec, "choices", None) or []
        if choices:
            console.print(f"\n[yellow]Select value for {action_name} ({param_name}):[/yellow]")
            for idx, choice in enumerate(choices, start=1):
                console.print(f"  {idx}. {choice}")
            while True:
                user_input = console.input(f"Enter choice (1-{len(choices)}): ").strip()
                if user_input.isdigit():
                    idx = int(user_input)
                    if 1 <= idx <= len(choices):
                        return choices[idx - 1]
                console.print("[red]Invalid selection. Try again.[/red]")

        prompt_label = f"Enter value for {action_name} ({param_name}): "
        while True:
            value = console.input(prompt_label).strip()
            if value:
                return value
            console.print("[red]Value cannot be empty.[/red]")

    # Always enable verbose output to show real-time progress
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Use provided name or auto-generate
    simulation_name = run_name if run_name else None

    history, runner = run_simulation(
        rm,
        obj,
        action_specs,
        simulation_name,
        verbose=True,
        interactive=True,
        unknown_paths=None,
        parameter_resolver=_resolve_parameter,
    )

    # Save history under outputs/histories
    history_path = resolve_history_path(history.simulation_id)
    runner.save_history_to_yaml(history, history_path)

    # Also build and save a result text to outputs/results
    result_path = resolve_result_path(history.simulation_id)
    text = build_interactive_dataset_text(history)
    from pathlib import Path as _P

    _p = _P(result_path)
    _p.parent.mkdir(parents=True, exist_ok=True)
    _p.write_text(text, encoding="utf-8")

    failed_steps = history.get_failed_steps()
    if failed_steps:
        console.print("\n[red]Failed actions detected:[/red]")
        for step in failed_steps:
            action_label = step.action_name.replace("_", " ")
            reason = _humanize_attr_paths(getattr(step, "error_message", "") or "unknown error")
            console.print(f"  • {action_label} — {reason}")

    console.print("\n[bold]Simulation Summary[/bold]")
    console.print(f"Name: {history.simulation_id}")
    console.print(f"Saved history: {history_path}")
    console.print(f"Saved result: {result_path}")

    successful = len(history.get_successful_steps())
    failed = len(failed_steps)
    if successful:
        console.print(f"✅ Successful actions: {successful}")
    if failed:
        console.print(f"❌ Failed actions: {failed}")


@app.command()
def history(
    file_path: str = typer.Argument(
        ...,
        help="History name or path (bare names resolve to outputs/histories/<name>.yaml automatically)",
    ),
    step: Optional[int] = typer.Option(None, "--step", "-s", help="Show detailed table for a specific step"),
    all_steps: bool = typer.Option(False, "--all", "-a", help="Show detailed tables for every step"),
) -> None:
    from simulator.cli.paths import find_history_file
    from simulator.core.simulation_runner import SimulationRunner

    # Smart path resolution: accepts full path or just filename
    try:
        resolved_path = find_history_file(file_path)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    rm = RegistryManager()

    # Load KB for space definitions (needed for constrained options display)
    try:
        from simulator.cli.paths import kb_actions_path, kb_objects_path, kb_spaces_path
        from simulator.io.loaders.action_loader import load_actions
        from simulator.io.loaders.object_loader import load_object_types
        from simulator.io.loaders.yaml_loader import load_spaces

        load_spaces(kb_spaces_path(None), rm)
        rm.register_defaults()
        load_object_types(kb_objects_path(None), rm)
        load_actions(kb_actions_path(None), rm)
    except Exception:
        pass  # KB loading failed, constrained options won't be shown

    if all_steps and step is not None:
        console.print("[red]Cannot use --all and --step together.[/red]")
        raise typer.Exit(code=2)

    runner = SimulationRunner(rm)
    try:
        history_obj = runner.load_history_from_yaml(resolved_path)
    except Exception as exc:
        console.print(f"[red]Error loading history file[/red]: {exc}")
        raise typer.Exit(code=1)

    console.print(f"[bold]Simulation History[/bold]: {history_obj.simulation_id}")
    console.print(f"Object: {history_obj.object_type}")
    console.print(f"Total steps: {history_obj.total_steps}")
    console.print(f"Date: {history_obj.started_at}")

    table = Table(title="Step Summary")
    table.add_column("Step")
    table.add_column("Action")
    table.add_column("Status")
    table.add_column("Changes")
    for step_obj in history_obj.steps:
        status_color = "green" if step_obj.status == "ok" else "red"
        table.add_row(
            str(step_obj.step_number),
            step_obj.action_name,
            f"[{status_color}]{step_obj.status}[/{status_color}]",
            str(len(step_obj.changes)),
        )
    console.print(table)

    # Print inline errors for any failed steps
    for step_obj in history_obj.steps:
        if step_obj.status != "ok" and step_obj.error_message:
            console.print(
                f"[red]Step {step_obj.step_number} '{step_obj.action_name}' failed:[/red] {step_obj.error_message}"
            )

    def _render_step_detail(target_step):
        console.print("")
        console.print(f"[bold]Step {target_step.step_number} Detail[/bold]: {target_step.action_name}")
        status_color = "green" if target_step.status == "ok" else "red"
        console.print(f"Status: [{status_color}]{target_step.status}[/{status_color}]")
        if target_step.error_message:
            console.print(f"Error: {target_step.error_message}")

        if target_step.changes:
            detail_table = Table(title=f"Step {target_step.step_number} Changes")
            detail_table.add_column("Attribute")
            detail_table.add_column("Before")
            detail_table.add_column("After")
            detail_table.add_column("Kind")

            def resolve_snapshot_attr(snapshot, attr_path: str):
                """Find the AttributeSnapshot for a change path."""
                if snapshot is None or not attr_path or attr_path.startswith("["):
                    return None
                parts = attr_path.split(".")
                if parts and parts[-1] == "trend":
                    parts = parts[:-1]
                if not parts:
                    return None

                if len(parts) == 1:
                    return (snapshot.global_attributes or {}).get(parts[0])

                part_name = parts[0]
                attr_name = ".".join(parts[1:])
                part_state = (snapshot.parts or {}).get(part_name)
                if not part_state:
                    return None
                return part_state.attributes.get(attr_name)

            def describe_value(raw_value, snapshot_attr):
                """Format change value, showing constrained options for unknowns."""
                if raw_value is None:
                    return "—"
                if raw_value != "unknown" or snapshot_attr is None:
                    return str(raw_value)

                direction = snapshot_attr.last_trend_direction or snapshot_attr.trend
                if direction in ("up", "down") and snapshot_attr.last_known_value and snapshot_attr.space_id:
                    try:
                        space = rm.spaces.get(snapshot_attr.space_id)
                        constrained = space.constrained_levels(
                            last_known_value=snapshot_attr.last_known_value,
                            trend=direction,
                        )
                        if constrained:
                            return ", ".join(constrained)
                    except Exception:
                        pass
                return "unknown"

            for change in target_step.changes:
                before_attr = resolve_snapshot_attr(target_step.object_state_before, change.attribute or "")
                after_attr = resolve_snapshot_attr(target_step.object_state_after, change.attribute or "")
                before_val = describe_value(change.before, before_attr)
                after_val = describe_value(change.after, after_attr)
                detail_table.add_row(change.attribute or "", before_val, after_val, change.kind)
            console.print(detail_table)
        else:
            console.print("No recorded changes for this step.")

        state_after = history_obj.get_state_at_step(target_step.step_number)
        if state_after:
            console.print("State after step (tracked attributes):")
            state_table = Table(show_header=True)
            state_table.add_column("Location")
            state_table.add_column("Value")
            state_table.add_column("Trend")

            # Helper function to format value with constraints
            def format_value(attr) -> str:
                if attr.value != "unknown":
                    return str(attr.value)

                # Value is unknown - check if we can show constrained options
                if (
                    hasattr(attr, "last_known_value")
                    and attr.last_known_value
                    and hasattr(attr, "last_trend_direction")
                    and attr.last_trend_direction in ("up", "down")
                    and hasattr(attr, "space_id")
                    and attr.space_id
                ):
                    try:
                        space = rm.spaces.get(attr.space_id)
                        constrained = space.constrained_levels(
                            last_known_value=attr.last_known_value,
                            trend=attr.last_trend_direction,
                        )
                        if constrained:
                            # Show ONLY the constrained options (without "unknown" prefix)
                            return ", ".join(constrained)
                    except Exception:
                        pass

                return "unknown"

            for part_name, part in (state_after.parts or {}).items():
                for attr_name, attr in part.attributes.items():
                    value_display = format_value(attr)
                    state_table.add_row(f"{part_name}.{attr_name}", value_display, str(attr.trend))
            for attr_name, attr in (state_after.global_attributes or {}).items():
                value_display = format_value(attr)
                state_table.add_row(attr_name, value_display, str(attr.trend))
            if state_table.row_count:
                console.print(state_table)

        # Show conditional effect structure if the action has one
        action = rm.create_behavior_enhanced_action(history_obj.object_type, target_step.action_name)
        if action and action.effects:
            from simulator.core.actions.effects.attribute_effects import SetAttributeEffect
            from simulator.core.actions.effects.conditional_effects import ConditionalEffect
            from simulator.core.actions.effects.trend_effects import TrendEffect
            from simulator.core.engine.transition_engine import TransitionEngine

            # Check if there are any conditional effects
            def has_conditional(effects):
                if isinstance(effects, list):
                    return any(isinstance(e, ConditionalEffect) or has_conditional(e) for e in effects)
                return isinstance(effects, ConditionalEffect)

            engine = TransitionEngine(rm)
            has_cond = has_conditional(action.effects)
            title = "Effect Structure:" if has_cond else "Effects:"
            console.print(f"\n[bold]{title}[/bold]")

            step_params = target_step.parameters or {}
            change_value_lookup = {}
            for change in target_step.changes or []:
                if not change.attribute or change.kind not in ("value", "clarification"):
                    continue
                change_value_lookup.setdefault(change.attribute, []).append(change.after)

            def _resolve_param_value(param_name: str, effect_target) -> Optional[str]:
                if param_name in step_params and step_params[param_name] is not None:
                    return step_params[param_name]
                target_path = effect_target.to_string() if effect_target else None
                if target_path and target_path in change_value_lookup:
                    for candidate in reversed(change_value_lookup[target_path]):
                        if candidate is not None:
                            return candidate
                return None

            def describe_effects(effects, indent=0):
                if not isinstance(effects, list):
                    effects = [effects]

                for effect in effects:
                    if isinstance(effect, ConditionalEffect):
                        prefix = "  " * indent
                        cond_desc = engine._describe_condition_structure(effect.condition)
                        console.print(f"{prefix}[cyan]IF[/cyan] {cond_desc}")

                        then_effects = (
                            effect.then_effect if isinstance(effect.then_effect, list) else [effect.then_effect]
                        )
                        console.print(f"{prefix}[cyan]THEN:[/cyan]")
                        describe_effects(then_effects, indent + 1)

                        if effect.else_effect:
                            console.print(f"{prefix}[cyan]ELSE:[/cyan]")
                            else_effects = (
                                effect.else_effect if isinstance(effect.else_effect, list) else [effect.else_effect]
                            )
                            describe_effects(else_effects, indent + 1)
                    else:
                        # Describe non-conditional effects
                        prefix = "  " * indent
                        if isinstance(effect, SetAttributeEffect):
                            # Resolve parameter references for display
                            from simulator.core.actions.parameter import ParameterReference

                            if isinstance(effect.value, ParameterReference):
                                resolved = _resolve_param_value(effect.value.name, effect.target)
                                value_desc = resolved if resolved is not None else f"parameter:{effect.value.name}"
                            else:
                                value_desc = str(effect.value)
                            console.print(f"{prefix}[dim]• Set {effect.target.to_string()} = {value_desc}[/dim]")
                        elif isinstance(effect, TrendEffect):
                            console.print(
                                f"{prefix}[dim]• Trend {effect.target.to_string()} → {effect.direction}[/dim]"
                            )

            describe_effects(action.effects)

    if all_steps:
        for st in history_obj.steps:
            _render_step_detail(st)
        return

    if step is not None:
        target = next((st for st in history_obj.steps if st.step_number == step), None)
        if target is None:
            console.print(f"[red]Step {step} not found in history.[/red]")
            return
        _render_step_detail(target)


__all__ = ["app"]
