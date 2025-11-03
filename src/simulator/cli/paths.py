from __future__ import annotations

"""Utilities for resolving common knowledge-base and output paths."""

from pathlib import Path


def kb_spaces_path(path: str | None) -> str:
    return path or str(Path.cwd() / "kb" / "spaces")


def kb_objects_path(path: str | None) -> str:
    return path or str(Path.cwd() / "kb" / "objects")


def kb_actions_path(path: str | None) -> str:
    return path or str(Path.cwd() / "kb" / "actions")


def outputs_dir() -> Path:
    return Path.cwd() / "outputs"


def histories_dir() -> Path:
    return outputs_dir() / "histories"


def results_dir() -> Path:
    return outputs_dir() / "results"


def ensure_output_dirs() -> None:
    histories_dir().mkdir(parents=True, exist_ok=True)
    results_dir().mkdir(parents=True, exist_ok=True)


def default_history_path(simulation_id: str) -> str:
    ensure_output_dirs()
    filename = f"{simulation_id}.yaml"
    return str(histories_dir() / filename)


def default_result_path(simulation_id: str) -> str:
    ensure_output_dirs()
    filename = f"{simulation_id}.txt"
    return str(results_dir() / filename)


def resolve_history_path(name: str) -> str:
    """Resolve a history filename under outputs/histories.

    The name is used directly without any prefixing.
    If name has no .yaml extension, it will be added.
    """
    ensure_output_dirs()
    p = Path(name)
    base = p.name
    if not base.endswith(".yaml"):
        base = f"{base}.yaml"
    return str(histories_dir() / base)


def resolve_result_path(name: str) -> str:
    """Resolve result path under outputs/results using the name.

    The name is used directly without any prefixing.
    If name has no .txt extension, it will be added.
    """
    ensure_output_dirs()
    p = Path(name)
    base = p.name
    if not base.endswith(".txt"):
        base = f"{base}.txt"
    return str(results_dir() / base)


__all__ = [
    "kb_spaces_path",
    "kb_objects_path",
    "kb_actions_path",
    "ensure_output_dirs",
    "results_dir",
    "default_history_path",
    "default_result_path",
    "resolve_history_path",
    "resolve_result_path",
]
