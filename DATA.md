# Motor Town Modding Knowledge Base

Everything learned about modding Motor Town (UE5.5) via UAssetAPI JSON manipulation.

---

## Table of Contents

- [Toolchain](#toolchain)
- [Map Structure Overview](#map-structure-overview)
- [JSON Format: RawExport vs NormalExport](#json-format-rawexport-vs-normalexport)
- [PersistentLevel Binary Layout](#persistentlevel-binary-layout)
- [Unversioned Property Headers](#unversioned-property-headers)
- [Import System](#import-system)
- [Export System](#export-system)
- [MTDealerVehicleSpawnPoint (Dealerships)](#mtdealervehiclespawnpoint-dealerships)
- [StaticMeshActor (Map Objects)](#staticmeshactor-map-objects)
- [Other Spawn Point Types](#other-spawn-point-types)
- [Vehicle Registry](#vehicle-registry)
- [Game Asset Paths](#game-asset-paths)
- [Packing & Deployment](#packing--deployment)
- [Scripts Reference](#scripts-reference)
- [Gotchas & Lessons Learned](#gotchas--lessons-learned)

---

## Toolchain

### UAssetAPI / UAssetGUI

Converts .umap/.uasset to JSON and back.

```bash
# .umap -> .json
UAssetGUI.exe tojson Jeju_World.umap Jeju_Worldaa.json VER_UE5_5 MototTown

# .json -> .umap
UAssetGUI.exe fromjson Jeju_Worldaa.json Jeju_World.umap VER_UE5_5
```

- Dirty/unreadable serialized parts in the JSON are fine. UAssetAPI round-trips them as base64 `RawExport` data.
- `SerialSize` and `SerialOffset` can be left as 0 on new exports; UAssetAPI recalculates on `fromjson`.

### repak

Packs mod directories into `.pak` files.

```bash
repak pack .\MapChangeTest_P
```

---

## Map Structure Overview

Motor Town uses **Jeju_World** as the main map. The map file is massive (~400MB JSON).

### Key Exports in Jeju_World

| Export # | ObjectName | Class | Notes |
|----------|------------|-------|-------|
| 26486 | PersistentLevel | Level (RawExport) | Contains the actor list |
| 26644 | Model_0 | Model | Referenced in PersistentLevel binary |
| 59238 | Jeju_World | World | The world object |
| 76464 | WorldSettings | WorldSettings | Referenced in PersistentLevel binary |

### Stats

- **76,469 total exports** (all RawExport)
- **10,795 imports**
- **67,424 names** in NameMap
- **~4,500 actors** registered in PersistentLevel
- **5,741 WorldPartition streaming cells** (sub-levels)
- **336 unique actor/component classes**

### Top Actor/Component Classes by Count

| Count | Class |
|-------|-------|
| 19,427 | BodySetup |
| 19,353 | SplineMeshComponent |
| 5,741 | WorldPartitionRuntimeCellDataSpatialHash |
| 2,813 | SceneComponent |
| 2,657 | StaticMeshComponent |
| 881 | MTInteractableComponent |
| 628 | StaticMeshActor |
| 478 | MotorTownRoad |
| 326 | TrashBagSpawner_01_C |
| 182 | MTDealerVehicleSpawnPoint |
| 132 | MWorldVehicleSpawnPoint |

---

## JSON Format: RawExport vs NormalExport

UAssetAPI serializes exports in two modes depending on the map:

### RawExport (Jeju_World main map)

```
"$type": "UAssetAPI.ExportTypes.RawExport, UAssetAPI"
"Data": "<base64-encoded binary>"  // unversioned property blob
```

- **All 76,469 exports** in Jeju_World are RawExport
- Properties are binary-encoded with unversioned headers (not human-readable)
- You construct raw bytes and base64-encode them
- `IsUnversioned: true` in the asset

### NormalExport (sub-level partition files)

```
"$type": "UAssetAPI.ExportTypes.NormalExport, UAssetAPI"
"Data": [ { "$type": "...PropertyData...", "Name": "...", "Value": ... }, ... ]
```

- Used by smaller sub-level files (e.g., `BPITA48KRY74AFBRZBJY6ENBZ.json`, `1M4YA9A3QFA1GU7GM0BGY8JM8.json`)
- Properties are human-readable JSON
- `conver.py` works with this format

### LevelExport (sub-levels only)

```
"$type": "UAssetAPI.ExportTypes.LevelExport, UAssetAPI"
```

Has structured fields: `Actors` (list), `URL` (object), `Model`, `ModelComponents`, etc. Only appears in sub-level files, NOT in the main Jeju_World map (which uses RawExport for PersistentLevel).

### Important Implication

**`conver.py` (NormalExport) works for sub-level partition files. `convert2.py` (RawExport) works for the main Jeju_World map.** They are NOT interchangeable.

---

## PersistentLevel Binary Layout

The PersistentLevel export in Jeju_World is a RawExport. Its binary Data has this structure:

```
[0:10]          Unversioned property header (5 fragments, 2 bytes each)
[10:923]        Serialized ULevel properties
[923:927]       int32 actor_count (e.g., 4502)
[927:927+N*4]   Actor list: N x int32 export indices (1-based)
[after actors]  URL FString: int32(7) + "unreal\0" (protocol)
                  + int32(0) (host, empty)
                  + int32(20) + "/Game/Maps/MainMenu\0" (map)
                  + int32(0) (portal, empty)
                  + int32(0) (op count)
                  + int32(7777) (port)
                  + int32(1) (valid)
[after URL]     int32 Model_0 export ref (26679)
                int32(1)
                int32 ModelComponent ref (26709)
                int32 WorldSettings ref (22244 -> Jeju_World_C_0)
                96 bytes zero padding
```

### Finding the Actor Count Programmatically

The count offset can vary. To find it:
1. Locate the URL marker: `struct.pack("<i", 7) + b"unreal\x00"`
2. Scan backwards from URL for an int32 `N` where `probe_offset + 4 + N*4 == url_offset`

### Patching the Actor List (CRITICAL)

To add actors you MUST do BOTH:
1. Add actor export numbers to `CreateBeforeSerializationDependencies` (JSON field)
2. **Increment the int32 actor count** AND insert int32 entries before the URL marker in the binary `Data`

If you insert entries without incrementing the count, the engine reads the old count, stops short, then tries to parse actor data as the URL string length -> **instant crash**.

---

## Unversioned Property Headers

When `IsUnversioned: true`, properties are serialized with compact binary headers instead of names. Each header is a sequence of 2-byte "fragments":

```
uint16 fragment:
  bits [0:6]   = skip count (property indices to skip)
  bit  [7]     = has defaults bitmap
  bit  [8]     = is last fragment
  bits [9:15]  = value count - 1
```

Different property sets produce different headers. The same class can have multiple header variants depending on which properties have non-default values.

### MTDealerVehicleSpawnPoint Headers

- Most common (144/182): `0002020203023903` (VehicleClass, EditorVisualVehicleClass, SceneComponent, RootComponent)
- 24 unique header variants across 182 exports
- Some set additional properties (dashboard, etc.)

### RootScene (SceneComponent) Header

- Standard: `0505` (RelativeLocation, RelativeRotation)
- 2 bytes, always the same for basic position+rotation

---

## Import System

Imports are negative 1-based indices (import at array index 0 = reference `-1`).

### Import Structure

```json
{
    "$type": "UAssetAPI.Import, UAssetAPI",
    "ObjectName": "MTDealerVehicleSpawnPoint",
    "OuterIndex": -7353,
    "ClassPackage": "/Script/CoreUObject",
    "ClassName": "Class",
    "PackageName": null,
    "bImportOptional": false
}
```

### Import Hierarchy for Dealerships

```
-7353: /Script/MotorTown                    (Package, outer=0)
-1512:   MTDealerVehicleSpawnPoint          (Class, outer=-7353)
-3196:   Default__MTDealerVehicleSpawnPoint  (outer=-7353, ClassPackage=/Script/MotorTown)

-7348: /Script/Engine                       (Package, outer=0)
-1473:   SceneComponent                     (Class, outer=-7348)
-8493:   RootScene                          (SceneComponent, outer=-3196, ClassPackage=/Script/Engine)

Vehicle (example: EnfoGT):
-6424: /Game/Cars/Models/EnfoGT/EnfoGT      (Package, outer=0)
-551:    EnfoGT_C                            (BlueprintGeneratedClass, outer=-6424)
```

### Script Packages Present

```
/Script/CoreUObject
/Script/Engine
/Script/Foliage
/Script/GameplayAbilities
/Script/GameplayTags
/Script/Landscape
/Script/MotorTown
/Script/NavigationSystem
/Script/Niagara
/Script/PCG
/Script/PrefabricatorRuntime
/Script/UMG
/Script/Water
```

### Adding New Imports

Use `find_or_add_import()` which:
1. Searches for an existing import with matching ObjectName + OuterIndex
2. If found, returns its negative index
3. If not found, creates a new import + adds names to NameMap

---

## Export System

Exports are 1-based positive indices (export at array index 0 = reference `1`).

### Export Fields

```json
{
    "$type": "UAssetAPI.ExportTypes.RawExport, UAssetAPI",
    "Data": "<base64>",
    "ObjectName": "MTDealerVehicleSpawnPoint_MOD_0",
    "OuterIndex": 26486,          // parent (PersistentLevel)
    "ClassIndex": -1512,          // class import (negative = import)
    "SuperIndex": 0,              // no super
    "TemplateIndex": -3196,       // template import (Default__)
    "ObjectFlags": "RF_Transactional",
    "SerialSize": 0,              // UAssetAPI recalculates
    "SerialOffset": 0,            // UAssetAPI recalculates
    "IsInheritedInstance": false,  // true for sub-objects (RootScene)
    "PackageFlags": "PKG_None",
    "bNotAlwaysLoadedForEditorGame": true,
    "Extras": "",                 // empty for RawExport
    // Dependency arrays:
    "SerializationBeforeSerializationDependencies": [],
    "CreateBeforeSerializationDependencies": [-551, 76471],
    "SerializationBeforeCreateDependencies": [-1512, -3196, -8493],
    "CreateBeforeCreateDependencies": [26486]
}
```

### Bookkeeping When Adding Exports

1. Append empty `[]` to `DependsMap` for each new export
2. Update `Generations[0].ExportCount` and `NameCount`
3. Add actor export numbers to PersistentLevel's actor list AND CBSD

---

## MTDealerVehicleSpawnPoint (Dealerships)

### Actor Export Binary Data

Header: `0002020203023903` (8 bytes)

```
[0:8]   Unversioned property header
[8:12]  VehicleClass (int32 import ref -> BlueprintGeneratedClass)
[12:16] EditorVisualVehicleClass (same value as VehicleClass)
[16:20] SceneComponent (int32 export ref -> RootScene)
[20:24] RootComponent (same value as SceneComponent)
[24:28] Zero padding
[28:]   Actor label: int32(1) + int32(strlen) + UTF-8 label + null + 16-byte random GUID + 16 zero bytes
```

Total: 28 + label overhead + 32 bytes.

### RootScene Export Binary Data

Header: `0505` (2 bytes)

```
[0:2]   Unversioned property header
[2:10]  X (float64)
[10:18] Y (float64)
[18:26] Z (float64)
[26:34] Pitch (float64)
[34:42] Yaw (float64)
[42:50] Roll (float64)
[50:58] Zero padding (8 bytes)
```

Total: always 58 bytes.

### Dependencies

**Actor:**
```
CBSD: [vehicle_class_import, rootscene_export]
SBCD: [dealer_class(-1512), default_dealer(-3196), rootscene_template(-8493)]
CBCD: [level_num(26486)]
```

**RootScene:**
```
SBCD: [scene_class(-1473), rootscene_template(-8493)]
CBCD: [actor_export_num]
```

---

## StaticMeshActor (Map Objects)

Used by `conver.py` for sub-level partition files.

### Import Chain

```
/Script/Engine (Package)
  StaticMeshActor (Class)
  Default__StaticMeshActor (template)
  StaticMeshComponent (Class)
  StaticMeshComponent0 (template, under Default__StaticMeshActor)
  StaticMesh (Class, for mesh asset refs)
```

### In Jeju_World (RawExport)

- 628 StaticMeshActor exports
- Header varies: `00020a0206022a02` etc.
- Data size: ~93 bytes
- Component is StaticMeshComponent0 with mesh reference, location, rotation, scale

### In Sub-levels (NormalExport)

Properties are structured JSON with named fields (StaticMesh, RelativeLocation, RelativeRotation, RelativeScale3D).

---

## Other Spawn Point Types

| Count | Class | Notes |
|-------|-------|-------|
| 182 | MTDealerVehicleSpawnPoint | Player-purchasable vehicles at dealers |
| 132 | MWorldVehicleSpawnPoint | World vehicles (parked cars, traffic) |
| 48 | MTSpawnVehicleListComponent | Vehicle list spawn configs |
| 326 | TrashBagSpawner_01_C | Trash bag spawn points |
| 39 | TrashBin_Spawner_01_C | Trash bin spawns |
| 19 | DeliveryVehicleSpawnPoint_C | Delivery vehicles |
| 10 | TrailerSpawner_C | Trailer spawn points |
| 9 | FireFighterVehicleSpawner_C | Fire trucks |
| 8 | PoliceVehicleSpawner_C | Police vehicles |
| 4 | BusSpawner_C | Bus spawns |
| 4 | DeliveryScooterSpawner_C | Scooter spawns |
| 3 | AmbulanceSpawner_C | Ambulance spawns |
| 3 | VehicleSpawner_C | Generic vehicle spawner |
| 1 | VulcanSpawner_C | Vulcan-specific spawner |
| 1 | MTVehicleSpawnPoint | Generic spawn point |
| 1 | MTAIVehicleSpawnSystem | AI vehicle system |
| 1 | MTAICharacterSpawnConfig | AI character config |

---

## Vehicle Registry

161 vehicle model packages in imports. Convention:

```
Package:  /Game/Cars/Models/{VehicleKey}/{VehicleKey}
Class:    {VehicleKey}_C  (BlueprintGeneratedClass)
```

Examples from the map:
- `/Game/Cars/Models/EnfoGT/EnfoGT` -> `EnfoGT_C`
- `/Game/Cars/Models/Vulcan/Vulcan` -> `Vulcan_C`
- `/Game/Cars/Models/Bike/Gunthoo/Gunthoo` -> `Gunthoo_C`
- `/Game/Cars/Models/Atlas/Atlas_4x2_Semi` -> `Atlas_4x2_Semi_C`

Note: Some vehicles have sub-paths (e.g., `Bike/Gunthoo/Gunthoo`).

---

## Game Asset Paths

### Categories by Import Count

| Category | Count | Example |
|----------|-------|---------|
| Objects | 253 | `/Game/Objects/Fuel/FuelPump_01A` |
| Models | 245 | `/Game/Models/PolygonAncientEmpire/Meshes/...` |
| Cars | 171 | `/Game/Cars/Models/EnfoGT/EnfoGT` |
| Env | 98 | `/Game/Env/Blueprints/Bridge_Support_01` |
| Road | 86 | `/Game/Road/Crossroad_3Way_01_TypeA` |
| Maps | 32 | `/Game/Maps/Jeju/...` |
| Characters | 29 | `/Game/Characters/MTAICharacter` |
| PolygonNature | 25 | `/Game/PolygonNature/Materials/...` |
| AssetsvilleTown | 11 | `/Game/AssetsvilleTown/Materials/MI_Leaf_01` |
| DataLayers | 10 | `/Game/DataLayers/Jeju_World_WP/...` |
| DataAsset | 9 | `/Game/DataAsset/StringTables/BusRoute` |

### Mesh Path Format

For `conver.py` (StaticMesh):
```
/Game/PolygonTown/Meshes/Buildings/SM_Bld_Church_01.SM_Bld_Church_01
^--- package path ---^                               ^--- export name --^
```

For `convert2.py` (vehicle BlueprintGeneratedClass):
```
/Game/Cars/Models/EnfoGT/EnfoGT  ->  EnfoGT_C
^--- package path ---^                ^--- class --^
```

---

## Packing & Deployment

### Directory Structure

```
MapChangeTest_P/
  MotorTown/
    Content/
      Maps/
        Jeju/
          Jeju_World/
            _Generated_/
              BPITA48KRY74AFBRZBJY6ENBZ.umap   (sub-level)
              BPITA48KRY74AFBRZBJY6ENBZ.uexp
```

### Pipeline

1. Convert JSON to .umap: `UAssetGUI.exe fromjson <input.json> <output.umap> VER_UE5_5`
2. Place .umap + .uexp in the correct directory structure
3. Pack: `repak pack .\MapChangeTest_P`
4. Copy .pak to game: `D:\SteamLibrary\steamapps\common\Motor Town\MotorTown\Content\Paks`

### Batch Scripts

- **modp.bat** `<MODNAME>`: Cleans .bak files, runs repak, copies .pak to game directory
- **plm.bat**: Runs conver.py pipeline for the sub-level partition file

---

## Scripts Reference

### conver.py

Injects **StaticMeshActor** instances into sub-level partition files (NormalExport/LevelExport format). Creates actor + StaticMeshComponent0 export pairs with structured JSON properties.

Input: `map_modifications.json` with `assets` groups containing mesh paths + transforms.

### convert2.py

Injects **MTDealerVehicleSpawnPoint** actors into the main Jeju_World map (RawExport format). Creates actor + RootScene export pairs with raw binary data matching existing export patterns.

Input: `dealership_modifications.json` with `dealerships` groups containing VehicleKey/vehicle_path + transforms.

---

## Gotchas & Lessons Learned

### 1. RawExport vs NormalExport Mismatch = Crash

`conver.py` creates `NormalExport` with JSON property arrays. This only works for sub-level files that already use NormalExport. The main Jeju_World uses RawExport exclusively. Injecting NormalExport into a RawExport-only map will fail.

### 2. Actor Count in PersistentLevel Binary MUST Be Updated

The PersistentLevel binary has an int32 actor count before the actor list. If you insert actor entries without incrementing this count, the engine reads past the list boundary and crashes trying to parse actor indices as URL data.

### 3. Both CBSD and Binary Actor List Must Be Patched

Actors must appear in BOTH:
- `CreateBeforeSerializationDependencies` (JSON field, used for dependency resolution)
- The binary actor list in `Data` (used by ULevel deserialization)

### 4. Binary Headers Are Position-Dependent

Unversioned property headers encode WHICH properties are set by index. The same class with different properties set will have different binary headers. Clone headers from existing exports of the same class with the same property set.

### 5. Dirty JSON Round-Trips Fine

UAssetAPI preserves unresolved/dirty serialized data as base64 blobs. You don't need clean, fully-mapped JSON to produce a working .umap. The engine reads the binary regardless.

### 6. SerialSize/SerialOffset Are Auto-Calculated

Leave them as 0 on new exports. UAssetAPI recalculates correct values during `fromjson`.

### 7. NameMap Must Include FName Bases

UAssetAPI splits names like `Foo_123` into base `Foo` + number `123`. Both the full name AND the base must be in NameMap, or lookups fail.

### 8. Import OuterIndex Matters

Two imports with the same ObjectName but different OuterIndex are different imports. When searching for existing imports, always match both ObjectName and OuterIndex.

### 9. Sub-level Files Use LevelExport with Actors Array

Sub-level partition files (like `BPITA48KRY74AFBRZBJY6ENBZ.json`) have `LevelExport` with a structured `Actors` list. Adding actors to these files just means appending to that list. No binary patching needed.

### 10. Vehicle Path Convention Has Exceptions

Most vehicles follow `/Game/Cars/Models/{Key}/{Key}`, but some have sub-paths like `/Game/Cars/Models/Bike/Gunthoo/Gunthoo`. When adding new vehicle references, verify the actual path exists in the game files.
