#!/usr/bin/env python3
"""
convert_sublevel.py - Injects blueprint actors (parking spots etc.) into a
sub-level .umap via NormalExport format.

Uses BPITA48KRY74AFBRZBJY6ENBZ.json as a template (known working NormalExport).
Strips existing actors, adds new ones from map_work_changes.json["blueprint_actors"].

Usage:
    python convert_sublevel.py [map_work_changes.json] [output.json]
"""

import json
import sys
import os
import copy
import uuid

TEMPLATE = "BPITA48KRY74AFBRZBJY6ENBZ.json"


def ensure_name(name_map, name):
    if name not in name_map:
        name_map.append(name)


def fname_base(name):
    last_us = name.rfind("_")
    if last_us > 0 and name[last_us + 1:].isdigit():
        return name[:last_us]
    return name


def ensure_fname(name_map, name):
    ensure_name(name_map, name)
    base = fname_base(name)
    if base != name:
        ensure_name(name_map, base)


def find_import_index(imports, object_name, outer_index=None):
    for i, imp in enumerate(imports):
        if imp["ObjectName"] == object_name:
            if outer_index is None or imp["OuterIndex"] == outer_index:
                return -(i + 1)
    return None


def add_import(imports, object_name, outer_index, class_package, class_name):
    imports.append({
        "$type": "UAssetAPI.Import, UAssetAPI",
        "ObjectName": object_name,
        "OuterIndex": outer_index,
        "ClassPackage": class_package,
        "ClassName": class_name,
        "PackageName": None,
        "bImportOptional": False,
    })
    return -(len(imports))


def find_or_add_import(imports, name_map, object_name, outer_index, class_package, class_name):
    idx = find_import_index(imports, object_name, outer_index)
    if idx is not None:
        return idx
    ensure_fname(name_map, object_name)
    ensure_fname(name_map, class_package)
    ensure_fname(name_map, class_name)
    return add_import(imports, object_name, outer_index, class_package, class_name)


def _fmt_rot(v):
    return "+0" if v == 0.0 else v


def _obj_prop(name, value):
    return {
        "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
        "Name": name, "ArrayIndex": 0, "IsZero": False,
        "PropertyTagFlags": "None", "PropertyTypeName": None,
        "PropertyTagExtensions": "NoExtension", "Value": value,
    }


def _vector_prop(name, x, y, z):
    return {
        "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
        "StructType": "Vector", "SerializeNone": True,
        "StructGUID": "{00000000-0000-0000-0000-000000000000}",
        "SerializationControl": "NoExtension", "Operation": "None",
        "Name": name, "ArrayIndex": 0, "IsZero": False,
        "PropertyTagFlags": "None", "PropertyTypeName": None,
        "PropertyTagExtensions": "NoExtension",
        "Value": [{
            "$type": "UAssetAPI.PropertyTypes.Structs.VectorPropertyData, UAssetAPI",
            "Name": name, "ArrayIndex": 0, "IsZero": False,
            "PropertyTagFlags": "None", "PropertyTypeName": None,
            "PropertyTagExtensions": "NoExtension",
            "Value": {"$type": "UAssetAPI.UnrealTypes.FVector, UAssetAPI",
                      "X": x, "Y": y, "Z": z},
        }],
    }


def _rotator_prop(name, pitch, yaw, roll):
    return {
        "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
        "StructType": "Rotator", "SerializeNone": True,
        "StructGUID": "{00000000-0000-0000-0000-000000000000}",
        "SerializationControl": "NoExtension", "Operation": "None",
        "Name": name, "ArrayIndex": 0, "IsZero": False,
        "PropertyTagFlags": "None", "PropertyTypeName": None,
        "PropertyTagExtensions": "NoExtension",
        "Value": [{
            "$type": "UAssetAPI.PropertyTypes.Structs.RotatorPropertyData, UAssetAPI",
            "Name": name, "ArrayIndex": 0, "IsZero": False,
            "PropertyTagFlags": "None", "PropertyTypeName": None,
            "PropertyTagExtensions": "NoExtension",
            "Value": {"$type": "UAssetAPI.UnrealTypes.FRotator, UAssetAPI",
                      "Pitch": _fmt_rot(pitch), "Yaw": _fmt_rot(yaw), "Roll": _fmt_rot(roll)},
        }],
    }


