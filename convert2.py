#!/usr/bin/env python3
"""
convert2.py - Injects actors into a UAssetAPI JSON (Jeju_World RawExport format).

Supports:
  - MTDealerVehicleSpawnPoint (dealership vehicle spawners)
  - StaticMeshActor (static mesh props/objects)

Usage:
    python convert2.py <input.json> [map_work_changes.json] [output.json]

If map_work_changes.json is not specified, looks for it in the script directory.

Config format (map_work_changes.json):
{
    "dealerships": {
        "group_name": [
            {
                "vehicle_path": "/Game/Cars/Models/Trailer_Cotra/Cotra_20_3L",
                "vehicle_key": "Cotra_20_3L",
                "X": 0, "Y": 0, "Z": 0,
                "Pitch": 0, "Roll": 0, "Yaw": 0
            }
        ]
    },
    "static_meshes": {
        "group_name": [
            {
                "asset_path": "/Game/Models/.../SM_Something",
                "asset_key": "SM_Something",
                "X": 0, "Y": 0, "Z": 0,
                "Pitch": 0, "Roll": 0, "Yaw": 0
            }
        ]
    }
}
"""

import json
import sys
import uuid
import struct
import base64
import os
import shutil


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Asset file paths (for copying missing mesh assets into the mod pak)
# ---------------------------------------------------------------------------
GAME_CONTENT = r"D:\MT\Output\Exports\MotorTown\Content"
COOKED_CONTENT = r"C:\Users\Milea\Documents\Unreal Projects\MTMapAddon\Saved\Cooked\Windows\MTMapAddon\Content"
MOD_CONTENT = r"MapChangeTest_P\MotorTown\Content"


def _copy_mesh_asset(game_path, script_dir):
    """Copy mesh .uasset/.uexp/.ubulk to mod pak if not in game files."""
    if not game_path.startswith("/Game/"):
        return
    rel = game_path[len("/Game/"):]
    game_file = os.path.join(GAME_CONTENT, rel + ".uasset")
    if os.path.exists(game_file):
        return  # already in game, no copy needed
    cooked_file = os.path.join(COOKED_CONTENT, rel + ".uasset")
    if not os.path.exists(cooked_file):
        return
    mod_target = os.path.join(script_dir, MOD_CONTENT, rel)
    os.makedirs(os.path.dirname(mod_target), exist_ok=True)
    copied = []
    for ext in [".uasset", ".uexp", ".ubulk"]:
        src = os.path.join(COOKED_CONTENT, rel + ext)
        dst = mod_target + ext
        try:
            if os.path.exists(src):
                shutil.copy2(src, dst)
                copied.append(ext)
        except Exception:
            pass
    if copied:
        print(f"  Copied {rel} ({', '.join(copied)})")


def ensure_name(name_map, name):
    if name not in name_map:
        name_map.append(name)


def fname_base(name):
    last_us = name.rfind("_")
    if last_us > 0 and name[last_us + 1 :].isdigit():
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
    idx = find_import_index(imports, object_name, outer_index)
    if idx is not None:
        return idx
    ensure_fname(name_map, object_name)
    ensure_fname(name_map, class_package)
    ensure_fname(name_map, class_name)
    return add_import(imports, object_name, outer_index, class_package, class_name)


def make_actor_extras(label):
    """Actor export extras: count + label string + GUID + padding."""
    label_bytes = label.encode("utf-8") + b"\x00"
    data = struct.pack("<I", 1)
    data += struct.pack("<I", len(label_bytes))
    data += label_bytes
    data += uuid.uuid4().bytes
    data += b"\x00" * 16
    return data


def make_raw_export(data_b64, object_name, outer_index, class_index, template_index,
                    object_flags="RF_Transactional", is_inherited=False,
                    sbsd=None, cbsd=None, sbcd=None, cbcd=None):
    return {
        "$type": "UAssetAPI.ExportTypes.RawExport, UAssetAPI",
        "Data": data_b64,
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
        "Extras": "",
    }


# ---------------------------------------------------------------------------
# Dealership binary builders
# ---------------------------------------------------------------------------

DEALER_ACTOR_HEADER = bytes.fromhex("0002020203023903")
DEALER_ROOTSCENE_HEADER = bytes.fromhex("0505")


def build_dealer_actor_data(vehicle_class_ref, scene_comp_ref, label):
    data = bytearray()
    data += DEALER_ACTOR_HEADER
    data += struct.pack("<i", vehicle_class_ref)
    data += struct.pack("<i", vehicle_class_ref)
    data += struct.pack("<i", scene_comp_ref)
    data += struct.pack("<i", scene_comp_ref)
    data += b"\x00\x00\x00\x00"
    data += make_actor_extras(label)
    return base64.b64encode(bytes(data)).decode("ascii")


