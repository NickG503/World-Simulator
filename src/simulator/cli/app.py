"""
Simulator CLI: validate knowledge base, inspect objects, and run simulations.

Simplified for tree-based simulation:
- No interactive prompts
- Uses TreeSimulationRunner for simulation execution
- Outputs tree history to YAML and optional HTML visualization
"""

from __future__ import annotations

from typing import Dict, Optional

import typer
from rich.console import Console
from rich.table import Table

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
)
from simulator.core.engine.transition_engine import TransitionResult
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.registries import RegistryManager
from simulator.core.registries.validators import RegistryValidator
from simulator.io.loaders.action_loader import load_actions
from simulator.io.loaders.object_loader import load_object_types
from simulator.io.loaders.yaml_loader import load_spaces

app = typer.Typer(help="Simulator CLI: validate knowledge base, inspect objects, and run simulations.")
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


@app.command()
def validate(
    objs: str | None = typer.Argument(None, help="Path to kb/objects folder"),
    acts: str | None = typer.Option(None, help="Path to kb/actions folder"),
    verbose: bool = typer.Option(False, "--verbose-load", help="Display full validation trace on loader errors"),
) -> None:
    """Validate the knowledge base."""
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
    """Show object details or behaviors."""
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
                console.print(f"  - {behaviour}")
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
    objs: str | None = typer.Option(None, help="Path to kb/objects folder"),
    acts: str | None = typer.Option(None, help="Path to kb/actions folder"),
    verbose: bool = typer.Option(False, "--verbose-load", help="Display full validation trace on loader errors"),
) -> None:
    """Apply a single action to an object."""
    rm = _load_registries(objs, acts, verbose_load=verbose)

    param_map: Dict[str, str] = {}
    for item in params:
        if "=" not in item:
            console.print(f"[red]Bad --param[/red] (expected key=value): {item}")
            raise typer.Exit(code=2)
        key, value = item.split("=", 1)
        param_map[key.strip()] = value.strip()

    from simulator.cli.services import apply_action

    obj_type, action, instance, result = apply_action(
        rm,
        object_name,
        action_name,
        param_map,
        console,
        interactive=False,
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
        console.print(f"\n[red bold]Constraint Violations ({len(result.violations)}):[/red bold]")
        for violation in result.violations:
            console.print(f"  - {violation}")

    _render_changes(result)

    if full and instance is not None:
        _render_instance_state("Resulting state", instance)


@app.command()
def simulate(
    obj: str = typer.Option(..., "--obj", help="Object type to simulate"),
    actions: list[str] = typer.Argument(..., help="Actions to execute (use action=value for inline parameters)"),
    run_name: str | None = typer.Option(None, "--name", help="Name for output files (auto-generated if not provided)"),
    objs: str | None = typer.Option(None, "--objs-path", help="Path to kb/objects folder"),
    acts: str | None = typer.Option(None, "--acts-path", help="Path to kb/actions folder"),
    verbose_load: bool = typer.Option(False, "--verbose-load", help="Display full validation trace on loader errors"),
    visualize: bool = typer.Option(False, "--viz", help="Open HTML visualization after simulation"),
) -> None:
    """Run a simulation with multiple actions using tree-based execution."""
    rm = _load_registries(objs, acts, verbose_load=verbose_load)

    # Parse actions
    action_specs: list[dict] = []
    for action_str in actions:
        if "=" in action_str:
            action_name_raw, inline_value = action_str.split("=", 1)
            action_name = action_name_raw.strip()
            value = inline_value.strip()

            if not value:
                console.print(f"[red]Bad action value[/red]: expected 'action=value', got '{action_str}'")
                raise typer.Exit(code=2)

            param_name = _infer_inline_param_name(rm, obj, action_name)
            if param_name:
                action_specs.append({"name": action_name, "parameters": {param_name: value}})
            else:
                console.print(f"[red]Cannot infer parameter for action '{action_name}'[/red]")
                raise typer.Exit(code=2)
        else:
            action_specs.append({"name": action_str.strip(), "parameters": {}})

    # Run simulation using TreeSimulationRunner
    from simulator.core.tree import TreeSimulationRunner

    runner = TreeSimulationRunner(rm)
    simulation_name = run_name if run_name else None

    tree = runner.run(
        object_type=obj,
        actions=action_specs,
        simulation_id=simulation_name,
        verbose=False,
    )

    # Store CLI command and actions in tree for visualization
    tree.cli_command = f"sim simulate --obj {obj} {' '.join(actions)}" + (f" --name {run_name}" if run_name else "")
    tree.actions = actions

    # Save tree to file
    history_path = resolve_history_path(tree.simulation_id)
    runner.save_tree_to_yaml(tree, history_path)

    # Summary output
    console.print("\n[bold]Simulation Complete[/bold]")
    console.print(f"ID: {tree.simulation_id}")
    console.print(f"Object: {tree.object_type}")
    console.print(f"Nodes: {len(tree.nodes)}")
    console.print(f"Saved: {history_path}")

    # Count results
    successful = sum(1 for n in tree.nodes.values() if n.action_status == "ok" and n.action_name)
    failed = sum(1 for n in tree.nodes.values() if n.action_status != "ok" and n.action_name)

    if successful:
        console.print(f"[green]Successful: {successful}[/green]")
    if failed:
        console.print(f"[red]Failed: {failed}[/red]")

    # Show path summary
    console.print(f"\n[dim]Path: {' -> '.join(tree.current_path)}[/dim]")

    # Optionally open visualization
    if visualize:
        from simulator.visualizer import generate_visualization, open_visualization

        viz_path = generate_visualization(history_path)
        console.print(f"[cyan]Visualization: {viz_path}[/cyan]")
        open_visualization(viz_path)


def _infer_inline_param_name(rm: RegistryManager, object_name: str, action_name: str) -> Optional[str]:
    """Infer which parameter should receive an inline value for an action."""
    try:
        action_spec = rm.find_action_for_object(object_name, action_name)
    except Exception:
        action_spec = None

    if not action_spec:
        return None

    params = getattr(action_spec, "parameters", {}) or {}
    if not params:
        return None

    if len(params) == 1:
        return next(iter(params.keys()))

    required = [name for name, spec in params.items() if getattr(spec, "required", False)]
    if len(required) == 1:
        return required[0]

    return None


@app.command()
def visualize(
    file_path: str = typer.Argument(..., help="History YAML file to visualize"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output HTML file path"),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open browser automatically"),
) -> None:
    """Generate and open HTML visualization for a simulation history."""
    from simulator.cli.paths import find_history_file
    from simulator.visualizer import generate_visualization, open_visualization

    # Resolve path
    try:
        resolved_path = find_history_file(file_path)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    # Generate visualization
    viz_path = generate_visualization(resolved_path, output)
    console.print(f"[green]Generated:[/green] {viz_path}")

    if not no_open:
        open_visualization(viz_path)
        console.print("[cyan]Opened in browser[/cyan]")


@app.command()
def history(
    file_path: str = typer.Argument(
        ...,
        help="History name or path (bare names resolve to outputs/histories/<name>.yaml automatically)",
    ),
    step: Optional[int] = typer.Option(None, "--step", "-s", help="Show detailed table for a specific step"),
) -> None:
    """View simulation history summary."""
    from simulator.cli.paths import find_history_file

    try:
        resolved_path = find_history_file(file_path)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    # Load tree data directly
    import yaml

    with open(resolved_path, "r") as f:
        data = yaml.safe_load(f)

    simulation_id = data.get("simulation_id", "Unknown")
    object_type = data.get("object_type", "Unknown")
    created_at = data.get("created_at", "Unknown")
    nodes = data.get("nodes", {})
    current_path = data.get("current_path", [])

    console.print(f"[bold]Simulation:[/bold] {simulation_id}")
    console.print(f"Object: {object_type}")
    console.print(f"Date: {created_at}")
    console.print(f"Nodes: {len(nodes)}")

    table = Table(title="Execution Path")
    table.add_column("Node")
    table.add_column("Action")
    table.add_column("Status")
    table.add_column("Changes")

    for node_id in current_path:
        node = nodes.get(node_id, {})
        action = node.get("action_name") or "Initial"
        status = node.get("action_status", "ok")
        changes = len(node.get("changes", []))

        status_color = "green" if status == "ok" else "red"
        table.add_row(
            node_id,
            action,
            f"[{status_color}]{status}[/{status_color}]",
            str(changes),
        )
    console.print(table)


__all__ = ["app"]
