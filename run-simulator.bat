@echo off
REM World-Simulator CLI Runner
REM Usage: run-simulator.bat [command] [args...]

REM Activate virtual environment and run the simulator
call .venv\Scripts\activate.bat
uv run python -m simulator.cli.app %*

REM Examples:
REM   run-simulator.bat validate
REM   run-simulator.bat show object kettle --version 1
REM   run-simulator.bat show object flashlight --version 1
