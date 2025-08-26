import httpx
from pathlib import Path
from itertools import product
import asyncio
import os


# ---- CONFIG ----
ZOOM_LEVELS = range(1, 7)   # zoom levels to fetch (inclusive range)
X_RANGE = range(0, 64)       # x values
Y_RANGE = range(0, 64)       # y values


BASE_URL = "https://www.aseanmotorclub.com/map_tiles/{z}_{x}_{y}.avif"
TILE_DIR = Path("tiles")
TILE_DIR.mkdir(parents=True, exist_ok=True)

# use half the available CPU cores (at least 1)
MAX_CONCURRENCY = max(1, os.cpu_count() // 2)


async def fetch_tile(client, sem, z, x, y):
    local_path = TILE_DIR / f"{z}_{x}_{y}.avif"

    # ✅ Skip if already downloaded
    if local_path.exists():
        print(f"⏩ Skipped {local_path} (already exists)")
        return

    url = BASE_URL.format(z=z, x=x, y=y)
    async with sem:  # limit concurrency
        try:
            resp = await client.get(url, timeout=10)
            resp.raise_for_status()
            local_path.write_bytes(resp.content)
            print(f"⬇️ Downloaded {local_path}")
        except Exception as e:
            print(f"❌ Failed {z}_{x}_{y}: {e}")


async def main():
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    async with httpx.AsyncClient() as client:
        tasks = [
            fetch_tile(client, sem, z, x, y)
            for z, x, y in product(ZOOM_LEVELS, X_RANGE, Y_RANGE)
        ]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    print(f"🔄 Starting downloads with up to {MAX_CONCURRENCY} concurrent requests...")
    asyncio.run(main())