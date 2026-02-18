# Kasa Sports Light Control

Script to drive a Kasa smart bulb based on live sports events via the ESPN API. It is currently wired to a single bulb IP and tracks the Baltimore Ravens, Ohio State Buckeyes, and Baltimore Orioles.

## What it does
- Polls the ESPN schedule/summary endpoints for each configured team.
- Before game start, turns the bulb to the team color (Ravens purple, Buckeyes scarlet, Orioles orange).
 - Flashes the light for scoring events, then restores the bulb to its previous settings when the game is final (instead of forcing a warm white).
 - Runs both teams concurrently with `asyncio`.

## Requirements
- Python 3.9+ (tested with the shebang environment shown in `light-control.py`).
- Dependencies: `kasa`, `requests`.
- A Kasa-compatible color bulb on your network.

## Configuration
- Bulb IP: update `BULB_IP` in `light-control.py` to your bulb's address (currently `192.168.1.222`).
- Teams: edit `TEAM_CONFIGS` to change or add teams; the script ships with Ravens, Buckeyes, and Orioles.
- Colors/behavior: team HSV values are defined at the top of the script.

## Running
- Activate your Python environment with the required packages.
- Run the script: `python light-control.py`.
- Keep the process running; it polls periodically and sleeps between games.

## Notes
- Uses ESPN's public API; if the API format changes, updates may be needed.
- The script assumes a reachable bulb and will log errors if connection fails or the device is not a light.
