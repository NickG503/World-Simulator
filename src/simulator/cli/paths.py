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


def find_history_file(name_or_path: str) -> str:
    """
    Find history file with smart resolution.

    1. If path exists as-is, use it
    2. If path exists with .yaml extension, use it
    3. Otherwise, look in outputs/histories/ folder
    4. Add .yaml extension if missing

    Args:
        name_or_path: Either full path or just filename (with or without .yaml)

    Returns:
        Resolved path to history file

    Raises:
        FileNotFoundError: If file cannot be found
    """
    p = Path(name_or_path)

    # Check if it's an absolute or relative path that exists
    if p.exists():
        return str(p)

    # Check if adding .yaml makes it exist
    if not str(name_or_path).endswith(".yaml"):
        p_with_yaml = Path(f"{name_or_path}.yaml")
        if p_with_yaml.exists():
            return str(p_with_yaml)

    # Otherwise, look in histories folder
    base_name = p.name
    if not base_name.endswith(".yaml"):
        base_name = f"{base_name}.yaml"

    history_file = histories_dir() / base_name
    if history_file.exists():
        return str(history_file)

    # File not found anywhere
    raise FileNotFoundError(
        f"History file not found: '{name_or_path}'\nLooked in:\n  - {name_or_path}\n  - {history_file}"
    )


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
    "find_history_file",
]
