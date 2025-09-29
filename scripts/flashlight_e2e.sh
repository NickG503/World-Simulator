#!/usr/bin/env bash
set -euo pipefail

echo "== Validate KB =="
uv run sim validate

echo "\n== Show flashlight behaviors =="
uv run sim show behaviors flashlight

echo "\n== Show flashlight object (summary) =="
uv run sim show object flashlight

echo "\n== Simple simulate (turn_on, turn_off) and save artifacts =="
uv run sim simulate flashlight turn_on turn_off \
  --history-name basic.yaml --dataset-name basic.txt --id basic

echo "\n== Inspect compact history =="
uv run sim history outputs/histories/basic.yaml

echo "\n== Failure case: drain then turn_on (precondition fail) =="
uv run sim simulate flashlight drain_battery turn_on \
  --history-name fail.yaml --dataset-name fail.txt --id failv2
uv run sim history outputs/histories/fail.yaml

echo "\n== Interactive simulate (prompt for unknown then continue) =="
uv run sim simulate flashlight turn_on \
  --history-name turn_on_interactive.yaml --dataset-name turn_on_interactive.txt --id turn_on_interactive

echo "\nAll flashlight E2E checks completed."
