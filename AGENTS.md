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

### Local Game Asset Exports

Vehicle assets are exported to local disk at:
```
D:\MT\Output\Exports\MotorTown\Content\Cars\Models\
```

Each subfolder contains `.uasset` files with the vehicle blueprint exports. The folder name does NOT always match the asset name:

| Folder | Asset(s) | Game Path |
|--------|----------|-----------|
| `Crany/` | `Crany.uasset` | `/Game/Cars/Models/Crany/Crany` |
| `Trailer_Cotra/` | `Cotra_20_3L.uasset`, `Cotra_40_3.uasset` | `/Game/Cars/Models/Trailer_Cotra/Cotra_20_3L` |

Rule: the game path is always `/Game/Cars/Models/{folder}/{asset_name}` (without `.uasset`).

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

Vehicle (example: Cotra_20_3L):
-6513: /Game/Cars/Models/Trailer_Cotra/Cotra_20_3L  (Package, outer=0)
-640:    Cotra_20_3L_C                               (BlueprintGeneratedClass, outer=-6513)
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
    "CreateBeforeSerializationDependencies": [-640, 76471],
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

161 vehicle model packages in imports. Path format is fully flexible:

```
"vehicle_path": "/Game/Cars/Models/{folder}/{asset_name}"
```

The class name is always the last path segment + `_C`.

### Examples

| vehicle_path | Class | Local export folder |
|-------------|-------|---------------------|
| `/Game/Cars/Models/Crany/Crany` | `Crany_C` | `Crany/` |
| `/Game/Cars/Models/Trailer_Cotra/Cotra_20_3L` | `Cotra_20_3L_C` | `Trailer_Cotra/` |
| `/Game/Cars/Models/Trailer_Cotra/Cotra_40_3` | `Cotra_40_3_C` | `Trailer_Cotra/` |
| `/Game/Cars/Models/EnfoGT/EnfoGT` | `EnfoGT_C` | `EnfoGT/` |
| `/Game/Cars/Models/Bike/Gunthoo/Gunthoo` | `Gunthoo_C` | `Bike/Gunthoo/` |
| `/Game/Cars/Models/Atlas/Atlas_4x2_Semi` | `Atlas_4x2_Semi_C` | `Atlas/` |

Key points:
- Folder name does NOT always match asset name (e.g., `Trailer_Cotra/Cotra_20_3L`)
- Multiple assets can live in one folder (e.g., `Cotra_20_3L` and `Cotra_40_3` both in `Trailer_Cotra/`)
- Some have nested sub-paths (e.g., `Bike/Gunthoo/Gunthoo`)
- Always use the full `vehicle_path` — the `VehicleKey` shorthand only works for simple `{Key}/{Key}` cases

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
/Game/Cars/Models/Trailer_Cotra/Cotra_20_3L  ->  Cotra_20_3L_C
^--- full package path (vehicle_path) ---^        ^--- class name --^
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

Injects actors into the main Jeju_World map (RawExport format). Supports:
- **MTDealerVehicleSpawnPoint** — vehicle dealership spawners
- **StaticMeshActor** — static mesh props with optional scale
- **Blueprint actors** — generic BP actor spawning (e.g. parking spots)

Also auto-copies missing mesh assets from cooked content to the mod pak.

Input: `map_work_changes.json`:

```json
{
    "dealerships": { ... },
    "static_meshes": { ... },
    "blueprint_actors": { ... }
}
```

### import_meshes.py

Imports meshes from `static_meshes.json` (exported by `ue.py`) into `map_work_changes.json`. Applies coordinate offsets. Converts `Parking1` meshes to `blueprint_actors` entries. Copies missing assets from cooked content to mod pak. Rounds coordinates to avoid float precision artifacts.

### ue.py

Runs inside Unreal Editor. Exports all StaticMeshActors and foliage instances (from HISM components) to `static_meshes.json` with full transforms including scale.

### build_and_deploy.bat

Full pipeline: convert2.py → UAssetGUI fromjson → wait for .umap → modp.bat (pack + deploy).

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

