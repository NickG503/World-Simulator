from __future__ import annotations

"""Shared helpers for loading knowledge-base components with CLI-friendly errors."""

from pathlib import Path
from typing import Any, Callable

import typer
from rich.console import Console

from simulator.io.loaders import LoaderError


def load_or_exit(
    loader_fn: Callable[..., Any],
    *args: Any,
    console: Console,
    verbose_errors: bool = False,
    **kwargs: Any,
) -> None:
    if args:
        first = args[0]
        if isinstance(first, str) and not Path(first).exists():
            console.print(f"[red]Path not found:[/red] {first}")
            raise typer.Exit(code=1)
    try:
        loader_fn(*args, **kwargs)
    except LoaderError as err:
        if verbose_errors and err.cause:
            console.print(f"[red]Failed to load data:[/red] {err.message}\n{err.cause}")
        else:
            console.print(f"[red]Failed to load data:[/red] {err}")
        raise typer.Exit(code=1)


__all__ = ["load_or_exit"]
