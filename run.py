from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import requests
import threading
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


raw_player_data = {"status": "initializing"}
npc_data = {"status": "initializing"}
garages_data = {"status": "initializing"}

last_positions = {}

def convert_xyz_speed_to_kmh(x1, y1, z1, x2, y2, z2, time_diff_in_seconds):
    distance = ((x2 - x1)**2 + (y2 - y1)**2 + (z2 - z1)**2)**0.5
    speed_in_units_per_second = distance / time_diff_in_seconds

    if speed_in_units_per_second > 0:
        # conversion_factor = 100.0 / 7000.0 * 57/22
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

def fetch_npcs_loop():
    global npc_data
    while True:
        try:
            resp = requests.get("http://localhost:5001/vehicles?isPlayerControlled=false&Net_CompanyGuid=00000000000000000000000000000000", timeout=50)
            if resp.status_code == 200:
                # npc_data = resp.json()
                response_data = resp.json()
                npc_data_list = response_data.get("data", [])

                data = []

                for npc_data_item in npc_data_list:
                    if is_npc_driven(npc_data_item):
                        data.append({
                            "X":npc_data_item.get("VehicleReplicatedMovement", {}).get("Location", {}).get("X"),
                            "Y":npc_data_item.get("VehicleReplicatedMovement", {}).get("Location", {}).get("Y"),
                            "Z":npc_data_item.get("VehicleReplicatedMovement", {}).get("Location", {}).get("Z"),
                        })
                
                npc_data = {"status": "ok", "data": data}

            else:
                npc_data = {"status": f"error {resp.status_code}"}
        except Exception as e:
            npc_data = {"status": f"fetch error: {e}"}
        
        time.sleep(10)

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
    while True:
        try:
            current_time = time.time()
            resp = requests.get("http://localhost:5001/players", timeout=2)
            
            if resp.status_code == 200:
                new_data = resp.json()
                processed_data = []

                # Iterate through the new player data to calculate speed
                for p in new_data.get("data", []):
                    unique_id = p.get("UniqueID")
                    if unique_id and unique_id in last_positions:
                        # Get previous position and time
                        last_pos = last_positions[unique_id]
                        
                        # Calculate time difference in seconds
                        time_diff = current_time - last_pos["timestamp"]

                        # Ensure a valid time difference to avoid division by zero
                        if time_diff > 0:
                            # Calculate speed using the previous and current positions
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
                        # If no previous position, speed is unknown
                        p["SpeedKMH"] = 0.0
                    
                    processed_data.append(p)

                    # Update the last_positions dictionary for the next loop
                    last_positions[unique_id] = {
                        "X": p.get("Location", {}).get("X"),
                        "Y": p.get("Location", {}).get("Y"),
                        "Z": p.get("Location", {}).get("Z"),
                        "timestamp": current_time
                    }
                
                raw_player_data = {"status": "ok", "data": processed_data}

            else:
                raw_player_data = {"status": f"error {resp.status_code}"}
        except Exception as e:
            raw_player_data = {"status": f"fetch error: {e}"}
        
        # Wait for a short period before the next fetch
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
            "SpeedKMH": p.get("SpeedKMH") # Add the new speed field
        })
    return {"status": "ok", "players": simplified}

@app.on_event("startup")
def start_fetcher():
    # Start players loop
    players_thread = threading.Thread(target=fetch_players_loop, daemon=True)
    players_thread.start()
    
    # Start NPCs loop
    # npcs_thread = threading.Thread(target=fetch_npcs_loop, daemon=True)
    # npcs_thread.start()

    # Start garages loop
    garages_thread = threading.Thread(target=fetch_garages_loop, daemon=True)
    garages_thread.start()

@app.get("/playerlocations")
async def player_locations():
    return JSONResponse(content=simplify_player_data(raw_player_data))

@app.get("/garages")
async def garages_location():
    return JSONResponse(content=garages_data)

# @app.get("/npcs")
# async def npc_locations():
#     return JSONResponse(content=npc_data)

if __name__ == "__main__":
    uvicorn.run("run:app", host="127.0.0.1", port=8000, reload=False)
