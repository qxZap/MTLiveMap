"""
Spawn blueprint actors from map_work_changes.json via the MotorTownMods
UE4SS Lua HTTP server.

Requires the game to be running with RE-UE4SS + MotorTownMods installed.
See: https://github.com/drpsyko101/MotorTownMods
Endpoint default: http://localhost:5001/assets/spawn
Auth: Basic <base64(user:pass)> if MOD_SERVER_PASSWORD env var is set on the game side.
"""

import argparse
import base64
import json
import os
import sys
import urllib.request
import urllib.error


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="map_work_changes.json")
    ap.add_argument("--host", default=os.getenv("MOD_SERVER_HOST", "localhost"))
    ap.add_argument("--port", default=os.getenv("MOD_SERVER_PORT", "5001"))
    ap.add_argument("--password", default=os.getenv("MOD_SERVER_PASSWORD"),
                    help="Basic-auth password (user is 'admin').")
    ap.add_argument("--despawn-tag", help="Despawn existing actors with this tag prefix first")
    args = ap.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    bp_section = cfg.get("blueprint_actors", {})
    entries = []
    for group in bp_section.values():
        if isinstance(group, list):
            entries.extend(group)
    if not entries:
        print("No blueprint_actors entries.")
        return 0

    url_base = f"http://{args.host}:{args.port}"
    headers = {"Content-Type": "application/json"}
    if args.password:
        token = base64.b64encode(f"admin:{args.password}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"

    # Build the spawn payload. MotorTownMods expects the AssetPath with the
    # "_C" suffix for blueprint classes (e.g. /Game/.../Foo.Foo_C).
    payload = []
    for e in entries:
        bp_path = e["blueprint_path"]
        bp_class = e.get("blueprint_class") or (bp_path.rsplit("/", 1)[-1] + "_C")
        full_path = f"{bp_path}.{bp_class}"
        payload.append({
            "AssetPath": full_path,
            "Location": {"X": e["X"], "Y": e["Y"], "Z": e["Z"]},
            "Rotation": {
                "Pitch": e.get("Pitch", 0.0),
                "Roll":  e.get("Roll", 0.0),
                "Yaw":   e.get("Yaw", 0.0),
            },
            "Tag": f"MTLiveMap_BP_{len(payload)}",
        })

    if args.despawn_tag:
        _post(f"{url_base}/assets/despawn", headers, {"Tag": args.despawn_tag})

    print(f"POST {url_base}/assets/spawn  [{len(payload)} actor(s)]")
    resp = _post(f"{url_base}/assets/spawn", headers, payload)
    print(resp)
    return 0


def _post(url, headers, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}"
    except Exception as e:
        return f"ERROR: {e}"


if __name__ == "__main__":
    sys.exit(main() or 0)
