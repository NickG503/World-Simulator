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

app = typer.Typer(help="""Simulator CLI: validate/inspect (Phase 1) + apply actions (Phase 2).""")
console = Console()


def _kb_spaces_path(path: str | None) -> str:
    return path or str(Path.cwd() / "kb" / "spaces")

def _kb_obj_path(path: str | None) -> str:
    return path or str(Path.cwd() / "kb" / "objects")

def _kb_act_path(path: str | None) -> str:
    return path or str(Path.cwd() / "kb" / "actions")


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
    what: str = typer.Argument(..., help="What to show: 'object', 'capabilities'"),
    name: str = typer.Argument(..., help="Object type name"),
    path: str | None = typer.Option(None, help="Path to kb/objects folder"),
    full: bool = typer.Option(False, "--full", help="Show full details (default: summary only)"),
) -> None:
    rm = RegistryManager()
    load_spaces(_kb_spaces_path(None), rm)
    rm.register_defaults()
    load_object_types(_kb_obj_path(path), rm)
    
    # Detect capabilities
    rm.detect_and_register_capabilities()
    
    try:
        obj = rm.objects.get(name)
    except KeyError:
        console.print(f"[red]Object type not found[/red]: {name}")
        raise typer.Exit(code=2)

    if what == "capabilities":
        capabilities = rm.capabilities.get_capabilities(name)
        if full:
            console.print(f"\n[bold]Capabilities for {name}:[/bold]")
            if capabilities:
                for cap in sorted(capabilities):
                    console.print(f"  ✓ {cap}")
            else:
                console.print("  [dim]No capabilities detected[/dim]")
        else:
            # Clean capabilities output
            console.print(f"[bold]{name} capabilities:[/bold] {', '.join(sorted(capabilities)) if capabilities else 'none'}")
        return
    elif what != "object":
        console.print("[red]Supported options[/red]: 'object', 'capabilities'")
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
    objs: str | None = typer.Option(None, help="Path to kb/objects folder"),
    acts: str | None = typer.Option(None, help="Path to kb/actions folder"),
) -> None:
    rm = RegistryManager()
    load_spaces(_kb_spaces_path(None), rm)
    rm.register_defaults()
    load_object_types(_kb_obj_path(objs), rm)
    load_actions(_kb_act_path(acts), rm)
    
    # NEW: Detect capabilities after loading objects
    rm.detect_and_register_capabilities()

    obj = rm.objects.get(object_name)
    
    # NEW: Find compatible actions (capability-based or object-specific)
    compatible_actions = rm.find_compatible_actions(object_name, action_name)
    
    if not compatible_actions:
        console.print(f"[red]No compatible actions found[/red] for {object_name}.{action_name}")
        console.print(f"Available capabilities: {list(rm.capabilities.get_capabilities(object_name))}")
        raise typer.Exit(code=1)
    
    # Use the first compatible action (prioritize object-specific over capability-based)
    action_key = compatible_actions[0]
    action = rm.actions.get(action_key)
    
    if len(compatible_actions) > 1:
        console.print(f"[yellow]Multiple compatible actions found[/yellow]: {compatible_actions}")
        console.print(f"[yellow]Using[/yellow]: {action_key}")

    p: dict[str, str] = {}
    for kv in params:
        if "=" not in kv:
            console.print(f"[red]Bad --param[/red] (expected k=v): {kv}")
            raise typer.Exit(code=2)
        k, v = kv.split("=", 1)
        p[k.strip()] = v.strip()

    instance = instantiate_default(obj, rm)

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