### 10. Vehicle Paths Are Fully Variable

Folder name != asset name. Multiple assets per folder. Sub-paths exist. Always use the explicit `vehicle_path` field with the full `/Game/Cars/Models/...` path rather than assuming any naming convention.

### 11. NormalExport in RawExport .umap = Crash or Memory Leak

UAssetAPI cannot serialize NormalExport properties into unversioned binary for the main .umap. It works in standalone .uasset files (like actorTemplate.json, Goliath4_Actor.json) but NOT when injected into the all-RawExport Jeju_World.umap. Always use RawExport with manually constructed binary.

### 12. Scale Uses Tail Fragment num=4 Instead of num=3

The SMC no-scale header ends with `0x056E` (tail frag num=3). With scale: `0x076E` (num=4). Scale data (3 doubles) goes as the first element of the tail frag, before the tail zeros. Total: 120 bytes vs 96 bytes. The tail skip stays at 110 because the cursor position before the tail hasn't changed.

### 13. Blueprint Actors Have Embedded Cross-References

Blueprint actor components (like ChildActor, InteractionCube) contain hardcoded export indices inside their binary Data blobs pointing to sibling components. Cloning these binaries without patching EVERY internal ref causes access violations. The parking system (ParkingSpace_Middle_01_C, Interaction_PublicParkingSpac_C) is particularly complex with 5+ interconnected components.

### 14. ChildActor CBSD Must Reference Parent Actor, Not Siblings

ChildActorComponent's CBSD should point to the parent actor export, not to sibling components like Root. Pointing to a sibling creates a circular dependency → EXCEPTION_STACK_OVERFLOW.

### 15. Game Updates Invalidate Extracted JSON

When the game updates, the .umap binary changes. The extracted `Jeju_Worldaa.json` must be re-extracted from the updated game files. Using stale JSON with updated .ubulk/.uexp files causes crashes.

### 16. Float Precision in Python JSON

Python float addition creates artifacts like `-91700.17000000001`. Use `round(value, 4)` when writing coordinates to JSON to keep them clean.

### 17. Asset Path Dot Suffix Must Be Stripped

UE asset references use `Package/Path.ExportName` format. The `.ExportName` suffix must be stripped in `resolve_mesh_path()` to get the package path. Otherwise UAssetAPI creates phantom imports with the wrong path.

---

## BP Actor Injection (Settled Approach)

After many failed paths (hand-crafted NormalExport parking in the main map,
hand-crafted BP children with wrong `Extras` sizes, sub-level registration),
the reliable strategy is **cloning a vanilla in-game instance** into a
WorldPartition cell.

### Why hand-crafted BP actors don't spawn

- BP-class-instance NormalExports require an exact 5-field SCS-component
  pattern per subobject class (`BodyInstance`, `AttachParent`,
  `UCSSerializationIndex`, `bNetAddressable`, `CreationMethod` encoded as
  `ByteProperty` with value `SimpleConstructionScript=1`), plus class-
  specific extras:
  - Root-style `RF_Transactional | RF_DefaultSubObject, Inherited=True`,
    2 props, 4-byte Extras
  - SCS component `RF_NoFlags, Inherited=False`, 4 props, 4-byte Extras
  - SCS primitive (StaticMeshComponent-like) 4 props, **16-byte Extras**
    `00×8 01 00 00 00 00×4`
- Main-map BP injection into `PersistentLevel.Actors` doesn't spawn at
  runtime for cooked WP maps. Vanilla BP instances that *are* in
  `PersistentLevel.Actors` are editor placeholders; the engine runs the
  game from the partitioned cells.
- The only thing in the main map's `PersistentLevel.Actors` path that
  reliably spawns at runtime is native `StaticMeshActor` content.

### Working path: cross-cell clone

`MTBPInjector clone-cross-cell`:
1. Load a source `.umap` that has a working vanilla instance.
2. Find the actor + its direct children (`OuterIndex == srcActorNum`).
3. Deep-clone actor + children, remapping every `FPackageIndex`:
   src-actor → new-actor, src-children → new-children, src-imports →
   dst-imports (adding new imports as needed), and `PersistentLevel` →
   dst-`PersistentLevel`.
