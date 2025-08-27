from __future__ import annotations
import json
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
from simulator.io.yaml_loader import load_object_types
from simulator.io.actions_loader import load_actions
from simulator.core.action_engine import ActionEngine
from simulator.core.state import ObjectState

app = typer.Typer(help="""Simulator CLI: validate/inspect (Phase 1) + apply actions (Phase 2).""")
console = Console()


def _kb_obj_path(path: str | None) -> str:
    return path or str(Path.cwd() / "kb" / "objects")

def _kb_act_path(path: str | None) -> str:
    return path or str(Path.cwd() / "kb" / "actions")


@app.command()
def validate(objs: str | None = typer.Option(None, help="Path to kb/objects folder"),
             acts: str | None = typer.Option(None, help="Path to kb/actions folder")) -> None:
    kb = _kb_obj_path(objs)
    try:
        reg = load_object_types(kb)
    except Exception as e:
        console.print(f"[red]Object type validation failed:[/red] {e}")
        raise typer.Exit(code=1)
    types = list(reg.all())
    console.print(f"[green]OK[/green] Loaded {len(types)} object type(s) from {kb}")
    for t in types:
        console.print(f" - {t.name}@v{t.version} ({len(t.attributes)} attrs)")

    if acts is not None:
        try:
            actions = load_actions(_kb_act_path(acts))
        except Exception as e:
            console.print(f"[red]Action validation failed:[/red] {e}")
            raise typer.Exit(code=1)
        console.print(f"[green]OK[/green] Loaded {len(actions)} action(s) from {_kb_act_path(acts)}")


@app.command("show")
def show_object(
    what: str = typer.Argument(..., help="What to show: 'object'"),
    name: str = typer.Argument(..., help="Object type name"),
    version: int = typer.Option(..., "--version", "-v", help="Version"),
    path: str | None = typer.Option(None, help="Path to kb/objects folder"),
) -> None:
    if what != "object":
        console.print("[red]Only 'object' is supported for 'show'[/red]")
        raise typer.Exit(code=2)

    reg = load_object_types(_kb_obj_path(path))
    obj = reg.get(name, version)

    table = Table(title=f"{obj.name}@v{obj.version}")
    table.add_column("Attribute")
    table.add_column("Space (ordered)")
    table.add_column("Mutable")
    table.add_column("Default")
    for attr_name, attr in obj.attributes.items():
        table.add_row(attr_name, ", ".join(attr.space.levels), str(attr.mutable), str(attr.default))
    console.print(table)

    state_json = obj.default_state().model_dump()
    console.print("\n[bold]Default state[/bold]:")
    console.print_json(data=state_json)


@app.command()
def apply(
    object_name: str = typer.Argument(..., help="Object type name"),
    version: int = typer.Option(..., "--version", "-v", help="Object type version"),
    action_name: str = typer.Argument(..., help="Action name"),
    params: list[str] = typer.Option([], "--param", "-p", help="key=value pairs"),
    state_path: str | None = typer.Option(None, "--state", "-s", help="Path to JSON state (optional)"),
    objs: str | None = typer.Option(None, help="Path to kb/objects folder"),
    acts: str | None = typer.Option(None, help="Path to kb/actions folder"),
) -> None:
    reg = load_object_types(_kb_obj_path(objs))
    obj = reg.get(object_name, version)
    actions = load_actions(_kb_act_path(acts))

    key = (object_name, action_name)
    if key not in actions:
        console.print(f"[red]Unknown action[/red]: {object_name}/{action_name}")
        raise typer.Exit(code=2)
    action = actions[key]

    p: dict[str, str] = {}
    for kv in params:
        if "=" not in kv:
            console.print(f"[red]Bad --param[/red] (expected k=v): {kv}")
            raise typer.Exit(code=2)
        k, v = kv.split("=", 1)
        p[k.strip()] = v.strip()

    if state_path is None:
        state = obj.default_state()
    else:
        from json import load
        with open(state_path, "r", encoding="utf-8") as f:
            data = load(f)
        if "values" in data:
            vals = data["values"]
            tr = data.get("trends", {})
        else:
            console.print("[red]State JSON must contain a 'values' mapping[/red]")
            raise typer.Exit(code=2)
        state = ObjectState(object_type=obj, values=vals, trends=tr)

    engine = ActionEngine(obj)
    result = engine.apply(state, action, p)

    console.print("\n[bold]Result[/bold]:")
    console.print_json(data=result.model_dump())

    if result.diff:
        table = Table(title="Diff")
        table.add_column("Attribute")
        table.add_column("Before")
        table.add_column("After")
        table.add_column("Kind")
        for d in result.diff:
            table.add_row(d.attribute, d.before, d.after, d.kind)
        console.print(table)