# Kasa Sports Light Control - Project Instructions & Context

## Project Overview
This project automates a TP-Link Kasa smart bulb based on live sports schedules and game scores.
- **Entry Script**: `light-control.py`
- **Python Environment**: `/home/mdinitz/mykasaenv/bin/python3`
- **Target Device**: Kasa smart color bulb at IP `192.168.1.222`

## Tracked Teams & APIs
1. **Baltimore Ravens** (NFL)
   - Provider: ESPN API (`football/nfl`, team ID `33`)
   - Color: Purple (HSV `280, 100, 100`)
2. **Ohio State Buckeyes** (NCAA Football)
   - Provider: ESPN API (`football/college-football`, team ID `194`)
   - Color: Scarlet (HSV `348, 94, 73`)
3. **Baltimore Orioles** (MLB)
   - Provider: MLB Stats API (`statsapi.mlb.com`, team ID `110`)
   - Color: Orange (HSV `8, 92, 87`)

## Light Behavior & Workflow
- **Pre-Game (5 min before start)**: Turns bulb on and sets it to the team's color.
- **During Game (Scoring)**: Flashes the bulb off and on for each point or run scored, then restores that team's color.
- **Score Reversals**: If a score decreases (e.g., overturned play or stat correction), `last_score` syncs to the new score without flashing.
- **Post-Game (Final)**: Switches bulb to soft white (2500K color temp). Brightness is determined dynamically by local NOAA sunset calculation for Baltimore:
  - 5% brightness after sunset
  - 50% brightness before sunset
- **Concurrency**: All teams are monitored simultaneously using `asyncio`. Bulb communication is serialized with `BULB_LOCK` to prevent hardware/command collisions.

## Service Management
The process runs as a systemd user service:
- **Service Name**: `ravens_light.service`
- **Unit File**: `~/.config/systemd/user/ravens_light.service`
- **Control Mode**: User session (no `sudo` required; user lingering is enabled)

### Operational Commands
- **Restart service**: `systemctl --user restart ravens_light.service`
- **Check status**: `systemctl --user status ravens_light.service`
- **View live logs**: `journalctl --user -u ravens_light.service -f`
- **View recent logs**: `journalctl --user -u ravens_light.service -n 50 --no-pager`
- **Start / Stop**: `systemctl --user start ravens_light.service` / `systemctl --user stop ravens_light.service`
