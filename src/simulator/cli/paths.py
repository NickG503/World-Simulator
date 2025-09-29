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


def datasets_dir() -> Path:
    return outputs_dir() / "datasets"


def ensure_output_dirs() -> None:
    histories_dir().mkdir(parents=True, exist_ok=True)
    datasets_dir().mkdir(parents=True, exist_ok=True)


def default_history_path(simulation_id: str, object_type: str) -> str:
    ensure_output_dirs()
    filename = f"{object_type}_{simulation_id}.yaml"
    return str(histories_dir() / filename)


def default_dataset_path(simulation_id: str, object_type: str) -> str:
    ensure_output_dirs()
    filename = f"{object_type}_{simulation_id}.txt"
    return str(datasets_dir() / filename)


def resolve_history_path(name_or_dir: str | None, simulation_id: str, object_type: str) -> str:
    """Resolve a history filename under outputs/histories.

    Policy:
    - None → default {object}_{id}.yaml under outputs/histories
    - If argument is a directory → place default filename in that directory
    - If argument is a filename (with or without directories) → use its basename under outputs/histories
    - Supports placeholders {id} and {object}
    """
    ensure_output_dirs()
    if not name_or_dir:
        return default_history_path(simulation_id, object_type)

    text = str(name_or_dir)
    # Substitute placeholders
    if "{" in text and "}" in text:
        try:
            text = text.format(id=simulation_id, object=object_type)
        except Exception:
            pass
    p = Path(text)
    if p.is_dir():
        # Directory provided; keep it
        filename = f"{object_type}_{simulation_id}.yaml"
        return str(p / filename)

    # Treat any non-directory input as a filename; store under outputs/histories
    base = p.name
    if not base.endswith(".yaml"):
        base = f"{base}.yaml"
    return str(histories_dir() / base)


def resolve_dataset_path(name: str | None, simulation_id: str, object_type: str) -> str:
    """Resolve dataset path under outputs/datasets using a simple name.

    If name is None, default to {object}_{id}.txt
    If name has no suffix, append .txt
    """
    ensure_output_dirs()
    if not name:
        return default_dataset_path(simulation_id, object_type)
    p = Path(name)
    if not p.suffix:
        p = p.with_suffix(".txt")
    return str(datasets_dir() / p.name)


__all__ = [
    "kb_spaces_path",
    "kb_objects_path",
    "kb_actions_path",
    "ensure_output_dirs",
    "datasets_dir",
    "default_history_path",
    "default_dataset_path",
    "resolve_history_path",
    "resolve_dataset_path",
]
