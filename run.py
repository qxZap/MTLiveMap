import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import requests
import threading
import time
import random
import uuid

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEBUG_PLAYERS_FAKE = True  # Toggle to include fake players alongside real players

ALLOW_NPC_QUERY = False

player_ranks = {}
PLAYER_RANKS_FILE = Path("players_ranks.json")
raw_player_data = {"status": "initializing"}
npc_data = {"status": "initializing"}
garages_data = {"status": "initializing"}
last_positions = {}
fake_players = {}  # Store persistent fake player data

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
    # Generate random movement within max_distance
    angle = random.uniform(0, 2 * 3.14159)  # Random direction
    distance = random.uniform(0, max_distance)  # Random distance up to max
    delta_x = distance * random.uniform(-1, 1)
    delta_y = distance * random.uniform(-1, 1)
    delta_z = distance * random.uniform(-0.5, 0.5)  # Smaller Z movement

    # Update position, ensuring it stays within map boundaries
    new_x = max(minX, min(maxX, player["Location"]["X"] + delta_x))
    new_y = max(minY, min(maxY, player["Location"]["Y"] + delta_y))
    new_z = max(0, min(10000, player["Location"]["Z"] + delta_z))

    player["Location"]["X"] = new_x
    player["Location"]["Y"] = new_y
    player["Location"]["Z"] = new_z
    return player

def fetch_player_ranks_loop():
    global player_ranks
    while True:
        try:
            if PLAYER_RANKS_FILE.exists():
                with PLAYER_RANKS_FILE.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    player_ranks = data
        except Exception as e:
            print(f"Error reading player_ranks.json: {e}")
        time.sleep(20)

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

def eject_player(user_id: str):
    url = f"http://localhost:5001/players/{user_id}/eject"
    try:
        resp = requests.post(url, timeout=5)
        if resp.status_code == 200:
            return {"status": "ok", "response": resp.json() if resp.text else {}}
        else:
            return {"status": f"error {resp.status_code}", "response": resp.text}
    except Exception as e:
        return {"status": f"request error: {e}"}


def is_cop_car(vehicle_key: str):
    return 'police' in vehicle_key.lower()

def annouce_player(user_id: str, message: str):
    url = f"http://localhost:5001/messages/popup"
    payload = {
        "message": message,
        "playerId" : user_id
    }
    try:
        resp = requests.post(url, json=payload, timeout=5)
        if resp.status_code == 200:
            return {"status": "ok", "response": resp.json() if resp.text else {}}
        else:
            return {"status": f"error {resp.status_code}", "response": resp.text}
    except Exception as e:
        return {"status": f"request error: {e}"}

def money_player(user_id: str, amount: int, reason: str):
    url = f"http://localhost:5001/players/{user_id}/money"
    payload = {
        "Amount": amount,
        "Message": reason,
        "AllowNegative": False
    }
    try:
        resp = requests.post(url, json=payload, timeout=5)
        if resp.status_code == 200:
            return {"status": "ok", "response": resp.json() if resp.text else {}}
        else:
            return {"status": f"error {resp.status_code}", "response": resp.text}
    except Exception as e:
        return {"status": f"request error: {e}"}

def fetch_npcs_loop():
    global npc_data
    while True:
        try:
            resp = requests.get("http://localhost:5001/vehicles?isPlayerControlled=false&Net_CompanyGuid=00000000000000000000000000000000", timeout=50)
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
        time.sleep(30)

def fetch_garages_loop():
    global garages_data
    while True:
        try:
            resp = requests.get("http://localhost:5001/garages", timeout=50)
            if resp.status_code == 200:
                response_data = resp.json()
                garages = []
                for response_item_data in response_data.get("data", []):
                    location_Data = response_item_data.get("Location", {})
                    if location_Data:
                        garages.append({
                            "X": location_Data.get("X"),
                            "Y": location_Data.get("Y"),
                            "Z": location_Data.get("Z"),
                        })
                garages_data = {"status": "ok", "data": garages}
            else:
                garages_data = {"status": f"error {resp.status_code}"}
        except Exception as e:
            garages_data = {"status": f"fetch error: {e}"}
        time.sleep(20)


def fetch_players_loop():
    global raw_player_data
    global last_positions
    global fake_players
    while True:
        try:
            current_time = time.time()
            processed_data = []

            # Fetch real players
            try:
                resp = requests.get("http://localhost:5001/players", timeout=2)
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

                        if( is_cop_car(p.get("VehicleKey", "")) and not player_ranks.get(unique_id) in ['police', 'admin'] ):
                            eject_player(unique_id)
                            money_player(unique_id, -5000, "Driving a police vehicle without authorization")
                            annouce_player(unique_id, "<Title>VEHICLE NOT ALLOWED</>\n\nYou are not allowed to drive this type of vehicle as is strictly restricted only to police officers that went through the rigirous program of traning of the server!\n\n-5000\n\n<Small>Constact server administration to get approved</>")

                    raw_player_data = {"status": "ok", "data": processed_data}
                else:
                    raw_player_data = {"status": f"error {resp.status_code}"}
            except Exception as e:
                raw_player_data = {"status": f"fetch error: {e}"}

            # Add fake players if DEBUG_PLAYERS_FAKE is True
            if DEBUG_PLAYERS_FAKE:
                # Initialize fake players if empty
                if not fake_players:
                    for _ in range(random.randint(5, 40)):
                        player = generate_fake_player()
                        fake_players[player["UniqueID"]] = player

                # Update fake player positions
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
        time.sleep(0.2)

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

@app.on_event("startup")
def start_fetcher():
    players_thread = threading.Thread(target=fetch_players_loop, daemon=True)
    players_thread.start()

    if ALLOW_NPC_QUERY:
        npcs_thread = threading.Thread(target=fetch_npcs_loop, daemon=True)
        npcs_thread.start()

    garages_thread = threading.Thread(target=fetch_garages_loop, daemon=True)
    garages_thread.start()

    ranks_thread = threading.Thread(target=fetch_player_ranks_loop, daemon=True)
    ranks_thread.start()

@app.get("/playerlocations")
async def player_locations():
    return JSONResponse(content=simplify_player_data(raw_player_data))

@app.get("/garages")
async def garages_location():
    return JSONResponse(content=garages_data)

if ALLOW_NPC_QUERY:
    @app.get("/npcs")
    async def npc_locations():
        return JSONResponse(content=npc_data)

if __name__ == "__main__":
    uvicorn.run("run:app", host="127.0.0.1", port=8000, reload=False)