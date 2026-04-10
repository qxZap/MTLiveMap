#!/usr/bin/env python3
"""
convert2.py - Injects MTDealerVehicleSpawnPoint actors into a UAssetAPI JSON file.

Works with RawExport (unversioned properties) by cloning binary data from an
existing MTDealerVehicleSpawnPoint export and patching the values.

Usage:
    python convert2.py <input.json> [dealership_mods.json] [output.json]

If dealership_mods.json is not specified, looks for dealership_modifications.json
in the same directory as the script.

Dealership modifications format:
{
    "dealerships": {
        "group_name": [
            {
                "vehicle_path": "/Game/Cars/Models/EnfoGT/EnfoGT",
                "X": 37982.8, "Y": -162517.7, "Z": -21926.5,
                "Pitch": 0, "Roll": 0, "Yaw": -79.0
            }
        ]
    }
}

If "vehicle_path" is omitted but "VehicleKey" is present, the path is derived as:
    /Game/Cars/Models/{VehicleKey}/{VehicleKey}
"""

import json
import sys
import uuid
import struct
import base64
import os


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def ensure_name(name_map, name):
    """Add name to NameMap if not already present."""
    if name not in name_map:
        name_map.append(name)


def fname_base(name):
    """Return the FName base (without trailing _NUMBER suffix)."""
    last_us = name.rfind("_")
    if last_us > 0 and name[last_us + 1 :].isdigit():
        return name[:last_us]
    return name


def ensure_fname(name_map, name):
    """Add both full name and its FName base to NameMap."""
    ensure_name(name_map, name)
    base = fname_base(name)
    if base != name:
        ensure_name(name_map, base)


def find_import_index(imports, object_name, outer_index=None):
    """Return negative 1-based index of an import, or None."""
    for i, imp in enumerate(imports):
        if imp["ObjectName"] == object_name:
            if outer_index is None or imp["OuterIndex"] == outer_index:
                return -(i + 1)
    return None


def add_import(imports, object_name, outer_index, class_package, class_name):
    """Append a new import, return its negative 1-based index."""
    imports.append(
        {
            "$type": "UAssetAPI.Import, UAssetAPI",
            "ObjectName": object_name,
            "OuterIndex": outer_index,
            "ClassPackage": class_package,
            "ClassName": class_name,
            "PackageName": None,
            "bImportOptional": False,
        }
    )
    return -(len(imports))


def find_or_add_import(imports, name_map, object_name, outer_index, class_package, class_name):
    """Find existing import or create a new one. Returns negative 1-based index."""
    idx = find_import_index(imports, object_name, outer_index)
    if idx is not None:
        return idx
    ensure_fname(name_map, object_name)
    ensure_fname(name_map, class_package)
    ensure_fname(name_map, class_name)
    return add_import(imports, object_name, outer_index, class_package, class_name)


# ---------------------------------------------------------------------------
# Binary data builders for RawExport
# ---------------------------------------------------------------------------

# Unversioned property header for MTDealerVehicleSpawnPoint actor
# Cloned from a known-working export (27779 in Jeju_World).
# Encodes: VehicleClass, EditorVisualVehicleClass, SceneComponent, RootComponent
ACTOR_PROP_HEADER = bytes.fromhex("0002020203023903")

# Unversioned property header for RootScene (SceneComponent)
# Encodes: RelativeLocation, RelativeRotation
ROOTSCENE_PROP_HEADER = bytes.fromhex("0505")


def build_actor_data(vehicle_class_ref, scene_comp_ref, label):
    """
    Build raw binary Data for a MTDealerVehicleSpawnPoint RawExport.

    Binary layout (verified from existing exports):
      [0:8]   Unversioned property header
      [8:12]  VehicleClass (int32 import ref)
      [12:16] EditorVisualVehicleClass (int32 import ref, same as VehicleClass)
      [16:20] SceneComponent (int32 export ref to RootScene)
      [20:24] RootComponent (int32 export ref, same as SceneComponent)
      [24:28] Zero padding (part of unversioned property serialization)
      [28:]   Actor extras: count(4) + strlen(4) + label_bytes + GUID(16) + padding(16)
    """
    data = bytearray()
    data += ACTOR_PROP_HEADER
    data += struct.pack("<i", vehicle_class_ref)       # VehicleClass
    data += struct.pack("<i", vehicle_class_ref)       # EditorVisualVehicleClass
    data += struct.pack("<i", scene_comp_ref)          # SceneComponent
    data += struct.pack("<i", scene_comp_ref)          # RootComponent
    data += b"\x00\x00\x00\x00"                       # zero field
    # Actor extras
    label_bytes = label.encode("utf-8") + b"\x00"
    data += struct.pack("<I", 1)                       # count
    data += struct.pack("<I", len(label_bytes))        # string length (incl null)
    data += label_bytes                                # label string
    data += uuid.uuid4().bytes                         # 16-byte GUID
    data += b"\x00" * 16                               # trailing padding
    return base64.b64encode(bytes(data)).decode("ascii")


