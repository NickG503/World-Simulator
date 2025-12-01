"""
Unit tests for CLI commands.

Tests cover:
- validate command
- show object/behaviors commands
- apply command
"""

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

    def test_show_object_flashlight(self):
        """Show flashlight object definition."""
        result = runner.invoke(app, ["show", "object", "flashlight"])

        assert result.exit_code == 0
        assert "flashlight" in result.stdout
        assert "battery.level" in result.stdout or "battery" in result.stdout

    def test_show_object_tv(self):
        """Show TV object definition."""
        result = runner.invoke(app, ["show", "object", "tv"])

        assert result.exit_code == 0
        assert "tv" in result.stdout

    def test_show_object_kettle(self):
        """Show kettle object definition."""
        result = runner.invoke(app, ["show", "object", "kettle"])

        assert result.exit_code == 0
        assert "kettle" in result.stdout

    def test_show_object_invalid(self):
        """Show invalid object returns error."""
        result = runner.invoke(app, ["show", "object", "nonexistent"])

        assert result.exit_code != 0

    def test_show_behaviors_flashlight(self):
        """Show flashlight behaviors."""
        result = runner.invoke(app, ["show", "behaviors", "flashlight"])

        assert result.exit_code == 0
        assert "turn_on" in result.stdout
        assert "turn_off" in result.stdout

    def test_show_behaviors_tv(self):
        """Show TV behaviors."""
        result = runner.invoke(app, ["show", "behaviors", "tv"])

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
