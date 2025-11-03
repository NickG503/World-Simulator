"""Interactive prompt system for resolving unknown attribute values."""

from __future__ import annotations

from typing import List, Optional, Tuple

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from simulator.core.attributes import AttributeInstance
from simulator.core.objects.object_instance import ObjectInstance
from simulator.core.registries.registry_manager import RegistryManager


class UnknownValueResolver:
    """Resolves unknown attribute values through interactive prompts."""

    def __init__(self, registries: RegistryManager, console: Optional[Console] = None):
        self.registries = registries
        self.console = console or Console()

    def get_allowed_levels(self, attr_inst: AttributeInstance, space) -> List[str]:
        """Determine selectable levels based on trend metadata."""
        direction = attr_inst.last_trend_direction or attr_inst.trend
        if direction in ("up", "down") and attr_inst.current_value == "unknown" and attr_inst.last_known_value:
            constrained = space.constrained_levels(
                last_known_value=attr_inst.last_known_value,
                trend=direction,
            )
            if constrained:
                return constrained
        return list(space.levels)

    def find_unknown_attributes(self, instance: ObjectInstance) -> List[Tuple[str, AttributeInstance]]:
        """Find all attributes with unknown values in the instance."""
        unknowns = []

        # Check global attributes
        for attr_name, attr_inst in instance.global_attributes.items():
            if attr_inst.current_value == "unknown":
                unknowns.append((f"global.{attr_name}", attr_inst))

        # Check part attributes
        for part_name, part in instance.parts.items():
            for attr_name, attr_inst in part.attributes.items():
                if attr_inst.current_value == "unknown":
                    unknowns.append((f"{part_name}.{attr_name}", attr_inst))

        return unknowns

    def resolve_unknowns(self, instance: ObjectInstance, interactive: bool = True) -> bool:
        """
        Resolve all unknown values in the instance.

        Args:
            instance: The object instance to resolve
            interactive: If True, prompt user; if False, use first value from space

        Returns:
            True if all unknowns were resolved, False otherwise
        """
        unknowns = self.find_unknown_attributes(instance)

        if not unknowns:
            return True

        if interactive:
            self.console.print(f"\n[yellow]Found {len(unknowns)} unknown attribute(s) that need values:[/yellow]")

            for path, attr_inst in unknowns:
                space = self.registries.spaces.get(attr_inst.spec.space_id)
                options = self.get_allowed_levels(attr_inst, space)

                # Display attribute info
                self.console.print(f"\n[bold]Attribute:[/bold] {path}")

                # Show available options
                table = Table(show_header=False, box=None)
                table.add_column("Option", style="cyan")
                for i, level in enumerate(options, 1):
                    table.add_row(f"{i}. {level}")
                self.console.print(table)

                # Get user choice
                while True:
                    choice = Prompt.ask(
                        f"Select value for [cyan]{path}[/cyan] (1-{len(options)})",
                        console=self.console,
                    )

                    try:
                        idx = int(choice) - 1
                        if 0 <= idx < len(options):
                            selected_value = options[idx]
                            attr_inst.current_value = selected_value
                            attr_inst.confidence = 1.0  # User-provided values have full confidence
                            attr_inst.last_known_value = selected_value
                            attr_inst.last_trend_direction = None
                            self.console.print(f"[green]Set {path} = {selected_value}[/green]")
                            break
                        else:
                            self.console.print(f"[red]Please enter a number between 1 and {len(options)}[/red]")
                    except ValueError:
                        # Try direct value match
                        if choice in options:
                            attr_inst.current_value = choice
                            attr_inst.confidence = 1.0
                            attr_inst.last_known_value = choice
                            attr_inst.last_trend_direction = None
                            self.console.print(f"[green]Set {path} = {choice}[/green]")
                            break
                        else:
                            self.console.print("[red]Invalid choice. Please enter a number or valid value.[/red]")
        else:
            # Non-interactive mode: use first value from space
            for path, attr_inst in unknowns:
                space = self.registries.spaces.get(attr_inst.spec.space_id)
                options = self.get_allowed_levels(attr_inst, space)
                selected = options[0] if options else space.levels[0]
                attr_inst.current_value = selected
                attr_inst.confidence = 0.5  # Lower confidence for auto-resolved values
                attr_inst.last_known_value = selected
                attr_inst.last_trend_direction = None

        return True

    def prompt_for_value(
        self,
        attribute_path: str,
        space_id: str,
        action_name: Optional[str] = None,
        question: Optional[str] = None,
        *,
        attribute_instance: Optional[AttributeInstance] = None,
        allowed_levels: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Prompt for a single attribute value.

        Args:
            attribute_path: Full path to the attribute (e.g., "battery.level")
            space_id: ID of the qualitative space
            action_name: Optional name of the action that requires this value
            question: Optional clarification question to display (e.g., "Precondition: what is X?")

        Returns:
            Selected value or None if cancelled
        """
        space = self.registries.spaces.get(space_id)
        if allowed_levels is not None:
            options = list(allowed_levels)
        elif attribute_instance is not None:
            options = self.get_allowed_levels(attribute_instance, space)
        else:
            options = list(space.levels)

        if question:
            # Display the clarification question (includes Pre/Postcondition prefix)
            self.console.print(f"[yellow]{question}[/yellow]\n")
        elif action_name:
            self.console.print(
                f"[yellow]Trying to run '{action_name}' action but {attribute_path} is unknown.[/yellow]\n"
            )

        self.console.print(f"[bold]Select value for {attribute_path}:[/bold]")

        # Show options
        for i, level in enumerate(options, 1):
            self.console.print(f"  {i}. {level}")

        while True:
            choice = Prompt.ask(f"Enter choice (1-{len(options)})", console=self.console)

            try:
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    return options[idx]
                else:
                    self.console.print(f"[red]Please enter a number between 1 and {len(options)}[/red]")
            except ValueError:
                if choice in options:
                    return choice
                else:
                    self.console.print("[red]Invalid choice[/red]")
