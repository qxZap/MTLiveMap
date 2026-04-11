#!/usr/bin/env python3
"""
import_meshes.py - Imports static meshes from static_meshes.json into
map_work_changes.json, applying a hardcoded offset to each entry.
Skips any mesh with asset_key == "SM_SkySphere".

Usage:
    python import_meshes.py
"""

import json
import os

# ---------------------------------------------------------------------------
# Offsets applied to every imported mesh (edit these as needed)
# ---------------------------------------------------------------------------
OFFSET_X = -39800.86
OFFSET_Y = -195000.17
OFFSET_Z = -22450.35


# OFFSET_X = 242898.812
# OFFSET_Y = -177002.594
# OFFSET_Z = -22079.715
# OFFSET_X = 0
# OFFSET_Y = 0
# OFFSET_Z = 0

# x
# : 
# 242898.812
# y
# : 
# -177002.594
# z
# : 
# -22079.715
OFFSET_PITCH = 0.0
OFFSET_ROLL = 0.0
OFFSET_YAW = 0.0

# Which group inside map_work_changes.json["static_meshes"] to write to
TARGET_GROUP = "imported"

# Mesh names to skip (by asset_key)
SKIP_KEYS = {"SM_SkySphere"}

SRC = "static_meshes.json"
DST = "map_work_changes.json"


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.join(script_dir, SRC)
    dst_path = os.path.join(script_dir, DST)

    with open(src_path, "r", encoding="utf-8") as f:
        src = json.load(f)
    with open(dst_path, "r", encoding="utf-8") as f:
        dst = json.load(f)

    imported = []
    skipped = 0

    for group_name, items in src.get("static_meshes", {}).items():
        if not isinstance(items, list):
            continue
        for entry in items:
            if entry.get("asset_key") in SKIP_KEYS:
                skipped += 1
                continue
            new_entry = {
                "asset_path": entry["asset_path"],
                "asset_key": entry["asset_key"],
                "X": float(entry.get("X", 0)) + OFFSET_X,
                "Y": float(entry.get("Y", 0)) + OFFSET_Y,
                "Z": float(entry.get("Z", 0)) + OFFSET_Z,
                "Pitch": float(entry.get("Pitch", 0)) + OFFSET_PITCH,
                "Roll": float(entry.get("Roll", 0)) + OFFSET_ROLL,
                "Yaw": float(entry.get("Yaw", 0)) + OFFSET_YAW,
            }
            imported.append(new_entry)

    dst.setdefault("static_meshes", {})[TARGET_GROUP] = imported

    with open(dst_path, "w", encoding="utf-8") as f:
        json.dump(dst, f, indent=4, ensure_ascii=False)

    print(f"Imported {len(imported)} meshes, skipped {skipped}")
    print(f"Offsets: X={OFFSET_X}, Y={OFFSET_Y}, Z={OFFSET_Z}, "
          f"Pitch={OFFSET_PITCH}, Roll={OFFSET_ROLL}, Yaw={OFFSET_YAW}")
    print(f"Target group: static_meshes.{TARGET_GROUP} in {DST}")


if __name__ == "__main__":
    main()
