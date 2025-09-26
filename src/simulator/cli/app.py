from __future__ import annotations
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
from simulator.core.registries import RegistryManager
from simulator.core.registries.validators import RegistryValidator
from simulator.io.loaders.yaml_loader import load_spaces
from simulator.io.loaders.object_loader import load_object_types, instantiate_default
from simulator.io.loaders.action_loader import load_actions
from simulator.core.engine import TransitionEngine
from simulator.core.prompt import UnknownValueResolver

app = typer.Typer(help="""Simulator CLI: validate/inspect (Phase 1) + apply actions (Phase 2).""")
console = Console()


def _kb_spaces_path(path: str | None) -> str:
    return path or str(Path.cwd() / "kb" / "spaces")

def _kb_obj_path(path: str | None) -> str:
    return path or str(Path.cwd() / "kb" / "objects")

def _kb_act_path(path: str | None) -> str:
    return path or str(Path.cwd() / "kb" / "actions")


def _outputs_dir() -> Path:
    """Get the outputs directory path."""
    return Path.cwd() / "outputs"

def _histories_dir() -> Path:
    """Get the histories directory path."""
    return _outputs_dir() / "histories"

def _stories_dir() -> Path:
    """Get the stories directory path."""
    return _outputs_dir() / "stories"

def _ensure_output_dirs() -> None:
    """Ensure output directories exist."""
    _histories_dir().mkdir(parents=True, exist_ok=True)
    _stories_dir().mkdir(parents=True, exist_ok=True)

def _default_history_path(simulation_id: str, object_type: str) -> str:
    """Generate default path for history file."""
    _ensure_output_dirs()
    filename = f"{object_type}_{simulation_id}.yaml"
    return str(_histories_dir() / filename)

def _default_story_path(simulation_id: str, object_type: str) -> str:
    """Generate default path for story file."""
    _ensure_output_dirs()
    filename = f"{object_type}_{simulation_id}_story.txt"
    return str(_stories_dir() / filename)


def _format_constraint_description(constraint) -> str:
    """Convert a constraint object to human-readable description."""
    if constraint.type == "dependency":
        condition_desc = _format_condition_description(constraint.condition)
        requires_desc = _format_condition_description(constraint.requires)
        return f"If {condition_desc}, then {requires_desc}"
    else:
        return f"{constraint.type} constraint"


def _format_condition_description(condition) -> str:
    """Convert a condition dict/object to human-readable description."""
    # Handle both dict and object formats
    if hasattr(condition, 'type'):
        ctype = condition.type
        target = getattr(condition, 'target', None)
        operator = getattr(condition, 'operator', None)
        value = getattr(condition, 'value', None)
        conditions = getattr(condition, 'conditions', None)
    else:
        ctype = condition.get('type')
        target = condition.get('target')
        operator = condition.get('operator')
        value = condition.get('value')
        conditions = condition.get('conditions')
    
    if ctype == "attribute_check":
        # Convert operators to readable format
        op_map = {
            "equals": "==",
            "not_equals": "!=", 
            "lt": "<",
            "lte": "<=",
            "gt": ">",
            "gte": ">="
        }
        op_symbol = op_map.get(operator, operator)
        
        return f"{target} {op_symbol} {value}"
    elif ctype == "and":
        sub_conditions = [_format_condition_description(c) for c in (conditions or [])]
        return f"({' AND '.join(sub_conditions)})"
    elif ctype == "or":
        sub_conditions = [_format_condition_description(c) for c in (conditions or [])]
        return f"({' OR '.join(sub_conditions)})"
    elif ctype == "not":
        sub_condition = _format_condition_description((conditions or [None])[0]) if conditions else "<missing>"
        return f"NOT ({sub_condition})"
    else:
        return f"{ctype} condition"



@app.command()
def validate(
    objs: str | None = typer.Argument(None, help="Path to kb/objects folder"),
    acts: str | None = typer.Option(None, help="Path to kb/actions folder"),
) -> None:
    rm = RegistryManager()
    load_spaces(_kb_spaces_path(None), rm)
    rm.register_defaults()
    load_object_types(_kb_obj_path(objs), rm)
    load_actions(_kb_act_path(acts or None), rm)

    console.print(f"[green]OK[/green] Loaded {len(list(rm.objects.all()))} object type(s)")
    console.print(f"[green]OK[/green] Loaded {len(rm.actions.items)} action(s)")

    # Run registry validation
    validator = RegistryValidator(rm)
    errors = validator.validate_all()
    if errors:
        console.print("[red]Validation errors detected:[/red]")
        for e in errors:
            console.print(f" - {e}")
        raise typer.Exit(code=1)
    console.print("[green]All validations passed[/green]")


