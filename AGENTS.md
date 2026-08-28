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

### Row name is not asset name — resolve through the table

A `Spawn_<Key>` / `Dealership_<Key>` placeholder names a **DataTable row**,
which is what the game calls the vehicle and what the roster lists. The row's
`VehicleClass` field names the actor to place, and for a handful of rows it is
NOT the row's own name:

| Row | Actual asset |
|-----|--------------|
| `Police_01` | `/Game/Cars/Models/Police/Police` |
| `PoliceInterceptor_01` | `/Game/Cars/Models/PoliceInterceptor1/PoliceInterceptor1` |
| `Nuke_Police` | `/Game/Cars/Models/Nuke/NukePolice` |
| `Nuke_Taxi` | `/Game/Cars/Models/Nuke/NukeTaxi` |
| `Trailer_30ft_Log_01` | `/Game/Cars/Models/Trailer_9m_Flat_01/Trailer_9m_Log_01` |

So `resolve_vehicle_path_by_key` asks the vehicle tables FIRST (mod-aware,
via `unlock_vehicles.vehicle_class_by_row`) and only falls back to a filename
scan for an asset that ships with no row. Guessing the asset from the key
places a spawner referencing a class that exists in no package: it fails
**silently**, with a clean build log and nothing in the world.

The class name likewise comes from the package's last segment, never from the
placeholder key — see `convert2.resolve_vehicle_path`.

### Hardcoded on purpose: clone templates

`bp_registry._TEMPLATES` hardcodes the vanilla classes a delivery point can be
cloned from (`farm` -> `Farm_Corn_C` / `CornFarm_2`). This is deliberate and
is not the same as a hardcoded assumption: it is a curated catalogue of vanilla
classes verified to survive cloning. Most vanilla DP classes do not —
`Container_ExportImport_C` and the `Factory_*` family have shown crashes and
persistence problems. Adding a template is a data entry once a class is proven,
and any single delivery point can bypass the list with `source_class` /
`source_actor`.

Everything else that could be hardcoded is not: the mod name lives in `.env`
as `MTMI_MOD_NAME`, and no vehicle, mesh or cargo name appears in framework code.

### Placeholder scale is discarded — so it is free for authoring

`import_meshes` reads a spawner placeholder's position, Pitch, Roll and Yaw and
throws its scale away; the placeholder mesh is never shipped either. Same for
`DeliveryPoint_*`.

That is worth telling users rather than hiding, because it turns a dead field
into a free authoring aid: stretching a spawner placeholder along X makes it an
arrow showing the vehicle's heading in the viewport, since X is Unreal's
forward axis. Nothing downstream sees the number.

If scale ever DOES become meaningful for a placeholder type, this doc and the
README section "Which way a spawned vehicle faces" both have to change, because
people will by then have scaled placeholders purely to see them.

### Injecting a class the game never places: cook one and diff it

`LocalFogVolume` cost two days and two world-load crashes because we built the
actor from first principles instead of comparing it with a real one. The
moment one was placed in the editor project and cooked, the diff found both
bugs in twenty minutes.

Two things an injected actor needs that are easy to miss, because they are not
properties and nothing warns when they are absent:

**An archetype.** `TemplateIndex` must point at the class CDO, and a component's
at the CDO's subobject — `ExponentialHeightFog_1` is `TemplateIndex=-1729`
(`Default__ExponentialHeightFog`) with `HeightFogComponent0` at `-1730`. At 0,
UE has nothing to construct from and the actor silently does nothing.

**Export metadata.** Every actor export in a cooked level carries a trailing
blob: count, label, FGuid, padding. With `ExtrasLen=0` the loader reads the
FOLLOWING export's bytes as this actor's metadata, which is a world-load crash
rather than a missing actor. `MakeActorExtras` emits the right layout.
Components carry 4 zero bytes. Set `bNotAlwaysLoadedForEditorGame` too, and
mark an inherited component `IsInheritedInstance`.

So: place the class in the editor level, cook, `inspect-export` and
`inspect-imports` the result, and match every field — class and template
indices, object flags, `CBCD/CBSD/SBCD/SBSD` counts, `ExtrasLen`. Guessing at
any of them is how you get an actor that loads and does nothing, or a crash.

