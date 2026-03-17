# Kasa Sports Light Control

Script to drive a Kasa smart bulb based on live sports events. It is currently wired to a single bulb IP and tracks the Baltimore Ravens, Ohio State Buckeyes, and Baltimore Orioles.

## What it does
- Polls ESPN for Ravens and Buckeyes schedule/live-score updates.
- Polls the MLB Stats API for Orioles schedule/live-score updates.
- Before game start, turns the bulb to the team color (Ravens purple, Buckeyes scarlet, Orioles orange).
 - Flashes the light for scoring events, then sets the bulb to soft white (2500K) when the game is final.
 - Uses 5% brightness after sunset and 50% brightness before sunset for the post-game soft white state.
 - Runs both teams concurrently with `asyncio`.

## Requirements
- Python 3.9+ (tested with the shebang environment shown in `light-control.py`).
- Dependencies: `kasa`, `requests`.
- A Kasa-compatible color bulb on your network.

## Configuration
- Bulb IP: update `BULB_IP` in `light-control.py` to your bulb's address (currently `192.168.1.222`).
- Sunset location: update `LOCATION_LATITUDE` and `LOCATION_LONGITUDE` in `light-control.py` if the bulb is not in the Baltimore area.
- Teams: edit `TEAM_CONFIGS` to change or add teams; the script ships with Ravens, Buckeyes, and Orioles.
- Providers: Ravens and Buckeyes use ESPN team IDs and sport paths; Orioles use the MLB Stats API with MLB team ID `110`.
- Colors/behavior: team HSV values are defined at the top of the script.

## Running
- Activate your Python environment with the required packages.
- Run the script: `python light-control.py`.
- Keep the process running; it polls periodically and sleeps between games.

## Notes
- Uses ESPN's public API for football and MLB Stats API for Orioles baseball. If either API format changes, updates may be needed.
- Orioles tracking includes spring training, regular season, and postseason MLB game types.
- The script assumes a reachable bulb and will log errors if connection fails or the device is not a light.
