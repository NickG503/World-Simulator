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
    default_story_path,
)
from simulator.cli.services import apply_action, run_simulation
from simulator.core.engine.transition_engine import TransitionResult
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.registries import RegistryManager
from simulator.core.registries.validators import RegistryValidator
from simulator.io.loaders.action_loader import load_actions
from simulator.io.loaders.object_loader import load_object_types, instantiate_default
from simulator.io.loaders.yaml_loader import load_spaces


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
    full: bool = typer.Option(False, "--full", help="Render full details"),
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

    if full:
        table = Table(title=f"{obj.name} (Full Details)")
        table.add_column("Part")
        table.add_column("Attribute")
        table.add_column("Space id")
        table.add_column("Mutable")
        table.add_column("Default")
        for part_name, part in obj.parts.items():
            for attr_name, attr in part.attributes.items():
                table.add_row(part_name, attr_name, attr.space_id, str(attr.mutable), str(attr.default_value))
        for attr_name, attr in obj.global_attributes.items():
            table.add_row("<global>", attr_name, attr.space_id, str(attr.mutable), str(attr.default_value))
        console.print(table)

        instance = instantiate_default(obj, rm)
        console.print("\n[bold]Default instance[/bold]:")
        console.print_json(data=instance.model_dump())
    else:
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
    save_to: str | None = typer.Option(None, "--save", help="Save simulation history to this path"),
    simulation_id: str | None = typer.Option(None, "--id", help="Custom simulation ID"),
    objs: str | None = typer.Option(None, help="Path to kb/objects folder"),
    acts: str | None = typer.Option(None, help="Path to kb/actions folder"),
    verbose_load: bool = typer.Option(False, "--verbose-load", help="Display full validation trace on loader errors"),
    verbose_run: bool = typer.Option(False, "--verbose-run", help="Print simulation progress"),
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

    history, runner = run_simulation(rm, object_type, action_specs, simulation_id, verbose=verbose_run)

    target_path = save_to or default_history_path(history.simulation_id, object_type)
    runner.save_history_to_yaml(history, target_path)

    console.print("\n[bold]Simulation Summary[/bold]")
    console.print(f"ID: {history.simulation_id}")
    console.print(f"Object: {history.object_type}")
    console.print(f"Duration: {history.started_at} to {history.completed_at}")

    successful = len(history.get_successful_steps())
    failed = len(history.get_failed_steps())
    if successful:
        console.print(f"✅ Successful actions: {successful}")
    if failed:
        console.print(f"❌ Failed actions: {failed}")


@app.command()
def history(
    file_path: str = typer.Argument(..., help="Path to simulation history YAML file"),
    step: int | None = typer.Option(None, "--step", help="Show state at a specific step"),
    action: str | None = typer.Option(None, "--action", help="Filter by action name"),
    show_states: bool = typer.Option(False, "--states", help="Display initial and final states"),
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

    if step is not None:
        snapshot = history_obj.get_state_at_step(step)
        if snapshot is None:
            console.print(f"[red]Step {step} not found[/red]")
            raise typer.Exit(code=2)
        _render_snapshot(f"State after step {step}", snapshot)
        return

    if action:
        steps = history_obj.find_step_by_action(action)
        console.print(f"\n[bold]Steps with action '{action}':[/bold]")
        if steps:
            for step_obj in steps:
                status_color = "green" if step_obj.status == "ok" else "red"
                console.print(f"  Step {step_obj.step_number}: [{status_color}]{step_obj.status}[/{status_color}]")
                if step_obj.status != "ok" and step_obj.error_message:
                    console.print(f"    Error: {step_obj.error_message}")
        else:
            console.print("  [dim]No matching steps[/dim]")
        return

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

    if show_states:
        initial = history_obj.get_initial_state()
        final = history_obj.get_final_state()
        if initial:
            _render_snapshot("Initial State", initial)
        if final:
            _render_snapshot("Final State", final)


@app.command()
def story(
    history_file: str = typer.Argument(..., help="Path to simulation history YAML file"),
    output_file: str | None = typer.Option(None, "--output", "-o", help="Output text file"),
) -> None:
    from simulator.core.simulation_runner import SimulationRunner
    from simulator.core.story_generator import create_story_generator

    rm = RegistryManager()
    runner = SimulationRunner(rm)
    try:
        history_obj = runner.load_history_from_yaml(history_file)
    except Exception as exc:
        console.print(f"[red]Error loading history file[/red]: {exc}")
        raise typer.Exit(code=1)

    generator = create_story_generator()
    story_text = generator.generate_story(history_obj)

    target_path = output_file or default_story_path(history_obj.simulation_id, history_obj.object_type)
    generator.save_story_to_file(story_text, target_path)

    console.print("\nPreview:")
    console.print("-" * 40)
    for line in story_text.splitlines()[:15]:
        console.print(line or "")
    if len(story_text.splitlines()) > 15:
        console.print("[dim]... (see full story in output file)[/dim]")
    console.print("-" * 40)
    console.print(f"Story saved to: [green]{target_path}[/green]")


__all__ = ["app"]