Two things a cloned template drags along, both handled by the framework rather
than per point:

**Its scenery.** `LiquidSupplier_C` carries `SM_Bld_Silo_Small_01`, so every
gas station cloned from it grew a set of tanks. Skipping the cloned child
export does NOT help — these are BP construction-script components
(`CreationMethod`, `UCSSerializationIndex` on the export), so UE rebuilds them
from the class at spawn whether or not the level carries an override. The only
lever is a per-instance override, and the one that works is nulling
`StaticMesh`: `UStaticMeshComponent::GetBodySetup()` reads through the mesh, so
no mesh means no geometry AND no collision, with no dependence on
`FBodyInstance` profile fixup running in a cooked build. Opt out per point with
`"keep_template_mesh": true`.

**"Is a StaticMeshComponent" is not "is scenery".** `InteractionCube` — the
volume the entire delivery point is interacted through — is a
`StaticMeshComponent` too, sharing the silo's class index exactly
(`ClassIndex=-1497` on both in Jeju_World). A first cut that matched on class
alone hid the interaction volume on all 33 points and turned each one into a
solid invisible block that could not be walked up to or driven through:
`bVisible=false` took, `BodyInstance.CollisionProfileName=NoCollision` did not.
Match on the `SM_` asset-naming convention instead. A component that fails the
match stays visible, which is the safe direction to fail in — a stray visible
mesh is a complaint, a broken interaction volume is a dead delivery point.

The same cut also fired on fuel pumps, garages and parking spaces, which are
cloned precisely so their meshes show up. Scenery-hiding is therefore opt-in
per clone job (`hide_template_mesh`), set by `bp_registry` for delivery points
only — never a default in the injector.

**Its name.** There is no single name property. Unversioned serialization only
writes values that differ from the class default, so which one a vanilla
instance carries depends on the class: `CornFarm_2` has `MissionPointName` and
`PointName`, `Warehouse_Ranch` has only `PointName`, `LogSupply_2` has only
`MissionPointName`. Patching `PointName` and logging a warning for the rest is
what left LogSupply clones displaying their vanilla Jeju names. `CloneBatch`
now patches whichever are present and synthesizes `PointName` when it is
absent. Do not add a name property to a template's shopping list — the general
rule is that a label is the framework's job, not the template's.

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

### build.bat

The single entry point. Reads `.env`, validates config, then runs the
6-step pipeline: MTBPInjector build → clean → import_meshes → convert2 →
UAssetGUI fromjson → clone_bp_actors → modp.bat (pack + deploy). Has
`--skip-<stage>` / `--only-<stage>` flags for partial re-runs (these
replaced the old standalone `cell_test.bat` / `build_and_deploy.bat`).

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

## DEFINITIVE: Per-Actor Identity GUIDs Must Be Deterministic

Vanilla `MTDeliveryPoint`s carry a `DeliveryPointGuid` struct property
that MT's save system + map-marker registry both key by. Naive cloning
copies the GUID verbatim, so multiple clones collide — only one
"exists" to the save system → no production persistence + flaky
markers.

Regenerating with `Guid.NewGuid()` per deploy fixes the collision but
breaks save compatibility: the player's save references the GUID
written on first deploy; second deploy mints a different one; the
loader can't find the actor → crash on subsequent boot.

Fix: deterministic GUIDs derived from a stable seed —
`SHA1("MTLiveMap-DPGuid|" + target_class | field_name)`. Same seed
across deploys, unique per (entry, field). Markers stick, production
persists, saves remain valid. Implemented in `MutateBpCdo` /
CloneBatch's actor-clone block in `MTBPInjector/Program.cs`.

Note: changing a delivery point's `key` in `delivery_points.json`
changes its derived `target_class`, which changes its GUID — same
effect as renaming an entity in any save-keyed system. Existing saves
will lose state for that actor. Don't rename keys casually.

## Template-Based Delivery Point Sources

`bp_registry._TEMPLATES` maps a short `template` name → vanilla
`(source_class, source_actor)` pair the framework knows how to clone
end-to-end. Currently only `farm` (Farm_Corn_C/CornFarm_2) is
validated — heavier classes (`Container_ExportImport_C`, `ComonDrop_C`,
`Factory_*`) crashed cell-streaming or save-game in earlier tests
because of transitive component dependencies our cloner doesn't
fully reconstruct.