def make_normal_export(data_props, object_name, outer_index, class_index, template_index,
                       object_flags="RF_Transactional", is_inherited=False,
                       sbsd=None, cbsd=None, sbcd=None, cbcd=None, extras=""):
    return {
        "$type": "UAssetAPI.ExportTypes.NormalExport, UAssetAPI",
        "Data": data_props,
        "ObjectGuid": None,
        "SerializationControl": "NoExtension",
        "Operation": "None",
        "HasLeadingFourNullBytes": False,
        "ObjectName": object_name,
        "OuterIndex": outer_index,
        "ClassIndex": class_index,
        "SuperIndex": 0,
        "TemplateIndex": template_index,
        "ObjectFlags": object_flags,
        "SerialSize": 0,
        "SerialOffset": 0,
        "ScriptSerializationStartOffset": 0,
        "ScriptSerializationEndOffset": 0,
        "bForcedExport": False,
        "bNotForClient": False,
        "bNotForServer": False,
        "PackageGuid": "{00000000-0000-0000-0000-000000000000}",
        "IsInheritedInstance": is_inherited,
        "PackageFlags": "PKG_None",
        "bNotAlwaysLoadedForEditorGame": True,
        "bIsAsset": False,
        "GeneratePublicHash": False,
        "SerializationBeforeSerializationDependencies": sbsd or [],
        "CreateBeforeSerializationDependencies": cbsd or [],
        "SerializationBeforeCreateDependencies": sbcd or [],
        "CreateBeforeCreateDependencies": cbcd or [],
        "Extras": extras,
    }


