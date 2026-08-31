#!/home/mdinitz/mykasaenv/bin/python3

import asyncio
import datetime
import math
from dataclasses import dataclass
from typing import Optional
from zoneinfo import ZoneInfo
import requests
from kasa import Module, KasaException
from kasa.iot import IotBulb

# --- Configuration ---
BULB_IP = "192.168.1.222"
WARM_WHITE_COLOR_TEMP = 2500
POST_GAME_BRIGHTNESS_AFTER_SUNSET = 5
POST_GAME_BRIGHTNESS_BEFORE_SUNSET = 50
LOCATION_LATITUDE = 39.2904
LOCATION_LONGITUDE = -76.6122
LOCAL_TIMEZONE = ZoneInfo("America/New_York")
MAX_SCHEDULE_SLEEP_SECONDS = 7200

# Game On: Purple (Hue 280, Sat 100, Val 100)
RAVENS_COLOR = (280, 100, 100)

# Buckeyes Color (Hue 348, Sat 94, Val 73)
BUCKEYES_COLOR = (348, 94, 73)

# Orioles Color (Hue 15.325 rounded to 15, Sat 92, Val 98)
ORIOLES_COLOR = (8, 92, 87)

ESPN_PROVIDER = "espn"
MLB_PROVIDER = "mlb"

MLB_SPORT_ID = 1
MLB_GAME_TYPES = ("S", "R", "F", "D", "L", "W")

HTTP_SESSION = requests.Session()
HTTP_TIMEOUT = 10
BULB_LOCK = asyncio.Lock()


@dataclass(frozen=True)
class TeamConfig:
    label: str
    name: str
    provider: str
    color: tuple
    espn_team_id: Optional[str] = None
    sport_path: Optional[str] = None
    mlb_team_id: Optional[int] = None


@dataclass(frozen=True)
class Game:
    id: str
    name: str
    time: datetime.datetime
    completed: bool
    status: str = ""


TEAM_CONFIGS = (
    TeamConfig(
        label="RAVENS",
        name="Baltimore Ravens",
        provider=ESPN_PROVIDER,
        espn_team_id="33",
        sport_path="football/nfl",
        color=RAVENS_COLOR,
    ),
    TeamConfig(
        label="BUCKEYES",
        name="Ohio State Buckeyes",
        provider=ESPN_PROVIDER,
        espn_team_id="194",
        sport_path="football/college-football",
        color=BUCKEYES_COLOR,
    ),
    TeamConfig(
        label="ORIOLES",
        name="Baltimore Orioles",
        provider=MLB_PROVIDER,
        mlb_team_id=110,
        color=ORIOLES_COLOR,
    ),
)


def normalize_degrees(angle):
    return angle % 360


def calculate_sunset(target_date: datetime.date):
    """Calculate local sunset time using the NOAA solar calculation."""
    day_of_year = target_date.timetuple().tm_yday
    longitude_hour = LOCATION_LONGITUDE / 15

    approximate_time = day_of_year + ((18 - longitude_hour) / 24)
    mean_anomaly = (0.9856 * approximate_time) - 3.289

    true_longitude = mean_anomaly + (
        1.916 * math.sin(math.radians(mean_anomaly))
    ) + (
        0.020 * math.sin(math.radians(2 * mean_anomaly))
    ) + 282.634
    true_longitude = normalize_degrees(true_longitude)

    right_ascension = math.degrees(
        math.atan(0.91764 * math.tan(math.radians(true_longitude)))
    )
    right_ascension = normalize_degrees(right_ascension)

    true_longitude_quadrant = math.floor(true_longitude / 90) * 90
    right_ascension_quadrant = math.floor(right_ascension / 90) * 90
    right_ascension += true_longitude_quadrant - right_ascension_quadrant
    right_ascension /= 15

    sin_declination = 0.39782 * math.sin(math.radians(true_longitude))
    cos_declination = math.cos(math.asin(sin_declination))

    cos_local_hour_angle = (
        math.cos(math.radians(90.833))
        - (math.sin(math.radians(LOCATION_LATITUDE)) * sin_declination)
    ) / (math.cos(math.radians(LOCATION_LATITUDE)) * cos_declination)

    if cos_local_hour_angle <= -1 or cos_local_hour_angle >= 1:
        return datetime.datetime.combine(
            target_date,
            datetime.time(hour=18, minute=0),
            tzinfo=LOCAL_TIMEZONE,
        )

    local_hour_angle = math.degrees(math.acos(cos_local_hour_angle)) / 15
    local_mean_time = (
        local_hour_angle + right_ascension - (0.06571 * approximate_time) - 6.622
    )

    utc_hour = (local_mean_time - longitude_hour) % 24
    utc_midnight = datetime.datetime.combine(
        target_date,
        datetime.time.min,
        tzinfo=datetime.timezone.utc,
    )
    sunset_utc = utc_midnight + datetime.timedelta(hours=utc_hour)
    return sunset_utc.astimezone(LOCAL_TIMEZONE)