Adding a new template requires verifying:
1. Cloned actor spawns without crash
2. Both interact + mission offers register
3. Save state persists across reload
4. Multiple instances coexist

Per-entry `source_class` + `source_actor` fields in
`delivery_points.json` allow experimental clones without modifying
the registry — useful for one-off testing.

## Map Markers DO Render For Injected Delivery Points (corrected)

**Superseded.** This section previously claimed injected DPs never show a
marker, and that the registry was baked into the studio's cook and
unreachable. That is WRONG — confirmed in game with 33 injected DPs, all
showing markers.

The original conclusion came from a single-DP test whose marker was
attributed to a nearby vanilla DP. Don't repeat that: verify with several
DPs far from vanilla ones before concluding anything about markers.

What IS true, and easy to mistake for a bug:

- **The DP actor itself is invisible.** Vanilla `Farm_Corn.uasset` has 2
  references and ZERO visual ones — a Motor Town delivery point is an
  invisible actor. The barn or warehouse you see at a vanilla DP is
  separate scenery the level designer placed beside it. Injected DPs match
  that exactly, so "I see the marker but nothing on the ground" is correct
  behaviour; place a building mesh next to the marker.
- **Cargo props appear only once the DP has stock.** Most recipes need
  inputs delivered first, so a fresh world shows empty DPs. Timer-only
  producers (no `inputs`) are the ones to check if you suspect a fault.
  Props also refresh lazily — reload or re-enter the cell.

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
| `inputs`        | `{Cargo: Count}` map         | Specific named cargos (vanilla OR `new_id` from `new_cargos`). |
| `outputs`       | `{Cargo: Count}` map         | Same name space as `inputs`.                |
| `input_types`   | `[Type, ...]` or `{Type:N}`  | EDeliveryCargoType filter (Wood, Log etc.). |
| `output_types`  | `[Type, ...]` or `{Type:N}`  |                                             |
| `speed`         | float                        | `ProductionSpeedMultiplier` (1.0 default).  |
| `time_seconds`  | float                        | `ProductionTimeSeconds`.                    |

Recipe with NO `inputs` / `input_types` = timed background production.
`import_cargo_data.py` dumps every vanilla delivery-point class as a
ready-to-paste example under `CargoImport/delivery_points/`.

## Custom Cargos (`new_cargos`)

Single mechanism for adding cargo rows to `Cargos_01.uasset`. Each
entry clones a vanilla row by name, applies arbitrary field
overrides, and registers a per-cargo `safety_dps` list for the
runtime-registry workaround.

```json
"new_cargos": [
  {
    "copy_from":         "Fuel",
    "new_id":            "Fuelx2",
    "display_source":    "Fuel",
    "PaymentPer1Km":     600,
    "BasePayment":       100000,
    "SpawnProbability":  10,
    "PaymentSqrtRatio":  1.0,
    "safety_dps":        ["Farm_Cabbage_C", "Farm_Hemp_C"]
  }
]
```

Reserved keys: `copy_from`, `new_id`, `display_source`, `safety_dps`,
`_*`. Anything else is treated as a UE cargo-row field name and set
verbatim by `MTBPInjector mutate-cargos`. The setter dispatches on
the actual property type (Float / Int / Int64 / Bool / Name);
unknown field names print a warning, fractional JSON on an Int field
warns rather than truncating silently.

### `Cargos_01.uasset`, NOT `Cargos.uasset`

MT loads both `/Game/DataAsset/Cargos.uasset` and
`/Game/DataAsset/Cargos_01.uasset`. Adding boosted rows to BOTH crashes
on world load (likely a duplicate-row registration collision when MT
merges the tables). Modifying just `Cargos.uasset` also crashes —
re-serialized bytes appear to fail an asset-registry hash. Modifying
`Cargos_01.uasset` only is the only stable path; that's where the
framework writes new rows. The mod tree never ships `Cargos.uasset`.

### Display labels via StringTable