@app.command("show")
def show_object(
    what: str = typer.Argument(..., help="What to show: 'object', 'behaviors'"),
    name: str = typer.Argument(..., help="Object type name"),
    path: str | None = typer.Option(None, help="Path to kb/objects folder"),
    full: bool = typer.Option(False, "--full", help="Show full details (default: summary only)"),
) -> None:
    rm = RegistryManager()
    load_spaces(_kb_spaces_path(None), rm)
    rm.register_defaults()
    load_object_types(_kb_obj_path(path), rm)
    
    try:
        obj = rm.objects.get(name)
    except KeyError:
        console.print(f"[red]Object type not found[/red]: {name}")
        raise typer.Exit(code=2)

    if what == "behaviors":
        behaviors = list(obj.behaviors.keys())
        if full:
            console.print(f"\n[bold]Behaviors for {name}:[/bold]")
            if behaviors:
                for behavior in sorted(behaviors):
                    console.print(f"  ✓ {behavior}")
            else:
                console.print("  [dim]No behaviors defined[/dim]")
        else:
            # Clean behaviors output
            console.print(f"[bold]{name} behaviors:[/bold] {', '.join(sorted(behaviors)) if behaviors else 'none'}")
        return
    elif what != "object":
        console.print("[red]Supported options[/red]: 'object', 'behaviors'")
        raise typer.Exit(code=2)

    # Clean object type definition by default
    if not full:
        console.print(f"[bold]{obj.name}[/bold] (Object Type)")
        
        # Count attributes by part
        attr_count = 0
        for part_name, part in obj.parts.items():
            attr_count += len(part.attributes)
        attr_count += len(obj.global_attributes)
        
        console.print(f"Parts: {len(obj.parts)}, Attributes: {attr_count}, Constraints: {len(obj.constraints)}")
        
        # Show pure object type definition (no instance data)
        table = Table(title="Definition", show_header=True, header_style="bold blue")
        table.add_column("Attribute", style="cyan")
        table.add_column("Default", style="green")
        table.add_column("Mutable", style="dim")
        
        # Show part attributes
        for part_name, part_spec in obj.parts.items():
            for attr_name, attr_spec in part_spec.attributes.items():
                full_name = f"{part_name}.{attr_name}"
                mutable_icon = "✓" if attr_spec.mutable else "✗"
                
                # Get default value from spec or space
                default_val = attr_spec.default_value
                if default_val is None:
                    space = rm.spaces.get(attr_spec.space_id)
                    default_val = space.levels[0]
                
                table.add_row(
                    full_name, 
                    str(default_val), 
                    mutable_icon
                )
        
        # Show global attributes
        for g_name, g_attr_spec in obj.global_attributes.items():
            mutable_icon = "✓" if g_attr_spec.mutable else "✗"
            
            # Get default value from spec or space
            default_val = g_attr_spec.default_value
            if default_val is None:
                space = rm.spaces.get(g_attr_spec.space_id)
                default_val = space.levels[0]
            
            table.add_row(
                f"global.{g_name}", 
                str(default_val), 
                mutable_icon
            )
        
        console.print(table)
        
        # Show constraints in human-readable format
        if obj.constraints:
            console.print(f"\n[bold]Constraints ({len(obj.constraints)}):[/bold]")
            for i, constraint in enumerate(obj.constraints, 1):
                constraint_desc = _format_constraint_description(constraint)
                console.print(f"  {i}. {constraint_desc}")
    else:
        # Full detailed output (original behavior)
        table = Table(title=f"{obj.name} (Full Details)")
        table.add_column("Part")
        table.add_column("Attribute")
        table.add_column("Space id")
        table.add_column("Mutable")
        table.add_column("Default")
        for part_name, part in obj.parts.items():
            for attr_name, attr in part.attributes.items():
                table.add_row(part_name, attr_name, attr.space_id, str(attr.mutable), str(attr.default_value))
        for g_name, g_attr in obj.global_attributes.items():
            table.add_row("<global>", g_name, g_attr.space_id, str(g_attr.mutable), str(g_attr.default_value))
        console.print(table)

        inst = instantiate_default(obj, rm)
        state_json = inst.model_dump()
        console.print("\n[bold]Default instance[/bold]:")
        console.print_json(data=state_json)


