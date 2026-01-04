#!/home/mdinitz/mykasaenv/bin/python3

import asyncio
import requests
import datetime
from dataclasses import dataclass
from zoneinfo import ZoneInfo
# We import Module to access the new light control system
from kasa import Module, KasaException
from kasa.iot import IotBulb

# --- Configuration ---
BULB_IP = "192.168.1.222"

# Game On: Purple (Hue 280, Sat 100, Val 100)
RAVENS_COLOR = (280, 100, 100) 

# Buckeyes Color (Hue 348, Sat 94, Val 73)
BUCKEYES_COLOR = (348, 94, 73)


@dataclass(frozen=True)
class TeamConfig:
    label: str
    name: str
    espn_team_id: str
    sport_path: str 
    color: tuple


TEAM_CONFIGS = (
    TeamConfig(
        label="RAVENS",
        name="Baltimore Ravens",
        espn_team_id="33",
        sport_path="football/nfl",
        color=RAVENS_COLOR,
    ),
    TeamConfig(
        label="BUCKEYES",
        name="Ohio State Buckeyes",
        espn_team_id="194",
        sport_path="football/college-football",
        color=BUCKEYES_COLOR,
    ),
)

async def get_bulb():
    """
    Connects directly to the bulb using the modern IotBulb class.
    """
    bulb = IotBulb(BULB_IP)
    await bulb.update()
    return bulb

async def turn_on_team_color(team: TeamConfig):
    """Connects to the bulb, turns it on, and sets it to the team color."""
    try:
        bulb = await get_bulb()
        
        # Check if the device actually has a Light module (Safety check)
        if Module.Light in bulb.modules:
            print(f"[{team.label}] Game Time! Setting color at {BULB_IP}...")
            
            # 1. Turn On
            await bulb.turn_on()
            
            # 2. Set Color using the new Module syntax
            await bulb.modules[Module.Light].set_hsv(*team.color)
        else:
            print("Error: Device does not appear to be a light.")
            
    except KasaException as e:
        print(f"[{team.label}] Kasa Device Error: {e}")
    except Exception as e:
        print(f"[{team.label}] Failed to set team color: {e}")


async def capture_bulb_state():
    """Capture the bulb's current light state so we can restore it later."""
    try:
        bulb = await get_bulb()
        await bulb.update()

        light = bulb.modules.get(Module.Light)
        if not light:
            print("Error: Device does not appear to be a light.")
            return None

        return {
            "is_on": bulb.is_on,
            "hsv": getattr(light, "hsv", None),
            "color_temp": getattr(light, "color_temp", None),
            "brightness": getattr(light, "brightness", None),
        }

    except Exception as e:
        print(f"Failed to capture bulb state: {e}")
        return None


async def restore_bulb_state(state):
    """Restore a previously captured bulb state after a game ends."""
    if not state:
        print("No saved bulb state to restore.")
        return

    try:
        bulb = await get_bulb()
        light = bulb.modules.get(Module.Light)
        if not light:
            print("Error: Device does not appear to be a light.")
            return

        if state.get("is_on"):
            await bulb.turn_on()

            if state.get("hsv"):
                await light.set_hsv(*state["hsv"])
                if state.get("brightness") is not None:
                    await light.set_brightness(state["brightness"])
            elif state.get("color_temp"):
                await light.set_color_temp(
                    state["color_temp"], brightness=state.get("brightness")
                )
        else:
            await bulb.turn_off()

    except Exception as e:
        print(f"Failed to restore bulb state: {e}")

def get_game_info(team: TeamConfig):
    """Fetches the next game schedule and status from ESPN API for the team."""
    url = (
        f"http://site.api.espn.com/apis/site/v2/sports/{team.sport_path}/teams/{team.espn_team_id}/schedule"
    )
    try:
        data = requests.get(url, timeout=10).json()
        events = data.get('events', [])
        now = datetime.datetime.now(ZoneInfo('America/New_York'))

        for event in events:
            date_str = event.get('date')
            game_time = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            # Convert from UTC to Eastern Time
            game_time = game_time.astimezone(ZoneInfo('America/New_York'))
            
            competitions = event.get('competitions', [])
            if not competitions:
                continue
                
            status = competitions[0].get('status', {})
            is_complete = status.get('type', {}).get('completed', False)
            game_id = event.get('id')

            if game_time > now - datetime.timedelta(hours=6):
                return {
                    'time': game_time,
                    'name': event.get('name', 'Unknown Game'),
                    'id': game_id,
                    'completed': is_complete
                }
                
    except Exception as e:
        print(f"[{team.label}] Error fetching schedule: {e}")
    
    return None