def build_rootscene_data(x, y, z, pitch, yaw, roll):
    """
    Build raw binary Data for a RootScene (SceneComponent) RawExport.

    Binary layout (verified from existing exports):
      [0:2]   Unversioned property header
      [2:26]  RelativeLocation (3 x float64: X, Y, Z)
      [26:50] RelativeRotation (3 x float64: Pitch, Yaw, Roll)
      [50:58] Zero padding
    """
    data = bytearray()
    data += ROOTSCENE_PROP_HEADER
    data += struct.pack("<ddd", x, y, z)               # RelativeLocation
    data += struct.pack("<ddd", pitch, yaw, roll)       # RelativeRotation
    data += b"\x00" * 8                                 # padding
    return base64.b64encode(bytes(data)).decode("ascii")


# ---------------------------------------------------------------------------
# Vehicle path helpers
# ---------------------------------------------------------------------------


def resolve_vehicle_path(entry):
    """
    Get the full game path for the vehicle blueprint.
    Supports either explicit 'vehicle_path' or derives from 'VehicleKey'.
    Returns (package_path, class_name).
    """
    if "vehicle_path" in entry:
        pkg = entry["vehicle_path"]
        base_name = pkg.rsplit("/", 1)[-1]
        return pkg, f"{base_name}_C"
    elif "VehicleKey" in entry:
        key = entry["VehicleKey"]
        return f"/Game/Cars/Models/{key}/{key}", f"{key}_C"
    else:
        raise ValueError(f"Entry missing both 'vehicle_path' and 'VehicleKey': {entry}")


# ---------------------------------------------------------------------------
# Main conversion
# ---------------------------------------------------------------------------