@app.command()
def apply(
    object_name: str = typer.Argument(..., help="Object type name"),
    action_name: str = typer.Argument(..., help="Action name"),
    params: list[str] = typer.Option([], "--param", "-p", help="key=value pairs"),
    full: bool = typer.Option(False, "--full", help="Show full object states (default: summary only)"),
    no_interactive: bool = typer.Option(False, "--no-interactive", help="Skip interactive prompts for unknown values"),
    objs: str | None = typer.Option(None, help="Path to kb/objects folder"),
    acts: str | None = typer.Option(None, help="Path to kb/actions folder"),
) -> None:
    rm = RegistryManager()
    load_spaces(_kb_spaces_path(None), rm)
    rm.register_defaults()
    load_object_types(_kb_obj_path(objs), rm)
    load_actions(_kb_act_path(acts), rm)

    obj = rm.objects.get(object_name)
    
    # Create behavior-enhanced action (merges object behavior with base action)
    action = rm.create_behavior_enhanced_action(object_name, action_name)
    
    if not action:
        console.print(f"[red]No action found[/red] for {object_name}.{action_name}")
        raise typer.Exit(code=1)
    
    # Check if object has custom behavior
    obj_type = rm.objects.get(object_name)
    if action_name in obj_type.behaviors:
        console.print(f"[cyan]Using object-specific behavior for[/cyan] {object_name}.{action_name}")
    else:
        console.print(f"[yellow]Using generic behavior for[/yellow] {object_name}.{action_name}")

    p: dict[str, str] = {}
    for kv in params:
        if "=" not in kv:
            console.print(f"[red]Bad --param[/red] (expected k=v): {kv}")
            raise typer.Exit(code=2)
        k, v = kv.split("=", 1)
        p[k.strip()] = v.strip()

    instance = instantiate_default(obj, rm)
    
    # Resolve any unknown attribute values
    resolver = UnknownValueResolver(rm, console)
    resolver.resolve_unknowns(instance, interactive=not no_interactive)

    engine = TransitionEngine(rm)
    result = engine.apply_action(instance, action, p)

    # Show summary by default, full details with --full flag
    if full:
        console.print("\n[bold]Full Result[/bold]:")
        console.print_json(data=result.model_dump())
    else:
        # Clean summary output
        status_color = "green" if result.status == "ok" else "red" if result.status == "rejected" else "yellow"
        console.print(f"\n[bold]Status:[/bold] [{status_color}]{result.status}[/{status_color}]")
        
        if result.reason:
            console.print(f"[bold]Reason:[/bold] {result.reason}")

    # Show constraint violations prominently
    if result.violations:
        console.print(f"\n[red bold]⚠️  Constraint Violations ({len(result.violations)}):[/red bold]")
        for violation in result.violations:
            console.print(f"[red]  • {violation}[/red]")

    # Show changes diff (always shown as it's the most important info)
    if result.changes:
        table = Table(title="Changes")
        table.add_column("Attribute")
        table.add_column("Before")
        table.add_column("After")
        table.add_column("Kind")
        for d in result.changes:
            table.add_row(d.attribute or "", str(d.before), str(d.after), d.kind)
        console.print(table)
    elif result.status == "ok":
        console.print("\n[dim]No changes made[/dim]")