Each cloned row's `Name` TextProperty uses HistoryType=StringTableEntry
pointing at `/Game/DataAsset/StringTables/Cargo.Cargo` with
`Value = display_source`. The new row's display label is whatever
that StringTable maps the source key to (e.g. Fuelx2's
`display_source: "Fuel"` → "Fuel" in the mission UI).

Inline FText (HistoryType=None or Base with a CultureInvariantString)
rendered blank for cloned rows in this MT build, even when the bytes
matched mod patterns we audited (ProxyOversizeCargo). Shipping a
modified `StringTables/Cargo.uasset` crashes on world load. Distinct
labels per variant need a SEPARATE-path StringTable asset
(`/Game/DataAsset/StringTables/CargoBoosted.uasset` or similar) —
not yet wired.

### Editor markers: name a mesh, get an actor

Place a mesh, name it, done. Position, height and rotation come from where the
mesh sits, so nothing is typed into a config and nothing drifts out of sync
with the scene.

    BusStop_<Name>      a bus stop, displayed as "<Name>"
    Home_<Name>         a POI people live at     (POI_House_C)
    Work_<Name>         a POI people work at     (POI_Office_C)
    Zone_<Key>_<NN>     corner NN of zone <Key>'s polygon

Underscores become spaces: Home_Old_Harbour reads "Old Harbour".

The mesh is still placed for BusStop/Home/Work -- the shelter, the house, the
office is the thing you see. Zone corners are survey markers: their mesh is
consumed and never ships, so a cone named Zone_Arini_01 leaves nothing in
game.

A zone needs 3+ corners. The trailing number is winding order, so walk the
boundary in one direction. The volume is derived from the corners' bounding
box -- the polygon is the only thing to author, and a key authored this way
replaces any zones.json entry of the same name.

Matching is on the object name, which is the part after the last DOT of the
asset path, not the last slash. The prefix needs its underscore: BusStopSign
is an ordinary mesh.

Checks: test_markers.py.

### A StringTable is only loaded if a package IMPORTS it

`TableId` on a Text is an FName, not an object reference, so pointing text at
a table imports nothing. The table is then never loaded and every lookup
returns `<MISSING STRING TABLE ENTRY>` -- with the entry sitting right there
in the shipped asset, which makes it look like the table is wrong when it is
merely absent.

Vanilla shows the shape to copy. `Jeju_World` carries the table twice in its
import list and references neither:

    -6679:  /Game/DataAsset/StringTables/BusStop  (class=Package, outer=0)
    -10455: BusStop  (class=StringTable, outer=-6679)

Their presence IS the load. Any map pointing text at a mod-owned table needs
both halves; the label patch adds them.

Cargos_01 already did this for ModCargo (package + object), which is why
custom cargo names survived the package rename above.

### A generated StringTable must rename its PACKAGE, not just its export

`make-stringtable` clones a vanilla table, clears it and adds our entries. It
used to rename only the export object and the namespace, so the asset shipped
still calling itself `/Game/DataAsset/StringTables/BusStop` -- a mod-priority
copy of the vanilla package whose table had been emptied down to our handful
of keys. Every vanilla bus stop then read `<MISSING STRING TABLE ENTRY>`,
including ones nothing of ours touches.

The path appears TWICE: once in the name map, once in the summary's
FolderName. FolderName is the one UE takes the asset's identity from, so
renaming the name-map entry alone still left the header pointing at the
vanilla package. Both are rewritten now.

ModCargo carried the same defect against `/Game/DataAsset/StringTables/Cargo`
for as long as it has shipped.

### The same wall, on bus stops

`BusStopDisplayName` written as inline culture-invariant FText renders as
`<MISSING STRING TABLE ENTRY>` in game -- the bus-stop version of the blank
cargo labels above. Same fix: a mod-owned table at a separate package path
(`/Game/DataAsset/StringTables/ModBusStop.uasset`, cloned from whatever the
game actually loads for `BusStop`), with the stop's text pointing at it as a
StringTableEntry. `build_bus_stringtable()` in clone_bp_actors.py.

Delivery points are NOT affected and keep the inline form: `PointName` is
MoreTuning's trick and it does display. The rule is per-property, not global.

### The safety-net constraint (world-load crash)