4. Overwrite `RelativeLocation` / `RelativeRotation` on the root child.
5. Regenerate the `FGuid` inside the actor's `Extras` (otherwise WP
   dedupes against the original).
6. Append the new actor to the destination's `PersistentLevel.Actors` via
   `PatchActorsInBytes` (binary patch of the count + list, preserving WP
   `Extras`).

Source actor's import chain (`/Game/.../SomeClass.SomeClass_C` → package
→ package root) has to be transplanted. `CloneCrossCell`'s `RemapImport`
walks the outer chain recursively, dedupes against existing dst-imports,
and adds missing ones.

### WP cell runtime hash (new-cell creation)

`Jeju_World.umap` holds the runtime partition data:

```
WorldPartition_0 (class UWorldPartition)
  └─ RuntimeHash → WorldPartitionRuntimeSpatialHash_0
      └─ StreamingGrids [SpatialHashStreamingGrid × 2]
          MainGrid:   CellSize=12800, 11 GridLevels
          Landscape:  CellSize=51200,  9 GridLevels
          Each GridLevel:
            LayerCells [SpatialHashStreamingGridLayerCell × N]
              Each LayerCell: GridCells → [ObjectProperty → cell export]
            LayerCellsMapping Map<Int64, Int32>  (grid key → LayerCells idx)
```

Each vanilla cell is expressed in Jeju_World via 3 linked exports:
- **WorldPartitionRuntimeLevelStreamingCell** (the cell) — child of
  `WorldPartitionRuntimeSpatialHash_0`. Props: `LevelStreaming` (→ cell
  streaming actor), `CellGuid`, `RuntimeCellData` (→ spatial info).
- **WorldPartitionRuntimeCellDataSpatialHash** — Props: `Position`
  (FVector = cell center), `Extent` (half-width), `ContentBounds`,
  `GridName` (FName), `HierarchicalLevel` (int). Extras contains a
  `Jeju_World_MainGrid_Lx_Xx_Yy` C-string.