@app.command()
def simulate(
    object_type: str = typer.Argument(..., help="Object type to simulate"),
    actions: list[str] = typer.Argument(..., help="Actions to run in sequence (e.g., turn_on drain_battery turn_off)"),
    save_to: str = typer.Option(None, "--save", help="Save simulation history to YAML file"),
    simulation_id: str = typer.Option(None, "--id", help="Custom simulation ID"),
    objs: str | None = typer.Option(None, help="Path to kb/objects folder"),
    acts: str | None = typer.Option(None, help="Path to kb/actions folder"),
) -> None:
    """Run a multi-step simulation on an object."""
    from simulator.core.simulation_runner import create_simulation_runner
    
    # Initialize registry
    rm = RegistryManager()
    load_spaces(_kb_spaces_path(None), rm)
    rm.register_defaults()
    load_object_types(_kb_obj_path(objs), rm)
    load_actions(_kb_act_path(acts), rm)
    
    # Parse actions (format: "action_name" or "action_name:param1=value1,param2=value2")
    action_specs = []
    for action_str in actions:
        if ":" in action_str:
            action_name, params_str = action_str.split(":", 1)
            params = {}
            for param_pair in params_str.split(","):
                if "=" in param_pair:
                    key, value = param_pair.split("=", 1)
                    params[key.strip()] = value.strip()
            action_specs.append({"name": action_name.strip(), "parameters": params})
        else:
            action_specs.append({"name": action_str.strip()})
    
    # Create and run simulation
    runner = create_simulation_runner(rm)
    history = runner.run_simulation(object_type, action_specs, simulation_id)
    
    # Save to file (auto-save to organized location or custom path)
    if save_to:
        runner.save_history_to_yaml(history, save_to)
    else:
        # Auto-save to organized outputs directory
        default_path = _default_history_path(history.simulation_id, object_type)
        runner.save_history_to_yaml(history, default_path)
    
    # Show summary
    console.print(f"\n[bold]Simulation Summary[/bold]")
    console.print(f"ID: {history.simulation_id}")
    console.print(f"Object: {history.object_type}")
    console.print(f"Duration: {history.started_at} to {history.completed_at}")
    
    successful = len(history.get_successful_steps())
    failed = len(history.get_failed_steps())
    
    if successful > 0:
        console.print(f"✅ Successful actions: {successful}")
    if failed > 0:
        console.print(f"❌ Failed actions: {failed}")


@app.command()
def history(
    file_path: str = typer.Argument(..., help="Path to simulation history YAML file"),
    step: int = typer.Option(None, "--step", help="Show state at specific step (0-based)"),
    action: str = typer.Option(None, "--action", help="Find steps that executed this action"),
    show_states: bool = typer.Option(False, "--states", help="Show object states"),
) -> None:
    """Query simulation history from saved YAML file."""
    from simulator.core.simulation_runner import SimulationRunner
    
    # Load history
    rm = RegistryManager()  # Minimal registry for loading
    runner = SimulationRunner(rm)
    
    try:
        history = runner.load_history_from_yaml(file_path)
    except Exception as e:
        console.print(f"[red]Error loading history file[/red]: {e}")
        raise typer.Exit(code=1)
    
    # Show basic info
    console.print(f"[bold]Simulation History[/bold]: {history.simulation_id}")
    console.print(f"Object: {history.object_type}")
    console.print(f"Total steps: {history.total_steps}")
    console.print(f"Duration: {history.started_at} to {history.completed_at}")
    
    # Handle specific queries
    if step is not None:
        state = history.get_state_at_step(step)
        if state:
            console.print(f"\n[bold]State at step {step}:[/bold]")
            
            # Show state in table format
            table = Table(title=f"Object State After Step {step}")
            table.add_column("Attribute")
            table.add_column("Value") 
            table.add_column("Trend")
            
            # Add part attributes
            for part_name, part_data in state.get("parts", {}).items():
                for attr_name, attr_data in part_data.items():
                    table.add_row(
                        f"{part_name}.{attr_name}",
                        str(attr_data.get("value", "")),
                        str(attr_data.get("trend", "none"))
                    )
            
            # Add global attributes
            for attr_name, attr_data in state.get("global_attributes", {}).items():
                table.add_row(
                    attr_name,
                    str(attr_data.get("value", "")),
                    str(attr_data.get("trend", "none"))
                )
            
            console.print(table)
        else:
            console.print(f"[red]Step {step} not found[/red] (valid range: 0-{len(history.steps)-1})")
        return
    
    if action:
        steps = history.find_step_by_action(action)
        console.print(f"\n[bold]Steps with action '{action}':[/bold]")
        if steps:
            for step in steps:
                status_color = "green" if step.status == "ok" else "red"
                console.print(f"  Step {step.step_number}: [{status_color}]{step.status}[/{status_color}]")
                if step.status != "ok":
                    console.print(f"    Error: {step.error_message}")
        else:
            console.print(f"  No steps found with action '{action}'")
        return
    
    # Default: show step summary
    console.print(f"\n[bold]Step Summary:[/bold]")
    table = Table()
    table.add_column("Step")
    table.add_column("Action")
    table.add_column("Status")
    table.add_column("Changes")
    
    for step in history.steps:
        status_color = "green" if step.status == "ok" else "red"
        table.add_row(
            str(step.step_number),
            step.action_name,
            f"[{status_color}]{step.status}[/{status_color}]",
            str(len(step.changes))
        )
    
    console.print(table)
    
    if show_states:
        # Show initial and final states in table format
        def _show_state_table(state_data, title):
            table = Table(title=title)
            table.add_column("Attribute")
            table.add_column("Value") 
            table.add_column("Trend")
            
            for part_name, part_data in state_data.get("parts", {}).items():
                for attr_name, attr_data in part_data.items():
                    table.add_row(
                        f"{part_name}.{attr_name}",
                        str(attr_data.get("value", "")),
                        str(attr_data.get("trend", "none"))
                    )
            
            for attr_name, attr_data in state_data.get("global_attributes", {}).items():
                table.add_row(
                    attr_name,
                    str(attr_data.get("value", "")),
                    str(attr_data.get("trend", "none"))
                )
            
            console.print(table)
        
        initial_state = history.get_initial_state()
        final_state = history.get_final_state()
        
        if initial_state:
            _show_state_table(initial_state, "Initial State")
        
        if final_state:
            _show_state_table(final_state, "Final State")


