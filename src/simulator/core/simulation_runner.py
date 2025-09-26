"""
Simulation Runner: Execute multiple actions sequentially and track state history.

This module provides functionality to:
1. Run multiple actions in sequence on an object
2. Track object state changes after each action
3. Save/load simulation history to/from YAML
4. Query object state at any point in the simulation timeline
"""

from __future__ import annotations
from typing import Dict, List, Optional, Union
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field
import yaml

from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.engine.transition_engine import TransitionEngine, DiffEntry
import logging
from simulator.core.registries.registry_manager import RegistryManager


class AttributeSnapshot(BaseModel):
    value: Optional[str]
    trend: Optional[str]
    confidence: float


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
    timestamp: str
    status: str  # "ok", "rejected", "error"
    error_message: Optional[str] = None
    object_state_before: ObjectStateSnapshot
    object_state_after: ObjectStateSnapshot
    changes: List[DiffEntry] = Field(default_factory=list)


class SimulationHistory(BaseModel):
    """Complete history of a simulation run."""
    
    simulation_id: str
    object_type: str
    object_name: str
    started_at: str
    completed_at: Optional[str] = None
    total_steps: int = 0
    steps: List[SimulationStep] = Field(default_factory=list)
    
    def get_state_at_step(self, step_number: int) -> Optional[ObjectStateSnapshot]:
        """Get object state after a specific step (0-based)."""
        if step_number < 0 or step_number >= len(self.steps):
            return None
        return self.steps[step_number].object_state_after

    def get_initial_state(self) -> Optional[ObjectStateSnapshot]:
        """Get the initial object state (before any actions)."""
        if not self.steps:
            return None
        return self.steps[0].object_state_before

    def get_final_state(self) -> Optional[ObjectStateSnapshot]:
        """Get the final object state (after all actions)."""
        if not self.steps:
            return None
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
        from simulator.io.loaders.object_loader import instantiate_default
        obj_instance = instantiate_default(obj_type, self.registry_manager)
        
        # Initialize simulation history
        history = SimulationHistory(
            simulation_id=simulation_id,
            object_type=object_type,
            object_name=object_type,  # Could be parameterized later
            started_at=datetime.now().isoformat(),
            total_steps=len(actions)
        )
        
        logger = logging.getLogger(__name__)
        if verbose:
            logger.info("Starting simulation '%s' with %d actions", simulation_id, len(actions))
            logger.info("Object: %s", object_type)
        
        current_instance = obj_instance
        action_requests = [
            action if isinstance(action, ActionRequest) else ActionRequest.model_validate(action)
            for action in actions
        ]

        for step_num, request in enumerate(action_requests):
            action_name = request.name
            parameters = request.parameters
            
            if verbose:
                logger.info("Step %d: %s", step_num + 1, action_name)
            
            # Capture state before action
            state_before = self._capture_object_state(current_instance)
            
            # Get and execute action
            action = self.registry_manager.create_behavior_enhanced_action(object_type, action_name)
            
            if not action:
                # Handle missing action
                step = SimulationStep(
                    step_number=step_num,
                    action_name=action_name,
                    object_name=object_type,
                    parameters=parameters,
                    timestamp=datetime.now().isoformat(),
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
            
            # Execute action
            result = self.engine.apply_action(current_instance, action, parameters)
            
            # Capture state after action
            state_after = self._capture_object_state(result.after if result.after else current_instance)
            
            # Create simulation step
            step = SimulationStep(
                step_number=step_num,
                action_name=action_name,
                object_name=object_type,
                parameters=parameters,
                timestamp=datetime.now().isoformat(),
                status=result.status,
                error_message=result.reason if result.status != "ok" else None,
                object_state_before=state_before,
                object_state_after=state_after,
                changes=result.changes,
            )
            
            history.steps.append(step)
            
            # Update current instance for next iteration
            if result.after:
                current_instance = result.after
            
            if verbose:
                if result.status == "ok":
                    logger.info("Success: %d change(s)", len(result.changes))
                    for change in result.changes[:3]:
                        logger.info("  • %s: %s → %s", change.attribute, change.before, change.after)
                    if len(result.changes) > 3:
                        logger.info("  ... and %d more", len(result.changes) - 3)
                else:
                    logger.warning("Action failed: %s", result.reason)

        # Complete simulation
        history.completed_at = datetime.now().isoformat()
        
        successful_steps = len(history.get_successful_steps())
        if verbose:
            logger.info("Simulation complete: %d successful, %d failed", successful_steps, len(actions) - successful_steps)
        
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
                )
            parts[part_name] = PartStateSnapshot(attributes=attrs)

        global_attrs: Dict[str, AttributeSnapshot] = {}
        for attr_name, attr_instance in obj_instance.global_attributes.items():
            global_attrs[attr_name] = AttributeSnapshot(
                value=attr_instance.current_value,
                trend=attr_instance.trend,
                confidence=attr_instance.confidence,
            )

        return ObjectStateSnapshot(
            type=obj_instance.type.name,
            parts=parts,
            global_attributes=global_attrs,
        )
    
    def save_history_to_yaml(self, history: SimulationHistory, file_path: str) -> None:
        """Save simulation history to YAML file."""
        # Ensure parent directory exists
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w') as f:
            yaml.dump(history.model_dump(), f, default_flow_style=False, indent=2)
        logging.getLogger(__name__).info("Saved simulation history to %s", file_path)
    
    def load_history_from_yaml(self, file_path: str) -> SimulationHistory:
        """Load simulation history from YAML file."""
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)
        return SimulationHistory.model_validate(data)


def create_simulation_runner(registry_manager: RegistryManager) -> SimulationRunner:
    """Factory function to create a simulation runner."""
    return SimulationRunner(registry_manager)
