#!/usr/bin/env python3
"""Create the full set of ground-truth histories and run regression tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List

GROUND_TRUTH_DIR = Path(__file__).parent / "data" / "ground_truth"
BUILD_SCRIPT = Path("scripts") / "build_ground_truth.py"

SCENARIOS = [
    {
        "simulation_id": "flashlight_battery_trend_low",
        "object": "flashlight",
        "actions": ["replace_battery:to=low", "turn_on", "turn_off", "turn_on"],
        "hide": ["battery.level"],
        "answers": ["battery.level=empty"],
    },
    {
        "simulation_id": "flashlight_charge_cycle",
        "object": "flashlight",
        "actions": ["turn_on", "turn_off", "charge_battery", "turn_off"],
        "initial": ["battery.level=medium"],
        "hide": ["battery.level"],
        "answers": ["battery.level=medium"],
    },
    {
        "simulation_id": "tv_stream_hd",
        "object": "tv",
        "actions": ["turn_on", "stream_hd"],
        "initial": ["power_source.connection=on", "network.wifi_connected=on"],
        "hide": ["network.wifi_connected", "power_source.connection"],
    },
    {
        "simulation_id": "tv_stream_hd_smart_adjust",
        "object": "tv",
        "actions": ["turn_on", "stream_hd", "smart_adjust"],
        "initial": [
            "power_source.connection=on",
            "network.wifi_connected=on",
            "power_source.voltage=high",
        ],
        "hide": ["network.wifi_connected", "power_source.connection", "power_source.voltage"],
    },
    {
        "simulation_id": "tv_smart_adjust_low_signal",
        "object": "tv",
        "actions": ["turn_on", "smart_adjust"],
        "initial": ["network.wifi_connected=off", "power_source.voltage=medium"],
        "hide": ["network.wifi_connected", "power_source.voltage"],
    },
    {
        "simulation_id": "tv_premium_mode_high",
        "object": "tv",
        "actions": ["turn_on", "premium_mode"],
        "initial": [
            "power_source.connection=on",
            "power_source.voltage=high",
            "network.wifi_connected=off",
            "audio.channel=medium",
            "cooling.temperature=cold",
        ],
        "hide": ["power_source.voltage", "audio.channel", "cooling.temperature"],
        "answers": ["cooling.temperature=cold"],
    },
    {
        "simulation_id": "tv_premium_mode_audio_low",
        "object": "tv",
        "actions": ["turn_on", "premium_mode"],
        "initial": [
            "power_source.connection=on",
            "power_source.voltage=high",
            "network.wifi_connected=on",
            "audio.channel=low",
            "cooling.temperature=cold",
        ],
        "hide": ["audio.channel", "cooling.temperature"],
        "answers": ["cooling.temperature=cold"],
    },
    {
        "simulation_id": "tv_open_streaming_wifi_on",
        "object": "tv",
        "actions": ["turn_on", "open_streaming"],
        "initial": ["network.wifi_connected=on"],
        "hide": ["network.wifi_connected"],
    },
    {
        "simulation_id": "tv_open_streaming_wifi_off",
        "object": "tv",
        "actions": ["turn_on", "open_streaming"],
        "initial": ["network.wifi_connected=off"],
        "hide": ["network.wifi_connected"],
    },
    {
        "simulation_id": "tv_adjust_brightness_wifi_on",
        "object": "tv",
        "actions": ["turn_on", "adjust_brightness"],
        "initial": ["network.wifi_connected=on"],
        "hide": ["network.wifi_connected"],
    },
]


def _execute(cmd: List[str]) -> None:
    print("\n→", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    python_exe = sys.executable
    GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)

    for scenario in SCENARIOS:
        output = GROUND_TRUTH_DIR / f"{scenario['simulation_id']}.yaml"
        cmd: List[str] = [
            python_exe,
            str(BUILD_SCRIPT),
            "--object",
            scenario["object"],
            "--simulation-id",
            scenario["simulation_id"],
            "--output",
            str(output),
        ]
        for assignment in scenario.get("initial", []):
            cmd.extend(["--initial", assignment])
        for hidden in scenario.get("hide", []):
            cmd.extend(["--hide", hidden])
        for tracked in scenario.get("track", []):
            cmd.extend(["--track", tracked])
        for answer in scenario.get("answers", []):
            cmd.extend(["--answer", answer])
        cmd.extend(scenario["actions"])
        _execute(cmd)

    print("\nRunning regression tests against generated ground-truth histories...\n")
    _execute([python_exe, "-m", "pytest", "tests/test_ground_truth_replay.py"])


if __name__ == "__main__":
    main()