Shipping a new cargo row that no in-world DP references (input or
output) crashes MT on world load — empirically reproduced. The
`safety_dps` list per `new_cargos` entry names vanilla DP classes
that get the new cargo added to their `inputs` map (input-only
wholesale injection driven by `inject_new_cargos_into_safety_dps`).

Side effect: those vanilla DPs WILL accept the new cargo at their
in-game instances and pay out at the boosted rate. Pick low-traffic
destinations and tune `BasePayment` so the leakage is acceptable.
`Farm_Cabbage_C` + `Farm_Hemp_C` are the documented defaults.

The wholesale injection happens by deep-copying recipes from
`CargoImport/delivery_points/<class>.example.json` (extracted by
`import_cargo_data.py` at setup time), splicing the new cargo into
the FIRST recipe with a non-empty `inputs` map, and shipping the
modified DP CDO via `mutate-bp-cdo` (same path used for our own
mod BPs).

## Path Centralization (`mt_paths.py` + `.env`)

Every script imports `mt_paths` at the top. The module reads, in
priority order:
  1. Process environment variables (highest)
  2. `.env` at the repo root (`KEY=VALUE` lines, `#` comments)
  3. Auto-detection — `MT_GAME_DIR` is probed against the usual Steam
     install paths on every drive C:..Z: when neither env nor `.env`
     supplies it

Required keys (after auto-detect): `MT_GAME_DIR`, `MTMI_MAPPINGS`.
`MTMI_GAME_PAKDIR` derives from `MT_GAME_DIR` automatically.
`MTMI_GAME_CONTENT` defaults to `<repo>/vanilla_extract/MotorTown/
Content`, populated by `bootstrap_extract.py`. `MTMI_MAPPINGS_TAG`
defaults to the basename of `MTMI_MAPPINGS` without `.usmap`.

If a required path is missing or unresolvable, `mt_paths` writes a
multi-line diagnostic to stderr (variable name, what's wrong, where
to obtain the underlying content) and exits with code 2.

`build.bat` and `modp.bat` each have a small inline `.env` parser
so they pick up the same config when run standalone, plus the same
Steam-install auto-detect logic mirrored from `mt_paths`.

`.env.example` ships in the repo with every key documented.
`.env` is gitignored.

Never re-introduce a hardcoded `D:\MT\...` path in any script.

## Vendored Tools (`tools/`)

`tools/` holds `repak.exe`, `UAssetGUI.exe`, and `oo2core_9_win64.dll`,
committed to the repo so a fresh clone has the full toolchain. The
Oodle dll MUST sit next to `repak.exe` (repak looks beside its own exe
for it) — that's why both live in `tools/`. Without the dll, repak
fails to decompress Oodle-compressed pak entries with "failed to fill
whole buffer".

`mt_paths` exposes `TOOLS_DIR`, `REPAK`, `UASSETGUI`. build.bat and
modp.bat prefer `%~dp0tools\...` and fall back to PATH. Python scripts
use the `mt_paths` constants. The vendored repak is 0.2.2 — pinning
matters because pak format quirks are version-sensitive.

## Pak AES Key (`mt_paths.MT_AES_KEY`)

Motor Town's `MotorTown-Windows.pak` is AES-encrypted. The key is
public — it ships in `qxZap/ZMTLoader/run.py` as `MT_AES`. We embed it
as the default in `mt_paths.MT_AES_KEY` so extraction works out of the
box; a `.env` `MT_AES_KEY` overrides it when a game update rotates the
key. The current key:
`0xD9633F9140D5494AE4A469BDA384896BD1B9644D50D281E64ECFF4900B8E8E80`.

## Bootstrap Extract (`bootstrap_extract.py`)

Populates `vanilla_extract/MotorTown/Content` straight from the game
pak. Two modes:

  - **repak mode (default — self-contained)**: vendored `tools/repak.exe`
    + the built-in AES key extract from the encrypted
    `MotorTown-Windows.pak`. Needs only the game install. Per bundle,
    each `includes` entry is passed as `repak unpack --include`; repak
    accepts both specific files and directory prefixes (extracting
    directories recursively, so `.uexp`/`.ubulk` siblings come free).
  - **FModel mode (opt-in)**: `--fmodel` flag or no AES key + a set
    `MT_FMODEL_EXPORT`. Copies per-feature globs from an existing
    FModel export into `vanilla_extract/`. Idempotent.