def build_dealer_rootscene_data(x, y, z, pitch, yaw, roll):
    data = bytearray()
    data += DEALER_ROOTSCENE_HEADER
    data += struct.pack("<ddd", x, y, z)
    data += struct.pack("<ddd", pitch, yaw, roll)
    data += b"\x00" * 8
    return base64.b64encode(bytes(data)).decode("ascii")


# ---------------------------------------------------------------------------
# StaticMeshActor binary builders
# ---------------------------------------------------------------------------

# StaticMeshActor header: props 0,1 (SMC ref, RootComponent)
# Then skip to prop 62,63 (actor label extras area)
SMA_ACTOR_HEADER = bytes.fromhex("00023c03")

# SMC headers (RawExport)
# No scale: [4,5] [42,43] [49,50] [161,162,163]     tail num=3 (96 bytes)
SMC_HEADER = struct.pack('<HHHH', 0x0204, 0x0224, 0x0205, 0x056E)
# With scale: [4,5] [42,43] [49,50] [161,162,163,164] tail num=4 (116 bytes)
# Cloned from working export 57200 (SM_Bld_Trim_Ceiling_01 with scale 2,1,1)
SMC_HEADER_SCALE = struct.pack('<HHHH', 0x0204, 0x0224, 0x0205, 0x076E)


def build_sma_actor_data(comp_ref, label):
    """Build raw binary for a StaticMeshActor export."""
    data = bytearray()
    data += SMA_ACTOR_HEADER
    data += struct.pack("<i", comp_ref)
    data += struct.pack("<i", comp_ref)
    data += b"\x00\x00\x00\x00"
    data += make_actor_extras(label)
    return base64.b64encode(bytes(data)).decode("ascii")


def build_smc_data(mesh_imp_ref, x, y, z, pitch, yaw, roll,
                   sx=1.0, sy=1.0, sz=1.0, cached_draw_dist=100000.0):
    """
    Build raw binary for StaticMeshComponent0 (RawExport).
    No scale: 96 bytes (tail num=3).  With scale: 116 bytes (tail num=4).
    Scale header cloned from existing working export 57200.
    """
    has_scale = not (sx == 1.0 and sy == 1.0 and sz == 1.0)
    data = bytearray()
    data += SMC_HEADER_SCALE if has_scale else SMC_HEADER
    # Props [4,5]
    data += struct.pack("<i", mesh_imp_ref)
    data += struct.pack("<i", 2)                       # Mobility = Movable
    # Props [42,43]
    data += struct.pack("<i", 0)                       # OverrideMaterials (empty)
    data += struct.pack("<i", 0)                       # padding
    data += struct.pack("<f", cached_draw_dist)
    # Props [49,50]
    data += struct.pack("<ddd", x, y, z)
    data += struct.pack("<ddd", pitch, yaw, roll)
    # Tail frag: scale (if present) + zeros + footer
    if has_scale:
        data += struct.pack("<ddd", sx, sy, sz)        # first tail prop = scale
    data += b"\x00" * 12                               # tail zeros
    data += struct.pack("<ii", 1, 0)                   # footer
    return base64.b64encode(bytes(data)).decode("ascii")


# ---------------------------------------------------------------------------
# Path resolvers
# ---------------------------------------------------------------------------


def resolve_vehicle_path(entry):
    """Returns (package_path, class_name, vehicle_key)."""
    if "vehicle_path" not in entry:
        raise ValueError(f"Entry missing 'vehicle_path': {entry}")
    pkg = entry["vehicle_path"]
    veh_key = entry.get("vehicle_key", pkg.rsplit("/", 1)[-1])
    return pkg, f"{veh_key}_C", veh_key


def resolve_mesh_path(entry):
    """
    Returns (package_path, export_name).

    Required:
        "asset_path" - full game package path. Accepts either form:
                         "/Game/Models/.../SM_Foo"
                         "/Game/Models/.../SM_Foo.SM_Foo"  (UE reference format)
        "asset_key"  - (recommended) the export name in that package
                       falls back to last segment of asset_path if omitted
    """
    if "asset_path" not in entry:
        raise ValueError(f"Entry missing 'asset_path': {entry}")
    package_path = entry["asset_path"]
    # Strip "<package>.<object>" suffix if present (UE asset reference format)
    last_slash = package_path.rfind("/")
    dot_pos = package_path.find(".", last_slash)
    if dot_pos != -1:
        package_path = package_path[:dot_pos]
    export_name = entry.get("asset_key", package_path.rsplit("/", 1)[-1])
    return package_path, export_name


