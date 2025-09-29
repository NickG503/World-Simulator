from __future__ import annotations

import logging
from typing import Dict, Iterable

import typer
from rich.console import Console
from rich.table import Table

from simulator.cli.formatters import (
    format_constraint,
    build_object_definition_table,
    build_changes_table,
)
from simulator.cli.load_helpers import load_or_exit
from simulator.cli.paths import (
    kb_actions_path,
    kb_objects_path,
    kb_spaces_path,
    default_history_path,
    default_dataset_path,
    resolve_history_path,
    resolve_dataset_path,
)
from simulator.cli.services import apply_action, run_simulation
from simulator.core.engine.transition_engine import TransitionResult
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.registries import RegistryManager
from simulator.core.registries.validators import RegistryValidator
from simulator.io.loaders.action_loader import load_actions
from simulator.io.loaders.object_loader import load_object_types, instantiate_default
from simulator.io.loaders.yaml_loader import load_spaces
from simulator.core.objects.part import AttributeTarget
from simulator.core.dataset.sequential_dataset import build_interactive_dataset_text


app = typer.Typer(help="Simulator CLI: validate knowledge base, inspect objects, and run actions.")
console = Console()


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


@app.command()
def simulate(
    object_type: str = typer.Argument(..., help="Object type to simulate"),
    actions: list[str] = typer.Argument(..., help="Actions (name or name:param=value pairs)"),
    history_name: str | None = typer.Option(None, "--history-name", help="History filename under outputs/histories (e.g., run1.yaml)"),
    dataset_name: str | None = typer.Option(None, "--dataset-name", help="Dataset filename under outputs/datasets (e.g., run1.txt)"),
    simulation_id: str | None = typer.Option(None, "--id", help="Custom simulation ID (used in defaults)"),
    objs: str | None = typer.Option(None, help="Path to kb/objects folder"),
    acts: str | None = typer.Option(None, help="Path to kb/actions folder"),
    verbose_load: bool = typer.Option(False, "--verbose-load", help="Display full validation trace on loader errors"),
    verbose_run: bool = typer.Option(False, "--verbose-run", help="Print simulation progress"),
    save_to: str | None = typer.Option(None, "--save", help="[Deprecated] Use --history-name instead"),
) -> None:
    rm = _load_registries(objs, acts, verbose_load=verbose_load)

    action_specs: list[dict] = []
    for action_str in actions:
        if ":" in action_str:
            name, params_str = action_str.split(":", 1)
            params: Dict[str, str] = {}
            for pair in params_str.split(","):
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    params[key.strip()] = value.strip()
            action_specs.append({"name": name.strip(), "parameters": params})
        else:
            action_specs.append({"name": action_str.strip()})

    if verbose_run:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    history, runner = run_simulation(
        rm,
        object_type,
        action_specs,
        simulation_id,
        verbose=verbose_run,
        interactive=True,
        unknown_paths=None,
    )

    # Backward-compat: map deprecated --save to history_name if provided
    if not history_name and save_to:
        history_name = save_to

    # Save history under outputs/histories, using provided name or default
    if history_name:
        target_path = resolve_history_path(history_name, history.simulation_id, history.object_type)
    else:
        target_path = default_history_path(history.simulation_id, history.object_type)
    runner.save_history_to_yaml(history, target_path)

    # Also build and save a dataset text next to outputs/datasets
    dataset_path = resolve_dataset_path(dataset_name, history.simulation_id, history.object_type)
    text = build_interactive_dataset_text(history)
    from pathlib import Path as _P
    _p = _P(dataset_path)
    _p.parent.mkdir(parents=True, exist_ok=True)
    _p.write_text(text, encoding="utf-8")

    console.print("\n[bold]Simulation Summary[/bold]")
    console.print(f"ID: {history.simulation_id}")
    console.print(f"Object: {history.object_type}")
    console.print(f"Saved history: {target_path}")
    console.print(f"Saved dataset: {dataset_path}")

    successful = len(history.get_successful_steps())
    failed = len(history.get_failed_steps())
    if successful:
        console.print(f"✅ Successful actions: {successful}")
    if failed:
        console.print(f"❌ Failed actions: {failed}")


