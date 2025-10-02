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

LUA_API = "http://localhost:5001"

IS_SERVER_ONLINE = False
STARTUP_CREATED = False
DEALERS_SPAWN_ENABLED = True
FILE_CHANGES_FREQUENCY = 20

DEALERSHIP_MODIFICATIONS_FILE = Path("dealership.json")
DEALERSHIP_TAGS_FILE = Path("dealership_tags_DONT_EDIT.json")

def load_dealership_tags():
    if DEALERSHIP_TAGS_FILE.exists():
        with DEALERSHIP_TAGS_FILE.open("r") as f:
            loaded_tags = json.load(f)
            return loaded_tags
    else:
        return []


DEALERSHIPS_TAGS = load_dealership_tags()
DEALERSHIP_MODIFICATIONS={}


async def shutdown_at(target_hour=5, target_minute=0):
    while True:
        now = datetime.datetime.now()
        if now.hour == target_hour and now.minute == target_minute:
            print("Shutting down FastAPI server at scheduled time...")
            os._exit(0)
        await asyncio.sleep(30)

def save_dealership_tags():
    with DEALERSHIP_TAGS_FILE.open("w") as f:
        json.dump(DEALERSHIPS_TAGS, f)

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
            
            if DEALERS_SPAWN_ENABLED:
                asyncio.create_task(watch_dealers_modifications())

        await asyncio.sleep(5)


async def reload_dealerships_from_file():
    global DEALERSHIPS_TAGS, DEALERSHIP_MODIFICATIONS
    await despawn_assets(DEALERSHIPS_TAGS)

    tags = []

    for dealer in DEALERSHIP_MODIFICATIONS:
        new_tags = await spawn_dealers(DEALERSHIP_MODIFICATIONS[dealer])
        tags+=new_tags
    DEALERSHIPS_TAGS = tags
    save_dealership_tags()

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

        await asyncio.sleep(FILE_CHANGES_FREQUENCY)

@app.on_event("startup")
async def start_fetcher():
    asyncio.create_task(fetch_server_health_check())

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
    loop = asyncio.get_event_loop()
    loop.create_task(shutdown_at(5, 00))
    
    config = uvicorn.Config("run:app", host="0.0.0.0", port=8001, reload=False, loop="asyncio")
    server = uvicorn.Server(config)
    loop.run_until_complete(server.serve())