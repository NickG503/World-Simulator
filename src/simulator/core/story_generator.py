"""
Story Generator: Convert simulation history to natural language narratives.

This module converts YAML simulation history into readable stories that describe
what happened to objects during multi-step simulations in intuitive language.
"""

from __future__ import annotations
from typing import List, Optional
from datetime import datetime
import re
import logging
from pathlib import Path

from simulator.core.engine.transition_engine import DiffEntry
from .simulation_runner import (
    SimulationHistory,
    SimulationStep,
    ObjectStateSnapshot,
)


class ObjectLanguageTemplate:
    """Handles text generation for object states and actions."""
    
    def __init__(self, object_type: str):
        self.object_type = object_type
    
    def describe_initial_state(self, state: ObjectStateSnapshot) -> str:
        """Describe the object's starting state."""
        attributes = []
        for part_name, part_data in state.parts.items():
            for attr_name, attr_data in part_data.attributes.items():
                value = attr_data.value
                attributes.append(f"{part_name} {attr_name} is {value}")

        if attributes:
            return f"the {self.object_type} has " + ", ".join(attributes)
        else:
            return f"the {self.object_type} has no visible attributes"
    
    def describe_action_attempt(self, step: SimulationStep) -> str:
        """Describe an action being attempted."""
        return f"Attempting to {step.action_name} the {self.object_type}"
    
    def describe_action_success(self, step: SimulationStep) -> str:
        """Describe what happens when an action works."""
        if not step.changes:
            return f"The {step.action_name} action completed with no changes"
        
        changes_text = []
        for change in step.changes:
            changes_text.append(self._describe_change(change))

        return f"The {step.action_name} action succeeded. " + ". ".join(changes_text)
    
    def describe_action_failure(self, step: SimulationStep) -> str:
        """Describe what happens when an action fails."""
        reason = step.error_message or "unknown reason"
        return f"the {step.action_name} action failed: {reason}"
    
    def describe_final_state(self, initial_state: ObjectStateSnapshot, final_state: ObjectStateSnapshot) -> str:
        """Describe how the object ended up."""
        attributes = []
        for part_name, part_data in final_state.parts.items():
            for attr_name, attr_data in part_data.attributes.items():
                value = attr_data.value
                attributes.append(f"{part_name} {attr_name} is {value}")

        if attributes:
            return f"In the end, the {self.object_type} has " + ", ".join(attributes)
        else:
            return f"In the end, the {self.object_type} has no visible attributes"

    def _describe_change(self, change: DiffEntry) -> str:
        """Convert a single change to natural language."""
        attribute = change.attribute or ""
        before = change.before or ""
        after = change.after or ""
        kind = change.kind
        
        # Clean up attribute name
        clean_attr = attribute.replace(".", " ").replace("_", " ")
        
        if kind == "trend":
            if after == "down":
                return f"{clean_attr} starts decreasing"
            elif after == "up":
                return f"{clean_attr} starts increasing"
            elif after == "none":
                return f"{clean_attr} stops changing"
            else:
                return f"{clean_attr} trend changes to {after}"
        else:
            # Value change
            return f"{clean_attr} changes from {before} to {after}"
    
    def _simplify_error(self, error_message: str) -> str:
        """Simplify error messages for natural language."""
        # Extract meaningful parts from technical error messages
        if "==" in error_message and "current:" in error_message:
            # Pattern: "attribute == expected (current: actual, target: expected)"
            match = re.search(r'([^=]+)==\s*(\w+).*current:\s*\'([^\']*)\'\s*,\s*target:\s*\'([^\']*)\'', error_message)
            if match:
                attr, expected, current, target = match.groups()
                clean_attr = attr.strip().replace(".", " ")
                return f"the {clean_attr} is {current} but needs to be {expected}"
        
        return error_message




class StoryGenerator:
    """Converts simulation history into readable text stories."""
    
    def __init__(self):
        pass
    
    def generate_story(self, history: SimulationHistory) -> str:
        """Turn simulation history into a story."""
        template = ObjectLanguageTemplate(history.object_type)
        
        story_parts = []
        
        # Beginning
        if history.steps and len(history.steps) > 0:
            initial_state = history.steps[0].object_state_before
            initial_description = template.describe_initial_state(initial_state)
            story_parts.append(f"In the beginning, {initial_description.lower()}")
        
        # Process each step in narrative flow
        for i, step in enumerate(history.steps):
            # Transition phrases based on step number
            if i == 0:
                transition = "We start by trying to"
            elif i == 1:
                transition = "Now, after the previous action, we attempt to"
            elif i == 2:
                transition = "Then we try to"
            else:
                transition = "After that, we try to"
            
            action_verb = step.action_name.replace("_", " ")
            
            if step.status == "ok":
                success_desc = template.describe_action_success(step)
                story_parts.append(f"{transition} {action_verb} it. {success_desc}.")
            else:
                failure_desc = template.describe_action_failure(step)
                story_parts.append(f"{transition} {action_verb} it, but {failure_desc}.")
        
        # Final state in narrative form
        if history.steps and len(history.steps) > 0:
            initial_state = history.steps[0].object_state_before
            final_state = history.steps[-1].object_state_after
            final_desc = template.describe_final_state(initial_state, final_state)
            story_parts.append(final_desc + ".")
        
        # Join all parts with proper spacing
        full_story = ""
        for i, part in enumerate(story_parts):
            if i == 0:
                full_story += part
            elif part.startswith("In the end"):
                full_story += "\n\n" + part
            elif part.startswith("Now, after"):
                full_story += "\n\n" + part  
            elif part.startswith("Then"):
                full_story += "\n\n" + part
            elif part.startswith("After that"):
                full_story += "\n\n" + part
            else:
                full_story += "\n\n" + part
        
        return full_story
    
    def _format_timestamp(self, timestamp_str: str) -> str:
        """Format timestamp."""
        try:
            dt = datetime.fromisoformat(timestamp_str)
            return dt.strftime("%Y-%m-%d at %H:%M:%S")
        except:
            return timestamp_str
    
    def _calculate_duration(self, history: SimulationHistory) -> str:
        """Calculate simulation duration."""
        try:
            if not history.completed_at:
                return "incomplete"
            
            start = datetime.fromisoformat(history.started_at)
            end = datetime.fromisoformat(history.completed_at)
            duration = end - start
            
            ms = int(duration.total_seconds() * 1000)
            if ms < 1000:
                return f"{ms}ms"
            else:
                return f"{duration.total_seconds():.2f}s"
        except:
            return "unknown"
    
    def save_story_to_file(self, story: str, file_path: str) -> None:
        """Save story to text file."""
        # Ensure parent directory exists
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w') as f:
            f.write(story)
        logging.getLogger(__name__).info("Saved story to: %s", file_path)


def create_story_generator() -> StoryGenerator:
    """Factory function to create a story generator."""
    return StoryGenerator()