@app.command()
def history(
    file_path: str = typer.Argument(..., help="Path to simulation history YAML file"),
) -> None:
    from simulator.core.simulation_runner import SimulationRunner

    rm = RegistryManager()
    runner = SimulationRunner(rm)
    try:
        history_obj = runner.load_history_from_yaml(file_path)
    except Exception as exc:
        console.print(f"[red]Error loading history file[/red]: {exc}")
        raise typer.Exit(code=1)

    console.print(f"[bold]Simulation History[/bold]: {history_obj.simulation_id}")
    console.print(f"Object: {history_obj.object_type}")
    console.print(f"Total steps: {history_obj.total_steps}")
    console.print(f"Duration: {history_obj.started_at} to {history_obj.completed_at}")

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
            console.print(f"[red]Step {step_obj.step_number} '{step_obj.action_name}' failed:[/red] {step_obj.error_message}")


__all__ = ["app"]


"""
# Flashlight CLI Cheat Sheet

# 1) Validate and inspect
uv run sim validate
uv run sim show behaviors flashlight
uv run sim show object flashlight

# Note: flashlight.battery.level default is 'unknown' in the KB.
# During simulation, you'll be asked for its value when needed.

# 2) Core simulations (compact history v2 + dataset text)
uv run sim simulate flashlight turn_on turn_off \
  --history-name basic.yaml --dataset-name basic.txt --id basic
uv run sim history outputs/histories/basic.yaml

# 3) Failure and reasoning evidence
uv run sim simulate flashlight drain_battery turn_on \
  --history-name fail.yaml --dataset-name fail.txt --id failv2
uv run sim history outputs/histories/fail.yaml

# 4) Dataset text is automatically saved for each simulate run

# 5) Interactive simulation (stop/clarify/continue)
# Interactive simulate is the default; unknowns should be defined in YAML defaults.
uv run sim simulate flashlight turn_on \
  --history-name turn_on_interactive.yaml --dataset-name turn_on_interactive.txt --id turn_on_interactive

# Failure handling semantics
# - Unknown-driven failure: If a precondition depends on an unknown value
#   (e.g., battery.level == unknown), the CLI will ASK a clarification, set
#   your answer, and RETRY the same action immediately. If it then succeeds,
#   the step is recorded as OK and the state advances.
# - True precondition failure: If a precondition is not met and no clarification
#   applies, the simulator ALWAYS STOPS the run immediately after recording the
#   failed step. The object state remains unchanged from the last valid state.
#   The dataset text will include the full story, Q/A clarifications (if any),
#   and per-step results including the failure reason.
# Example:
#   uv run sim simulate flashlight drain_battery turn_on turn_off \
#     --history-name fail.yaml --dataset-name fail.txt --id fail
#   # If 'turn_on' fails (empty battery), the run stops right there. The
#   # dataset shows 'turn_on' FAILED and no further actions are executed.

# 6) History inspection for any run
uv run sim history outputs/histories/basic.yaml

# 7) TV four-step sequence (no Q → Q → no Q → FAIL)
# Object: tv (network.wifi_connected default = unknown)
# Actions in a single simulate:
#   1) turn_on         → no question (precondition doesn't use unknown) → PASS
#   2) open_streaming  → asks for network.wifi_connected (unknown) → you answer 'on' → PASS
#                        (If you answer anything else, this step FAILS and the run stops.)
#   3) adjust_volume   → no question (requires power on) → PASS
#   4) factory_reset   → FAIL (requires screen.power == off; it's on) → STOP
uv run sim simulate tv turn_on open_streaming adjust_volume factory_reset \
  --history-name tv_advanced.yaml --dataset-name tv_advanced.txt --id tv_adv
uv run sim history outputs/histories/tv_advanced.yaml

# 8) TV flow without unknown-triggered action (no question asked)
# Here we skip open_streaming, so no unknown is needed.
uv run sim simulate tv turn_on adjust_volume \
  --history-name tv_simple.yaml --dataset-name tv_simple.txt --id tv_simple
uv run sim history outputs/histories/tv_simple.yaml

# =====
"""


@app.command()
def minimal():
    """Deprecated: minimal is now built into 'simulate' via dataset output generation."""
    console.print("[yellow]The 'minimal' command is deprecated. Use 'sim simulate ... --dataset-name <name>'.[/yellow]")
@app.command()
def dataset():
    """Deprecated: dataset generation is now part of 'simulate'."""
    console.print("[yellow]The 'dataset' command is deprecated. Use 'sim simulate ... --dataset-name <name>'.[/yellow]")
