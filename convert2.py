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
    # BLUEPRINT ACTORS (parking lots, interactions, etc.)
    # ======================================================================
    bp_entries = gather_list(mods, "blueprint_actors")
    if bp_entries:
        for n in ("SceneComponent", "RootComponent", "Root",
                  "RelativeLocation", "RelativeRotation", "BlueprintActor_MOD"):
            ensure_fname(name_map, n)

        bp_scene_class = find_or_add_import(
            imports, name_map, "SceneComponent", engine_pkg,
            "/Script/CoreUObject", "Class"
        )

        bp_cache = {}
        for entry in bp_entries:
            bp_path = entry["blueprint_path"]
            bp_class = entry["blueprint_class"]
            root_name = entry.get("root_name", "Root")
            if bp_path not in bp_cache:
                ensure_fname(name_map, bp_path)
                ensure_fname(name_map, bp_class)
                ensure_fname(name_map, f"Default__{bp_class}")
                ensure_fname(name_map, root_name)
                bp_pkg = find_or_add_import(imports, name_map, bp_path, 0,
                                            "/Script/CoreUObject", "Package")
                bp_cls = find_or_add_import(imports, name_map, bp_class, bp_pkg,
                                            "/Script/Engine", "BlueprintGeneratedClass")
                bp_default = find_or_add_import(imports, name_map,
                                                f"Default__{bp_class}", bp_pkg,
                                                bp_path, bp_class)
                bp_root = find_or_add_import(imports, name_map, root_name, bp_default,
                                             "/Script/Engine", "SceneComponent")
                bp_cache[bp_path] = (bp_cls, bp_default, bp_root, root_name)

        print(f"Injecting {len(bp_entries)} blueprint actors ...")
        for i, entry in enumerate(bp_entries):
            bp_cls, bp_default, bp_root, root_name = bp_cache[entry["blueprint_path"]]
            x, y, z = float(entry.get("X", 0)), float(entry.get("Y", 0)), float(entry.get("Z", 0))
            pitch, yaw, roll = float(entry.get("Pitch", 0)), float(entry.get("Yaw", 0)), float(entry.get("Roll", 0))

            actor_num = len(exports) + 1
            comp_num = len(exports) + 2

            # Actor — no class-specific properties, just extras
            actor_data = bytearray()
            actor_data += make_actor_extras(f"BlueprintActor_{i}")

            exports.append(make_raw_export(
                base64.b64encode(bytes(actor_data)).decode("ascii"),
                f"BlueprintActor_MOD_{i}", level_num, bp_cls, bp_default,
                cbsd=[comp_num],
                sbcd=[bp_cls, bp_default, bp_root],
                cbcd=[level_num],
            ))
            # Root component
            comp_data = bytearray()
            comp_data += DEALER_ROOTSCENE_HEADER
            comp_data += struct.pack("<ddd", x, y, z)
            comp_data += struct.pack("<ddd", pitch, yaw, roll)
            comp_data += b"\x00" * 8

            exports.append(make_raw_export(
                base64.b64encode(bytes(comp_data)).decode("ascii"),
                root_name, actor_num, bp_scene_class, bp_root,
                object_flags="RF_Transactional, RF_DefaultSubObject",
                is_inherited=True,
                sbcd=[bp_scene_class, bp_root],
                cbcd=[actor_num],
            ))
            all_new_actor_nums.append(actor_num)
            if depends_map is not None:
                depends_map.extend([[], []])

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
