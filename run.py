import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import httpx
import threading
import time
import random
import uuid
from typing import Dict, Set
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SPEED_LIMITS = {
    (300, 400): lambda v: -2000 - int((v - 300) * 10),
    (400, 500): lambda v: -8000 - int((v - 400) * 40),
    (500, float("inf")): lambda v: -20000 - int((v - 500) ** 2),
}
SPEED_ALLOW_ZONES = {
    "ansan_racing": {
        "minX": -276358.95,
        "maxX": -112504.23,
        "minY": 274476.92,
        "maxY": 335837.02
    },
    "olle_track": {
        "minX": -298974.21,
        "maxX": -272370.78,
        "minY": 171035.48,
        "maxY": 215267.80
    },
    "harbor": {
        "minX": -70816.14,
        "maxX": 44680.59,
        "minY": -243812.75,
        "maxY": -171259.99
    },
    "desert_patch": {
        "minX": -879360.30,
        "maxX": -224863.32,
        "minY": 1056796.30,
        "maxY": 1658226.04
    },
    "aewol": {
        "minX": -199680.32,
        "maxX": -133551.84,
        "minY": -21131.95,
        "maxY": 24852.31
    },
    "drag_strip_north": {
        "minX": 447157.12,
        "maxX": 447164.59,
        "minY": 1214688.82,
        "maxY": 1214692.85
    }
}


MAXIMUM_SPEEDING_FINE = 600

LUA_API = "http://localhost:5001"

IS_SERVER_ONLINE = False
STARTUP_CREATED = False

active_events: Dict[str, dict] = {}

# Constants
HOOK_SERVER_CHANGE_EVENT_STATE = '/Script/MotorTown.MotorTownPlayerController:ServerChangeEventState'
HOOK_SERVER_PASSED_RACE_SECTION = '/Script/MotorTown.MotorTownPlayerController:ServerPassedRaceSection'
HOOK_ENTER_VEHICLE = '/Script/MotorTown.MotorTownPlayerController:ServerEnterVehicle'

DEBUG_PLAYERS_FAKE = False
ASSETS_SPAWN_ENABLED = False
DEALERS_SPAWN_ENABLED = True
ALLOW_NPC_QUERY = False

POLICE_FINE_COOLDOWN = 2.0  # Configurable cooldown in seconds to prevent duplicate fines
SPEEDING_FINE_COOLDOWN = 10.0  # Configurable cooldown in seconds to prevent duplicate speeding fines
SPEEDING_THRESHOLD = 300.0  # Minimum speed in km/h to trigger a fine

PLAYER_RANKS_FILE = Path("players_ranks.json")
ANNOUNCEMENTS_FILE = Path("announcements.json")
MAP_MODIFICATIONS_FILE = Path("map_modifications.json")
DEALERSHIP_MODIFICATIONS_FILE = Path("dearlerships.json")


player_ranks = {}

DEALERSHIPS_TAGS = []
DEALERSHIP_MODIFICATIONS={}
MAP_MODIFICATIONS={}
raw_player_data = {"status": "initializing"}
npc_data = {"status": "initializing"}
garages_data = {"status": "initializing"}
last_positions = {}
fake_players = {}  # Store persistent fake player data
last_police_fines = {}  # unique_id: last_fine_time to prevent duplicate fines
last_speeding_fines = {}  # unique_id: last_fine_time to prevent duplicate speeding fines

# Map boundaries
minX = -1280000
minY = -320000
maxX = 920000
maxY = 1880000
MAX_SPEED_UNITS_PER_SECOND = 3500  # Maximum movement speed in units/second

# Fake player names
FAKE_NAMES = [
    "SkyRacer", "NeonDrift", "StarBlaze", "GhostRider", "ThunderBolt",
    "FrostByte", "ShadowHawk", "LunarWolf", "BlazeViper", "StormChaser"
]

EVENT_READY = 3
EVENT_FINISH = 2
EVENT_START = 1

def extract_ep_number(s):
    match = re.search(r'EP(\d+)EP', s)
    if match:
        return int(match.group(1))
    return 0

def build_image(id):
    return f"""<img id=\"{id}"/>"""

