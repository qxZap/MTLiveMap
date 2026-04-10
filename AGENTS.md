# UAssetAPI JSON Modding Reference (Jeju_World / MotorTown)

## Conversion Pipeline

```
# .umap -> .json
UAssetGUI.exe tojson Jeju_World.umap Jeju_Worldaa.json VER_UE5_5 MototTown

# .json -> .umap
UAssetGUI.exe fromjson Jeju_Worldaa.json Jeju_World.umap VER_UE5_5
```

Dirty/unreadable serialized parts in the JSON are fine — UAssetAPI can round-trip them as base64 `RawExport` data.

## Key Facts About the Jeju_World JSON

- **76,469 exports**, all typed `UAssetAPI.ExportTypes.RawExport, UAssetAPI` (unversioned properties = binary blobs, NOT structured JSON property lists)
- **IsUnversioned: true** — properties are serialized as binary with unversioned property headers, not as named JSON fields
- **PersistentLevel** is at export **26486** (0-indexed: 26485)
- All export `Data` fields are **base64-encoded raw binary**, not JSON property arrays

## PersistentLevel Binary Layout

```
[0:10]    Unversioned property header (5 fragments, 2 bytes each)
[10:923]  Property data (serialized ULevel properties)
[923:927] int32 actor_count (e.g., 4502)
[927:927+count*4]  Actor list: int32 export indices (1-based)
[after actors]     URL FString: starts with int32(7) + "unreal\0" + host + map ("/Game/Maps/MainMenu") + portal + ops + port(7777) + valid(1)
[after URL]        Model ref, ModelComponent ref, WorldSettings ref, zero padding
```

### Critical: Patching the Actor List

To add actors to PersistentLevel you MUST do both:
1. Add actor export numbers to `CreateBeforeSerializationDependencies` (JSON field)
2. **Increment the int32 actor count** at offset 923 AND insert int32 entries before the URL marker in the binary `Data`

If you insert entries without incrementing the count, the engine reads the old count, stops short, then tries to parse actor data as the URL string — instant crash.

### Finding the Actor Count Programmatically

The count is at a variable offset. To find it:
- Locate the URL marker: `struct.pack("<i", 7) + b"unreal\x00"`
- Scan backwards from the URL for an int32 `N` where `probe_offset + 4 + N*4 == url_offset`

## MTDealerVehicleSpawnPoint Export Structure

### Actor Export (RawExport)

```
ClassIndex:    -1512  (MTDealerVehicleSpawnPoint class)
TemplateIndex: -3196  (Default__MTDealerVehicleSpawnPoint)
OuterIndex:    26486  (PersistentLevel)
ObjectFlags:   RF_Transactional
Extras:        ""     (empty string for RawExport)
```

Binary Data layout (header `0002020203023903`, 8 bytes):
```
[0:8]   Unversioned property header
[8:12]  VehicleClass (int32 import ref, e.g., -551 for EnfoGT_C)
[12:16] EditorVisualVehicleClass (same as VehicleClass)
[16:20] SceneComponent (int32 export ref -> RootScene export number)
[20:24] RootComponent (same as SceneComponent)
[24:28] Zero padding
[28:]   Actor extras: int32(1) + int32(strlen) + label_bytes + 16-byte GUID + 16-byte zero padding
```

Dependencies:
```
CreateBeforeSerializationDependencies: [vehicle_class_import, rootscene_export]
SerializationBeforeCreateDependencies: [dealer_class, default_dealer, rootscene_template]
CreateBeforeCreateDependencies: [level_num]
```

### RootScene Export (SceneComponent, RawExport)

```
ClassIndex:    -1473  (SceneComponent class)
TemplateIndex: -8493  (RootScene template under Default__MTDealerVehicleSpawnPoint)
OuterIndex:    <actor_export_num>
ObjectFlags:   RF_Transactional, RF_DefaultSubObject
IsInheritedInstance: true
Extras:        ""
```

Binary Data layout (header `0505`, 2 bytes):
```
[0:2]   Unversioned property header
[2:26]  RelativeLocation: 3 x float64 (X, Y, Z)
[26:50] RelativeRotation: 3 x float64 (Pitch, Yaw, Roll)
[50:58] 8 bytes zero padding
```

Total: 58 bytes.

Dependencies:
```
SerializationBeforeCreateDependencies: [scene_class, rootscene_template]
CreateBeforeCreateDependencies: [actor_export_num]
```

## Import Chain

```
-7353: /Script/MotorTown               (Package, outer=0)
-1512:   MTDealerVehicleSpawnPoint      (Class, outer=-7353, ClassPackage=/Script/CoreUObject)
-3196:   Default__MTDealerVehicleSpawnPoint (MTDealerVehicleSpawnPoint, outer=-7353, ClassPackage=/Script/MotorTown)

-7348: /Script/Engine                   (Package, outer=0)
-1473:   SceneComponent                 (Class, outer=-7348, ClassPackage=/Script/CoreUObject)
-8493:   RootScene                      (SceneComponent, outer=-3196, ClassPackage=/Script/Engine)

Vehicle imports (example: EnfoGT):
-6424: /Game/Cars/Models/EnfoGT/EnfoGT  (Package, outer=0)
-551:    EnfoGT_C                        (BlueprintGeneratedClass, outer=-6424, ClassPackage=/Script/Engine)
```

Vehicle path convention: `/Game/Cars/Models/{VehicleKey}/{VehicleKey}` with class `{VehicleKey}_C`.

## Unversioned Property Headers

Different MTDealerVehicleSpawnPoint exports have different headers depending on which properties are set. The most common (144/182 exports): `0002020203023903` — sets VehicleClass, EditorVisualVehicleClass, SceneComponent, RootComponent.

There are 24 unique headers across 182 dealer exports. Some set additional properties (resulting in larger data). The `0002020203023903` variant is the safe minimal one.

## Other Notes

- `DependsMap` must have one entry per export (append empty `[]` for each new export)
- `Generations[0].ExportCount` and `NameCount` must be updated
- `find_or_add_import` handles both reusing existing imports and creating new ones + adding names to NameMap
- SerialSize and SerialOffset can be left as 0 — UAssetAPI recalculates them on `fromjson`
