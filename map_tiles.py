from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import httpx
from pathlib import Path
import uvicorn

app = FastAPI()

# Local storage path for cached tiles
TILE_DIR = Path("tiles")
TILE_DIR.mkdir(parents=True, exist_ok=True)

REMOTE_BASE = "https://www.aseanmotorclub.com/map_tiles"


@app.get("/map_tiles/{file_path:path}")
async def get_map_tile(file_path: str):
    """
    Transparent proxy/cache for AVIF tiles.
    - If file exists locally, serve it.
    - Otherwise fetch from remote, save, then serve.
    """
    local_path = TILE_DIR / file_path

    # Ensure parent dirs exist (if path contains subfolders)
    local_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Serve from cache if exists
    if local_path.exists():
        return FileResponse(local_path, media_type="image/avif")

    # 2. Fetch from remote
    url = f"{REMOTE_BASE}/{file_path}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error fetching remote tile: {str(e)}")

    # 3. Save locally
    with open(local_path, "wb") as f:
        f.write(resp.content)

    # 4. Serve response
    return FileResponse(local_path, media_type="image/avif")


if __name__ == "__main__":
    uvicorn.run("map_tiles:app", host="0.0.0.0", port=8001, reload=True)