def distance_2d(x1, y1, x2, y2):
    return ((x2 - x1)**2 + (y2 - y1)**2) ** 0.5

def is_near_garage(x, y, max_distance=3000):
    global garages_data
    for garage in garages_data.get("data", []):
        gx, gy = garage.get("X"), garage.get("Y")
        if gx is not None and gy is not None:
            if distance_2d(x, y, gx, gy) <= max_distance:
                return True
    return False

def in_speed_allow_zone(x: float, y: float) -> bool:
    """Check if coordinates fall inside any of the exempt zones."""
    for zone_name, bounds in SPEED_ALLOW_ZONES.items():
        if (bounds["minX"] <= x <= bounds["maxX"] and
            bounds["minY"] <= y <= bounds["maxY"]):
            return True
    return False

def generate_fake_player():
    """Generate a fake player with random position and name."""
    return {
        "UniqueID": str(uuid.uuid4()),
        "Name": random.choice(FAKE_NAMES) + str(random.randint(100, 999)),
        "Location": {
            "X": random.uniform(minX, maxX),
            "Y": random.uniform(minY, maxY),
            "Z": random.uniform(0, 10000),
        },
        "VehicleKey": f"Vehicle_{random.randint(1, 100)}",
        "SpeedKMH": 0.0
    }

def update_fake_player_position(player, time_diff):
    """Update fake player's position with a maximum speed of 3500 units/second."""
    max_distance = MAX_SPEED_UNITS_PER_SECOND * time_diff
    angle = random.uniform(0, 2 * 3.14159)  # Random direction
    distance = random.uniform(0, max_distance)  # Random distance up to max
    delta_x = distance * random.uniform(-1, 1)
    delta_y = distance * random.uniform(-1, 1)
    delta_z = distance * random.uniform(-0.5, 0.5)  # Smaller Z movement

    new_x = max(minX, min(maxX, player["Location"]["X"] + delta_x))
    new_y = max(minY, min(maxY, player["Location"]["Y"] + delta_y))
    new_z = max(0, min(10000, player["Location"]["Z"] + delta_z))

    player["Location"]["X"] = new_x
    player["Location"]["Y"] = new_y
    player["Location"]["Z"] = new_z
    return player

async def fetch_server_health_check():
    global IS_SERVER_ONLINE, STARTUP_CREATED
    while True:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{LUA_API}/status", timeout=5)
                if resp.status_code == 200 and resp.json().get("status","") == "ok":
                    IS_SERVER_ONLINE = True
                else:
                    IS_SERVER_ONLINE = False
                    STARTUP_CREATED = False
            except Exception as e:
                pass
        
        if IS_SERVER_ONLINE and not STARTUP_CREATED:
            STARTUP_CREATED = True
            if ASSETS_SPAWN_ENABLED:
                asyncio.create_task(watch_map_modifications())
            
            if DEALERS_SPAWN_ENABLED:
                asyncio.create_task(watch_dealers_modifications())

        await asyncio.sleep(5)

async def fetch_player_ranks_loop():
    global player_ranks
    while True:
        try:
            if PLAYER_RANKS_FILE.exists():
                with PLAYER_RANKS_FILE.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    player_ranks = data
        except Exception as e:
            print(f"Error reading player_ranks.json: {e}")
        await asyncio.sleep(20)


async def reload_models_from_file():
    global MAP_MODIFICATIONS

    tags = []
    assets_to_spawn = []

    for asset_tag in MAP_MODIFICATIONS.get("assets", {}):
        tags.append(asset_tag)
        for asset_to_spawn in MAP_MODIFICATIONS.get("assets", {}).get(asset_tag, []):
            assets_to_spawn.append(get_asset_object(
                asset_to_spawn.get("path", ""),
                asset_to_spawn.get("X", 0),
                asset_to_spawn.get("Y", 0),
                asset_to_spawn.get("Z", 0),
                asset_to_spawn.get("Pitch", 0),
                asset_to_spawn.get("Roll", 0),
                asset_to_spawn.get("Yaw", 0),
                asset_tag
            ))

    await despawn_assets(tags)
    await spawn_assets(assets_to_spawn)
    print(f"[Reloaded] Tags: {tags}, Spawned: {len(assets_to_spawn)}")

