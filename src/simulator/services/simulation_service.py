"""Simulation Service: Orchestrates simulation execution and history management."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from simulator.core.dataset.sequential_dataset import build_interactive_dataset_text
from simulator.core.engine.transition_engine import TransitionEngine, TransitionResult
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.simulation_runner import SimulationHistory, SimulationRunner
from simulator.repositories.action_repository import ActionRepository
from simulator.repositories.object_repository import ObjectRepository
from simulator.services.behavior_resolver import BehaviorResolverService


class SimulationService:
    """
    High-level service for running simulations.

    Coordinates object instantiation, action resolution, simulation execution,
    and history/dataset generation.
    """

    def __init__(
        self,
        object_repository: ObjectRepository,
        action_repository: ActionRepository,
        behavior_resolver: BehaviorResolverService,
        simulation_runner: SimulationRunner,
        transition_engine: TransitionEngine,
    ):
        """
        Initialize simulation service.

        Args:
            object_repository: Repository for object access
            action_repository: Repository for action access
            behavior_resolver: Service for resolving actions
            simulation_runner: Runner for multi-step simulations
            transition_engine: Engine for single action transitions
        """
        self.object_repo = object_repository
        self.action_repo = action_repository
        self.behavior_resolver = behavior_resolver
        self.runner = simulation_runner
        self.engine = transition_engine

    def apply_single_action(
        self,
        object_name: str,
        action_name: str,
        parameters: Dict[str, str] | None = None,
        *,
        instance: ObjectInstance | None = None,
    ) -> tuple[ObjectInstance, TransitionResult]:
        """
        Apply a single action to an object.

        Args:
            object_name: Object type name
            action_name: Action name
            parameters: Action parameters (optional)
            instance: Existing instance (creates default if None)

        Returns:
            Tuple of (object_instance, transition_result)

        Raises:
            KeyError: If object or action not found
            ValueError: If action fails validation
        """
        # Get or create instance
        if instance is None:
            instance = self.object_repo.get_default_instance(object_name)

        # Resolve action
        action = self.behavior_resolver.resolve_action(object_name, action_name)
        if not action:
            raise KeyError(f"Action '{action_name}' not found for object '{object_name}'")

        # Apply action
        params = parameters or {}
        result = self.engine.apply_action(instance, action, params)

        return instance, result

    def run_simulation(
        self,
        object_name: str,
        action_specs: List[Dict[str, Any]],
        *,
        simulation_id: Optional[str] = None,
        verbose: bool = False,
        interactive: bool = False,
        unknown_paths: Optional[List[str]] = None,
        parameter_resolver: Optional[Callable] = None,
    ) -> SimulationHistory:
        """
        Run a multi-step simulation.

        Args:
            object_name: Object type name
            action_specs: List of action specs (each with 'name' and optional 'parameters')
            simulation_id: Optional simulation ID (auto-generated if None)
            verbose: Enable verbose logging
            interactive: Enable interactive clarifications
            unknown_paths: Paths to mark as unknown initially
            parameter_resolver: Function to resolve unknown parameters

        Returns:
            SimulationHistory

        Raises:
            KeyError: If object not found
        """
        # Validate object exists
        if not self.object_repo.exists(object_name):
            raise KeyError(f"Object '{object_name}' not found")

        # Run simulation using the runner
        history = self.runner.run_simulation(
            object_type=object_name,
            actions=action_specs,
            simulation_id=simulation_id,
            verbose=verbose,
            interactive=interactive,
            unknown_paths=unknown_paths,
            parameter_resolver=parameter_resolver,
        )

        return history

    def save_history(
        self,
        history: SimulationHistory,
        history_path: str | Path,
        result_path: Optional[str | Path] = None,
    ) -> None:
        """
        Save simulation history and optionally generate dataset text.

        Args:
            history: Simulation history to save
            history_path: Path to save YAML history
            result_path: Optional path to save dataset text
        """
        # Save YAML history
        self.runner.save_history_to_yaml(history, str(history_path))

        # Optionally save dataset text
        if result_path:
            dataset_text = build_interactive_dataset_text(history)
            result_path_obj = Path(result_path)
            result_path_obj.parent.mkdir(parents=True, exist_ok=True)
            result_path_obj.write_text(dataset_text, encoding="utf-8")

    def load_history(self, history_path: str | Path) -> SimulationHistory:
        """
        Load simulation history from file.

        Args:
            history_path: Path to history YAML file

        Returns:
            SimulationHistory
        """
        return self.runner.load_history_from_yaml(str(history_path))

    def get_available_actions(self, object_name: str) -> List[str]:
        """
        Get list of available actions for an object.

        Args:
            object_name: Object type name

        Returns:
            List of action names

        Raises:
            KeyError: If object not found
        """
        if not self.object_repo.exists(object_name):
            raise KeyError(f"Object '{object_name}' not found")

        return self.behavior_resolver.list_actions_for_object(object_name)


__all__ = ["SimulationService"]