Per-feature bundles (defined in `bootstrap_extract.BUNDLES`):

  | Bundle | What |
  |--------|------|
  | `cargos` | `DataAsset/Cargos*.uasset` + `StringTables/Cargo.uasset` |
  | `delivery_cdos` | every `Objects/Mission/Delivery/DeliveryPoint/*.uasset` |
  | `map_persistent` | `Maps/Jeju/Jeju_World.umap` (top-level persistent only) |
  | `map_cells` | one hand-picked WP template cell for clone_bp_actors |
  | `map_cells_all` | the entire `_Generated_/` tree (~12k files, ~2.7GB) |

Default invocation (`python bootstrap_extract.py`) pulls all bundles
except `map_cells_all`. The full cell tree is fetched **lazily** by
`clone_bp_actors.py` on the first pipeline run that touches a cell
beyond the template — it auto-invokes `bootstrap_extract.py
map_cells_all` whenever the local `_Generated_/` is sparse (< 100
cells). Since bootstrap defaults to the self-contained repak path,
this works with only the game installed. One-time cost, idempotent
after.

## UE Editor Install (`install_editor.py`)

`ue.py` runs inside the UE editor's Python runtime, which is a
separate process from the shell `build.bat` lives in. The editor
process can't see `.env`. `install_editor.py` uses Windows `setx` to
persist `MTMI_REPO_ROOT` as a user-level env var so the editor
inherits it on next launch, and prints the exact Python-console
one-liner to invoke `ue.py`. One-time setup unless the repo is moved.

## Pak Load Order Workaround

The mod deploys as `zzzz_MapChangeTest_P.pak` (lowercase prefix) so
it sorts after every other Cargos-overriding pak in the user's load
order — `ZZZ_qxZap_*_A.pak`, `zzProxysOversize*_A.pak`, etc.
Empirically confirmed: with an uppercase `ZZZ_` prefix our
`Cargos_01.uasset` was being shadowed by `zzProxys*` paks; switching
to `zzzz_` fixed it.

Note: only `_P.pak` paks load by default in this build of MT.
`_A.pak` files in the user's Paks folder (the proxy mods) are
inactive — disable suspicion of them as the override source if the
user's setup is unusual. The deploy step is still in `modp.bat` and
respects `MTMI_GAME_PAKDIR`.

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

## DEFINITIVE: Foliage Instance Transform Model (corrects 902ba02)

`902ba02` concluded FISMC instance transforms are stored in **absolute
world** coords. **That is wrong.** Verified against every
`InstancedFoliageActor` in the shipped Jeju map (426 IFAs, 397 tiles):

```
world = IFA.RootComponent0.RelativeLocation
      + FISMC.TranslatedInstanceSpaceOrigin
      + instance matrix translation (m[12..14])
```

The earlier probe only summed the last two, so it read centroids of
±25600 (cell-local) and mistook them for world coords. Anything built on
that model places foliage at the map origin instead of its tile.

### The actor-partition grid

Every vanilla IFA is named `InstancedFoliageActor_<G>_<TX>_<TY>_<TZ>`
with **G = 25600 uu (256 m), without exception**. The actor's root sits
at the tile **centre**, exact on all three axes:

```
RelativeLocation = ((TX + 0.5) * G, (TY + 0.5) * G, (TZ + 0.5) * G)
```

e.g. tile `(16, 51, -2)` -> `(422400, 1318400, -38400)`. Confirmed on
every cell checked; no exceptions, no rounding.

`TranslatedInstanceSpaceOrigin` is a small per-component precision
anchor (order ±10k), NOT a world offset. Instances may sit well outside
their tile vertically — Z bucketing is loose — so don't validate a
generated cell by asserting its instances fall inside the tile's Z span.

This grid is the EDITOR-side actor partition, independent of the
**runtime streaming grid** (`MainGrid`, cell extent 6400 -> 12800 wide)
that `register-and-clone` writes. An IFA spanning 25600 lives in
whatever runtime cell contains it; its reach is declared through the
cell's `ContentBounds`, which is why that field has to be right.