def main():
    if len(sys.argv) < 2:
        print("Usage: python convert2.py <input.json> [dealership_mods.json] [output.json]")
        print("\nInjects MTDealerVehicleSpawnPoint actors into a UAssetAPI JSON file.")
        sys.exit(1)

    input_path = sys.argv[1]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mods_path = (
        sys.argv[2]
        if len(sys.argv) > 2
        else os.path.join(script_dir, "dealership_modifications.json")
    )

    if len(sys.argv) > 3:
        output_path = sys.argv[3]
    else:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}MOD{ext}"

    # ---- Load files -------------------------------------------------------
    with open(input_path, "r", encoding="utf-8") as f:
        asset = json.load(f)
    with open(mods_path, "r", encoding="utf-8") as f:
        mods = json.load(f)

    name_map = asset["NameMap"]
    exports = asset["Exports"]
    imports = asset["Imports"]
    depends_map = asset.get("DependsMap")

    # ---- Locate PersistentLevel export ------------------------------------
    level_idx = None
    for i, exp in enumerate(exports):
        if exp.get("ObjectName") == "PersistentLevel":
            level_idx = i
            break
    if level_idx is None:
        print("Error: No PersistentLevel export found in input JSON.")
        sys.exit(1)

    level_export = exports[level_idx]
    level_num = level_idx + 1  # 1-based export number
    is_raw = level_export.get("$type") == "UAssetAPI.ExportTypes.RawExport, UAssetAPI"
    print(f"Found PersistentLevel at export {level_num} (type: {'RawExport' if is_raw else 'LevelExport'})")

    # ---- Ensure common names are present ----------------------------------
    for n in (
        "MTDealerVehicleSpawnPoint",
        "Default__MTDealerVehicleSpawnPoint",
        "SceneComponent",
        "RootScene",
        "RootComponent",
        "VehicleClass",
        "EditorVisualVehicleClass",
        "RelativeLocation",
        "RelativeRotation",
        "/Script/Engine",
        "/Script/CoreUObject",
        "/Script/MotorTown",
        "Class",
        "Package",
        "BlueprintGeneratedClass",
        "MTDealerVehicleSpawnPoint_MOD",
    ):
        ensure_fname(name_map, n)

    # ---- Find / create shared class & template imports --------------------

    # /Script/MotorTown package
    motortown_pkg = find_or_add_import(
        imports, name_map, "/Script/MotorTown", 0, "/Script/CoreUObject", "Package"
    )

    # /Script/Engine package
    engine_pkg = find_or_add_import(
        imports, name_map, "/Script/Engine", 0, "/Script/CoreUObject", "Package"
    )

    # MTDealerVehicleSpawnPoint class
    dealer_class = find_or_add_import(
        imports, name_map,
        "MTDealerVehicleSpawnPoint", motortown_pkg,
        "/Script/CoreUObject", "Class"
    )

    # Default__MTDealerVehicleSpawnPoint template
    default_dealer = find_or_add_import(
        imports, name_map,
        "Default__MTDealerVehicleSpawnPoint", motortown_pkg,
        "/Script/MotorTown", "MTDealerVehicleSpawnPoint"
    )

    # SceneComponent class
    scene_class = find_or_add_import(
        imports, name_map,
        "SceneComponent", engine_pkg,
        "/Script/CoreUObject", "Class"
    )

    # RootScene default sub-object template
    rootscene_template = find_or_add_import(
        imports, name_map,
        "RootScene", default_dealer,
        "/Script/Engine", "SceneComponent"
    )

    # ---- Gather all spawn entries -----------------------------------------
    all_spawns = []
    dealerships = mods.get("dealerships", mods)
    for group_name, group_items in dealerships.items():
        if not isinstance(group_items, list):
            continue
        for item in group_items:
            all_spawns.append(item)

    if not all_spawns:
        print("No spawn entries found. Nothing to inject.")
        sys.exit(0)

    print(f"Injecting {len(all_spawns)} dealer vehicle spawn points ...")

    # ---- Build import cache for unique vehicle types ----------------------
    vehicle_import_cache = {}

    for entry in all_spawns:
        pkg_path, class_name = resolve_vehicle_path(entry)
        if pkg_path not in vehicle_import_cache:
            ensure_fname(name_map, pkg_path)
            ensure_fname(name_map, class_name)
            veh_pkg = find_or_add_import(
                imports, name_map, pkg_path, 0,
                "/Script/CoreUObject", "Package"
            )
            veh_class = find_or_add_import(
                imports, name_map, class_name, veh_pkg,
                "/Script/Engine", "BlueprintGeneratedClass"
            )
            vehicle_import_cache[pkg_path] = veh_class

    # ---- Create export pairs for every spawn point ------------------------
    new_actor_nums = []

    for i, entry in enumerate(all_spawns):
        pkg_path, class_name = resolve_vehicle_path(entry)
        veh_class_imp = vehicle_import_cache[pkg_path]

        x = float(entry.get("X", 0))
        y = float(entry.get("Y", 0))
        z = float(entry.get("Z", 0))
        pitch = float(entry.get("Pitch", 0))
        yaw = float(entry.get("Yaw", 0))
        roll = float(entry.get("Roll", 0))

        veh_key = entry.get("VehicleKey", class_name.replace("_C", ""))
        actor_name = f"MTDealerVehicleSpawnPoint_MOD_{i}"

        # 1-based export numbers for the new pair
        actor_num = len(exports) + 1
        comp_num = len(exports) + 2

        # ---- Actor export (MTDealerVehicleSpawnPoint) ---------------------
        actor_data_b64 = build_actor_data(veh_class_imp, comp_num, veh_key)

        actor_export = {
            "$type": "UAssetAPI.ExportTypes.RawExport, UAssetAPI",
            "Data": actor_data_b64,
            "ObjectName": actor_name,
            "OuterIndex": level_num,
            "ClassIndex": dealer_class,
            "SuperIndex": 0,
            "TemplateIndex": default_dealer,
            "ObjectFlags": "RF_Transactional",
            "SerialSize": 0,
            "SerialOffset": 0,
            "ScriptSerializationStartOffset": 0,
            "ScriptSerializationEndOffset": 0,
            "bForcedExport": False,
            "bNotForClient": False,
            "bNotForServer": False,
            "PackageGuid": "{00000000-0000-0000-0000-000000000000}",
            "IsInheritedInstance": False,
            "PackageFlags": "PKG_None",
            "bNotAlwaysLoadedForEditorGame": True,
            "bIsAsset": False,
            "GeneratePublicHash": False,
            "SerializationBeforeSerializationDependencies": [],
            "CreateBeforeSerializationDependencies": [veh_class_imp, comp_num],
            "SerializationBeforeCreateDependencies": [
                dealer_class,
                default_dealer,
                rootscene_template,
            ],
            "CreateBeforeCreateDependencies": [level_num],
            "Extras": "",
        }

        # ---- Component export (RootScene / SceneComponent) ----------------
        comp_data_b64 = build_rootscene_data(x, y, z, pitch, yaw, roll)

        comp_export = {
            "$type": "UAssetAPI.ExportTypes.RawExport, UAssetAPI",
            "Data": comp_data_b64,
            "ObjectName": "RootScene",
            "OuterIndex": actor_num,
            "ClassIndex": scene_class,
            "SuperIndex": 0,
            "TemplateIndex": rootscene_template,
            "ObjectFlags": "RF_Transactional, RF_DefaultSubObject",
            "SerialSize": 0,
            "SerialOffset": 0,
            "ScriptSerializationStartOffset": 0,
            "ScriptSerializationEndOffset": 0,
            "bForcedExport": False,
            "bNotForClient": False,
            "bNotForServer": False,
            "PackageGuid": "{00000000-0000-0000-0000-000000000000}",
            "IsInheritedInstance": True,
            "PackageFlags": "PKG_None",
            "bNotAlwaysLoadedForEditorGame": True,
            "bIsAsset": False,
            "GeneratePublicHash": False,
            "SerializationBeforeSerializationDependencies": [],
            "CreateBeforeSerializationDependencies": [],
            "SerializationBeforeCreateDependencies": [scene_class, rootscene_template],
            "CreateBeforeCreateDependencies": [actor_num],
            "Extras": "",
        }

        exports.append(actor_export)
        exports.append(comp_export)
        new_actor_nums.append(actor_num)

        # Extend DependsMap
        if depends_map is not None:
            depends_map.append([])
            depends_map.append([])

    # ---- Register actors in PersistentLevel -------------------------------
    level_export.setdefault("CreateBeforeSerializationDependencies", [])
    level_export["CreateBeforeSerializationDependencies"].extend(new_actor_nums)

    if is_raw:
        # RawExport: also patch the binary actor list inside Data.
        # Layout: ... [int32 actor_count] [actor_count * int32 exports] [URL FString] ...
        # The URL starts with int32(7) + "unreal\0".
        level_raw = bytearray(base64.b64decode(level_export["Data"]))
        url_marker = struct.pack("<i", 7) + b"unreal\x00"
        url_offset = level_raw.find(url_marker)
        if url_offset == -1:
            print("Warning: Could not locate URL marker in PersistentLevel binary data.")
            print("         New actors added to CBSD only; binary actor list NOT patched.")
        else:
            # The actor count is an int32 right before the actor list.
            # Find it: count_offset + 4 + count*4 == url_offset
            # Scan backwards from url_offset for an int32 that satisfies this.
            count_offset = None
            for probe in range(url_offset - 4, 3, -4):
                candidate_count = struct.unpack_from("<i", level_raw, probe)[0]
                if candidate_count > 0:
                    expected_end = probe + 4 + candidate_count * 4
                    if expected_end == url_offset:
                        count_offset = probe
                        break

            if count_offset is None:
                print("Warning: Could not locate actor count field. Binary NOT patched.")
            else:
                old_count = struct.unpack_from("<i", level_raw, count_offset)[0]
                new_count = old_count + len(new_actor_nums)

                # Update the count
                struct.pack_into("<i", level_raw, count_offset, new_count)

                # Insert new actor export numbers right before the URL
                insert_bytes = b""
                for actor_num in new_actor_nums:
                    insert_bytes += struct.pack("<i", actor_num)
                level_raw[url_offset:url_offset] = insert_bytes

                level_export["Data"] = base64.b64encode(bytes(level_raw)).decode("ascii")
                print(f"Patched PersistentLevel binary: actor count {old_count} -> {new_count}, inserted at offset {url_offset}")
    else:
        # LevelExport: actors tracked in Actors list
        level_export["Actors"].extend(new_actor_nums)

    # ---- Update Generations bookkeeping -----------------------------------
    if asset.get("Generations"):
        asset["Generations"][0]["ExportCount"] = len(exports)
        asset["Generations"][0]["NameCount"] = len(name_map)

    # ---- Write output -----------------------------------------------------
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(asset, f, indent=2, ensure_ascii=False)

    print(f"Done!  {output_path}")
    print(
        f"  {len(all_spawns)} spawn points  |  "
        f"{len(vehicle_import_cache)} unique vehicles  |  "
        f"{len(exports)} exports  |  "
        f"{len(imports)} imports  |  "
        f"{len(name_map)} names"
    )


if __name__ == "__main__":
    main()
