#!/usr/bin/env python3
"""
conver.py - Injects mesh instances from map_modifications.json into a UAssetAPI JSON file.

Usage:
    python conver.py <input.json> [map_modifications.json] [output.json]

If map_modifications.json is not specified, looks for it in the same directory as the script.
If output.json is not specified, generates <input>MOD.json.

Map modification entries support optional scaleX, scaleY, scaleZ fields (default 1.0):
    {
        "path": "/Game/path/Mesh.Mesh",
        "X": 0, "Y": 0, "Z": 0,
        "Pitch": 0, "Roll": 0, "Yaw": 0,
        "scaleX": 1.0, "scaleY": 1.0, "scaleZ": 1.0
    }
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


def parse_mesh_path(path):
    """
    Parse '/Game/path/Mesh.ExportName' -> (package_path, export_name).
    e.g. '/Game/Town/SM_Bld.SM_Bld' -> ('/Game/Town/SM_Bld', 'SM_Bld')
    """
    parts = path.rsplit(".", 1)
    package_path = parts[0]
    export_name = parts[1] if len(parts) > 1 else package_path.rsplit("/", 1)[-1]
    return package_path, export_name


def ensure_name(name_map, name):
    """Add name to NameMap if not already present."""
    if name not in name_map:
        name_map.append(name)


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


def fname_base(name):
    """
    Return the FName base (without trailing _NUMBER suffix).
    UAssetAPI splits 'Foo_123' into base='Foo' + Number=123.
    If the part after the last '_' is NOT purely digits, the whole string is the base.
    """
    last_us = name.rfind("_")
    if last_us > 0 and name[last_us + 1 :].isdigit():
        return name[:last_us]
    return name


def ensure_fname(name_map, name):
    """Add BOTH the full name AND its FName base to NameMap.
    UAssetAPI first tries the full string; if not found it splits off
    a trailing _NUMBER.  Adding both covers either lookup strategy."""
    ensure_name(name_map, name)
    base = fname_base(name)
    if base != name:
        ensure_name(name_map, base)


def find_or_add_import(
    imports, name_map, object_name, outer_index, class_package, class_name
):
    """Find existing import or create a new one. Returns negative 1-based index."""
    idx = find_import_index(imports, object_name, outer_index)
    if idx is not None:
        return idx
    # Ensure ALL FName fields used by this import are in the NameMap
    ensure_fname(name_map, object_name)
    ensure_fname(name_map, class_package)
    ensure_fname(name_map, class_name)
    return add_import(imports, object_name, outer_index, class_package, class_name)


# ---------------------------------------------------------------------------
# Extras generators  (binary blobs serialized by UAssetAPI as base64)
# ---------------------------------------------------------------------------


def make_actor_extras(label):
    """Actor export Extras: count + label string + GUID + padding."""
    label_bytes = label.encode("utf-8") + b"\x00"
    data = struct.pack("<I", 1)  # count
    data += struct.pack("<I", len(label_bytes))  # string length (incl. null)
    data += label_bytes  # actor label
    data += uuid.uuid4().bytes  # 16-byte random GUID
    data += b"\x00" * 16  # trailing padding
    return base64.b64encode(data).decode("ascii")


# Constant component Extras taken from Example.json
COMPONENT_EXTRAS = base64.b64encode(struct.pack("<IIII", 0, 0, 1, 0)).decode("ascii")


# ---------------------------------------------------------------------------
# UAssetAPI property builders
# ---------------------------------------------------------------------------


def _fmt_rot(v):
    """Rotation zero -> string '+0'; non-zero -> float."""
    return "+0" if v == 0.0 else v


def make_object_prop(name, value):
    return {
        "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
        "Name": name,
        "ArrayIndex": 0,
        "IsZero": False,
        "PropertyTagFlags": "None",
        "PropertyTypeName": None,
        "PropertyTagExtensions": "NoExtension",
        "Value": value,
    }


def make_location_prop(x, y, z):
    return {
        "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
        "StructType": "Vector",
        "SerializeNone": True,
        "StructGUID": "{00000000-0000-0000-0000-000000000000}",
        "SerializationControl": "NoExtension",
        "Operation": "None",
        "Name": "RelativeLocation",
        "ArrayIndex": 0,
        "IsZero": False,
        "PropertyTagFlags": "None",
        "PropertyTypeName": None,
        "PropertyTagExtensions": "NoExtension",
        "Value": [
            {
                "$type": "UAssetAPI.PropertyTypes.Structs.VectorPropertyData, UAssetAPI",
                "Name": "RelativeLocation",
                "ArrayIndex": 0,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": {
                    "$type": "UAssetAPI.UnrealTypes.FVector, UAssetAPI",
                    "X": x,
                    "Y": y,
                    "Z": z,
                },
            }
        ],
    }


def make_rotation_prop(pitch, yaw, roll):
    return {
        "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
        "StructType": "Rotator",
        "SerializeNone": True,
        "StructGUID": "{00000000-0000-0000-0000-000000000000}",
        "SerializationControl": "NoExtension",
        "Operation": "None",
        "Name": "RelativeRotation",
        "ArrayIndex": 0,
        "IsZero": False,
        "PropertyTagFlags": "None",
        "PropertyTypeName": None,
        "PropertyTagExtensions": "NoExtension",
        "Value": [
            {
                "$type": "UAssetAPI.PropertyTypes.Structs.RotatorPropertyData, UAssetAPI",
                "Name": "RelativeRotation",
                "ArrayIndex": 0,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": {
                    "$type": "UAssetAPI.UnrealTypes.FRotator, UAssetAPI",
                    "Pitch": _fmt_rot(pitch),
                    "Yaw": _fmt_rot(yaw),
                    "Roll": _fmt_rot(roll),
                },
            }
        ],
    }


def make_scale_prop(sx, sy, sz):
    return {
        "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
        "StructType": "Vector",
        "SerializeNone": True,
        "StructGUID": "{00000000-0000-0000-0000-000000000000}",
        "SerializationControl": "NoExtension",
        "Operation": "None",
        "Name": "RelativeScale3D",
        "ArrayIndex": 0,
        "IsZero": False,
        "PropertyTagFlags": "None",
        "PropertyTypeName": None,
        "PropertyTagExtensions": "NoExtension",
        "Value": [
            {
                "$type": "UAssetAPI.PropertyTypes.Structs.VectorPropertyData, UAssetAPI",
                "Name": "RelativeScale3D",
                "ArrayIndex": 0,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTypeName": None,
                "PropertyTagExtensions": "NoExtension",
                "Value": {
                    "$type": "UAssetAPI.UnrealTypes.FVector, UAssetAPI",
                    "X": sx,
                    "Y": sy,
                    "Z": sz,
                },
            }
        ],
    }


# ---------------------------------------------------------------------------
# Main conversion
# ---------------------------------------------------------------------------


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: python conver.py <input.json> [map_modifications.json] [output.json]"
        )
        print(
            "\nInjects meshes from map_modifications.json into a UAssetAPI JSON file."
        )
        sys.exit(1)

    input_path = sys.argv[1]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    map_mods_path = (
        sys.argv[2]
        if len(sys.argv) > 2
        else os.path.join(script_dir, "map_modifications.json")
    )

    if len(sys.argv) > 3:
        output_path = sys.argv[3]
    else:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}MOD{ext}"

    # ---- Load files -------------------------------------------------------
    with open(input_path, "r", encoding="utf-8") as f:
        asset = json.load(f)
    with open(map_mods_path, "r", encoding="utf-8") as f:
        map_mods = json.load(f)

    name_map = asset["NameMap"]
    exports = asset["Exports"]
    imports = asset["Imports"]
    depends_map = asset.get("DependsMap")

    # ---- Locate the LevelExport (PersistentLevel) -------------------------
    level_idx = None
    for i, exp in enumerate(exports):
        if exp.get("$type") == "UAssetAPI.ExportTypes.LevelExport, UAssetAPI":
            level_idx = i
            break
    if level_idx is None:
        print("Error: No LevelExport (PersistentLevel) found in input JSON.")
        sys.exit(1)

    level_export = exports[level_idx]
    level_num = level_idx + 1  # 1-based export number

    # ---- Ensure common names are present ----------------------------------
    # These are all FNames used in imports, exports, and properties.
    # ensure_fname handles the base/number split for names ending in digits.
    for n in (
        "StaticMesh",
        "StaticMeshActor",
        "StaticMeshComponent",
        "StaticMeshComponent0",
        "/Script/Engine",
        "/Script/CoreUObject",
        "Class",
        "Package",
        "Default__StaticMeshActor",
        "RelativeLocation",
        "RelativeRotation",
        "RelativeScale3D",
        "RootComponent",
        "StaticMeshComponent0",
    ):
        ensure_fname(name_map, n)

    # ---- Find / create shared class & template imports --------------------
    engine_pkg = find_or_add_import(
        imports, name_map, "/Script/Engine", 0, "/Script/CoreUObject", "Package"
    )

    sma_class = find_or_add_import(
        imports, name_map, "StaticMeshActor", engine_pkg, "/Script/CoreUObject", "Class"
    )

    smc_class = find_or_add_import(
        imports,
        name_map,
        "StaticMeshComponent",
        engine_pkg,
        "/Script/CoreUObject",
        "Class",
    )

    default_sma = find_or_add_import(
        imports,
        name_map,
        "Default__StaticMeshActor",
        engine_pkg,
        "/Script/Engine",
        "StaticMeshActor",
    )

    smc0_template = find_or_add_import(
        imports,
        name_map,
        "StaticMeshComponent0",
        default_sma,
        "/Script/Engine",
        "StaticMeshComponent",
    )

    # ---- Gather all mesh entries from every group -------------------------
    all_meshes = []
    for group_name, group_items in map_mods.get("assets", {}).items():
        for item in group_items:
            all_meshes.append(item)

    if not all_meshes:
        print("No mesh entries found in map_modifications. Nothing to inject.")
        sys.exit(0)

    print(f"Injecting {len(all_meshes)} mesh instances …")

    # ---- Build import cache for unique mesh types -------------------------
    mesh_import_cache = {}  # package_path -> negative import index

    for entry in all_meshes:
        pkg_path, exp_name = parse_mesh_path(entry["path"])
        if pkg_path not in mesh_import_cache:
            pkg_imp = find_or_add_import(
                imports, name_map, pkg_path, 0, "/Script/CoreUObject", "Package"
            )
            mesh_imp = find_or_add_import(
                imports, name_map, exp_name, pkg_imp, "/Script/Engine", "StaticMesh"
            )
            mesh_import_cache[pkg_path] = mesh_imp

    # ---- Create export pairs for every mesh instance ----------------------
    new_actor_nums = []

    for i, entry in enumerate(all_meshes):
        pkg_path, exp_name = parse_mesh_path(entry["path"])
        mesh_imp = mesh_import_cache[pkg_path]

        # Read transform (with scale defaulting to 1)
        x = float(entry.get("X", 0))
        y = float(entry.get("Y", 0))
        z = float(entry.get("Z", 0))
        pitch = float(entry.get("Pitch", 0))
        yaw = float(entry.get("Yaw", 0))
        roll = float(entry.get("Roll", 0))
        sx = float(entry.get("scaleX", entry.get("ScaleX", 1.0)))
        sy = float(entry.get("scaleY", entry.get("ScaleY", 1.0)))
        sz = float(entry.get("scaleZ", entry.get("ScaleZ", 1.0)))

        # Derive a short label (strip _C Blueprint suffix if present)
        short_name = exp_name[:-2] if exp_name.endswith("_C") else exp_name
        # Actor ObjectName = base_Number.  UAssetAPI splits trailing _N
        # so we add the BASE to NameMap, and use _N as the FName Number.
        actor_base = f"{short_name}_MOD"
        ensure_name(name_map, actor_base)
        actor_name = f"{actor_base}_{i}"

        # 1-based export numbers for the new pair
        actor_num = len(exports) + 1
        comp_num = len(exports) + 2

        # ---- Actor export (StaticMeshActor) -------------------------------
        actor_export = {
            "$type": "UAssetAPI.ExportTypes.NormalExport, UAssetAPI",
            "Data": [
                make_object_prop("StaticMeshComponent", comp_num),
                make_object_prop("RootComponent", comp_num),
            ],
            "ObjectGuid": None,
            "SerializationControl": "NoExtension",
            "Operation": "None",
            "HasLeadingFourNullBytes": False,
            "ObjectName": actor_name,
            "OuterIndex": level_num,
            "ClassIndex": sma_class,
            "SuperIndex": 0,
            "TemplateIndex": default_sma,
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
            "CreateBeforeSerializationDependencies": [comp_num],
            "SerializationBeforeCreateDependencies": [
                sma_class,
                default_sma,
                smc0_template,
            ],
            "CreateBeforeCreateDependencies": [level_num],
            "Extras": make_actor_extras(short_name),
        }

        # ---- Component export (StaticMeshComponent0) ----------------------
        comp_export = {
            "$type": "UAssetAPI.ExportTypes.NormalExport, UAssetAPI",
            "Data": [
                make_object_prop("StaticMesh", mesh_imp),
                make_location_prop(x, y, z),
                make_rotation_prop(pitch, yaw, roll),
                make_scale_prop(sx, sy, sz),
            ],
            "ObjectGuid": None,
            "SerializationControl": "NoExtension",
            "Operation": "None",
            "HasLeadingFourNullBytes": False,
            "ObjectName": "StaticMeshComponent0",
            "OuterIndex": actor_num,
            "ClassIndex": smc_class,
            "SuperIndex": 0,
            "TemplateIndex": smc0_template,
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
            "CreateBeforeSerializationDependencies": [mesh_imp],
            "SerializationBeforeCreateDependencies": [smc_class, smc0_template],
            "CreateBeforeCreateDependencies": [actor_num],
            "Extras": COMPONENT_EXTRAS,
        }

        exports.append(actor_export)
        exports.append(comp_export)
        new_actor_nums.append(actor_num)

        # Extend DependsMap (one empty list per new export)
        if depends_map is not None:
            depends_map.append([])
            depends_map.append([])

    # ---- Patch the LevelExport --------------------------------------------
    level_export["Actors"].extend(new_actor_nums)
    level_export.setdefault("CreateBeforeSerializationDependencies", [])
    level_export["CreateBeforeSerializationDependencies"].extend(new_actor_nums)

    # ---- Update Generations bookkeeping -----------------------------------
    if asset.get("Generations"):
        asset["Generations"][0]["ExportCount"] = len(exports)
        asset["Generations"][0]["NameCount"] = len(name_map)

    # ---- Write output -----------------------------------------------------
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(asset, f, indent=2, ensure_ascii=False)

    print(f"Done!  {output_path}")
    print(
        f"  {len(all_meshes)} instances  |  "
        f"{len(mesh_import_cache)} unique meshes  |  "
        f"{len(exports)} exports  |  "
        f"{len(imports)} imports  |  "
        f"{len(name_map)} names"
    )


if __name__ == "__main__":
    main()