async def reload_dealerships_from_file():
    global DEALERSHIPS_TAGS, DEALERSHIP_MODIFICATIONS
    await despawn_assets(DEALERSHIPS_TAGS)

    tags = []

    for dealer in DEALERSHIP_MODIFICATIONS:
        new_tags = await spawn_dealers(DEALERSHIP_MODIFICATIONS[dealer])
        tags+=new_tags
    DEALERSHIPS_TAGS = tags

async def watch_map_modifications():
    global MAP_MODIFICATIONS
    last_data = None

    while True:
        try:
            if MAP_MODIFICATIONS_FILE.exists():
                with MAP_MODIFICATIONS_FILE.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data != last_data:
                        last_data = data
                        MAP_MODIFICATIONS = data
                        # Fire async reload
                        await reload_models_from_file()
        except Exception as e:
            print(f"Error reading {MAP_MODIFICATIONS_FILE}: {e}")

        await asyncio.sleep(5)

async def watch_dealers_modifications():
    global DEALERSHIP_MODIFICATIONS
    last_data = None

    while True:
        try:
            if DEALERSHIP_MODIFICATIONS_FILE.exists():
                with DEALERSHIP_MODIFICATIONS_FILE.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data != last_data:
                        last_data = data
                        DEALERSHIP_MODIFICATIONS = data
                        await reload_dealerships_from_file()
        except Exception as e:
            print(f"Error reading {DEALERSHIP_MODIFICATIONS_FILE}: {e}")

        await asyncio.sleep(5)

def convert_xyz_speed_to_kmh(x1, y1, z1, x2, y2, z2, time_diff_in_seconds):
    distance = ((x2 - x1)**2 + (y2 - y1)**2 + (z2 - z1)**2)**0.5
    speed_in_units_per_second = distance / time_diff_in_seconds if time_diff_in_seconds > 0 else 0
    if speed_in_units_per_second > 0:
        conversion_factor = 0.03701298701
        speed_in_kmh = speed_in_units_per_second * conversion_factor
    else:
        speed_in_kmh = 0.0
    return speed_in_kmh

def is_npc_driven(npc_data_item):
    seats = npc_data_item.get("Net_Seats", [])
    for seat in seats:
        if seat.get("SeatName", "") == "DriverSeat" and seat.get("bHasCharacter", False):
            return True
    return False

async def eject_player(user_id: str):
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{LUA_API}/players/{user_id}/eject", timeout=5)
            if resp.status_code == 200:
                return {"status": "ok", "response": resp.json() if resp.text else {}}
            else:
                return {"status": f"error {resp.status_code}", "response": resp.text}
        except Exception as e:
            return {"status": f"request error: {e}"}

async def get_player_data(user_id: str):
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{LUA_API}/players/{user_id}", timeout=5)
            if resp.status_code == 200:
                return resp.json()
            else:
                return {"status": f"error {resp.status_code}", "response": resp.text}
        except Exception as e:
            return {"status": f"request error: {e}"}

def is_cop_car(vehicle_key: str):
    return 'police' in vehicle_key.lower()

async def announce_player(user_id: str, message: str):
    async with httpx.AsyncClient() as client:
        payload = {
            "message": message,
            "playerId": user_id
        }
        try:
            resp = await client.post(f"{LUA_API}/messages/popup", json=payload, timeout=5)
            if resp.status_code == 200:
                return {"status": "ok", "response": resp.json() if resp.text else {}}
            else:
                return {"status": f"error {resp.status_code}", "response": resp.text}
        except Exception as e:
            return {"status": f"request error: {e}"}

async def money_player(user_id: str, amount: int, reason: str):
    async with httpx.AsyncClient() as client:
        payload = {
            "Amount": amount,
            "Message": reason,
            "AllowNegative": False
        }
        try:
            resp = await client.post(f"{LUA_API}/players/{user_id}/money", json=payload, timeout=5)
            if resp.status_code == 200:
                return {"status": "ok", "response": resp.json() if resp.text else {}}
            else:
                return {"status": f"error {resp.status_code}", "response": resp.text}
        except Exception as e:
            return {"status": f"request error: {e}"}