# ---------------------------------------------------------------------------
# Gather entries from config
# ---------------------------------------------------------------------------


def gather_list(mods, key):
    """Gather all entries from grouped lists under mods[key]."""
    result = []
    section = mods.get(key, {})
    for group_name, group_items in section.items():
        if isinstance(group_items, list):
            result.extend(group_items)
    return result


# ---------------------------------------------------------------------------
# PersistentLevel binary patcher
# ---------------------------------------------------------------------------


def patch_level_binary(level_export, new_actor_nums):
    """Patch the PersistentLevel binary actor list and CBSD."""
    level_export.setdefault("CreateBeforeSerializationDependencies", [])
    level_export["CreateBeforeSerializationDependencies"].extend(new_actor_nums)

    is_raw = level_export.get("$type") == "UAssetAPI.ExportTypes.RawExport, UAssetAPI"

    if is_raw:
        level_raw = bytearray(base64.b64decode(level_export["Data"]))
        url_marker = struct.pack("<i", 7) + b"unreal\x00"
        url_offset = level_raw.find(url_marker)
        if url_offset == -1:
            print("Warning: Could not locate URL marker. Binary NOT patched.")
            return

        count_offset = None
        for probe in range(url_offset - 4, 3, -4):
            candidate = struct.unpack_from("<i", level_raw, probe)[0]
            if candidate > 0 and probe + 4 + candidate * 4 == url_offset:
                count_offset = probe
                break

        if count_offset is None:
            print("Warning: Could not locate actor count. Binary NOT patched.")
            return

        old_count = struct.unpack_from("<i", level_raw, count_offset)[0]
        new_count = old_count + len(new_actor_nums)
        struct.pack_into("<i", level_raw, count_offset, new_count)

        insert_bytes = b"".join(struct.pack("<i", n) for n in new_actor_nums)
        level_raw[url_offset:url_offset] = insert_bytes

        level_export["Data"] = base64.b64encode(bytes(level_raw)).decode("ascii")
        print(f"  PersistentLevel binary: actor count {old_count} -> {new_count}")
    else:
        level_export["Actors"].extend(new_actor_nums)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    if len(sys.argv) < 2:
        print("Usage: python convert2.py <input.json> [map_work_changes.json] [output.json]")
        sys.exit(1)

    input_path = sys.argv[1]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mods_path = (
        sys.argv[2]
        if len(sys.argv) > 2
        else os.path.join(script_dir, "map_work_changes.json")
    )
    if len(sys.argv) > 3:
        output_path = sys.argv[3]
    else:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}MOD{ext}"

    with open(input_path, "r", encoding="utf-8") as f:
        asset = json.load(f)
    with open(mods_path, "r", encoding="utf-8") as f:
        mods = json.load(f)

    name_map = asset["NameMap"]
    exports = asset["Exports"]
    imports = asset["Imports"]
    depends_map = asset.get("DependsMap")

    # ---- Locate PersistentLevel -------------------------------------------
    level_idx = None
    for i, exp in enumerate(exports):
        if exp.get("ObjectName") == "PersistentLevel":
            level_idx = i
            break
    if level_idx is None:
        print("Error: No PersistentLevel export found.")
        sys.exit(1)

    level_export = exports[level_idx]
    level_num = level_idx + 1
    is_raw = level_export.get("$type") == "UAssetAPI.ExportTypes.RawExport, UAssetAPI"
    print(f"PersistentLevel at export {level_num} ({'RawExport' if is_raw else 'LevelExport'})")

    # ---- Common imports ---------------------------------------------------
    engine_pkg = find_or_add_import(
        imports, name_map, "/Script/Engine", 0, "/Script/CoreUObject", "Package"
    )

    all_new_actor_nums = []

    # ======================================================================
    # DEALERSHIPS
    # ======================================================================
    dealer_spawns = gather_list(mods, "dealerships")
    if dealer_spawns:
        for n in (
            "MTDealerVehicleSpawnPoint", "Default__MTDealerVehicleSpawnPoint",
            "SceneComponent", "RootScene", "RootComponent",
            "VehicleClass", "EditorVisualVehicleClass",
            "RelativeLocation", "RelativeRotation",
            "/Script/MotorTown", "BlueprintGeneratedClass",
            "MTDealerVehicleSpawnPoint_MOD",
        ):
            ensure_fname(name_map, n)

        motortown_pkg = find_or_add_import(
            imports, name_map, "/Script/MotorTown", 0, "/Script/CoreUObject", "Package"
        )
        dealer_class = find_or_add_import(
            imports, name_map, "MTDealerVehicleSpawnPoint", motortown_pkg,
            "/Script/CoreUObject", "Class"
        )
        default_dealer = find_or_add_import(
            imports, name_map, "Default__MTDealerVehicleSpawnPoint", motortown_pkg,
            "/Script/MotorTown", "MTDealerVehicleSpawnPoint"
        )
        scene_class = find_or_add_import(
            imports, name_map, "SceneComponent", engine_pkg,
            "/Script/CoreUObject", "Class"
        )
        rootscene_template = find_or_add_import(
            imports, name_map, "RootScene", default_dealer,
            "/Script/Engine", "SceneComponent"
        )

        # Vehicle import cache
        vehicle_cache = {}
        for entry in dealer_spawns:
            pkg_path, class_name, _ = resolve_vehicle_path(entry)
            if pkg_path not in vehicle_cache:
                ensure_fname(name_map, pkg_path)
                ensure_fname(name_map, class_name)
                veh_pkg = find_or_add_import(imports, name_map, pkg_path, 0,
                                             "/Script/CoreUObject", "Package")
                veh_cls = find_or_add_import(imports, name_map, class_name, veh_pkg,
                                             "/Script/Engine", "BlueprintGeneratedClass")
                vehicle_cache[pkg_path] = veh_cls

        print(f"Injecting {len(dealer_spawns)} dealer spawn points ...")
        for i, entry in enumerate(dealer_spawns):
            pkg_path, class_name, veh_key = resolve_vehicle_path(entry)
            veh_imp = vehicle_cache[pkg_path]
            x, y, z = float(entry.get("X", 0)), float(entry.get("Y", 0)), float(entry.get("Z", 0))
            pitch, yaw, roll = float(entry.get("Pitch", 0)), float(entry.get("Yaw", 0)), float(entry.get("Roll", 0))

            actor_num = len(exports) + 1
            comp_num = len(exports) + 2

            exports.append(make_raw_export(
                build_dealer_actor_data(veh_imp, comp_num, veh_key),
                f"MTDealerVehicleSpawnPoint_MOD_{i}", level_num, dealer_class, default_dealer,
                cbsd=[veh_imp, comp_num],
                sbcd=[dealer_class, default_dealer, rootscene_template],
                cbcd=[level_num],
            ))
            exports.append(make_raw_export(
                build_dealer_rootscene_data(x, y, z, pitch, yaw, roll),
                "RootScene", actor_num, scene_class, rootscene_template,
                object_flags="RF_Transactional, RF_DefaultSubObject",
                is_inherited=True,
                sbcd=[scene_class, rootscene_template],
                cbcd=[actor_num],
            ))
            all_new_actor_nums.append(actor_num)
            if depends_map is not None:
                depends_map.extend([[], []])

    # ======================================================================
    # BLUEPRINT ACTORS (parking etc.) — emit as NormalExport
    # ======================================================================
    # UAssetGUI fromjson with MotorTown718P1 mappings serializes NormalExport
    # entries correctly into unversioned binary, even alongside RawExport.
    # Structure validated by build_parking_blob.py round-trip.
    # Blueprint actors are injected at the WorldPartition cell level by
    # MTBPInjector (see fulltest.bat step [4b/5]). convert2 must not touch them
    # here — NormalExport BP actors in the main Jeju_World.umap crash the engine.
    bp_entries = []
    parking_blob_path = os.path.join(script_dir, "parking_blob.json")
    USE_NORMAL_EXPORT = False
    if bp_entries and USE_NORMAL_EXPORT:
        # Skip the old blob-based RawExport injection; do NormalExport instead
        bp_path = bp_entries[0]["blueprint_path"]
        bp_class = bp_entries[0]["blueprint_class"]

        for n in (bp_path, bp_class, f"Default__{bp_class}", "Root", "Box",
                  "MTInteractable", "MTInteractable_GEN_VARIABLE",
                  "InteractionCube", "InteractionCube_GEN_VARIABLE",
                  "BoxComponent", "MTInteractableComponent", "StaticMeshComponent",
                  "SceneComponent", "RelativeLocation", "RelativeRotation",
                  "RootComponent", "AttachParent", "ParkingLot_MOD",
                  "/Script/MotorTown"):
            ensure_fname(name_map, n)

        bp_pkg_imp = find_or_add_import(imports, name_map, bp_path, 0,
                                        "/Script/CoreUObject", "Package")
        bp_cls_imp = find_or_add_import(imports, name_map, bp_class, bp_pkg_imp,
                                        "/Script/Engine", "BlueprintGeneratedClass")
        bp_default_imp = find_or_add_import(imports, name_map, f"Default__{bp_class}",
                                            bp_pkg_imp, bp_path, bp_class)
        bp_root_imp = find_or_add_import(imports, name_map, "Root", bp_default_imp,
                                         "/Script/Engine", "SceneComponent")
        bp_box_imp = find_or_add_import(imports, name_map, "Box", bp_default_imp,
                                        "/Script/Engine", "BoxComponent")
        bp_mt_imp = find_or_add_import(imports, name_map, "MTInteractable_GEN_VARIABLE",
                                       bp_default_imp, "/Script/MotorTown",
                                       "MTInteractableComponent")
        bp_cube_imp = find_or_add_import(imports, name_map, "InteractionCube_GEN_VARIABLE",
                                         bp_default_imp, "/Script/Engine",
                                         "StaticMeshComponent")
        scene_class_imp = find_or_add_import(imports, name_map, "SceneComponent", engine_pkg,
                                             "/Script/CoreUObject", "Class")
        box_class_imp = find_or_add_import(imports, name_map, "BoxComponent", engine_pkg,
                                           "/Script/CoreUObject", "Class")
        motortown_pkg_imp = find_or_add_import(imports, name_map, "/Script/MotorTown", 0,
                                               "/Script/CoreUObject", "Package")
        mt_class_imp = find_or_add_import(imports, name_map, "MTInteractableComponent",
                                          motortown_pkg_imp, "/Script/CoreUObject", "Class")
        smc_class_imp = find_or_add_import(imports, name_map, "StaticMeshComponent", engine_pkg,
                                           "/Script/CoreUObject", "Class")

        component_extras = base64.b64encode(struct.pack("<IIII", 0, 0, 1, 0)).decode("ascii")

        def make_actor_extras_b64(label):
            lb = label.encode("utf-8") + b"\x00"
            d = struct.pack("<I", 1) + struct.pack("<I", len(lb)) + lb
            d += uuid.uuid4().bytes + b"\x00" * 16
            return base64.b64encode(d).decode("ascii")

        def _obj_p(name, value):
            return {
                "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                "Name": name, "ArrayIndex": 0, "IsZero": False,
                "PropertyTagFlags": "None", "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension", "Value": value,
            }

        def _vec_p(name, x, y, z):
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

        def _rot_p(name, p, y, r):
            fmt = lambda v: "+0" if v == 0.0 else v
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
                              "Pitch": fmt(p), "Yaw": fmt(y), "Roll": fmt(r)},
                }],
            }

        def make_ne(data_props, name, outer, ci, ti, flags, is_inh,
                    sbsd, cbsd, sbcd, cbcd, extras):
            return {
                "$type": "UAssetAPI.ExportTypes.NormalExport, UAssetAPI",
                "Data": data_props, "ObjectGuid": None,
                "SerializationControl": "NoExtension", "Operation": "None",
                "HasLeadingFourNullBytes": False,
                "ObjectName": name, "OuterIndex": outer, "ClassIndex": ci,
                "SuperIndex": 0, "TemplateIndex": ti, "ObjectFlags": flags,
                "SerialSize": 0, "SerialOffset": 0,
                "ScriptSerializationStartOffset": 0, "ScriptSerializationEndOffset": 0,
                "bForcedExport": False, "bNotForClient": False, "bNotForServer": False,
                "PackageGuid": "{00000000-0000-0000-0000-000000000000}",
                "IsInheritedInstance": is_inh, "PackageFlags": "PKG_None",
                "bNotAlwaysLoadedForEditorGame": True, "bIsAsset": False,
                "GeneratePublicHash": False,
                "SerializationBeforeSerializationDependencies": sbsd or [],
                "CreateBeforeSerializationDependencies": cbsd or [],
                "SerializationBeforeCreateDependencies": sbcd or [],
                "CreateBeforeCreateDependencies": cbcd or [],
                "Extras": extras,
            }

        print(f"Injecting {len(bp_entries)} parking actors (NormalExport) ...")
        for i, entry in enumerate(bp_entries):
            x = float(entry.get("X", 0))
            y = float(entry.get("Y", 0))
            z = float(entry.get("Z", 0))
            pitch = float(entry.get("Pitch", 0))
            yaw = float(entry.get("Yaw", 0))
            roll = float(entry.get("Roll", 0))

            actor_num = len(exports) + 1
            root_num = actor_num + 1
            box_num = actor_num + 2
            mt_num = actor_num + 3
            cube_num = actor_num + 4

            # Actor
            exports.append(make_ne(
                [_obj_p("BoxComponent", box_num),
                 _obj_p("MTInteractable", mt_num),
                 _obj_p("InteractionCube", cube_num),
                 _obj_p("RootComponent", root_num)],
                f"ParkingLot_MOD_{i}", level_num, bp_cls_imp, bp_default_imp,
                "RF_Transactional", False, [],
                [root_num, box_num, mt_num, cube_num],
                [bp_cls_imp, bp_default_imp, bp_root_imp, bp_box_imp, bp_mt_imp, bp_cube_imp],
                [level_num], make_actor_extras_b64(f"ParkingLot_{i}"),
            ))
            # Root
            exports.append(make_ne(
                [_vec_p("RelativeLocation", x, y, z),
                 _rot_p("RelativeRotation", pitch, yaw, roll)],
                "Root", actor_num, scene_class_imp, bp_root_imp,
                "RF_Transactional, RF_DefaultSubObject", True, [],
                [], [scene_class_imp, bp_root_imp], [actor_num], component_extras,
            ))
            # Box
            exports.append(make_ne(
                [_obj_p("AttachParent", root_num)],
                "Box", actor_num, box_class_imp, bp_box_imp,
                "RF_Transactional, RF_DefaultSubObject", True, [],
                [root_num], [box_class_imp, bp_box_imp], [actor_num], component_extras,
            ))
            # MTInteractable
            exports.append(make_ne(
                [_obj_p("AttachParent", root_num)],
                "MTInteractable", actor_num, mt_class_imp, bp_mt_imp,
                "RF_Transactional, RF_DefaultSubObject", True, [],
                [root_num], [mt_class_imp, bp_mt_imp], [actor_num], component_extras,
            ))
            # InteractionCube
            exports.append(make_ne(
                [_obj_p("AttachParent", root_num)],
                "InteractionCube", actor_num, smc_class_imp, bp_cube_imp,
                "RF_Transactional, RF_DefaultSubObject", True, [],
                [root_num], [smc_class_imp, bp_cube_imp], [actor_num], component_extras,
            ))
            all_new_actor_nums.append(actor_num)
            if depends_map is not None:
                depends_map.extend([[], [], [], [], []])
    elif bp_entries and os.path.exists(parking_blob_path):
        with open(parking_blob_path, "r", encoding="utf-8") as f:
            blob = json.load(f)

        # Resolve imports: the blob references imports by index in its OWN imports array.
        # We need to create/find matching imports in Jeju_World and build an index map.
        blob_imports = blob["imports"]
        blob_to_jeju = {}  # blob import index (negative) -> jeju import index (negative)

        def resolve_blob_import(blob_idx):
            """Recursively resolve a blob import to a Jeju import."""
            if blob_idx >= 0:
                return blob_idx
            if blob_idx in blob_to_jeju:
                return blob_to_jeju[blob_idx]
            imp = blob_imports[abs(blob_idx) - 1]
            outer_jeju = resolve_blob_import(imp["OuterIndex"]) if imp["OuterIndex"] < 0 else 0
            ensure_fname(name_map, imp["ObjectName"])
            ensure_fname(name_map, imp["ClassPackage"])
            ensure_fname(name_map, imp["ClassName"])
            jeju_idx = find_or_add_import(
                imports, name_map,
                imp["ObjectName"], outer_jeju,
                imp["ClassPackage"], imp["ClassName"]
            )
            blob_to_jeju[blob_idx] = jeju_idx
            return jeju_idx

        for n in ("ParkingLot_MOD", "Root", "Box", "MTInteractable", "InteractionCube",
                  "RelativeLocation", "RelativeRotation", "RootComponent",
                  "BoxComponent", "AttachParent"):
            ensure_fname(name_map, n)

        # Resolve blob imports and cache component info
        def resolve_component(c):
            return {
                "data": base64.b64decode(c["data_b64"]),
                "class_index": resolve_blob_import(c["class_index"]),
                "template_index": resolve_blob_import(c["template_index"]),
                "object_flags": c["object_flags"],
                "is_inherited": c["is_inherited"],
                "sbcd": [resolve_blob_import(i) for i in c["sbcd"]],
            }

        actor_info = resolve_component(blob["actor"])
        root_info = resolve_component(blob["root"])
        box_info = resolve_component(blob["box"])
        mt_info = resolve_component(blob["mt_interactable"])
        cube_info = resolve_component(blob["interaction_cube"])

        loc_off = blob["root"]["loc_offset"]
        rot_off = blob["root"]["rot_offset"]

        print(f"Injecting {len(bp_entries)} parking actors (via blob, full chain) ...")
        for i, entry in enumerate(bp_entries):
            x = float(entry.get("X", 0))
            y = float(entry.get("Y", 0))
            z = float(entry.get("Z", 0))
            pitch = float(entry.get("Pitch", 0))
            yaw = float(entry.get("Yaw", 0))
            roll = float(entry.get("Roll", 0))

            actor_num = len(exports) + 1
            root_num = actor_num + 1
            box_num = actor_num + 2
            mt_num = actor_num + 3
            cube_num = actor_num + 4

            # ----- Actor: patch component refs in Data and fresh GUID -----
            # Actor props (from build_parking_blob): Box, MTInteractable, InteractionCube, RootComponent
            # Those are 4 int32 refs starting at offset 0 in actor binary
            a_data = bytearray(actor_info["data"])
            struct.pack_into("<i", a_data, 0, box_num)
            struct.pack_into("<i", a_data, 4, mt_num)
            struct.pack_into("<i", a_data, 8, cube_num)
            struct.pack_into("<i", a_data, 12, root_num)
            # Fresh GUID in extras
            # Extras layout starts at offset 16: count(4) + strlen(4) + label + guid(16) + pad
            strlen = struct.unpack_from("<I", a_data, 24)[0]
            guid_offset = 28 + strlen
            if guid_offset + 16 <= len(a_data):
                a_data[guid_offset:guid_offset + 16] = uuid.uuid4().bytes

            exports.append(make_raw_export(
                base64.b64encode(bytes(a_data)).decode("ascii"),
                f"ParkingLot_MOD_{i}", level_num,
                actor_info["class_index"], actor_info["template_index"],
                object_flags=actor_info["object_flags"],
                cbsd=[root_num, box_num, mt_num, cube_num],
                sbcd=actor_info["sbcd"],
                cbcd=[level_num],
            ))

            # ----- Root: patch location/rotation -----
            r_data = bytearray(root_info["data"])
            struct.pack_into("<ddd", r_data, loc_off, x, y, z)
            struct.pack_into("<ddd", r_data, rot_off, pitch, yaw, roll)
            exports.append(make_raw_export(
                base64.b64encode(bytes(r_data)).decode("ascii"),
                "Root", actor_num,
                root_info["class_index"], root_info["template_index"],
                object_flags=root_info["object_flags"],
                is_inherited=root_info["is_inherited"],
                sbcd=root_info["sbcd"],
                cbcd=[actor_num],
            ))

            # ----- Box: patch AttachParent to Root -----
            # Blob had Box with AttachParent pointing to blob-root export num.
            # We need to patch it to our new root_num. The first int32 in Box should be AttachParent.
            b_data = bytearray(box_info["data"])
            struct.pack_into("<i", b_data, 0, root_num)
            exports.append(make_raw_export(
                base64.b64encode(bytes(b_data)).decode("ascii"),
                "Box", actor_num,
                box_info["class_index"], box_info["template_index"],
                object_flags=box_info["object_flags"],
                is_inherited=box_info["is_inherited"],
                cbsd=[root_num],
                sbcd=box_info["sbcd"],
                cbcd=[actor_num],
            ))

            # ----- MTInteractable -----
            m_data = bytearray(mt_info["data"])
            struct.pack_into("<i", m_data, 0, root_num)
            exports.append(make_raw_export(
                base64.b64encode(bytes(m_data)).decode("ascii"),
                "MTInteractable", actor_num,
                mt_info["class_index"], mt_info["template_index"],
                object_flags=mt_info["object_flags"],
                is_inherited=mt_info["is_inherited"],
                cbsd=[root_num],
                sbcd=mt_info["sbcd"],
                cbcd=[actor_num],
            ))

            # ----- InteractionCube -----
            c_data = bytearray(cube_info["data"])
            struct.pack_into("<i", c_data, 0, root_num)
            exports.append(make_raw_export(
                base64.b64encode(bytes(c_data)).decode("ascii"),
                "InteractionCube", actor_num,
                cube_info["class_index"], cube_info["template_index"],
                object_flags=cube_info["object_flags"],
                is_inherited=cube_info["is_inherited"],
                cbsd=[root_num],
                sbcd=cube_info["sbcd"],
                cbcd=[actor_num],
            ))

            all_new_actor_nums.append(actor_num)
            if depends_map is not None:
                depends_map.extend([[], [], [], [], []])

    # ======================================================================
    # STATIC MESHES
    # ======================================================================
    mesh_entries = gather_list(mods, "static_meshes")
    if mesh_entries:
        for n in (
            "StaticMeshActor", "Default__StaticMeshActor",
            "StaticMeshComponent", "StaticMeshComponent0",
            "StaticMesh", "RootComponent",
            "RelativeLocation", "RelativeRotation", "RelativeScale3D",
            "StaticMeshActor_MOD",
        ):
            ensure_fname(name_map, n)

        sma_class = find_or_add_import(
            imports, name_map, "StaticMeshActor", engine_pkg,
            "/Script/CoreUObject", "Class"
        )
        default_sma = find_or_add_import(
            imports, name_map, "Default__StaticMeshActor", engine_pkg,
            "/Script/Engine", "StaticMeshActor"
        )
        smc_class = find_or_add_import(
            imports, name_map, "StaticMeshComponent", engine_pkg,
            "/Script/CoreUObject", "Class"
        )
        smc0_template = find_or_add_import(
            imports, name_map, "StaticMeshComponent0", default_sma,
            "/Script/Engine", "StaticMeshComponent"
        )

        # Mesh import cache + copy missing assets to mod pak
        mesh_cache = {}
        for entry in mesh_entries:
            pkg_path, export_name = resolve_mesh_path(entry)
            if pkg_path not in mesh_cache:
                ensure_fname(name_map, pkg_path)
                ensure_fname(name_map, export_name)
                mesh_pkg = find_or_add_import(imports, name_map, pkg_path, 0,
                                              "/Script/CoreUObject", "Package")
                mesh_imp = find_or_add_import(imports, name_map, export_name, mesh_pkg,
                                              "/Script/Engine", "StaticMesh")
                mesh_cache[pkg_path] = mesh_imp
                # Copy asset files to mod if not in game
                _copy_mesh_asset(pkg_path, script_dir)

        print(f"Injecting {len(mesh_entries)} static mesh actors ...")
        for i, entry in enumerate(mesh_entries):
            pkg_path, export_name = resolve_mesh_path(entry)
            mesh_imp = mesh_cache[pkg_path]
            x, y, z = float(entry.get("X", 0)), float(entry.get("Y", 0)), float(entry.get("Z", 0))
            pitch, yaw, roll = float(entry.get("Pitch", 0)), float(entry.get("Yaw", 0)), float(entry.get("Roll", 0))
            sx = float(entry.get("ScaleX", 1.0))
            sy = float(entry.get("ScaleY", 1.0))
            sz = float(entry.get("ScaleZ", 1.0))

            actor_num = len(exports) + 1
            comp_num = len(exports) + 2

            # Actor (RawExport)
            exports.append(make_raw_export(
                build_sma_actor_data(comp_num, export_name),
                f"StaticMeshActor_MOD_{i}", level_num, sma_class, default_sma,
                cbsd=[comp_num],
                sbcd=[sma_class, default_sma, smc0_template],
                cbcd=[level_num],
            ))
            # Component (RawExport)
            exports.append(make_raw_export(
                build_smc_data(mesh_imp, x, y, z, pitch, yaw, roll, sx, sy, sz),
                "StaticMeshComponent0", actor_num, smc_class, smc0_template,
                object_flags="RF_Transactional, RF_DefaultSubObject",
                is_inherited=True,
                cbsd=[mesh_imp],
                sbcd=[smc_class, smc0_template],
                cbcd=[actor_num],
            ))
            all_new_actor_nums.append(actor_num)
            if depends_map is not None:
                depends_map.extend([[], []])

    # ---- Register all new actors in PersistentLevel -----------------------
    if not all_new_actor_nums:
        print("Nothing to inject.")
        sys.exit(0)

    patch_level_binary(level_export, all_new_actor_nums)

    # ---- Bookkeeping ------------------------------------------------------
    if asset.get("Generations"):
        asset["Generations"][0]["ExportCount"] = len(exports)
        asset["Generations"][0]["NameCount"] = len(name_map)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(asset, f, indent=2, ensure_ascii=False)

    n_dealers = len(dealer_spawns) if dealer_spawns else 0
    n_meshes = len(mesh_entries) if mesh_entries else 0
    print(f"Done!  {output_path}")
    print(f"  {n_dealers} dealers + {n_meshes} meshes  |  {len(exports)} exports  |  {len(imports)} imports  |  {len(name_map)} names")


if __name__ == "__main__":
    main()