async def flash_score(bulb, points, team: TeamConfig):
    """Flash the light to indicate a score.
    
    Args:
        bulb: The Kasa bulb instance
        points: Number of points scored (3 for field goal, 6 for TD, etc.)
    """
    if not bulb or points <= 0:
        print(f"[{team.label}] Invalid bulb or points")
        return
        
    light_module = bulb.modules.get(Module.Light)
    if not light_module:
        print(f"[{team.label}] No light module found")
        return
    
    try:
        # Get current color state from the bulb using modern Module syntax
        await bulb.update()  # Refresh bulb state
        light_state = bulb.modules[Module.Light]
                
        # Flash for each point (1 second on, 0.5 seconds off between flashes)
        for i in range(points):
            # Turn off
            await bulb.turn_off()
            await asyncio.sleep(0.5)
            # Turn on with current color
            await bulb.turn_on()
            await asyncio.sleep(0.5)
                
    except Exception as e:
        print(f"[{team.label}] Error during flash sequence: {e}")
        # Try to restore original state on error
        try:
            await light_module.set_hsv(*team.color)
        except:
            pass

async def wait_for_game_end(team: TeamConfig, game_id):
    """Polls the API to monitor game status and scores."""
    print(f"[{team.label}] Monitoring game {game_id}...")
    
    url = (
        f"http://site.api.espn.com/apis/site/v2/sports/{team.sport_path}/summary?event={game_id}"
    )
    last_score = 0
    bulb = None
    
    try:
        bulb = await get_bulb()
    except Exception as e:
        print(f"Could not connect to bulb: {e}")
    
    while True:
        try:
            data = requests.get(url, timeout=10).json()
            header = data.get('header', {})
            competitions = header.get('competitions', [])
            if not competitions:
                print("API Warning: No competition data found. Retrying...")
                await asyncio.sleep(60)
                continue
                
            competition = competitions[0]
            status = competition.get('status', {})
            completed = status.get('type', {}).get('completed', False)
            
            # Check for score changes
            for competitor in competition.get('competitors', []):
                if competitor.get('id') == team.espn_team_id:
                    current_score = int(competitor.get('score', '0'))
                    if current_score > last_score:
                        points_scored = current_score - last_score
                        print(
                            f"[{team.label}] Scored {points_scored} points! New score: {current_score}"
                        )
                        await flash_score(bulb, points_scored, team)
                        last_score = current_score
                    break
            
            if completed:
                print(f"[{team.label}] API reports game is FINAL.")
                return
            
            # period = status.get('type', {}).get('detail', 'In Progress')
            # print(
            #     f"[{team.label}] Game status: {period}, Score: {last_score}. Checking again in 10 seconds..."
            # )
            
        except Exception as e:
            print(f"[{team.label}] Error checking game status: {e}")
        
        await asyncio.sleep(10)  # Check more frequently for scores

async def test_flash(team: TeamConfig = TEAM_CONFIGS[0]):
    bulb = await get_bulb()
    await bulb.modules[Module.Light].set_hsv(*team.color)
    await flash_score(bulb, 6, team)


async def monitor_team(team: TeamConfig):
    """Continuously monitor the team's schedule and drive the light behavior."""
    print(f"[{team.label}] Starting light automation...")
    
    while True:
        game = get_game_info(team)
        
        if not game:
            print(f"[{team.label}] No upcoming games found. Sleeping for 24 hours...")
            await asyncio.sleep(86400)
            continue

        now = datetime.datetime.now(ZoneInfo('America/New_York'))
        game_time = game['time']
        trigger_time = game_time - datetime.timedelta(minutes=5)
        wait_seconds = (trigger_time - now).total_seconds()

        print(f"[{team.label}] Target Game: {game['name']}")
        print(f"[{team.label}] Kickoff: {game_time.strftime('%Y-%m-%d %H:%M:%S')} ET")

        # --- Scenario 1: Game is in the future ---
        if wait_seconds > 0:
            print(
                f"[{team.label}] Waiting {wait_seconds/60:.1f} minutes until kickoff trigger..."
            )
            await asyncio.sleep(wait_seconds)

            saved_state = await capture_bulb_state()

            await turn_on_team_color(team)
            try:
                await wait_for_game_end(team, game['id'])
            finally:
                await restore_bulb_state(saved_state)

            await asyncio.sleep(3600)

        # --- Scenario 2: Game started (or script restarted during game) ---
        elif wait_seconds <= 0 and not game['completed']:
            print(f"[{team.label}] Game in progress! Turning team color immediately.")
            saved_state = await capture_bulb_state()

            await turn_on_team_color(team)
            try:
                await wait_for_game_end(team, game['id'])
            finally:
                await restore_bulb_state(saved_state)

            await asyncio.sleep(3600)

        # --- Scenario 3: Old game found ---
        else:
            print(f"[{team.label}] Found a game, but it is Final. Skipping...")
            await asyncio.sleep(3600)

async def main():
#    state = await capture_bulb_state()
#    print("current state:", state)
#    await turn_on_team_color(TEAM_CONFIGS[0])
#    await restore_bulb_state(state)

    await asyncio.gather(*(monitor_team(team) for team in TEAM_CONFIGS))

if __name__ == "__main__":
    asyncio.run(main())