async def player_in_police_vehicle(unique_id: str):
    current_time = time.time()
    if unique_id in last_police_fines and current_time - last_police_fines[unique_id] < POLICE_FINE_COOLDOWN:
        return  # Skip if within cooldown
    # Update the last fine time before firing tasks
    last_police_fines[unique_id] = current_time
    # Fire-and-forget tasks for eject, fine, and announce
    asyncio.create_task(eject_player(unique_id))
    asyncio.create_task(money_player(unique_id, -5000, "Driving a police vehicle without authorization"))
    asyncio.create_task(announce_player(unique_id, f"<Title>VEHICLE NOT ALLOWED</>\n\nYou are not allowed to drive this type of vehicle as is strictly restricted only to police officers that went through the rigorous program of training of the server!\n\n- {build_image('Money')} 5.000\n\n<Small>Contact server administration to get approved</>"))

async def speeding_player(unique_id: str, speed_kmh: float):
    for (low, high), fine_formula in SPEED_LIMITS.items():
        if low <= speed_kmh < high:
            fine = fine_formula(speed_kmh)
            asyncio.create_task(money_player(
                unique_id, 
                fine, 
                f"You have been fined for speeding at {speed_kmh:.1f} KMH"
            ))
            return

    return

async def fetch_npcs_loop():
    global npc_data
    async with httpx.AsyncClient() as client:
        while True:
            try:
                resp = await client.get(f"{LUA_API}/vehicles?isPlayerControlled=false&Net_CompanyGuid=00000000000000000000000000000000", timeout=50)
                if resp.status_code == 200:
                    response_data = resp.json()
                    npc_data_list = response_data.get("data", [])
                    data = []
                    for npc_data_item in npc_data_list:
                        if is_npc_driven(npc_data_item):
                            data.append({
                                "X": npc_data_item.get("VehicleReplicatedMovement", {}).get("Location", {}).get("X"),
                                "Y": npc_data_item.get("VehicleReplicatedMovement", {}).get("Location", {}).get("Y"),
                                "Z": npc_data_item.get("VehicleReplicatedMovement", {}).get("Location", {}).get("Z"),
                            })
                    npc_data = {"status": "ok", "data": data}
                else:
                    npc_data = {"status": f"error {resp.status_code}"}
            except Exception as e:
                npc_data = {"status": f"fetch error: {e}"}
            await asyncio.sleep(30)

async def fetch_garages_loop():
    global garages_data
    async with httpx.AsyncClient() as client:
        while True:
            try:
                resp = await client.get(f"{LUA_API}/garages", timeout=50)
                if resp.status_code == 200:
                    response_data = resp.json()
                    garages = []
                    for response_item_data in response_data.get("data", []):
                        location_data = response_item_data.get("Location", {})
                        if location_data:
                            garages.append({
                                "X": location_data.get("X"),
                                "Y": location_data.get("Y"),
                                "Z": location_data.get("Z"),
                            })
                    garages_data = {"status": "ok", "data": garages}
                else:
                    garages_data = {"status": f"error {resp.status_code}"}
            except Exception as e:
                garages_data = {"status": f"fetch error: {e}"}
            await asyncio.sleep(20)

