#!/usr/bin/env python3
"""
import_meshes.py - Imports static meshes from static_meshes.json into
map_work_changes.json["static_meshes"]["imported"], applying offsets.
Skips SM_SkySphere. Copies missing assets into the mod pak directory.

Usage:
    python import_meshes.py
"""

import json
import os
import shutil

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
GAME_CONTENT = r"D:\MT\Output\Exports\MotorTown\Content"
COOKED_CONTENT = r"C:\Users\Milea\Documents\Unreal Projects\MTMapAddon\Saved\Cooked\Windows\MTMapAddon\Content"
MOD_CONTENT = r"MapChangeTest_P\MotorTown\Content"

# ---------------------------------------------------------------------------
# Offsets applied to every imported mesh (edit these as needed)
# ---------------------------------------------------------------------------

# Jeju imports
# OFFSET_X = -39800.86
# OFFSET_Y = -195000.17
# OFFSET_Z = -22450.35

# New map
OFFSET_X = -39800.0
OFFSET_Y = -195000.0
OFFSET_Z = -24450.0

# Paddy Track
# OFFSET_X = -39800.0
# OFFSET_Y = -195000.0
# OFFSET_Z = -24450.0


# OFFSET_X = 242898.812
# OFFSET_Y = -177002.594
# OFFSET_Z = -22079.715
# OFFSET_X = 0
# OFFSET_Y = 0
# OFFSET_Z = 0

OFFSET_PITCH = 0.0
OFFSET_ROLL = 0.0
OFFSET_YAW = 0.0

# Which group inside map_work_changes.json["static_meshes"] to write to
TARGET_GROUP = "imported"

from bp_registry import REGISTRY as _BP_REGISTRY, asset_keys as _bp_asset_keys

# Meshes intentionally excluded (never placed as static meshes or BP actors)
SKIP_KEYS = {"SM_SkySphere"}

# Placeholder asset_keys (from bp_registry) become blueprint_actors entries
# instead of static meshes. Registry keys are the single source of truth.
BP_CLASS_FROM_KEY = {
    key: {"blueprint_path": entry["bp_path"], "blueprint_class": entry["bp_class"]}
    for key, entry in _BP_REGISTRY.items()
}
PARKING_KEYS = _bp_asset_keys()

SRC = "static_meshes.json"
DST = "map_work_changes.json"


def game_path_to_disk(asset_path):
    """
    Convert a UE game path to a relative disk path under Content/.
    e.g. "/Game/Models/Foo/Bar" -> "Models/Foo/Bar"
         "/Engine/Foo/Bar"      -> None (engine asset, skip)
    """
    # Strip .ExportName suffix if present
    dot = asset_path.rfind("/")
    dot_pos = asset_path.find(".", dot)
    if dot_pos != -1:
        asset_path = asset_path[:dot_pos]

    # /Game/ maps to MotorTown/Content/ on disk
    if asset_path.startswith("/Game/"):
        return asset_path[len("/Game/"):]
    return None


def copy_asset_to_mod(relative_path, script_dir):
    """
    If the asset doesn't exist in extracted game files, copy it from
    cooked content (or game content) into the mod pak directory.
    Copies .uasset, .uexp, .ubulk — skips silently if any don't exist.
    """
    game_file = os.path.join(GAME_CONTENT, relative_path + ".uasset")
    mod_target = os.path.join(script_dir, MOD_CONTENT, relative_path)

    if os.path.exists(game_file):
        return  # exists in game, no need to copy

    # Try cooked content as source
    cooked_file = os.path.join(COOKED_CONTENT, relative_path + ".uasset")
    if not os.path.exists(cooked_file):
        print(f"  Warning: asset not found in game or cooked: {relative_path}")
        return

    mod_dir = os.path.dirname(mod_target)
    os.makedirs(mod_dir, exist_ok=True)

    copied = []
    for ext in [".uasset", ".uexp", ".ubulk"]:
        src = os.path.join(COOKED_CONTENT, relative_path + ext)
        dst = mod_target + ext
        try:
            if os.path.exists(src):
                shutil.copy2(src, dst)
                copied.append(ext)
        except Exception:
            pass

    # Silenced: per-asset copy log is noisy; summary is printed at end.
    # if copied:
    #     print(f"  Copied {relative_path} ({', '.join(copied)})")
    pass


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.join(script_dir, SRC)
    dst_path = os.path.join(script_dir, DST)

    with open(src_path, "r", encoding="utf-8") as f:
        src = json.load(f)
    with open(dst_path, "r", encoding="utf-8") as f:
        dst = json.load(f)

    imported = []
    parking = []
    skipped = 0
    copied_paths = set()

    for group_name, items in src.get("static_meshes", {}).items():
        if not isinstance(items, list):
            continue
        for entry in items:
            # SKIP_KEYS: completely ignore (unless also in PARKING_KEYS)
            if entry.get("asset_key") in SKIP_KEYS and entry.get("asset_key") not in PARKING_KEYS:
                skipped += 1
                continue

            # Copy missing assets to mod (once per unique path)
            raw_path = entry.get("asset_path", "")
            rel_path = game_path_to_disk(raw_path)
            if rel_path and rel_path not in copied_paths:
                copy_asset_to_mod(rel_path, script_dir)
                copied_paths.add(rel_path)

            base_entry = {
                "X": round(float(entry.get("X", 0)) + OFFSET_X, 4),
                "Y": round(float(entry.get("Y", 0)) + OFFSET_Y, 4),
                "Z": round(float(entry.get("Z", 0)) + OFFSET_Z, 4),
                "Pitch": round(float(entry.get("Pitch", 0)) + OFFSET_PITCH, 4),
                "Roll": round(float(entry.get("Roll", 0)) + OFFSET_ROLL, 4),
                "Yaw": round(float(entry.get("Yaw", 0)) + OFFSET_YAW, 4),
            }

            key = entry.get("asset_key")
            if key in PARKING_KEYS:
                base_entry.update(BP_CLASS_FROM_KEY[key])
                parking.append(base_entry)
            else:
                base_entry["asset_path"] = raw_path
                base_entry["asset_key"] = entry.get("asset_key", "")
                base_entry["ScaleX"] = float(entry.get("ScaleX", 1.0))
                base_entry["ScaleY"] = float(entry.get("ScaleY", 1.0))
                base_entry["ScaleZ"] = float(entry.get("ScaleZ", 1.0))
                imported.append(base_entry)

    # Always clear and set — never append
    dst.setdefault("static_meshes", {})[TARGET_GROUP] = imported
    dst.setdefault("blueprint_actors", {})[TARGET_GROUP] = parking

    with open(dst_path, "w", encoding="utf-8") as f:
        json.dump(dst, f, indent=4, ensure_ascii=False)

    print(f"Imported {len(imported)} meshes + {len(parking)} parking lots, skipped {skipped}")
    print(f"Offsets: X={OFFSET_X}, Y={OFFSET_Y}, Z={OFFSET_Z}")
    print(f"Target: {TARGET_GROUP} (cleared and set)")


if __name__ == "__main__":
    main()
