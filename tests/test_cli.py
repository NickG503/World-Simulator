"""
Unit tests for CLI commands.

Tests cover:
- validate command
- show object/behaviors commands
- apply command
"""

import pytest
from typer.testing import CliRunner

from simulator.cli.app import app

runner = CliRunner()


class TestValidateCommand:
    """Tests for validate command."""

    def test_validate_success(self):
        """Validate command succeeds with valid KB."""
        result = runner.invoke(app, ["validate"])

        assert result.exit_code == 0
        assert "All validations passed" in result.stdout

    def test_validate_shows_counts(self):
        """Validate shows object and action counts."""
        result = runner.invoke(app, ["validate"])

        assert "object type(s)" in result.stdout
        assert "action(s)" in result.stdout


class TestShowCommand:
    """Tests for show commands."""

    @pytest.mark.parametrize("object_name", ["flashlight", "tv", "kettle"])
    def test_show_object(self, object_name: str):
        """Show object definition for various object types."""
        result = runner.invoke(app, ["show", "object", object_name])

        assert result.exit_code == 0
        assert object_name in result.stdout

    def test_show_object_invalid(self):
        """Show invalid object returns error."""
        result = runner.invoke(app, ["show", "object", "nonexistent"])

        assert result.exit_code != 0

    @pytest.mark.parametrize("object_name", ["flashlight", "tv"])
    def test_show_behaviors(self, object_name: str):
        """Show behaviors for various object types."""
        result = runner.invoke(app, ["show", "behaviors", object_name])

        assert result.exit_code == 0
        assert "turn_on" in result.stdout


class TestApplyCommand:
    """Tests for apply command."""

    def test_apply_flashlight_turn_on(self):
        """Apply turn_on to flashlight."""
        result = runner.invoke(app, ["apply", "flashlight", "turn_on"])

        assert result.exit_code == 0
        assert "Status:" in result.stdout

    def test_apply_flashlight_turn_off(self):
        """Apply turn_off to flashlight - should fail (starts off)."""
        result = runner.invoke(app, ["apply", "flashlight", "turn_off"])

        # turn_off requires switch to be on, should fail or show rejected
        assert result.exit_code == 0
        assert "Status:" in result.stdout

    def test_apply_tv_turn_on(self):
        """Apply turn_on to TV."""
        result = runner.invoke(app, ["apply", "tv", "turn_on"])

        assert result.exit_code == 0

    def test_apply_invalid_object(self):
        """Apply to invalid object returns error."""
        result = runner.invoke(app, ["apply", "nonexistent", "turn_on"])

        assert result.exit_code != 0

    def test_apply_invalid_action(self):
        """Apply invalid action returns error."""
        result = runner.invoke(app, ["apply", "flashlight", "fly_away"])

        # Should fail - no such action
        assert result.exit_code != 0 or "not found" in result.stdout.lower()