async def fetch_players_loop():
    global raw_player_data, last_positions, fake_players
    async with httpx.AsyncClient() as client:
        while True:
            try:
                current_time = time.time()
                processed_data = []

                # Fetch real players
                try:
                    resp = await client.get(f"{LUA_API}/players", timeout=2)
                    if resp.status_code == 200:
                        new_data = resp.json()
                        for p in new_data.get("data", []):
                            unique_id = p.get("UniqueID")
                            if unique_id and unique_id in last_positions:
                                last_pos = last_positions[unique_id]
                                time_diff = current_time - last_pos["timestamp"]
                                if time_diff > 0:
                                    speed = convert_xyz_speed_to_kmh(
                                        last_pos["X"], last_pos["Y"], last_pos["Z"],
                                        p.get("Location", {}).get("X"),
                                        p.get("Location", {}).get("Y"),
                                        p.get("Location", {}).get("Z"),
                                        time_diff
                                    )
                                    p["SpeedKMH"] = speed
                                else:
                                    p["SpeedKMH"] = 0.0
                            else:
                                p["SpeedKMH"] = 0.0
                            processed_data.append(p)
                            last_positions[unique_id] = {
                                "X": p.get("Location", {}).get("X"),
                                "Y": p.get("Location", {}).get("Y"),
                                "Z": p.get("Location", {}).get("Z"),
                                "timestamp": current_time
                            }

                            if is_cop_car(p.get("VehicleKey", "")) and player_ranks.get(unique_id) not in ['police', 'admin']:
                                await player_in_police_vehicle(unique_id)

                            # Check for speeding
                            speed = p["SpeedKMH"]
                            pos = p.get("Location", {})
                            prev_pos = last_positions.get(unique_id, {})
                            vehicle_key = p.get("VehicleKey", "")
                            
                            if vehicle_key!="None":
                                if (
                                    speed > SPEEDING_THRESHOLD
                                    and player_ranks.get(unique_id) != 'admin'
                                    and vehicle_key!="None"
                                    and not is_cop_car(vehicle_key)
                                    and speed < MAXIMUM_SPEEDING_FINE
                                    and not in_speed_allow_zone(pos.get("X", 0), pos.get("Y", 0))
                                    and not is_near_garage(pos.get("X", 0), pos.get("Y", 0))
                                    and not is_near_garage(prev_pos.get("X", 0), prev_pos.get("Y", 0))
                                ):
                                    if unique_id not in last_speeding_fines or current_time - last_speeding_fines[unique_id] > SPEEDING_FINE_COOLDOWN:
                                        last_speeding_fines[unique_id] = current_time
                                        await speeding_player(unique_id, speed)

                        raw_player_data = {"status": "ok", "data": processed_data}
                    else:
                        raw_player_data = {"status": f"error {resp.status_code}"}
                except Exception as e:
                    raw_player_data = {"status": f"fetch error: {e}"}

                # Add fake players if DEBUG_PLAYERS_FAKE is True
                if DEBUG_PLAYERS_FAKE:
                    if not fake_players:
                        for _ in range(random.randint(5, 40)):
                            player = generate_fake_player()
                            fake_players[player["UniqueID"]] = player

                    for unique_id, player in list(fake_players.items()):
                        time_diff = 0.2  # Loop interval
                        player = update_fake_player_position(player, time_diff)
                        if unique_id in last_positions:
                            last_pos = last_positions[unique_id]
                            time_diff = current_time - last_pos["timestamp"]
                            if time_diff > 0:
                                speed = convert_xyz_speed_to_kmh(
                                    last_pos["X"], last_pos["Y"], last_pos["Z"],
                                    player["Location"]["X"],
                                    player["Location"]["Y"],
                                    player["Location"]["Z"],
                                    time_diff
                                )
                                player["SpeedKMH"] = speed
                            else:
                                player["SpeedKMH"] = 0.0
                        else:
                            player["SpeedKMH"] = 0.0
                        processed_data.append(player)
                        last_positions[unique_id] = {
                            "X": player["Location"]["X"],
                            "Y": player["Location"]["Y"],
                            "Z": player["Location"]["Z"],
                            "timestamp": current_time
                        }

                    raw_player_data = {"status": "ok", "data": processed_data}

            except Exception as e:
                raw_player_data = {"status": f"fetch error: {e}"}
            await asyncio.sleep(0.2)

def simplify_player_data(data: dict):
    simplified = []
    for p in data.get("data", []):
        simplified.append({
            "X": p.get("Location", {}).get("X"),
            "Y": p.get("Location", {}).get("Y"),
            "Z": p.get("Location", {}).get("Z"),
            "Name": p.get("Name"),
            "VehicleKey": p.get("VehicleKey"),
            "UniqueID": p.get("UniqueID"),
            "SpeedKMH": p.get("SpeedKMH"),
            "PlayerType": player_ranks.get(p.get("UniqueID"), "player")
        })
    return {"status": "ok", "players": simplified}