COMPONENT_EXTRAS = "AAAAAAAAAAABAAAAAAAAAA=="  # struct.pack("<IIII", 0, 0, 1, 0) base64


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mods_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(script_dir, "map_work_changes.json")
    output_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(script_dir, "sublevel_parking.json")
    template_path = os.path.join(script_dir, TEMPLATE)

    with open(mods_path, "r", encoding="utf-8") as f:
        mods = json.load(f)
    with open(template_path, "r", encoding="utf-8") as f:
        asset = json.load(f)

    # Gather blueprint_actors entries
    bp_entries = []
    for group_name, group_items in mods.get("blueprint_actors", {}).items():
        if isinstance(group_items, list):
            bp_entries.extend(group_items)

    if not bp_entries:
        print("No blueprint_actors entries. Nothing to do.")
        return

    name_map = asset["NameMap"]
    exports = asset["Exports"]
    imports = asset["Imports"]
    depends_map = asset.get("DependsMap", [])

    # Find LevelExport
    level_idx = None
    for i, exp in enumerate(exports):
        if exp.get("$type") == "UAssetAPI.ExportTypes.LevelExport, UAssetAPI":
            level_idx = i
            break
    if level_idx is None:
        print("Error: No LevelExport in template.")
        sys.exit(1)

    level_export = exports[level_idx]
    level_num = level_idx + 1

    # Strip existing actors (keep only infrastructure: Level, Model, World, WorldSettings, NavConfig)
    keep_names = {"PersistentLevel", "Model_0", "Jeju_World", "WorldSettings",
                  "NavigationSystemModuleConfig_0"}
    keep_indices = set()
    for i, exp in enumerate(exports):
        if exp.get("ObjectName") in keep_names:
            keep_indices.add(i)

    # Clear actor list — we'll add our own
    level_export["Actors"] = [0]  # 0 = null entry (required)

    # Find/keep WorldSettings export number
    for i, exp in enumerate(exports):
        if exp.get("ObjectName") == "WorldSettings":
            level_export["Actors"].insert(0, i + 1)
            break

    # Ensure imports for parking class
    engine_pkg = find_or_add_import(imports, name_map, "/Script/Engine", 0,
                                    "/Script/CoreUObject", "Package")
    scene_class = find_or_add_import(imports, name_map, "SceneComponent", engine_pkg,
                                     "/Script/CoreUObject", "Class")

    bp_cache = {}
    for entry in bp_entries:
        bp_path = entry["blueprint_path"]
        bp_class = entry["blueprint_class"]
        if bp_path not in bp_cache:
            for n in (bp_path, bp_class, f"Default__{bp_class}", "Root",
                      "RelativeLocation", "RelativeRotation", "RootComponent"):
                ensure_fname(name_map, n)

            bp_pkg = find_or_add_import(imports, name_map, bp_path, 0,
                                        "/Script/CoreUObject", "Package")
            bp_cls = find_or_add_import(imports, name_map, bp_class, bp_pkg,
                                        "/Script/Engine", "BlueprintGeneratedClass")
            bp_default = find_or_add_import(imports, name_map,
                                            f"Default__{bp_class}", bp_pkg,
                                            bp_path, bp_class)
            bp_root = find_or_add_import(imports, name_map, "Root", bp_default,
                                         "/Script/Engine", "SceneComponent")
            bp_cache[bp_path] = (bp_cls, bp_default, bp_root)

    # Ensure actor names in NameMap
    ensure_fname(name_map, "ParkingLot_MOD")

    print(f"Injecting {len(bp_entries)} blueprint actors into sub-level ...")

    new_actor_nums = []
    for i, entry in enumerate(bp_entries):
        bp_cls, bp_default, bp_root = bp_cache[entry["blueprint_path"]]
        x = float(entry.get("X", 0))
        y = float(entry.get("Y", 0))
        z = float(entry.get("Z", 0))
        pitch = float(entry.get("Pitch", 0))
        yaw = float(entry.get("Yaw", 0))
        roll = float(entry.get("Roll", 0))

        actor_num = len(exports) + 1
        comp_num = len(exports) + 2

        # Actor (NormalExport)
        actor_props = [
            _obj_prop("RootComponent", comp_num),
        ]
        import struct, base64
        label = f"ParkingLot_{i}"
        label_bytes = label.encode("utf-8") + b"\x00"
        extras_data = struct.pack("<I", 1)
        extras_data += struct.pack("<I", len(label_bytes))
        extras_data += label_bytes
        extras_data += uuid.uuid4().bytes
        extras_data += b"\x00" * 16
        actor_extras = base64.b64encode(extras_data).decode("ascii")

        exports.append(make_normal_export(
            actor_props,
            f"ParkingLot_MOD_{i}", level_num, bp_cls, bp_default,
            cbsd=[comp_num],
            sbcd=[bp_cls, bp_default, bp_root],
            cbcd=[level_num],
            extras=actor_extras,
        ))

        # Root component (NormalExport with location/rotation)
        comp_props = [
            _vector_prop("RelativeLocation", x, y, z),
            _rotator_prop("RelativeRotation", pitch, yaw, roll),
        ]
        exports.append(make_normal_export(
            comp_props,
            "Root", actor_num, scene_class, bp_root,
            object_flags="RF_Transactional, RF_DefaultSubObject",
            is_inherited=True,
            sbcd=[scene_class, bp_root],
            cbcd=[actor_num],
            extras=COMPONENT_EXTRAS,
        ))

        new_actor_nums.append(actor_num)
        depends_map.append([])
        depends_map.append([])

    # Add actors to level
    level_export["Actors"].extend(new_actor_nums)
    level_export.setdefault("CreateBeforeSerializationDependencies", [])
    level_export["CreateBeforeSerializationDependencies"].extend(new_actor_nums)

    # Update bookkeeping
    if asset.get("Generations"):
        asset["Generations"][0]["ExportCount"] = len(exports)
        asset["Generations"][0]["NameCount"] = len(name_map)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(asset, f, indent=2, ensure_ascii=False)

    print(f"Done! {output_path}")
    print(f"  {len(bp_entries)} parking actors | {len(exports)} exports | {len(imports)} imports")


if __name__ == "__main__":
    main()
