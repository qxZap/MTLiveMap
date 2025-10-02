import json
import os
import datetime
import base64
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

PLAYER_VEHICLE_INTERVAL = 0.3
FETCH_PLAYER_ON = True
FETCH_VEHICLE_ON = False

WEB_API_PASSWORD = 'BBTWebAPIServer'
WEB_API_URL = "http://motortown-bbt.com:8080"

IS_SERVER_ONLINE = False
STARTUP_CREATED = False

DEBUG_PLAYERS_FAKE = False
FILE_CHANGES_FREQUENCY = 20

PLAYER_RANKS_FILE = Path("players_ranks.json")

player_ranks = {}
raw_player_data = {"status": "initializing"}
last_positions = {}
fake_players = {}  # Store persistent fake player dataw

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

async def shutdown_at(target_hour=5, target_minute=0):
    while True:
        now = datetime.datetime.now()
        if now.hour == target_hour and now.minute == target_minute:
            print("Shutting down FastAPI server at scheduled time...")
            os._exit(0)
        await asyncio.sleep(30)

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
                resp = await client.get(f"{WEB_API_URL}/status", timeout=5)
                if resp.status_code == 404:
                    IS_SERVER_ONLINE = True
                else:
                    IS_SERVER_ONLINE = False
                    STARTUP_CREATED = False
            except Exception as e:
                pass
        
        if IS_SERVER_ONLINE and not STARTUP_CREATED:
            STARTUP_CREATED = True

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
        await asyncio.sleep(FILE_CHANGES_FREQUENCY)

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
        
async def getPlayerDataFromName(name):
    global raw_player_data
    
    for player in raw_player_data.get('data'):
        if player.get("Name") == name:
            return player

async def getPlayerIDFromName(name):
    player = await getPlayerDataFromName()
    return player.get('UniqueID')



async def fetch_players_loop():
    global raw_player_data, last_positions, fake_players, player_ranks, FETCH_PLAYER_ON
    async with httpx.AsyncClient() as client:
        if FETCH_PLAYER_ON:
            try:
                current_time = time.time()
                processed_data = []

                # Fetch real players
                try:
                    resp = await client.get(f"{WEB_API_URL}/player/list?password={WEB_API_PASSWORD}", timeout=2)
                    if resp.status_code == 200:
                        new_data = resp.json()
                        new_data_parsed = new_data.get('data',{})
                        for key in new_data_parsed:
                            p = new_data_parsed[key]
                            unique_id = p.get('unique_id')
                            name = p.get('name')
                            location_full = p.get('location')
                            vehicle = p.get('vehicle',{}).get('name')

                            X=Y=Z=None
                            for location_part in location_full.split(' '):
                                if location_part.startswith('X='):
                                    X=float(location_part.replace('X=',''))
                                if location_part.startswith('Y='):
                                    Y=float(location_part.replace('Y=',''))
                                if location_part.startswith('Z='):
                                    Z=float(location_part.replace('Z=',''))
                            
                            if unique_id and unique_id in last_positions:
                                last_pos = last_positions[unique_id]
                                time_diff = current_time - last_pos["timestamp"]
                                if time_diff > 0:
                                    speed = convert_xyz_speed_to_kmh(last_pos["X"], last_pos["Y"], last_pos["Z"], X, Y, Z, time_diff)
                                    p["SpeedKMH"] = speed
                                else:
                                    p["SpeedKMH"] = 0.0
                            else:
                                p["SpeedKMH"] = 0.0
                            
                            processed_data.append({
                                "X": X,
                                "Y": Y,
                                "Z": Z,
                                'Name' : name,
                                'UniqueID' : unique_id,
                                'SpeedKMH' : p["SpeedKMH"],
                                'VehicleKey' : vehicle
                            })
                            last_positions[unique_id] = {
                                "X": X,
                                "Y": Y,
                                "Z": Z,
                                "timestamp": current_time
                            }

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

def simplify_player_data(data: dict):
    simplified = []
    for p in data.get("data", []):
        simplified.append({
            "X": p.get("X"),
            "Y": p.get("Y"),
            "Z": p.get("Z"),
            "Name": p.get("Name"),
            "VehicleKey": p.get("VehicleKey"),
            "UniqueID": p.get("UniqueID"),
            "SpeedKMH": p.get("SpeedKMH"),
            "PlayerType": player_ranks.get(p.get("UniqueID"), "player")
        })
    return {"status": "ok", "players": simplified}

async def fetch_player_vehicles():
    while True:
        try:
            await fetch_players_loop()
        except Exception as e:
            print(f"Unexpected error in fetch loop: {e}")

        await asyncio.sleep(PLAYER_VEHICLE_INTERVAL)

@app.on_event("startup")
async def start_fetcher():
    asyncio.create_task(fetch_server_health_check())
    asyncio.create_task(fetch_player_vehicles())

    asyncio.create_task(fetch_player_ranks_loop())


@app.get("/playerlocations")
async def player_locations():
    return JSONResponse(content=simplify_player_data(raw_player_data))



if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(shutdown_at(5, 00))
    
    config = uvicorn.Config("run:app", host="0.0.0.0", port=8001, reload=False, loop="asyncio")
    server = uvicorn.Server(config)
    loop.run_until_complete(server.serve())