from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
import asyncio
import json
import time
from fastapi.middleware.cors import CORSMiddleware

import threading
from contextlib import asynccontextmanager
import httpx
import uvicorn

app = FastAPI(title="Live Map API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or restrict to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------- Data Models ---------------
class Position(BaseModel):
    X: float
    Y: float
    Z: float

class Player(BaseModel):
    UniqueID: str
    Name: str
    bIsAdmin: bool
    Location: Position
    LastUpdated: float

# --------------- In-Memory Store ---------------
class PlayerStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._players: Dict[str, Player] = {}

    def update_or_add(self, players: List[Player]):
        with self._lock:
            for p in players:
                p.LastUpdated = time.time()
                self._players[p.UniqueID] = p

    def to_list(self) -> List[Player]:
        with self._lock:
            return list(self._players.values())

    def prune_stale(self, ttl: float = 5.0):
        cutoff = time.time() - ttl
        with self._lock:
            stale = [uid for uid, p in self._players.items() if p.LastUpdated < cutoff]
            for uid in stale:
                del self._players[uid]

store = PlayerStore()

# --------------- Config for Ingestion ---------------
class IngestionConfig:
    endpoint: str = "http://localhost:5001/players"
    interval: float = 0.5

_live_config = IngestionConfig()

@app.get("/playerlocations")
async def stream_player_locations():
    async def event_stream():
        async with httpx.AsyncClient(timeout=10.0) as client:
            while True:
                try:
                    resp = await client.get(_live_config.endpoint)
                    if resp.status_code == 200:
                        data = resp.json()
                        items = data.get("data", []) if isinstance(data, dict) else data
                        players = [
                            _parse_player(item) for item in items if _parse_player(item)
                        ]
                        if players:
                            store.update_or_add(players)
                        store.prune_stale()
                        # Always send all active players
                        all_players = store.to_list()
                        yield f"data: {json.dumps({'type': 'update', 'players': [p.dict() for p in all_players]})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'error', 'message': 'API request failed'})}\n\n"
                except Exception:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Request or parsing error'})}\n\n"

                await asyncio.sleep(_live_config.interval)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
# --------------- Player Parsing ---------------
def _parse_player(item: dict) -> Optional[Player]:
    try:
        uid = item.get("UniqueID") or item.get("id") or item.get("user_id")
        name = item.get("Name") or item.get("name") or "Unknown"
        admin = bool(item.get("bIsAdmin", False))
        loc = item.get("Location") or {}
        x = float(loc.get("X", 0.0))
        y = float(loc.get("Y", 0.0))
        z = float(loc.get("Z", 0.0))
        return Player(
            UniqueID=str(uid),
            Name=name,
            bIsAdmin=admin,
            Location=Position(X=x, Y=y, Z=z),
            LastUpdated=time.time(),
        )
    except Exception:
        return None

# --------------- Lifespan Handler ---------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = threading.Event()
    try:
        yield
    finally:
        stop_event.set()

# Initialize FastAPI with lifespan
app = FastAPI(title="Live Map API", lifespan=lifespan)

# --------------- Main Function to Run the App ---------------
def main():
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()