- **WorldPartitionLevelStreaming_\<cellname\>** — Props: `StreamingCell`
  (weak back-ref), `OuterWorldPartition`, `WorldAsset` (soft ref to the
  cell's `.umap`), `PackageNameToLoad` = `/Game/Maps/Jeju/Jeju_World/_Generated_/<cellname>`.

Plus the companion `_Generated_/<cellname>.umap` file holds the actor
content that streams in.

### `LayerCellsMapping` key packing (MainGrid level 0 / L-1)

Empirically decoded:
```
key = (gridX + 524_800) + gridY * 1024
where gridX = floor(pos.X / 12800), gridY = floor(pos.Y / 12800)
```

(Derived by cross-referencing a sample of Map entries against the pointed
cell's `RuntimeCellData.Position`. Verified across positive/negative X
and Y. See `MTBPInjector decode-layer-keys`.)

### `MTBPInjector register-new-cell`

One-shot command that creates a cell at arbitrary coords:
1. Clones the 3 registration exports from a template vanilla cell (we use
   `0W5HFJERQNYIKT4TIFEZBU4PD` — small L-1 MainGrid cell with minimal
   content, ext=6400).
2. Updates the clone's `Position`, `Extent`, `GridName`, `HierarchicalLevel`
   to the new target; re-links cross-refs; regenerates `CellGuid`.
3. Updates `PackageNameToLoad` / Extras on the LevelStreaming clone so WP
   loads our new `.umap` instead of the template's.
4. Appends a new `LayerCell` to
   `StreamingGrids[grid].GridLevels[idx].LayerCells` and inserts a
   `LayerCellsMapping` entry with the decoded packed key.
5. Copies the template cell content file to `<new-name>.umap` under the
   mod `_Generated_/` dir so WP has something to stream.

`clone_bp_actors.py` calls this automatically when an entry's coords land
outside any useful (hierarchical level ≤ 2) vanilla cell. L10 / Landscape
catch-all cells (center 0,0 ext 6.5M) are deliberately rejected as
candidates — they don't spawn runtime BP actors we inject into them.

Multiple BP actors on the same 12800-unit grid tile share one created
cell. `clone_bp_actors.py` keys by `(floor(X/12800), floor(Y/12800))` and
reuses an already-registered MOD cell instead of registering again.

---

## BP Registry Convention (`bp_registry.py`)

Single source of truth — `REGISTRY` dict in `bp_registry.py`:

```python
"ParkingLarge": {
    "bp_path":      "/Game/Objects/ParkingSpace/ParkingSpace_Large_01",
    "bp_class":     "ParkingSpace_Large_01_C",
    "source_umap":  CELLS_DIR / "0MYO9WO9JBZ10BIDLXVFRXAOG.umap",
    "source_actor": "ParkingSpace_Large_01_UAID_2CF05D790A1CFFDB01_1915517403",
    "preload_bp":   ".../Interaction_ParkingSpace_Large.uasset",
}
```

- `import_meshes.py` uses registry keys to split rows into
  `blueprint_actors` vs `static_meshes`.
- `clone_bp_actors.py` looks up `bp_class` in the registry to find the
  source umap + actor to clone.
- Users add a new type by adding one entry and dropping a placeholder
  under `/Game/DC/Actors/<asset_key>` in their editor scene.

### Picking a source actor

For the source to clone reliably, pick an instance whose direct children
(`OuterIndex == actor`) actually include the actor's root / components.
Some BP classes only exist wrapped inside a `ChildActorComponent`
(e.g. `Interaction_PublicParkingSpac_C`). Those can't be cloned standalone
— register the wrapper class (`ParkingSpace_Small_02_C` etc.) instead.

## Persistent-Level vs WP-Cell BP Injection

Heavy BPs (delivery points, factories, gas stations) **crash** when cloned
into a WP cell — the cell-streaming path validates package imports and
runtime state more strictly than persistent-level load. Symptom: "corrupt
data" or memory leak on player approach.

The same actors clone cleanly when injected into `Jeju_World.umap`'s
**persistent level** (which is where the vanilla instances live). Same
load context as the originals → full subsystem init, mission-system
discovery, no streaming gap.

`bp_registry` flag `inject_into_main: True` routes the entry through
that path. CloneBatch uses `dst-cell = Jeju_World.umap` directly.

### Required differences from cell injection

1. **Synthesize actor-metadata Extras** (the `count + strlen + label +
   FGuid + pad` blob). Vanilla persistent-level actors carry it; WP cell
   actors leave Extras empty and use the level body's metadata table.
   Without it, MT's mission/save subsystems can't key the actor.

2. **Disable recursive ObjectProperty closure** for these clones. Heavy
   BPs reference sibling actors (Factory_Concrete's
   `InputInventoryShare`) — recursing duplicates them as new actors
   that conflict with the originals. Instead let `RemapIdx` pass refs
   through unchanged (src and dst are the same package, indices stay
   valid).

3. **Auto-slot reservation across the batch.** When multiple
   main-injected entries need an empty `Actors[]` slot, the picker must
   exclude slots already reserved by earlier entries in this batch
   (replace ops fire at end). Otherwise all entries grab the first null
   slot and only the last write survives.

### Discovered delivery-point archetypes

- **Standalone (no chaining):** `Farm_*_C` classes have no
  `InputInventoryShare`. Each placed instance is its own
  pickup-and-drop loop.
- **Two-way:** `Container_ExportImport_C` (`ContainerDropper` instances).
  Both pickup and drop without external dependencies.
- **Chained:** `Factory_*_C` reference sibling delivery points as
  inputs — cloning one with pass-through enabled makes the new spot a
  satellite of the original factory rather than a new endpoint.

### MT-doesn't-honor-instance-overrides

`ProductionConfigs` (the recipe table on every `MTDeliveryPoint`) is
read **only from the BP CDO**. Adding a `ProductionConfigs`
ArrayPropertyData to the cloned actor instance has no effect. To
customize a recipe (input cargo, output cargo, speed multiplier,
production time) the only path is a NEW BP CLASS:

1. Byte-copy the source `.uasset` + `.uexp` to a new same-length name
   in the mod folder.
2. Byte-replace the class name string everywhere in both files. UAsset
   layout is preserved as long as the new name has the same length
   (`Farm_Corn` → `ModFarmTr` works; `ComonDrop` → `ModDrop_1` works).
3. Mutate the new BP's `Default__<class>_C` `ProductionConfigs` array
   via UAssetAPI (load, edit struct values, save).
4. Register a `target_bp_path` / `target_bp_class` override in
   `bp_registry`. CloneBatch then rewrites the cloned actor's
   `ClassIndex` and `TemplateIndex` to point at the new mod-shipped
   class instead of the source's class.

`MTProductionConfig` struct fields (from `Farm_Corn` / `Factory_*` CDO):

| Field                           | Type                            |
|---------------------------------|---------------------------------|
| `InputCargos`                   | Map<Name, Int> (cargo → count)  |
| `InputCargoTypes`               | Map<Enum (EDeliveryCargoType), Int> |
| `InputCargoGameplayTagQuery`    | Struct GameplayTagQuery         |
| `OutputCargos`                  | Map<Name, Int>                  |
| `OutputCargoTypes`              | Map<Enum, Int>                  |
| `OutputCargoRowGameplayTagQuery`| Struct GameplayTagQuery         |
| `bStoreInputCargo`              | Bool                            |
| `ProductionTimeSeconds`         | Float (seconds)                 |
| `ProductionSpeedMultiplierZoneCoeffs` | (zone-based)             |
| `ProductionSpeedMultiplier`     | Float (1.0 = baseline)          |
| `LocalFoodSupply`               | (population-related)            |
| `bHidden`                       | Bool                            |

### Display-name strings

Vanilla delivery points read `PointName` from a StringTable (e.g.
`/Game/DataAsset/StringTables/Delivery`). The MoreTuning mod's
convention works here too: use `MTTextByTexts` with variant `None` and
the literal string as the name — bypasses the table lookup entirely.
Useful when adding a custom-named cloned delivery point without
patching the central string table asset.

## Pak Load Order Gotcha

UE loads `_P.pak` files in alphabetical order; later names shadow
earlier ones for any file path they both contain. `MapChangeTest_P`
sorts before `Racetrack_P`, so if both modify
`MotorTown/Content/Maps/Jeju/Jeju_World.umap`, Racetrack's version
wins and our changes look like they didn't apply.

Diagnose with `repak list <pak> | grep Jeju_World` on each installed
pak. Resolve by renaming our pak to sort last (e.g. `ZMapChange_P`)
or removing the conflicting pak.

## Vanilla-Cell Injection: Per-Actor Metadata Blob Mismatch

`ReplaceActorSlotInLevel` only swaps the `FPackageIndex` in the
`Actors` array. The level body also has a separate **per-actor
metadata blob** (one entry per slot, containing GUID + package name).
Vanilla cells fill this blob with metadata describing each real actor;
our template L-1 cells have placeholder/empty metadata that UE
tolerates being wrong.

When you replace a slot in a **vanilla** cell, the blob still
describes the OLD actor → UE's integrity check trips → "corrupt data"
crash. Workaround: `force_new_cell: True` in registry skips the
vanilla-cell route and always registers a fresh mod cell at the
target coords. Real fix would parse and patch the metadata blob
(deferred — adds complexity for marginal gain).

## Registry Lookup by `asset_key`, Not `blueprint_class`

When two `bp_registry` entries share the same `blueprint_class`
(e.g. `FarmCorn` and `FarmTransformer` both clone `Farm_Corn_C`),
class-based lookup is ambiguous and silently picks the first match.
`import_meshes.py` carries the placeholder's `asset_key` through to
`map_work_changes.json`'s `blueprint_actors` entries; `clone_bp_actors`
prefers `REGISTRY[asset_key]` over `template_for_class`.

## Cargo Catalog (`/Game/DataAsset/Cargos.uasset`)

Single `DataTableExport` named **Cargos** with 91 rows. Each row's `Name`
is the cargo identifier referenced by name from delivery-point recipes
(`MTProductionConfig.InputCargos` / `OutputCargos` keys), cargo orders,
mission scripts, etc. Adding a custom delivery point uses these names
verbatim (e.g. `"Transformer_50MVA"`, `"CrudeOil"`, `"CornPallet"`).

### Row schema (per cargo)

| Field                                  | Type      | Notes                                                        |
|----------------------------------------|-----------|--------------------------------------------------------------|
| `bDepcreated`                          | Bool      | `true` excludes from spawning. (sic, MT typo)                |
| `Name`                                 | Text      | In-game display label (string-table or inline `MTTextByTexts` variant=None). |
| `Name2`                                | Struct    | Secondary label, often empty.                                |
| `CargoType`                            | Enum      | `EDeliveryCargoType`. See distribution below.                |
| `CargoSpaceTypes`                      | Array     | Which cargo bays accept this cargo.                          |
| `VolumeSize`                           | Float     | Used for capacity packing.                                   |
| `WeightRange`                          | Struct    | Min/max weight for spawn variance.                           |
| `bAllowStacking`                       | Bool      |                                                              |
| `bUseDamage`                           | Bool      | Damage tracked & affects payout.                             |
| `Fragile`                              | Float     | Damage multiplier when handled rough.                        |
| `SpawnProbability`                     | Int       | Weight in random pickup generation.                          |
| `NumCargoMin` / `NumCargoMax`          | Int       | Pickup batch size range.                                     |
| `PaymentPer1Km`                        | Float     | Base $/km.                                                   |
| `PaymentPer1KmMultiplierByMaxWeight`   | Float     | Heavy cargo bonus.                                           |
| `PaymentSqrtRatio`                     | Float     | Diminishing-returns curve on volume/distance.                |
| `PaymentSqrtRatioMinCapcity`           | Int       |                                                              |
| `BasePayment`                          | Int64     | Floor payout regardless of distance.                         |
| `ExportPrice` / `ImportPrice`          | Int       | Container Export/Import economy.                             |
| `MaxDamagePaymentMultiplier`           | Float     | Cap on damage penalty.                                       |
| `DamageBonusMultiplier`                | Float     |                                                              |
| `ManualLoadingPayment`                 | Int64     | Bonus for hand-loaded cargo.                                 |
| `ActorClass`                           | Object    | Spawned BP class for the physical cargo (RawExport instance).|
| `DumpCargoSurfaceMesh` / `Material`    | Object    | Visual when poured/dumped (sand, gravel etc.).               |
| `DumpPileActorClass`                   | Object    | Pile-on-ground actor class.                                  |
| `CargoFlags`                           | Int       | Bitfield (export/import allowed, hidden, etc.).              |
| `GameplayTags`                         | Struct    | Tag query targets (used by some delivery points).            |
| `MinDeliveryDistance` / `Max...`       | Float     | Mission filtering.                                           |
| `bTimer` + `BaseTimeSeconds` + ...     | Bool/Float| Timed delivery missions (perishable).                        |
| `bHoldingOffsetUsingItemBounds`        | Bool      |                                                              |
| `Colors`                               | Array     | Optional palette variants.                                   |

### `CargoType` distribution

Roughly half the rows have `CargoType = None` (generic). The remainder
are tagged for filtering by delivery points / vehicles:

| Type             | Count |
|------------------|-------|
| `None`           | 22    |
| `SmallPackage`   | 15    |
| `LargePackage`   | 15    |
| `Food`           | 8     |
| `Furniture`      | 7     |
| `Container`      | 5     |
| `Stone`          | 5     |
| `Log`            | 4     |
| `FinalProduct`   | 2     |
| `Sand`           | 2     |
| `Garbage`        | 2     |
| `Wood`, `Coal`, `Concrete`, `MilitarySupply` | 1 each |

`MTProductionConfig.InputCargoTypes` / `OutputCargoTypes` use this enum
for cargo-class routing instead of a specific name (e.g. accept ANY
cargo of type `LargePackage`).

### All cargo names (alphabetical)

`AirlineMealPallet`, `AppleBox`, `BeanPallet`, `Bed_01`, `Bed_02`,
`Bed_03`, `BottlePallete`, `BoxPallete_01`, `BoxPallete_02`,
`BoxPallete_03`, `BreadBox`, `BreadPallet`, `Burger_01`,
`Burger_01_Signature`, `CabbagePallet`, `CarrotBox`, `Cement`,
`CheeseBox`, `CheesePallet`, `ChilliPallet`, `Coal`, `Concrete`,
`Container_20ft_01`, `Container_30ft_10t`, `Container_30ft_20t`,
`Container_30ft_5t`, `Container_40ft_01`, `CopperConcentrate`,
`CopperOre`, `CopperRodCoil_2t`, `CornBox`, `CornPallet`, `CrudeOil`,
`FineSand`, `FormulaSCM`, `Fuel`, `GiftBox_01`, `GlassBottleBox`,
`GroceryBag`, `GroceryBox`, `HempPallet`, `IronOre`, `Limestone`,
`LimestoneRock`, `LiveFish_01`, `Log_20ft`, `Log_30ft_30t`,
`Log_Oak_12ft`, `Log_Oak_24ft`, `MeatBox`, `MilitarySupplyBox_01`,
`MilitarySupplyBox_01_Empty`, `Milk`, `Oil`, `OrangeBox`,
`OrangeBoxes`, `Pizza_01`, `Pizza_01_Premium`, `Pizza_02`,
`Pizza_03`, `Pizza_04`, `Pizza_05`, `PlasticPallete`,
`PlasticPipes_6m`, `PotatoPallet`, `PowerBox`, `PumpkinBox`,
`PumpkinPallet`, `QuicklimePallet`, `Raven`, `Rice`, `RicePallet`,
`Sand`, `SmallBox`, `SnackBox`, `Sofa_01`, `Sofa_02`, `Sofa_03`,
`Sofa_04`, `SteelCoil_10t`, `SunflowerSeed`, `Tank_250kL`, `Terra`,
`ToyBoxes`, `Transformer_20MVA`, `Transformer_50MVA`,
`Transformer_5MVA`, `TrashBag`, `Trash_Big`, `WoodPlank_14ft_5t`,
`lHBeam_6m`.

### Adding cargo to a recipe

For `inputs`/`outputs` in a `production_recipes` JSON entry, the key
is the row's `Name` field above and the value is the integer count.
Two-input recipe example (the FarmTransformer registry entry):

```python
"production_recipes": [
    {
        "inputs":       {"Transformer_50MVA": 1, "CrudeOil": 1},
        "outputs":      {"CornPallet": 1},
        "speed":        5.0,
        "time_seconds": 30.0,
    },
],
```

Names that don't exist in `Cargos.uasset` will silently produce a recipe
that cannot fire — MT looks up by name with no error handling. Always
copy from the catalog above (or dump `Cargos.uasset` fresh if the
game has been updated).

## DEFINITIVE: Map Markers Don't Render For Injected Delivery Points

**Confirmed empirically**: deploy a single injected DP at the exact
world coords of a previously-working spot — no marker. Earlier
"TF has marker, TF2 doesn't" reads were misleading: the marker on TF
was a NEARBY VANILLA delivery point's icon overlapping TF's location.

The marker registry lives in cooked C++ / WP runtime hash data baked
at the studio's cook step. None of the inspected assets
(`MapIcons.uasset`, `MTDeliverySystemConfigActor.Config`,
`MotorTownNavigation_1` blob — that one is just the AI navmesh) carry
the per-class registration that would let us add our `Mod*_C` clones.

Consequence for the framework:
- Custom DPs spawn cleanly, accept/give cargo, register as mission
  endpoints, appear in the offer list.
- They DO NOT show on the world map.
- Placing one near a vanilla DP makes the vanilla DP's marker appear
  to "belong to" our DP — easy to mistake.

Unblocking needs UE editor + cook step, runtime memory patching, or
UE4SS-mediated registration — outside the static-`.uasset` scope.

## Marker / Icon Mutation (Pending)

`MTDeliveryPoint`-derived BPs have NO marker/color/icon properties on
their CDO — `import_cargo_data.py` confirmed `visuals_seen` is empty
across all 86 vanilla delivery-point classes. The marker that appears
on the in-game map is therefore set somewhere else, likely:

- Native `MTDeliveryPoint` C++ defaults (not exposed via .uasset).
- Per-instance properties on the actor in the persistent level (the
  blob is RawExport, opaque without the schema).
- Inferred at runtime from cargo type or mission system state.

Empirical observation: a delivery point with NO marker/icon set still
spawns and is interactable, but is invisible on the world map — a
de-facto "secret delivery point" mode. Useful future capability:
intentionally omit marker/icon to hide a destination from the map.

`delivery_points.json` accepts `marker_color` + `icon` fields today and
the framework propagates them through the registry, but no MTBPInjector
mutation is wired yet — pending identification of the actual property
names.

## Generic Delivery-Point Framework (`delivery_points.json`)

Scene placeholder convention: `DeliveryPoint_<KEY>` (asset under
`/Game/DC/Actors/`). The pipeline:

1. `import_meshes.py` carries `asset_key` through to
   `map_work_changes.json` `blueprint_actors` entries.
2. `bp_registry._load_delivery_points` registers each `delivery_points.json`
   key as `REGISTRY["DeliveryPoint_<KEY>"]`. `clone_bp_actors` looks up
   by `asset_key`, so the placeholder routes automatically.
3. Cloning machinery (`source_class`, `target_class`, mod BP path) is
   **auto-derived** from the key — JSON only carries user intent
   (`label`, `recipes`, future visuals).

`target_class` is hash-derived to keep byte-rename length-equal with
the source class (`Farm_Corn` = 9 chars → `Mod` + 6 hash chars).

### Recipe schema (per entry in `recipes`)

| Field           | Type                         | Notes                                       |
|-----------------|------------------------------|---------------------------------------------|
| `inputs`        | `{Cargo: Count}` map         | Specific named cargos (see Cargos catalog). |
| `outputs`       | `{Cargo: Count}` map         |                                             |
| `input_types`   | `[Type, ...]` or `{Type:N}`  | EDeliveryCargoType filter (Wood, Log etc.). |
| `output_types`  | `[Type, ...]` or `{Type:N}`  |                                             |
| `speed`         | float                        | `ProductionSpeedMultiplier` (1.0 default).  |
| `time_seconds`  | float                        | `ProductionTimeSeconds`.                    |

Recipe with NO `inputs` / `input_types` = timed background production.
`import_cargo_data.py` dumps every vanilla delivery-point class as a
ready-to-paste example under `CargoImport/delivery_points/`.

## Output Storage Cap (Pending)

Empirically a cloned delivery point caps each output cargo at ~100 units.
That cap is NOT in `MTProductionConfig` and NOT on any vanilla BP CDO —
it lives in a separate per-(DeliveryPoint, Cargo) actor of class
`MTDeliveryPointInventoryRatio` (one in vanilla Jeju at export 27825+,
~26 bytes each, props: `DeliveryPoint`, `CargoKey`, `bInputInventory`,
`CreationMethod`).

To raise/lower the cap per delivery point we'd need to spawn
matching `MTDeliveryPointInventoryRatio` instances tied to the cloned
actor — same persistent-level inject mechanism, but the numeric cap
field name isn't yet identified (parsed Data showed only the four
listed above; Serial/Extras likely carry a float ratio we haven't
located yet).

`delivery_points.json` `output_storage_cap` field is plumbed through
`bp_registry` for future use; mutation pending.
