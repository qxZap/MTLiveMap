from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import requests
import threading
import time

app = FastAPI()

# Allow CORS for all origins (for development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared cache for raw player data
raw_player_data = {"status": "initializing"}

def fetch_players_loop():
    global raw_player_data
    while True:
        try:
            resp = requests.get("http://localhost:5001/players", timeout=2)
            if resp.status_code == 200:
                raw_player_data = resp.json()
            else:
                raw_player_data = {"status": f"error {resp.status_code}"}
        except Exception as e:
            raw_player_data = {"status": f"fetch error: {e}"}
        time.sleep(0.5)

def simplify_player_data(data: dict):
    simplified = []
    for p in data.get("data", []):
        simplified.append({
            "X": p.get("Location", {}).get("X"),
            "Y": p.get("Location", {}).get("Y"),
            "Z": p.get("Location", {}).get("Z"),
            "Name": p.get("Name"),
            "VehicleKey": p.get("VehicleKey"),
            "UniqueID": p.get("UniqueID")
        })
    return {"status": "ok", "players": simplified}

@app.on_event("startup")
def start_fetcher():
    thread = threading.Thread(target=fetch_players_loop, daemon=True)
    thread.start()

@app.get("/playerlocations")
async def player_locations():
    return JSONResponse(content=simplify_player_data(raw_player_data))

if __name__ == "__main__":
    uvicorn.run("run:app", host="127.0.0.1", port=8000, reload=False)
