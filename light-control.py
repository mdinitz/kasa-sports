#!/home/mdinitz/mykasaenv/bin/python3

import asyncio
import requests
import datetime
from dataclasses import dataclass
# We import Module to access the new light control system
from kasa import Module, KasaException
from kasa.iot import IotBulb

# --- Configuration ---
BULB_IP = "192.168.1.222"

# Game On: Purple (Hue 280, Sat 100, Val 100)
RAVENS_COLOR = (280, 100, 100) 

# Buckeyes Color (Hue 348, Sat 94, Val 73)
BUCKEYES_COLOR = (348, 94, 73)

# Game Over: Warm White (2700K), Brightness 100%
NORMAL_TEMP = 2700
NORMAL_BRIGHTNESS = 100


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

async def turn_on_normal():
    """Sets the bulb to warm white and 100% brightness."""
    try:
        bulb = await get_bulb()
        
        if Module.Light in bulb.modules:
            print("Game Over. Resetting light to Normal (2700K, 100%)...")
            
            await bulb.turn_on()
            
            # Set Color Temp using the new Module syntax
            await bulb.modules[Module.Light].set_color_temp(
                NORMAL_TEMP, 
                brightness=NORMAL_BRIGHTNESS
            )
        else:
            print("Error: Device does not appear to be a light.")

    except KasaException as e:
        print(f"Kasa Device Error: {e}")
    except Exception as e:
        print(f"Failed to set Normal: {e}")

def get_game_info(team: TeamConfig):
    """Fetches the next game schedule and status from ESPN API for the team."""
    url = (
        f"http://site.api.espn.com/apis/site/v2/sports/{team.sport_path}/teams/{team.espn_team_id}/schedule"
    )
    try:
        data = requests.get(url, timeout=10).json()
        events = data.get('events', [])
        now = datetime.datetime.now(datetime.timezone.utc)

        for event in events:
            date_str = event.get('date')
            game_time = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            
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
            
            period = status.get('type', {}).get('detail', 'In Progress')
            print(
                f"[{team.label}] Game status: {period}, Score: {last_score}. Checking again in 30 seconds..."
            )
            
        except Exception as e:
            print(f"[{team.label}] Error checking game status: {e}")
        
        await asyncio.sleep(30)  # Check more frequently for scores

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

        now = datetime.datetime.now(datetime.timezone.utc)
        game_time = game['time']
        trigger_time = game_time - datetime.timedelta(minutes=5)
        wait_seconds = (trigger_time - now).total_seconds()

        print(f"[{team.label}] Target Game: {game['name']}")
        print(f"[{team.label}] Kickoff: {game_time} UTC")

        # --- Scenario 1: Game is in the future ---
        if wait_seconds > 0:
            print(
                f"[{team.label}] Waiting {wait_seconds/60:.1f} minutes until kickoff trigger..."
            )
            await asyncio.sleep(wait_seconds)
            
            await turn_on_team_color(team)
            await wait_for_game_end(team, game['id'])
            await turn_on_normal()
            
            await asyncio.sleep(3600)

        # --- Scenario 2: Game started (or script restarted during game) ---
        elif wait_seconds <= 0 and not game['completed']:
            print(f"[{team.label}] Game in progress! Turning team color immediately.")
            await turn_on_team_color(team)
            await wait_for_game_end(team, game['id'])
            await turn_on_normal()
            await asyncio.sleep(3600)

        # --- Scenario 3: Old game found ---
        else:
            print(f"[{team.label}] Found a game, but it is Final. Skipping...")
            await asyncio.sleep(3600)

async def main():
    await asyncio.gather(*(monitor_team(team) for team in TEAM_CONFIGS))

if __name__ == "__main__":
    asyncio.run(main())