@app.command()
def story(
    history_file: str = typer.Argument(..., help="Path to simulation history YAML file"),
    output_file: str = typer.Option(None, "--output", "-o", help="Output text file (auto-generated if not provided)"),
) -> None:
    """Convert simulation history to natural language story."""
    from simulator.core.story_generator import create_story_generator
    from simulator.core.simulation_runner import SimulationRunner
    
    # Load history
    rm = RegistryManager()  # Minimal registry for loading
    runner = SimulationRunner(rm)
    
    try:
        history = runner.load_history_from_yaml(history_file)
    except Exception as e:
        console.print(f"[red]Error loading history file[/red]: {e}")
        raise typer.Exit(code=1)
    
    # Generate story
    story_generator = create_story_generator()
    story_text = story_generator.generate_story(history)
    
    # Auto-generate output filename if not provided
    if not output_file:
        output_file = _default_story_path(history.simulation_id, history.object_type)
    
    # Save story
    story_generator.save_story_to_file(story_text, output_file)
    
    # Show preview
    console.print(f"\nPreview:")
    console.print("-" * 40)
    
    # Show first few lines
    lines = story_text.split('\n')
    preview_lines = lines[:15]  # Show first 15 lines
    for line in preview_lines:
        if line.startswith("#"):
            console.print(f"[bold blue]{line}[/bold blue]")
        elif line.strip():
            console.print(line)
        else:
            console.print("")
    
    if len(lines) > 15:
        console.print("[dim]... (see full story in output file)[/dim]")
    
    console.print("-" * 40)
    console.print(f"Story saved to: [green]{output_file}[/green]")


"""
uv run sim show object tv # show this 

uv run sim show behaviors tv # show this


uv run sim apply tv turn_on # show this
uv run sim apply flashlight turn_on # show this

uv run sim apply kettle heat  # should fail because kettle doesn't have heat behavior


# Run complete flashlight cycle
uv run sim simulate flashlight turn_on turn_off --save flashlight_cycle.yaml # show this

# Show step-by-step progression
uv run sim history flashlight_cycle.yaml # show this

# Show state after turn_on (step 0)
uv run sim history flashlight_cycle.yaml --step 0 # show this

# Show state after turn_off (step 1) 
uv run sim history flashlight_cycle.yaml --step 1 # show this

# Compare initial vs final states
uv run sim history flashlight_cycle.yaml --states # show this


########################################################
# stringing it all together
########################################################
uv run sim simulate flashlight turn_on turn_off --save flashlight_perfect.yaml # show this
uv run sim story flashlight_perfect.yaml # show this
cat flashlight_perfect_story.txt # show this


########################################################
# stringing it all together
########################################################
uv run sim simulate flashlight turn_on drain_battery --save flashlight_constraint_fail.yaml
uv run sim story flashlight_constraint_fail.yaml
cat flashlight_constraint_fail_story.txt
"""