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


def stories_dir() -> Path:
    return outputs_dir() / "stories"


def ensure_output_dirs() -> None:
    histories_dir().mkdir(parents=True, exist_ok=True)
    stories_dir().mkdir(parents=True, exist_ok=True)


def default_history_path(simulation_id: str, object_type: str) -> str:
    ensure_output_dirs()
    filename = f"{object_type}_{simulation_id}.yaml"
    return str(histories_dir() / filename)


def default_story_path(simulation_id: str, object_type: str) -> str:
    ensure_output_dirs()
    filename = f"{object_type}_{simulation_id}_story.txt"
    return str(stories_dir() / filename)


__all__ = [
    "kb_spaces_path",
    "kb_objects_path",
    "kb_actions_path",
    "ensure_output_dirs",
    "default_history_path",
    "default_story_path",
]