### Why this path exists: the UObject ceiling

Shipping foliage as one StaticMeshActor per instance crashes on load:

```
LowLevelFatalError [UObjectArray.cpp:612]
Maximum number of UObjects (2162688) exceeded when trying to add 1 object(s)
```

Each mesh actor costs >=2 UObjects (actor + component), so 3.39M meshes
= ~6.8M UObjects against a hard 2,162,688 cap. It is not a memory
problem and no amount of RAM fixes it. Measured ceiling for the actor
path is roughly 400-700k meshes; 427k loads fine.

As IFA cells the same 3.39M instances need 2,647 cells at ~12 UObjects
each (~32k total), because instances are transforms in a buffer, not
objects. 6M instances -> ~4,700 cells / ~56k UObjects / ~0.77 GB of
instance data. Streaming then bounds residency further.

### Pipeline ordering constraint

Both the cell-registration pass and the static-mesh injection
re-serialize the whole main map, so each one's cost is set by the map
size *at the time it runs*. Registering cells AFTER a full-density
injection means re-serializing 6.8M exports for an 11-cell mutation:
32 GB of RAM. `build.bat` therefore runs cells FIRST, on the 76k-export
vanilla map, and injects meshes into that result (peak 11.7 GB, 5 min).
Never reorder these two.

## DEFINITIVE: One WP Runtime Cell Per Grid Key

`RegisterCell` inserts each new cell into the streaming grid's
`LayerCellsMapping` under a key derived purely from position:

```
key = (gridX + 524800) + gridY * 1024      // gridX = floor(x / (extent*2))
```

It is a UE `TMap`: **one entry per key, last writer wins.** Register two
cells whose centres land in the same grid square and only the last is
ever reachable — the others ship in the pak, sit in the layer-cell
array, and never stream.

This bites foliage hard. Cells are grouped by the 25600 actor-partition
tile, whose centre `(tx+0.5)*25600` over the 12800 cell width gives
`gridX = 2*tx+1` — identical for every mesh in that tile. Shipping one
cell per `(tile, mesh)` produced 27,613 cells of which **2,164 were
reachable (7.8%)**, up to 18 colliding on one key, so ~265k of 3.38M
instances rendered. In game that looks like "parts of the foliage" —
plausible enough to be mistaken for a culling or LOD problem.

So: **one cell per tile**, carrying every mesh in it. Each mesh gets its
own IFA (+ root + FISMC) cloned inside that one cell, rather than one
IFA with N components, because the IFA's `Extras` carry a
FoliageType->info map we have not decoded — a cloned IFA keeps its own
self-consistent copy. Vanilla ships cells with up to 4 IFAs, so the
engine already loads this shape. Result: 2,647 cells, no collisions,
all 3,380,999 instances.

When retargeting a FISMC's mesh, rewrite THAT component's `StaticMesh`
import only. Rewriting every `StaticMesh` import in the file (fine when
a cell held one component) makes every mesh in a multi-FISMC cell
identical.

Corollary for any future cell work: if content goes missing in game but
the files are in the pak, count distinct grid keys before suspecting
the content itself.

## DEFINITIVE: Don't Script Foliage Deletion on a World Partition Map

UE 5.5 exposes exactly two foliage edits to script, and BOTH are unsafe on
a World Partition level. This cost a wiped level once; don't rediscover it.

**`comp.remove_instance()` does not persist.** A foliage component is only
a render proxy. `AInstancedFoliageActor` keeps the authoritative list in
its private `FoliageInfos` map (`TMap<TObjectPtr<UFoliageType>,
TUniqueObj<FFoliageInfo>>` — private, not a UPROPERTY, unreachable from
Python) and rebuilds the component from it on reload. Symptom: deleted
foliage reappears after undo or an editor restart, even though saving
looked fine.

**`AddInstances` / `RemoveAllInstances` destroy WP foliage.** They are the
only script-exposed edits (there is no remove-by-index), and the engine
source says why they can't be used:

