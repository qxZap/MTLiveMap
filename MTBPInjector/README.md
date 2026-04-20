# MTBPInjector

A .NET 8 console tool that uses the UAssetAPI library directly to inject blueprint
actors (parking spots, delivery points, garages, etc.) into Motor Town's
`Jeju_World.umap`. Bypasses the limitations of UAssetGUI's CLI.

## Why this exists

The Python+UAssetGUI pipeline works for static meshes and dealerships but
crashes when injecting blueprint actors (`Interaction_ParkingSpace_Large_C`
etc.) into the main `Jeju_World.umap`. UAssetAPI used directly gives us:

- Programmatic control over imports/exports/dependencies
- Ability to fix subtle binary issues UAssetGUI doesn't expose
- Round-trip cells that UAssetGUI's CLI can't (EnumPropertyData null bug)

## Setup (one-time)

1. **Install .NET 8 SDK** (not just runtime):
   - Download: https://dotnet.microsoft.com/download/dotnet/8.0
   - Pick "SDK 8.0.x" for Windows x64
   - Verify: `dotnet --version` should print `8.0.x`

2. **Restore dependencies**:
   ```
   cd D:\MTLiveMap\MTBPInjector
   dotnet restore
   ```

3. **Build**:
   ```
   dotnet build -c Release
   ```

   Output binary: `bin\Release\net8.0\MTBPInjector.exe`

## Usage

### Inject a parking actor into a sub-level cell

```
MTBPInjector.exe inject-cell ^
    --cell D:\MT\Output\Exports\MotorTown\Content\Maps\Jeju\Jeju_World\_Generated_\<CELL>.umap ^
    --output MapChangeTest_P\MotorTown\Content\Maps\Jeju\Jeju_World\_Generated_\<CELL>.umap ^
    --mappings MotorTown718P1.usmap ^
    --x -614930 --y -91700 --z 35080 ^
    --bp /Game/Objects/ParkingSpace/Interaction_ParkingSpace_Large
```

### Batch inject from JSON

```
MTBPInjector.exe inject-batch ^
    --mappings MotorTown718P1.usmap ^
    --config map_work_changes.json ^
    --game-content D:\MT\Output\Exports\MotorTown\Content\Maps\Jeju\Jeju_World\_Generated_ ^
    --mod-content MapChangeTest_P\MotorTown\Content\Maps\Jeju\Jeju_World\_Generated_
```

For each `blueprint_actors` entry in `map_work_changes.json`, this:
1. Finds the cell whose grid covers the entry's coordinates
2. Loads it from `--game-content`
3. Injects the parking actor preserving the cell's existing content
4. Saves to `--mod-content`

## Hooking into fulltest.bat

Add this step before the main map build:

```
echo [2c/5] Injecting BP actors into cells...
MTBPInjector\bin\Release\net8.0\MTBPInjector.exe inject-batch ^
    --mappings MotorTown718P1.usmap ^
    --config map_work_changes.json ^
    --game-content D:\MT\Output\Exports\MotorTown\Content\Maps\Jeju\Jeju_World\_Generated_ ^
    --mod-content MapChangeTest_P\MotorTown\Content\Maps\Jeju\Jeju_World\_Generated_
if errorlevel 1 echo   BP injection failed, skipping
```