def get_post_game_brightness(now=None):
    """Choose the post-game brightness based on whether sunset has passed."""
    current_time = now or datetime.datetime.now(LOCAL_TIMEZONE)
    sunset = calculate_sunset(current_time.date())

    if current_time >= sunset:
        return POST_GAME_BRIGHTNESS_AFTER_SUNSET, sunset

    return POST_GAME_BRIGHTNESS_BEFORE_SUNSET, sunset


def fetch_json_sync(url: str) -> dict:
    """Fetch JSON synchronously with configured timeouts."""
    response = HTTP_SESSION.get(url, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    return response.json()


async def fetch_json(url: str) -> dict:
    """Fetch JSON asynchronously via thread pool to keep the event loop unblocked."""
    return await asyncio.to_thread(fetch_json_sync, url)


def validate_team_configs():
    """Validate configured team IDs and log warnings for mismatches."""
    print("[CONFIG] Validating team configurations...")

    for team in TEAM_CONFIGS:
        if team.provider == ESPN_PROVIDER:
            validate_espn_team_config(team)
        elif team.provider == MLB_PROVIDER:
            validate_mlb_team_config(team)
        else:
            print(f"[CONFIG][{team.label}] WARNING: Unknown provider '{team.provider}'")


def validate_espn_team_config(team: TeamConfig):
    url = (
        f"https://site.api.espn.com/apis/site/v2/sports/{team.sport_path}/teams/{team.espn_team_id}"
    )
    try:
        data = fetch_json_sync(url)
        api_team = data.get("team", {})
        api_team_name = api_team.get("displayName")
        api_team_id = api_team.get("id")

        if not api_team_id or not api_team_name:
            print(
                f"[CONFIG][{team.label}] WARNING: Could not resolve team at {team.sport_path}/teams/{team.espn_team_id}"
            )
            return

        if str(api_team_id) != str(team.espn_team_id):
            print(
                f"[CONFIG][{team.label}] WARNING: Config team id {team.espn_team_id} resolved as {api_team_id} ({api_team_name})"
            )
            return

        configured_name = team.name.strip().lower()
        resolved_name = api_team_name.strip().lower()
        if configured_name != resolved_name:
            print(
                f"[CONFIG][{team.label}] WARNING: Config name '{team.name}' differs from ESPN '{api_team_name}'"
            )
        else:
            print(
                f"[CONFIG][{team.label}] OK: {api_team_name} ({team.sport_path}/teams/{team.espn_team_id})"
            )

    except Exception as e:
        print(
            f"[CONFIG][{team.label}] WARNING: Validation request failed for {team.sport_path}/teams/{team.espn_team_id}: {e}"
        )


def validate_mlb_team_config(team: TeamConfig):
    if team.mlb_team_id is None:
        print(f"[CONFIG][{team.label}] WARNING: No MLB team id configured.")
        return

    url = f"https://statsapi.mlb.com/api/v1/teams/{team.mlb_team_id}?sportId={MLB_SPORT_ID}"
    try:
        data = fetch_json_sync(url)
        teams = data.get("teams", [])
        if not teams:
            print(
                f"[CONFIG][{team.label}] WARNING: Could not resolve MLB team id {team.mlb_team_id}"
            )
            return

        api_team = teams[0]
        api_team_name = api_team.get("name")
        api_team_id = api_team.get("id")

        if int(api_team_id) != int(team.mlb_team_id):
            print(
                f"[CONFIG][{team.label}] WARNING: Config team id {team.mlb_team_id} resolved as {api_team_id} ({api_team_name})"
            )
            return

        configured_name = team.name.strip().lower()
        resolved_name = str(api_team_name).strip().lower()
        if configured_name != resolved_name:
            print(
                f"[CONFIG][{team.label}] WARNING: Config name '{team.name}' differs from MLB '{api_team_name}'"
            )
        else:
            print(
                f"[CONFIG][{team.label}] OK: {api_team_name} (MLB teamId={team.mlb_team_id})"
            )

    except Exception as e:
        print(
            f"[CONFIG][{team.label}] WARNING: Validation request failed for MLB team id {team.mlb_team_id}: {e}"
        )


async def get_bulb():
    """Connects directly to the bulb using the modern IotBulb class."""
    bulb = IotBulb(BULB_IP)
    await bulb.update()
    return bulb


async def turn_on_team_color(team: TeamConfig):
    """Connects to the bulb, turns it on, and sets it to the team color."""
    async with BULB_LOCK:
        try:
            bulb = await get_bulb()
            if Module.Light in bulb.modules:
                print(f"[{team.label}] Game Time! Setting color at {BULB_IP}...")
                await bulb.turn_on()
                await bulb.modules[Module.Light].set_hsv(*team.color)
            else:
                print(f"[{team.label}] Error: Device does not appear to be a light.")
        except KasaException as e:
            print(f"[{team.label}] Kasa Device Error: {e}")
        except Exception as e:
            print(f"[{team.label}] Failed to set team color: {e}")


async def set_post_game_light(team: TeamConfig):
    """Set the bulb to soft white after a game ends, with sunset-based brightness."""
    brightness, sunset = get_post_game_brightness()
    async with BULB_LOCK:
        try:
            bulb = await get_bulb()
            light = bulb.modules.get(Module.Light)
            if not light:
                print(f"[{team.label}] Error: Device does not appear to be a light.")
                return

            await bulb.turn_on()
            await light.set_color_temp(WARM_WHITE_COLOR_TEMP, brightness=brightness)
            print(
                f"[{team.label}] Post-game light set to soft white at {brightness}% brightness "
                f"(sunset: {sunset.strftime('%Y-%m-%d %H:%M:%S')} ET)."
            )
        except Exception as e:
            print(f"[{team.label}] Failed to set post-game light: {e}")


async def flash_score(points: int, team: TeamConfig, bulb=None):
    """Flash the light to indicate a score.

    Args:
        points: Number of points/runs scored
        team: The team configuration
        bulb: Optional existing Kasa bulb instance (re-acquired if None)
    """
    if points <= 0:
        return

    async with BULB_LOCK:
        try:
            if bulb is None:
                bulb = await get_bulb()
            else:
                await bulb.update()

            light_module = bulb.modules.get(Module.Light)
            if not light_module:
                print(f"[{team.label}] No light module found")
                return

            for _ in range(points):
                await bulb.turn_off()
                await asyncio.sleep(0.5)
                await bulb.turn_on()
                await asyncio.sleep(0.5)

            # Ensure team color is restored after flash sequence
            await light_module.set_hsv(*team.color)

        except Exception as e:
            print(f"[{team.label}] Error during flash sequence: {e}")


async def get_game_info(team: TeamConfig) -> Optional[Game]:
    """Fetch the next relevant game for the configured team."""
    if team.provider == MLB_PROVIDER:
        return await get_mlb_game_info(team)
    return await get_espn_game_info(team)


async def get_espn_game_info(team: TeamConfig) -> Optional[Game]:
    """Fetches the next game schedule and status from ESPN API for the team."""
    base_url = (
        f"https://site.api.espn.com/apis/site/v2/sports/{team.sport_path}/teams/{team.espn_team_id}/schedule"
    )
    urls = [
        f"{base_url}?seasontype=1",  # Preseason
        f"{base_url}?seasontype=2",  # Regular season
        f"{base_url}?seasontype=3",  # Postseason / playoffs / bowl games
    ]

    try:
        events = []
        seen_event_ids = set()

        for url in urls:
            try:
                data = await fetch_json(url)
                for event in data.get("events", []):
                    event_id = event.get("id")
                    if event_id and event_id in seen_event_ids:
                        continue
                    if event_id:
                        seen_event_ids.add(event_id)
                    events.append(event)
            except Exception as e:
                print(f"[{team.label}] Warning fetching schedule from {url}: {e}")

        events.sort(key=lambda event: event.get("date", ""))
        now = datetime.datetime.now(LOCAL_TIMEZONE)

        for event in events:
            date_str = event.get("date")
            if not date_str:
                continue

            game_time = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            game_time = game_time.astimezone(LOCAL_TIMEZONE)

            competitions = event.get("competitions", [])
            if not competitions:
                continue

            status = competitions[0].get("status", {})
            is_complete = status.get("type", {}).get("completed", False)
            game_id = str(event.get("id", ""))

            if game_time > now - datetime.timedelta(hours=6):
                return Game(
                    id=game_id,
                    name=event.get("name", "Unknown Game"),
                    time=game_time,
                    completed=is_complete,
                )

    except Exception as e:
        print(f"[{team.label}] Error fetching ESPN schedule: {e}")

    return None


async def get_mlb_game_info(team: TeamConfig) -> Optional[Game]:
    """Fetches the next Orioles game from MLB Stats API."""
    if team.mlb_team_id is None:
        print(f"[{team.label}] No MLB team id configured.")
        return None

    today = datetime.datetime.now(LOCAL_TIMEZONE).date()
    url = (
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId={MLB_SPORT_ID}"
        f"&teamId={team.mlb_team_id}"
        f"&startDate={today.isoformat()}"
        f"&endDate={(today + datetime.timedelta(days=14)).isoformat()}"
        f"&gameTypes={','.join(MLB_GAME_TYPES)}"
    )

    try:
        data = await fetch_json(url)
        games = []
        for date_entry in data.get("dates", []):
            games.extend(date_entry.get("games", []))

        now = datetime.datetime.now(LOCAL_TIMEZONE)
        games.sort(key=lambda game: game.get("gameDate", ""))

        for game in games:
            date_str = game.get("gameDate")
            if not date_str:
                continue

            game_time = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            game_time = game_time.astimezone(LOCAL_TIMEZONE)

            status = game.get("status", {})
            detailed_state = status.get("detailedState", "Unknown")
            is_complete = status.get("abstractGameState") == "Final"
            game_id = str(game.get("gamePk", ""))
            teams = game.get("teams", {})
            away_name = teams.get("away", {}).get("team", {}).get("name", "Away")
            home_name = teams.get("home", {}).get("team", {}).get("name", "Home")

            if game_time > now - datetime.timedelta(hours=6):
                return Game(
                    id=game_id,
                    name=f"{away_name} at {home_name}",
                    time=game_time,
                    completed=is_complete,
                    status=detailed_state,
                )

    except Exception as e:
        print(f"[{team.label}] Error fetching MLB schedule: {e}")

    return None


async def wait_for_game_end(team: TeamConfig, game_id: str):
    """Polls the API to monitor game status and scores."""
    print(f"[{team.label}] Monitoring game {game_id}...")

    if team.provider == MLB_PROVIDER:
        await wait_for_mlb_game_end(team, game_id)
    else:
        await wait_for_espn_game_end(team, game_id)


async def wait_for_espn_game_end(team: TeamConfig, game_id: str):
    """Poll the ESPN summary endpoint for live game status and score changes."""
    url = (
        f"https://site.api.espn.com/apis/site/v2/sports/{team.sport_path}/summary?event={game_id}"
    )
    last_score = None
    bulb = None

    try:
        bulb = await get_bulb()
    except Exception as e:
        print(f"[{team.label}] Could not connect to bulb on attach: {e}")

    while True:
        try:
            data = await fetch_json(url)
            header = data.get("header", {})
            competitions = header.get("competitions", [])
            if not competitions:
                print(f"[{team.label}] API Warning: No competition data found. Retrying...")
                await asyncio.sleep(60)
                continue

            competition = competitions[0]
            status = competition.get("status", {})
            completed = status.get("type", {}).get("completed", False)

            # Check for score changes
            for competitor in competition.get("competitors", []):
                if competitor.get("id") == team.espn_team_id:
                    current_score = int(competitor.get("score", "0"))
                    if last_score is None:
                        last_score = current_score
                        print(
                            f"[{team.label}] ESPN live monitor attached at current score {current_score}."
                        )
                    elif current_score > last_score:
                        points_scored = current_score - last_score
                        print(
                            f"[{team.label}] Scored {points_scored} points! New score: {current_score}"
                        )
                        await flash_score(points_scored, team, bulb)
                        last_score = current_score
                    break

            if completed:
                print(f"[{team.label}] API reports game is FINAL.")
                return

        except Exception as e:
            print(f"[{team.label}] Error checking game status: {e}")

        await asyncio.sleep(10)


def get_mlb_team_side(feed_data, team: TeamConfig):
    if team.mlb_team_id is None:
        return None

    teams = feed_data.get("gameData", {}).get("teams", {})
    for side in ("away", "home"):
        side_data = teams.get(side, {})
        if side_data.get("id") == team.mlb_team_id:
            return side

    return None


def get_mlb_team_score(feed_data, team: TeamConfig):
    if team.mlb_team_id is None:
        return 0

    team_side = get_mlb_team_side(feed_data, team)
    if not team_side:
        return 0

    linescore_teams = feed_data.get("liveData", {}).get("linescore", {}).get("teams", {})
    side_linescore = linescore_teams.get(team_side, {})
    if "runs" in side_linescore:
        return int(side_linescore.get("runs") or 0)

    boxscore_teams = feed_data.get("liveData", {}).get("boxscore", {}).get("teams", {})
    side_boxscore = boxscore_teams.get(team_side, {})
    team_stats = side_boxscore.get("teamStats", {}).get("batting", {})
    if "runs" in team_stats:
        return int(team_stats.get("runs") or 0)

    return 0


def is_mlb_game_complete(feed_data):
    status = feed_data.get("gameData", {}).get("status", {})
    abstract_state = status.get("abstractGameState")
    coded_state = status.get("codedGameState")
    return abstract_state == "Final" or coded_state == "F"


async def wait_for_mlb_game_end(team: TeamConfig, game_id: str):
    """Poll the MLB live feed for Orioles score changes and game completion."""
    url = f"https://statsapi.mlb.com/api/v1.1/game/{game_id}/feed/live"
    last_score = None
    bulb = None

    try:
        bulb = await get_bulb()
    except Exception as e:
        print(f"[{team.label}] Could not connect to bulb on attach: {e}")

    while True:
        try:
            data = await fetch_json(url)
            current_score = get_mlb_team_score(data, team)
            if last_score is None:
                last_score = current_score
                print(
                    f"[{team.label}] MLB live feed attached at current score {current_score}."
                )
            elif current_score > last_score:
                runs_scored = current_score - last_score
                print(
                    f"[{team.label}] Scored {runs_scored} run(s)! New score: {current_score}"
                )
                await flash_score(runs_scored, team, bulb)
                last_score = current_score

            if is_mlb_game_complete(data):
                print(f"[{team.label}] MLB API reports game is FINAL.")
                return

        except Exception as e:
            print(f"[{team.label}] Error checking MLB game status: {e}")

        await asyncio.sleep(10)


async def monitor_team(team: TeamConfig):
    """Continuously monitor the team's schedule and drive the light behavior."""
    print(f"[{team.label}] Starting light automation...")

    while True:
        game = await get_game_info(team)

        if not game:
            print(f"[{team.label}] No upcoming games found. Sleeping for 24 hours...")
            await asyncio.sleep(86400)
            continue

        now = datetime.datetime.now(LOCAL_TIMEZONE)
        trigger_time = game.time - datetime.timedelta(minutes=5)
        wait_seconds = (trigger_time - now).total_seconds()

        print(f"[{team.label}] Target Game: {game.name}")
        print(f"[{team.label}] Start: {game.time.strftime('%Y-%m-%d %H:%M:%S')} ET")

        # Game is in the future
        if wait_seconds > 0:
            if wait_seconds > MAX_SCHEDULE_SLEEP_SECONDS:
                print(
                    f"[{team.label}] Game is in {wait_seconds/3600:.1f} hours. "
                    f"Sleeping {MAX_SCHEDULE_SLEEP_SECONDS/3600:.1f} hours before next schedule check..."
                )
                await asyncio.sleep(MAX_SCHEDULE_SLEEP_SECONDS)
                continue

            print(
                f"[{team.label}] Waiting {wait_seconds/60:.1f} minutes until start trigger..."
            )
            await asyncio.sleep(wait_seconds)

        # Game is starting or in progress
        if not game.completed:
            print(f"[{team.label}] Game active! Setting team color.")
            await turn_on_team_color(team)
            try:
                await wait_for_game_end(team, game.id)
            finally:
                await set_post_game_light(team)

            await asyncio.sleep(3600)
        else:
            print(f"[{team.label}] Found game is already Final. Checking again in 1 hour...")
            await asyncio.sleep(3600)


async def main():
    validate_team_configs()
    await asyncio.gather(*(monitor_team(team) for team in TEAM_CONFIGS))


if __name__ == "__main__":
    asyncio.run(main())