```cpp
void AInstancedFoliageActor::RemoveAllInstances(UObject* Ctx, UFoliageType* T) {
    for (TActorIterator<AInstancedFoliageActor> It(World); It; ++It)
        IFA->RemoveFoliageType(&T, 1);          // EVERY IFA in the world
}
void AInstancedFoliageActor::AddInstances(...) {
    IFA = AInstancedFoliageActor::Get(World, true, World->PersistentLevel, Loc);
}                                                // re-adds to the PERSISTENT level
```

`RemoveAllInstances` strips the type from every IFA in the world, not just
the one you gathered survivors from; `AddInstances` re-adds into the
persistent level's IFA rather than the per-cell IFAs the instances came
from. On a WP map, where foliage lives in one IFA per cell, the pair is
data loss. They're built for simple non-partitioned levels.

Painted foliage also has no FoliageType ASSET — the type is
`NewObject<UFoliageType_InstancedStaticMesh>(this, NAME_None,
RF_Transactional)`, a subobject of the IFA. It IS reachable as
`FoliageType_InstancedStaticMesh_<n>` via `unreal.find_object(ifa, name)`,
which is how the report script enumerates types. Reachable, but useless:
the only things you can do with the handle are the two unsafe calls.

**What to do instead**

- Removing foliage from the SHIPPED PAK: the build-time cull in
  `inject_foliage_cells.py` (`MTMI_FOLIAGE_CULL_MESHES` / `_ZMAX` /
  `_FEATHER`). Non-destructive, re-runnable, editor-space Z.
- Removing foliage from the LEVEL: the Foliage editor's Select tool, by
  hand. It goes through `FFoliageInfo` and persists correctly.
- `ue_clean_foliage.py` reports counts only, and has no delete path.

---

## Fog: what does not work in Motor Town (investigated 2026-08-12)

A full day was spent trying to get localised fog onto the island. Recording
the dead ends so they are not retried.

**LocalFogVolume — impossible.** `ALocalFogVolume` and
`ULocalFogVolumeComponent` ARE in MT's `.usmap`, and the actor injects
correctly with all eight properties. It renders nothing.
`r.SupportLocalFogVolumes` is a read-only cvar gating shader permutations at
COOK time, and none of the 82 ini files the game ships mentions it — so the
permutations were never built and no runtime config can create them. Two
500-scale white volumes at 10x extinction were invisible at point blank.
Support was written, verified, and then removed (commit b5d5976).

**Volume-domain material on a static mesh — theoretically fine, never got it
rendering.** Contrary to a claim made mid-investigation, static meshes DO feed
volumetric fog: `SceneVisibility.cpp:1755` adds any StaticMesh whose
`ViewRelevance.bHasVolumeMaterialDomain` is set to `VolumetricMeshBatches`,
which the voxelization pass consumes. The heterogeneous-volumes branch needs
`Proxy->IsHeterogeneousVolume()`, false for a static mesh, so no diversion.
Everything checkable was verified correct — material domain Volume, blend
Additive, no illegal nodes, volumetric fog enabled in the level and confirmed
alive, Substrate off so `DoesPlatformSupportVolumetricFogVoxelization` passes,
voxelization permutations present. It still never appeared, in the editor or
in game. Unresolved.

**Traps that cost real time here:**
- A material that fails to compile is silently replaced by the Default
  Material. It looks exactly like a working material doing nothing. ALWAYS
  read `<project>/Saved/Logs/*.log` and the material editor Stats panel:
  the errors were sitting there for hours.
- `DepthFade` and anything reading scene depth is ILLEGAL in a Volume
  material ("Only transparent or postprocess materials can read from scene
  depth"), as is any blend mode other than Additive. Either one kills
  compilation.
- Check what material the MESH actually references before debugging a graph.
  Hours were spent tuning `M_Fog_03`, which nothing in the project referenced.
- Unversioned cooked assets do NOT store property names, so byte-searching a
  cooked `.umap` for a property name proves nothing either way. Uncooked
  editor assets DO store them, where absence means "at default".

**What did work and is worth keeping:** Jeju's own `ExponentialHeightFog` has
`bEnableVolumetricFog` set and `VolumetricFogDistance` raised to 15000, so
volumetric fog IS running in the shipped game. `merge_config.py` can ship any
console variable mod-aware, and `dump-schema` reads any engine class layout
from the mappings. Both came out of this and are useful independently.
