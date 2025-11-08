"""Test error message formatting for complex logical conditions."""

from pathlib import Path

from simulator.core.engine.transition_engine import TransitionEngine
from simulator.core.registries import RegistryManager
from simulator.io.loaders.action_loader import load_actions
from simulator.io.loaders.object_loader import instantiate_default, load_object_types
from simulator.io.loaders.yaml_loader import load_spaces


def _setup_rm() -> RegistryManager:
    """Setup registry manager with real KB objects."""
    rm = RegistryManager()
    rm.register_defaults()
    load_spaces(str(Path.cwd() / "kb" / "spaces"), rm)
    load_object_types(str(Path.cwd() / "kb" / "objects"), rm)
    load_actions(str(Path.cwd() / "kb" / "actions"), rm)
    return rm


def test_simple_attribute_condition_error_message():
    """Test error message for simple attribute condition failure.

    Tests the change_channel action which requires screen.power to be on.
    """
    rm = _setup_rm()
    obj = rm.objects.get("tv")
    action = rm.create_behavior_enhanced_action("tv", "change_channel")
    assert action is not None

    inst = instantiate_default(obj, rm)
    # Ensure screen power is off to trigger precondition failure
    inst.parts["screen"].attributes["power"].current_value = "off"

    engine = TransitionEngine(rm)
    result = engine.apply_action(inst, action, {"to": "medium"})

    assert result.status == "rejected"
    assert result.reason is not None
    # Should show structure and failure message
    assert "screen.power==on" in result.reason
    assert "should be on" in result.reason
    assert "but got off" in result.reason


def test_or_condition_error_shows_actual_values():
    """Test that OR condition failures show actual attribute values.

    Tests premium_mode which has: (power_source.voltage==high OR network.wifi_connected==on)
    """
    rm = _setup_rm()
    obj = rm.objects.get("tv")
    action = rm.create_behavior_enhanced_action("tv", "premium_mode")
    assert action is not None

    inst = instantiate_default(obj, rm)
    # Set screen.power to on to pass first precondition
    inst.parts["screen"].attributes["power"].current_value = "on"
    # Set values that will fail the OR precondition
    inst.parts["power_source"].attributes["voltage"].current_value = "low"
    inst.parts["network"].attributes["wifi_connected"].current_value = "off"

    engine = TransitionEngine(rm)
    result = engine.apply_action(inst, action, {})

    assert result.status == "rejected"
    assert result.reason is not None
    # Should show the OR structure
    assert "power_source.voltage==high OR network.wifi_connected==on" in result.reason
    # Should show actual values in failure message
    assert "instead got" in result.reason
    assert "power_source.voltage=" in result.reason
    assert "network.wifi_connected=" in result.reason


def test_and_condition_error_shows_actual_values():
    """Test that AND condition failures show actual attribute values.

    Tests stream_hd which has: (network.wifi_connected==on AND power_source.connection==on)
    """
    rm = _setup_rm()
    obj = rm.objects.get("tv")
    action = rm.create_behavior_enhanced_action("tv", "stream_hd")
    assert action is not None

    inst = instantiate_default(obj, rm)
    # Set screen.power to on to pass first precondition
    inst.parts["screen"].attributes["power"].current_value = "on"
    # Set values that will fail the AND precondition
    inst.parts["network"].attributes["wifi_connected"].current_value = "off"
    inst.parts["power_source"].attributes["connection"].current_value = "on"

    engine = TransitionEngine(rm)
    result = engine.apply_action(inst, action, {})

    assert result.status == "rejected"
    assert result.reason is not None
    # Should show the AND structure
    assert "network.wifi_connected==on AND power_source.connection==on" in result.reason
    # Should show actual values
    assert "instead got" in result.reason
    assert "network.wifi_connected=" in result.reason


def test_error_message_format_consistency():
    """Test that error messages have consistent format with structure and details.

    Verifies the complete format: "Precondition failed (structure): details"
    """
    rm = _setup_rm()
    obj = rm.objects.get("tv")
    action = rm.create_behavior_enhanced_action("tv", "change_channel")
    assert action is not None

    inst = instantiate_default(obj, rm)
    # Ensure screen power is off
    inst.parts["screen"].attributes["power"].current_value = "off"

    engine = TransitionEngine(rm)
    result = engine.apply_action(inst, action, {"to": "medium"})

    assert result.status == "rejected"
    assert result.reason is not None
    # Should have the complete format
    assert result.reason.startswith("Precondition failed")
    # Should include both structure and details
    assert "screen.power" in result.reason
