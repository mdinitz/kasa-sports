# Kasa Sports Light Control

Script to drive a Kasa smart bulb based on live sports events via the ESPN API. It is currently wired to a single bulb IP and only tracks the Baltimore Ravens and Ohio State Buckeyes.

## What it does
- Polls the ESPN schedule/summary endpoints for each configured team.
- Before kickoff, turns the bulb to the team color (Ravens purple, Buckeyes scarlet).
- Flashes the light for scoring events, then returns to normal warm white when the game is final.
- Runs both teams concurrently with `asyncio`.

## Requirements
- Python 3.9+ (tested with the shebang environment shown in `light-control.py`).
- Dependencies: `kasa`, `requests`.
- A Kasa-compatible color bulb on your network.

## Configuration
- Bulb IP: update `BULB_IP` in `light-control.py` to your bulb's address (currently `192.168.1.222`).
- Teams: edit `TEAM_CONFIGS` to change or add teams; the script ships with only the Ravens and Buckeyes.
- Colors/behavior: team HSV values and the default warm-white temperature/brightness are defined at the top of the script.

## Running
- Activate your Python environment with the required packages.
- Run the script: `python light-control.py`.
- Keep the process running; it polls periodically and sleeps between games.

## Notes
- Uses ESPN's public API; if the API format changes, updates may be needed.
- The script assumes a reachable bulb and will log errors if connection fails or the device is not a light.