async def announce_loop():
    """Run a loop to send configured announcements at specified intervals."""
    async with httpx.AsyncClient() as client:
        while True:
            try:
                announcements = []
                if ANNOUNCEMENTS_FILE.exists():
                    try:
                        with ANNOUNCEMENTS_FILE.open("r", encoding="utf-8") as f:
                            announcements = json.load(f)
                    except Exception as e:
                        print(f"Error reading announcements.json: {e}")

                for announcement in announcements:
                    message = announcement.get("message", "")
                    interval = announcement.get("interval", 60)  # Default to 60 seconds
                    is_pinned = announcement.get("isPinned", False)
                    payload = {
                        "message": message,
                        # "playerId": "",
                        "isPinned": is_pinned
                    }
                    try:
                        await client.post(f"{LUA_API}/messages/announce", json=payload, timeout=5)
                    except Exception as e:
                        print(f"Error sending announcement '{message}': {e}")
                    await asyncio.sleep(interval)
            except Exception as e:
                print(f"Unexpected error in announce_loop: {e}")
            await asyncio.sleep(10)  # Check file every 10 seconds

@app.on_event("startup")
async def start_fetcher():
    asyncio.create_task(fetch_server_health_check())

    # Start background loops as async tasks
    asyncio.create_task(fetch_players_loop())
    if ALLOW_NPC_QUERY:
        asyncio.create_task(fetch_npcs_loop())

    asyncio.create_task(fetch_garages_loop())

    asyncio.create_task(announce_loop())

    asyncio.create_task(fetch_player_ranks_loop())


@app.get("/playerlocations")
async def player_locations():
    return JSONResponse(content=simplify_player_data(raw_player_data))

@app.get("/garages")
async def garages_location():
    return JSONResponse(content=garages_data)

@app.post("/")
async def handle_webhook(request: Request):
    global active_events

    client_host = request.client.host
    if client_host != "127.0.0.1" and client_host != "localhost":
        return {"status", "why try hack?"}


    body = await request.body()
    data = json.loads(body.decode('utf-8'))
    for event in data:
        hook_type = event.get("hook", "")
        print(f"Received webhook of type: {hook_type}")

        hook_data = event.get("data", {})
        player_id = hook_data.get("PlayerId", "")

        # if hook_type == '/Script/MotorTown.MotorTownPlayerController:ServerSendChat':
        #     print(hook_data)

        if hook_type == HOOK_SERVER_CHANGE_EVENT_STATE:
            event_data = hook_data.get("Event", {})
            event_guid = event_data.get("EventGuid", "")
            state = event_data.get("State", 0)
            route_name = event_data.get("RaceSetup", {}).get("Route", {}).get("RouteName", "")
            
            entry_pool = extract_ep_number(route_name)
            if state == EVENT_START and entry_pool>0:
                race_setup = event_data.get("RaceSetup", {})
                player_count = len(hook_data.get("Event",{}).get("Players", []))
                if(player_count>1):
                    waypoints = len(race_setup.get("Route", {}).get("Waypoints", []))
                    last_waypoint_index = waypoints - 1 if waypoints>0 else 0

                    active_events[event_guid] = {
                        "entry_pool": entry_pool,
                        "last_waypoint_index": last_waypoint_index,
                        "race_name": route_name,
                        "reward_pool" : 0
                    }
        
        if hook_type == HOOK_SERVER_PASSED_RACE_SECTION:
            event_guid = hook_data.get("EventGuid", "")
            section_index = hook_data.get("SectionIndex", -1)
            if event_guid in active_events:
                if section_index == 0:
                    event_info = active_events[event_guid]
                    entry_pool = event_info["entry_pool"]
                    if entry_pool > 0:
                        active_events[event_guid]["reward_pool"] += entry_pool
                        race_name = active_events[event_guid]['race_name']
                        race_name_clean = race_name.replace(f"EP{entry_pool}EP","")
                        asyncio.create_task(money_player(player_id, -entry_pool, f"Entry fee for {race_name_clean}" ))
                if section_index == active_events.get(event_guid, {}).get("last_waypoint_index", -1):
                    entry_pool = active_events[event_guid]["entry_pool"]
                    active_events[event_guid]["entry_pool"] = 0
                    total_reward = active_events[event_guid]["reward_pool"]
                    active_events[event_guid]["reward_pool"] = 0
                    if total_reward > 0:
                        race_name = active_events[event_guid]["race_name"]
                        race_name_clean = race_name.replace(f"EP{entry_pool}EP","")
                        asyncio.create_task(money_player(player_id, total_reward, f"Reward for winning {race_name_clean}"))
    
    return {"status": "ok"}

