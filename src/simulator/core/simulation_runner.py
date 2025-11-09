"""
Simulation Runner: Execute multiple actions sequentially and track state history.

This module provides functionality to:
1. Run multiple actions in sequence on an object
2. Track object state changes after each action
3. Save/load simulation history to/from YAML
4. Query object state at any point in the simulation timeline
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, Field

from simulator.core.engine.transition_engine import DiffEntry, TransitionEngine
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.registries.registry_manager import RegistryManager


class AttributeSnapshot(BaseModel):
    value: Optional[str]
    trend: Optional[str]
    confidence: float
    last_known_value: Optional[str] = None
    last_trend_direction: Optional[str] = None
    space_id: Optional[str] = None


class PartStateSnapshot(BaseModel):
    attributes: Dict[str, AttributeSnapshot] = Field(default_factory=dict)


class ObjectStateSnapshot(BaseModel):
    type: str
    parts: Dict[str, PartStateSnapshot] = Field(default_factory=dict)
    global_attributes: Dict[str, AttributeSnapshot] = Field(default_factory=dict)


class ActionRequest(BaseModel):
    name: str
    parameters: Dict[str, str] = Field(default_factory=dict)


class SimulationStep(BaseModel):
    """Represents a single step in the simulation."""

    step_number: int
    action_name: str
    object_name: str
    parameters: Dict[str, str] = Field(default_factory=dict)
    status: str  # "ok", "rejected", "error"
    error_message: Optional[str] = None
    object_state_before: Optional[ObjectStateSnapshot] = None
    object_state_after: Optional[ObjectStateSnapshot] = None
    changes: List[DiffEntry] = Field(default_factory=list)


class SimulationHistory(BaseModel):
    """Complete history of a simulation run."""

    simulation_id: str
    object_type: str
    object_name: str
    started_at: str
    total_steps: int = 0
    steps: List[SimulationStep] = Field(default_factory=list)
    initial_state: Optional[ObjectStateSnapshot] = None
    # Interactive clarification events captured during run
    # Stored separately from steps for simple presentation
    interactions: List[Dict[str, Any]] = Field(default_factory=list)

    def get_state_at_step(self, step_number: int) -> Optional[ObjectStateSnapshot]:
        """Get object state after a specific step (0-based)."""
        if step_number < 0 or step_number >= len(self.steps):
            return None
        self.ensure_state_cache()
        return self.steps[step_number].object_state_after

    def get_initial_state(self) -> Optional[ObjectStateSnapshot]:
        """Get the initial object state (before any actions)."""
        if self.initial_state is not None:
            return self.initial_state
        if not self.steps:
            return None
        return self.steps[0].object_state_before

    def get_final_state(self) -> Optional[ObjectStateSnapshot]:
        """Get the final object state (after all actions)."""
        if not self.steps:
            return None
        self.ensure_state_cache()
        return self.steps[-1].object_state_after

    def find_step_by_action(self, action_name: str) -> List[SimulationStep]:
        """Find all steps that executed a specific action."""
        return [step for step in self.steps if step.action_name == action_name]

    def get_successful_steps(self) -> List[SimulationStep]:
        """Get all steps that completed successfully."""
        return [step for step in self.steps if step.status == "ok"]

    def get_failed_steps(self) -> List[SimulationStep]:
        """Get all steps that failed."""
        return [step for step in self.steps if step.status != "ok"]

    def ensure_state_cache(self) -> None:
        """Ensure before/after snapshots are populated using initial_state and deltas."""
        if not self.steps:
            return
        base_state = self.initial_state
        if base_state is None and self.steps[0].object_state_before is not None:
            base_state = self.steps[0].object_state_before.model_copy(deep=True)
        if base_state is None:
            return

        cursor = base_state.model_copy(deep=True)
        for step in self.steps:
            if step.object_state_before is None:
                step.object_state_before = cursor.model_copy(deep=True)
            cursor = _apply_changes_to_snapshot(cursor, step.changes)
            step.object_state_after = cursor.model_copy(deep=True)


def _ensure_attr_snapshot(state: ObjectStateSnapshot, part: Optional[str], attr: str) -> AttributeSnapshot:
    """Ensure an AttributeSnapshot exists for the given path on a state snapshot."""
    if part:
        if part not in state.parts:
            state.parts[part] = PartStateSnapshot()
        part_state = state.parts[part]
        if attr not in part_state.attributes:
            part_state.attributes[attr] = AttributeSnapshot(value=None, trend=None, confidence=1.0)
        return part_state.attributes[attr]

    if attr not in state.global_attributes:
        state.global_attributes[attr] = AttributeSnapshot(value=None, trend=None, confidence=1.0)
    return state.global_attributes[attr]


def _apply_changes_to_snapshot(state: ObjectStateSnapshot, changes: List[DiffEntry]) -> ObjectStateSnapshot:
    """Produce a new snapshot by applying a list of DiffEntry changes."""
    new_state = state.model_copy(deep=True)
    for change in changes:
        attr_path = change.attribute or ""
        parts = attr_path.split(".")
        is_trend = change.kind == "trend" or (parts and parts[-1] == "trend")
        if is_trend and parts:
            parts = parts[:-1]

        part_name: Optional[str] = None
        attr_name: Optional[str] = None

        if not parts:
            continue
        if len(parts) == 1:
            attr_name = parts[0]
        else:
            part_name = parts[0]
            attr_name = parts[1]

        if attr_name is None:
            continue

        attr_snapshot = _ensure_attr_snapshot(new_state, part_name, attr_name)
        if is_trend:
            # When trend becomes up/down, replicate the side effect behavior from ApplicationContext
            if change.after in ("up", "down"):
                # Preserve last known value if we have a concrete reading
                if attr_snapshot.value and attr_snapshot.value != "unknown":
                    attr_snapshot.last_known_value = attr_snapshot.value
                # Mark value unknown to signal follow-up clarification
                attr_snapshot.value = "unknown"
                attr_snapshot.confidence = 0.0
                attr_snapshot.last_trend_direction = change.after
            # Note: when trend becomes "none", we intentionally keep last_trend_direction
            # so that constrained options remain available until a concrete value is set
            attr_snapshot.trend = change.after
        else:
            # Track value changes and metadata
            if change.after == "unknown" and change.before and change.before != "unknown":
                # Value becoming unknown - preserve last known value
                attr_snapshot.last_known_value = change.before
            elif change.after != "unknown":
                # Value becoming known - update last known and clear trend direction
                attr_snapshot.last_known_value = change.after
                attr_snapshot.last_trend_direction = None
            attr_snapshot.value = change.after
    return new_state


class SimulationRunner:
    """Runs multiple actions in sequence and tracks state history."""

    def __init__(self, registry_manager: RegistryManager):
        self.registry_manager = registry_manager
        self.engine = TransitionEngine(registry_manager)

    def run_simulation(
        self,
        object_type: str,
        actions: List[Union[ActionRequest, Dict[str, str], Dict[str, Dict[str, str]]]],
        simulation_id: Optional[str] = None,
        resolve_unknowns: bool = True,
        verbose: bool = False,
        *,
        interactive: bool = False,
        unknown_paths: Optional[List[str]] = None,
        parameter_resolver=None,
    ) -> SimulationHistory:
        """
        Run a simulation with multiple actions.

        Args:
            object_type: Type of object to simulate
            actions: List of actions to execute, each with 'name' and optional 'parameters'
            simulation_id: Optional ID for the simulation (auto-generated if not provided)
            resolve_unknowns: Whether to resolve unknown attribute values (uses defaults if False)

        Returns:
            SimulationHistory with complete timeline

        Example:
            actions = [
                {"name": "turn_on"},
                {"name": "heat", "parameters": {"temperature": "high"}},
                {"name": "turn_off"}
            ]
        """
        if not simulation_id:
            simulation_id = f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Create object instance
        obj_type = self.registry_manager.objects.get(object_type)
        from simulator.core.objects.part import AttributeTarget
        from simulator.io.loaders.object_loader import instantiate_default

        obj_instance = instantiate_default(obj_type, self.registry_manager)
        # Apply unknown injections if requested
        if unknown_paths:
            for ref in unknown_paths:
                try:
                    ai = AttributeTarget.from_string(ref).resolve(obj_instance)
                    ai.current_value = "unknown"  # type: ignore
                    ai.confidence = 0.0
                    ai.last_trend_direction = None
                except Exception:
                    # ignore invalid unknown paths
                    pass

        # Initialize simulation history
        history = SimulationHistory(
            simulation_id=simulation_id,
            object_type=object_type,
            object_name=object_type,
            started_at=datetime.now().date().isoformat(),
            total_steps=len(actions),
        )

        logger = logging.getLogger(__name__)

        current_instance = obj_instance
        action_requests = [
            action if isinstance(action, ActionRequest) else ActionRequest.model_validate(action) for action in actions
        ]

        # Lazy import to avoid console hard-dependency
        from rich.console import Console

        from simulator.core.prompt import UnknownValueResolver

        resolver = UnknownValueResolver(self.registry_manager, Console()) if interactive else None

        step_index = 0
        for step_num, request in enumerate(action_requests):
            action_name = request.name
            parameters = request.parameters

            # Capture state before action
            state_before = self._capture_object_state(current_instance)
            if history.initial_state is None:
                history.initial_state = state_before.model_copy(deep=True)

            # Get and execute action
            action = self.registry_manager.create_behavior_enhanced_action(object_type, action_name)

            if not action:
                # Handle missing action
                step = SimulationStep(
                    step_number=step_num,
                    action_name=action_name,
                    object_name=object_type,
                    parameters=parameters,
                    status="error",
                    error_message=f"Action '{action_name}' not found for {object_type}",
                    object_state_before=state_before,
                    object_state_after=state_before,
                    changes=[],
                )
                history.steps.append(step)
                if verbose:
                    logger.warning("Action '%s' not found for object '%s'", action_name, object_type)
                continue

            # Execute action (with optional interactive clarification loop)
            if parameter_resolver:
                param_defs = getattr(action, "parameters", {}) or {}
                for param_name, param_spec in param_defs.items():
                    if not getattr(param_spec, "required", False):
                        continue
                    if param_name in parameters:
                        continue
                    value = parameter_resolver(action_name, param_name, param_spec)
                    parameters[param_name] = value
                    request.parameters[param_name] = value

            result = self.engine.apply_action(current_instance, action, parameters)
            if interactive:
                # If preconditions or postconditions failed due to unknowns, ask and retry
                def _extract_attr_from_question(q: str) -> Optional[str]:
                    qs = q.strip()
                    # Handle "Precondition: what is X?" format
                    if qs.lower().startswith("precondition: what is ") and qs.endswith("?"):
                        return qs[len("Precondition: what is ") : -1].strip()
                    # Handle "Postcondition: what is X?" format
                    if qs.lower().startswith("postcondition: what is ") and qs.endswith("?"):
                        return qs[len("Postcondition: what is ") : -1].strip()
                    # Legacy format for backward compatibility
                    if qs.lower().startswith("what is ") and qs.endswith("?"):
                        return qs[len("What is ") : -1].strip()
                    return None

                retry_guard = 0
                clarification_header_shown = False
                clarification_changes = []  # Track changes made during clarification
                while result.status == "rejected" and getattr(result, "clarifications", None) and retry_guard < 5:
                    retry_guard += 1
                    asked_any = False
                    if resolver is not None and not clarification_header_shown:
                        has_user_questions = any(not clar.startswith("[INFO]") for clar in result.clarifications)
                        if has_user_questions:
                            resolver.console.print(f"[cyan]Processing action '{action_name}'[/cyan]\n")
                            clarification_header_shown = True
                    for q in result.clarifications:
                        # Handle informational messages (structure descriptions)
                        if q.startswith("[INFO]"):
                            # Display informational message without asking for input
                            if resolver is not None:
                                info_msg = q.replace("[INFO] ", "")
                                resolver.console.print(f"[cyan]{info_msg}[/cyan]\n")
                            continue

                        attr_ref = _extract_attr_from_question(q)
                        if not attr_ref:
                            continue
                        try:
                            from simulator.core.objects.part import AttributeTarget as _AT

                            ai = _AT.from_string(attr_ref).resolve(current_instance)
                            space = self.registry_manager.spaces.get(ai.spec.space_id)
                            if resolver is not None:
                                picked = resolver.prompt_for_value(
                                    attr_ref,
                                    ai.spec.space_id,
                                    action_name=action_name,
                                    question=q,
                                    attribute_instance=ai,
                                )
                            else:
                                picked = None
                            if picked is None:
                                # user cancelled; stop clarification loop
                                break
                            # validate and set
                            if picked not in space.levels:
                                continue

                            # Record the previous value before setting
                            previous_value = ai.current_value

                            ai.current_value = picked
                            ai.confidence = 1.0
                            ai.last_known_value = picked
                            ai.last_trend_direction = None

                            # Record the change for the step
                            clarification_changes.append(
                                DiffEntry(
                                    attribute=attr_ref,
                                    before=previous_value if previous_value != "unknown" else "unknown",
                                    after=picked,
                                    kind="clarification",
                                )
                            )

                            # Show what was set
                            if resolver is not None:
                                resolver.console.print(f"[green]→ Set {attr_ref} = {picked}[/green]\n")

                            # Record interaction for history
                            self_log_entry = {
                                "step": step_index,
                                "action": action_name,
                                "attribute": attr_ref,
                                "question": q,
                                "answer": picked,
                                "options": list(space.levels),
                            }
                            history.interactions.append(self_log_entry)
                            asked_any = True
                        except Exception:
                            continue
                    # Retry if we asked at least one clarification
                    if asked_any:
                        result = self.engine.apply_action(current_instance, action, parameters)
                        # Prepend clarification changes to the result changes
                        if result.status == "ok" and clarification_changes:
                            result.changes = clarification_changes + result.changes
                    else:
                        break

                # If still failing without clarifications, offer to continue or stop the run
                if result.status != "ok" and not getattr(result, "clarifications", None):
                    keep_running = False
                    if resolver is not None:
                        from rich.prompt import Confirm

                        failure_msg = result.reason or f"Action '{action_name}' failed ({result.status})"
                        resolver.console.print(
                            f"[red]{action_name}: {failure_msg if result.reason else 'action failed'}[/red]"
                        )
                        keep_running = Confirm.ask(
                            "Continue simulation despite this failure?",
                            console=resolver.console,
                            default=False,
                        )
                    if not keep_running:
                        state_after = self._capture_object_state(current_instance)
                        step = SimulationStep(
                            step_number=step_index,
                            action_name=action_name,
                            object_name=object_type,
                            parameters=parameters,
                            status=result.status,
                            error_message=result.reason if result.status != "ok" else None,
                            object_state_before=state_before,
                            object_state_after=state_after,
                            changes=result.changes,
                        )
                        history.steps.append(step)
                        step_index += 1
                        return history
                    # User opted to continue; record failure but keep state unchanged
                    step = SimulationStep(
                        step_number=step_index,
                        action_name=action_name,
                        object_name=object_type,
                        parameters=parameters,
                        status=result.status,
                        error_message=f"{result.reason or 'Action failed'} (continued)",
                        object_state_before=state_before,
                        object_state_after=state_before.model_copy(deep=True),
                        changes=result.changes,
                    )
                    history.steps.append(step)
                    step_index += 1
                    continue

            # Capture state after action
            state_after = self._capture_object_state(result.after if result.after else current_instance)

            # Create simulation step
            step = SimulationStep(
                step_number=step_index,
                action_name=action_name,
                object_name=object_type,
                parameters=parameters,
                status=result.status,
                error_message=result.reason if result.status != "ok" else None,
                object_state_before=state_before,
                object_state_after=state_after,
                changes=result.changes,
            )

            history.steps.append(step)
            step_index += 1

            # Update current instance for next iteration
            if result.after:
                current_instance = result.after

            if verbose:
                if result.status == "ok":
                    logger.info("✅ %s ran successfully", action_name)
                    # Show what effects were applied
                    if resolver is not None:
                        # Show actual effects applied
                        value_changes = [c for c in result.changes if c.kind in ("value", "trend", "clarification")]
                        resolver.console.print("[dim cyan]Effects applied:[/dim cyan]")
                        if value_changes:
                            for change in value_changes:
                                if change.kind in ("value", "clarification"):
                                    resolver.console.print(
                                        f"[dim]  • {change.attribute}: {change.before} → {change.after}[/dim]"
                                    )
                                elif change.kind == "trend":
                                    trend_display = f"[dim]  • {change.attribute}: {change.before} → {change.after}"

                                    # Try to extract the attribute path and show constrained options
                                    if change.attribute.endswith(".trend") and result.after:
                                        attr_path = change.attribute[:-6]  # Remove ".trend"
                                        try:
                                            from simulator.core.objects.part import AttributeTarget

                                            ai = AttributeTarget.from_string(attr_path).resolve(result.after)
                                            if (
                                                ai.current_value == "unknown"
                                                and ai.last_known_value
                                                and change.after in ("up", "down")
                                            ):
                                                space = self.registry_manager.spaces.get(ai.spec.space_id)
                                                constrained = space.constrained_levels(
                                                    last_known_value=ai.last_known_value,
                                                    trend=change.after,
                                                )
                                                if constrained and len(constrained) < len(space.levels):
                                                    trend_display += f" (value now: {', '.join(constrained)})"
                                        except Exception:
                                            pass

                                    resolver.console.print(f"{trend_display}[/dim]")
                        else:
                            resolver.console.print("[dim]  • No visible changes[/dim]")
                        resolver.console.print("")  # Empty line
                else:
                    logger.warning("Action failed: %s", result.reason)

        # Complete simulation
        return history

    def _capture_object_state(self, obj_instance: ObjectInstance) -> ObjectStateSnapshot:
        """Capture the complete state of an object instance."""

        parts: Dict[str, PartStateSnapshot] = {}
        for part_name, part_instance in obj_instance.parts.items():
            attrs: Dict[str, AttributeSnapshot] = {}
            for attr_name, attr_instance in part_instance.attributes.items():
                attrs[attr_name] = AttributeSnapshot(
                    value=attr_instance.current_value,
                    trend=attr_instance.trend,
                    confidence=attr_instance.confidence,
                    last_known_value=attr_instance.last_known_value,
                    last_trend_direction=attr_instance.last_trend_direction,
                    space_id=attr_instance.spec.space_id,
                )
            parts[part_name] = PartStateSnapshot(attributes=attrs)

        global_attrs: Dict[str, AttributeSnapshot] = {}
        for attr_name, attr_instance in obj_instance.global_attributes.items():
            global_attrs[attr_name] = AttributeSnapshot(
                value=attr_instance.current_value,
                trend=attr_instance.trend,
                confidence=attr_instance.confidence,
                last_known_value=attr_instance.last_known_value,
                last_trend_direction=attr_instance.last_trend_direction,
                space_id=attr_instance.spec.space_id,
            )

        return ObjectStateSnapshot(
            type=obj_instance.type.name,
            parts=parts,
            global_attributes=global_attrs,
        )

    def save_history_to_yaml(self, history: SimulationHistory, file_path: str) -> None:
        """Save simulation history to YAML file (compact, readable format)."""
        # Ensure parent directory exists
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        # Build a compact v2 format to improve readability and avoid redundant fields
        data: Dict[str, Any] = {
            "history_version": 3,
            "simulation_id": history.simulation_id,
            "object_type": history.object_type,
            "object_name": history.object_name,
            "started_at": history.started_at,
            "total_steps": history.total_steps,
            "steps": [],
        }
        history.ensure_state_cache()
        if history.initial_state is None and history.steps and history.steps[0].object_state_before is not None:
            history.initial_state = history.steps[0].object_state_before.model_copy(deep=True)
        if history.initial_state is not None:
            data["initial_state"] = history.initial_state.model_dump()
        if history.interactions:
            data["interactions"] = history.interactions

        for s in history.steps:
            step_entry: Dict[str, Any] = {
                "step": s.step_number,
                "action": s.action_name,
                "status": s.status,
            }
            if s.error_message:
                step_entry["error"] = s.error_message
            if s.changes:
                # Filter out internal debug markers (info kind and attributes starting with [)
                filtered_changes = [c for c in s.changes if c.kind != "info" and not c.attribute.startswith("[")]
                if filtered_changes:
                    step_entry["changes"] = [
                        {"attribute": c.attribute, "before": c.before, "after": c.after, "kind": c.kind}
                        for c in filtered_changes
                    ]
            data["steps"].append(step_entry)

        with open(file_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, indent=2, sort_keys=False)

    def load_history_from_yaml(self, file_path: str) -> SimulationHistory:
        """Load simulation history from YAML file (supports v1 and compact v2 formats)."""
        with open(file_path, "r") as f:
            data = yaml.safe_load(f)

        # v3 delta format
        if isinstance(data, dict) and data.get("history_version") == 3 and "steps" in data:
            sim_id = data.get("simulation_id", "unknown")
            obj_type = data.get("object_type", "unknown")
            obj_name = data.get("object_name", obj_type)
            started = data.get("started_at")
            total = data.get("total_steps", len(data.get("steps") or []))

            initial_state_raw = data.get("initial_state")
            initial_state: Optional[ObjectStateSnapshot] = None
            if initial_state_raw:
                try:
                    initial_state = ObjectStateSnapshot.model_validate(initial_state_raw)
                except Exception as exc:
                    raise ValueError(f"Invalid initial_state in history file: {exc}") from exc

            steps: List[SimulationStep] = []
            cursor = initial_state.model_copy(deep=True) if initial_state is not None else None

            for entry in data.get("steps", []):
                step_num = entry.get("step") if entry.get("step") is not None else entry.get("step_number", 0)
                action = entry.get("action") or entry.get("action_name")
                status = entry.get("status", "ok")
                error = entry.get("error") or entry.get("error_message")

                changes_raw = entry.get("changes", []) or []
                changes: List[DiffEntry] = []
                for cr in changes_raw:
                    try:
                        changes.append(DiffEntry(**cr))
                    except Exception:
                        continue

                before_snapshot: Optional[ObjectStateSnapshot] = (
                    cursor.model_copy(deep=True) if cursor is not None else None
                )
                after_snapshot: Optional[ObjectStateSnapshot] = None
                if cursor is not None:
                    after_snapshot = _apply_changes_to_snapshot(cursor, changes)
                    cursor = after_snapshot.model_copy(deep=True)

                steps.append(
                    SimulationStep(
                        step_number=int(step_num),
                        action_name=str(action),
                        object_name=str(obj_name),
                        parameters={},
                        status=str(status),
                        error_message=error,
                        object_state_before=before_snapshot,
                        object_state_after=after_snapshot,
                        changes=changes,
                    )
                )

            history = SimulationHistory(
                simulation_id=str(sim_id),
                object_type=str(obj_type),
                object_name=str(obj_name),
                started_at=str(started),
                total_steps=int(total),
                steps=steps,
                initial_state=initial_state,
                interactions=list(data.get("interactions") or []),
            )
            history.ensure_state_cache()
            return history

        # v2 compact format
        if isinstance(data, dict) and data.get("history_version") == 2 and "steps" in data:
            sim_id = data.get("simulation_id", "unknown")
            obj_type = data.get("object_type", "unknown")
            obj_name = data.get("object_name", obj_type)
            started = data.get("started_at")
            total = data.get("total_steps", len(data.get("steps") or []))

            steps: List[SimulationStep] = []
            for entry in data.get("steps", []):
                step_num = entry.get("step") if entry.get("step") is not None else entry.get("step_number", 0)
                action = entry.get("action") or entry.get("action_name")
                status = entry.get("status", "ok")
                error = entry.get("error") or entry.get("error_message")
                before_raw = entry.get("object_state_before") or {}
                after_raw = entry.get("object_state_after") or {}

                try:
                    before = ObjectStateSnapshot.model_validate(before_raw)
                    after = ObjectStateSnapshot.model_validate(after_raw)
                except Exception as exc:
                    raise ValueError(f"Invalid state snapshot in history file: {exc}") from exc

                changes_raw = entry.get("changes", []) or []
                changes: List[DiffEntry] = []
                for cr in changes_raw:
                    try:
                        changes.append(DiffEntry(**cr))
                    except Exception:
                        # ignore malformed change entries
                        continue

                steps.append(
                    SimulationStep(
                        step_number=int(step_num),
                        action_name=str(action),
                        object_name=str(obj_name),
                        parameters={},
                        status=str(status),
                        error_message=error,
                        object_state_before=before,
                        object_state_after=after,
                        changes=changes,
                    )
                )

            return SimulationHistory(
                simulation_id=str(sim_id),
                object_type=str(obj_type),
                object_name=str(obj_name),
                started_at=str(started),
                total_steps=int(total),
                steps=steps,
                initial_state=steps[0].object_state_before if steps else None,
                interactions=list(data.get("interactions") or []),
            )

        # Fallback to legacy format (pydantic dump)
        return SimulationHistory.model_validate(data)


def create_simulation_runner(registry_manager: RegistryManager) -> SimulationRunner:
    """Factory function to create a simulation runner."""
    return SimulationRunner(registry_manager)