if ALLOW_NPC_QUERY:
    @app.get("/npcs")
    async def npc_locations():
        return JSONResponse(content=npc_data)

async def spawn_asset(asset_path, x, y, z, pitch=0, roll=0, yaw=0, tag="SomeIdentifiableTag"):
    async with httpx.AsyncClient() as client:
        payload = {
            "AssetPath": asset_path,
            "Location": {"X": x, "Y": y, "Z": z},
            "Rotation": {"Pitch": pitch, "Roll": roll, "Yaw": yaw},
            "Tag": tag
        }
        try:
            resp = await client.post(f"{LUA_API}/assets/spawn", json=payload, timeout=5)
            if resp.status_code == 200:
                return {"status": "ok", "response": resp.json() if resp.text else {}}
            return {"status": f"error {resp.status_code}", "response": resp.text}
        except Exception as e:
            return {"status": f"request error: {e}"}

def get_dealer_spawner_payload(x,y,z,pitch,roll,yaw, vehicle_key):
    return {
        "Location": {
                "Y": y,
                "Z": z,
                "X": x
        },
        "Rotation": { "Pitch": pitch, "Roll": roll, "Yaw": yaw },
        "VehicleClass": "",
        "VehicleParam": {
            "VehicleKey": vehicle_key
        }
    }

async def spawn_dealer(x,y,z,pitch,roll,yaw, vehicle_key):
    async with httpx.AsyncClient() as client:
        payload = get_dealer_spawner_payload(x,y,z,pitch,roll,yaw, vehicle_key)
        try:
            resp = await client.post(f"{LUA_API}/dealers/spawn", json=payload, timeout=5)
            await asyncio.sleep(1)
            if resp.status_code == 201:
                return resp.json()
            return {}
        except Exception as e:
            return {}

async def spawn_dealers(dealers):
    tags = []
    for dealer in dealers:
        response_data = await spawn_dealer(dealer.get("X",0), dealer.get("Y",0), dealer.get("Z",0), dealer.get("Pitch",0), dealer.get("Roll",0), dealer.get("Yaw",0), dealer.get("VehicleKey",""))
        if response_data:
            new_tag = response_data.get("data",{}).get("tag")
            if new_tag:
                tags.append(new_tag)
    
    return tags

def get_asset_object(asset_path, x, y, z, pitch=0, roll=0, yaw=0, tag="SomeIdentifiableTag"):
    return {
        "AssetPath": asset_path,
        "Location": {"X": x, "Y": y, "Z": z},
        "Rotation": {"Pitch": pitch, "Roll": roll, "Yaw": yaw},
        "Tag": tag
    }

async def spawn_assets(assets):
    async with httpx.AsyncClient() as client:
        payload = assets
        try:
            resp = await client.post(f"{LUA_API}/assets/spawn", json=payload, timeout=5)
            if resp.status_code == 201:
                return {"status": "ok", "response": resp.json() if resp.text else {}}
            return {"status": f"error {resp.status_code}", "response": resp.text}
        except Exception as e:
            return {"status": f"request error: {e}"}


async def despawn_asset(tag="SomeIdentifiableTag"):
    async with httpx.AsyncClient() as client:
        payload = {"Tag": tag}
        try:
            resp = await client.post(f"{LUA_API}/assets/despawn", json=payload, timeout=5)
            if resp.status_code == 202:
                return {"status": "ok", "response": resp.json() if resp.text else {}}
            return {"status": f"error {resp.status_code}", "response": resp.text}
        except Exception as e:
            return {"status": f"request error: {e}"}

async def despawn_assets(tags):
    async with httpx.AsyncClient() as client:
        payload = {"Tags": tags}  # fixed typo
        try:
            resp = await client.post(f"{LUA_API}/assets/despawn", json=payload, timeout=5)
            if resp.status_code == 202:
                return {"status": "ok", "response": resp.json() if resp.text else {}}
            return {"status": f"error {resp.status_code}", "response": resp.text}
        except Exception as e:
            return {"status": f"request error: {e}"}

if __name__ == "__main__":
    uvicorn.run("run:app", host="127.0.0.1", port=8000, reload=False)