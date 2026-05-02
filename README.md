# MTMapInjector

A static-asset modding pipeline for **Motor Town: Behind the Wheel** (UE5.5).
Injects custom delivery points, parking, garages, and gas stations into the
persistent map without touching the editor at runtime, and ships per-cargo
payment overrides for offroad-friendly economy tweaks.

> The repo folder is named `MTLiveMap` for historical reasons — the **project**
> is `MTMapInjector`. Everything user-facing (env vars, error messages, this
> README) uses the project name; the folder name is incidental.

---

## What this does

- **Inject delivery points** described in `delivery_points.json` into Motor
  Town's Jeju world (and World-Partition cells), cloned from a vanilla DP
  class so game systems treat them as real DPs.
- **Per-recipe production configs** with full input/output cargo control,
  cargo-type filters, production speed/time, and timer-only "thin air"
  outputs.
- **Boosted-cargo variants** (`Fuelx2`, `CornBoxx5`, etc.) with per-km and
  base-payment multipliers, plus absolute base-pay and sqrt-curve overrides
  for offroad routes.
- **Parking, garages, gas stations, fuel pumps** placed via scene-marker
  meshes in your UE editor scene, then auto-routed to vanilla BP clones.
- **Mod-pak deployment** to the game's `Paks/` folder under a load-order-late
  filename (`zzzz_*_P.pak`) so changes win against installed mods.

---

## Required external tools

| Tool | What it's for | Where to get it |
|------|---------------|-----------------|
| **Python 3.10+** | Pipeline orchestration | https://www.python.org |
| **.NET 8 SDK** | Builds `MTBPInjector` (the C# UAssetAPI layer) | https://dotnet.microsoft.com |
| **UAssetGUI** | umap to JSON conversion | https://github.com/atenfyr/UAssetGUI/releases (drop on PATH) |
| **repak** | .pak packer/unpacker | https://github.com/trumank/repak/releases (drop on PATH as `repak.exe`) |
| **FModel** | Extract vanilla MT content (.uasset/.uexp/.umap tree) | https://fmodel.app |
| **UnrealMappingsDumper / Dumper-7** | Generate the `.usmap` mappings file MT needs | https://github.com/OutTheShade/UnrealMappingsDumper |
| **oo2core_9_win64.dll** | Oodle decompression for repak | Copy from any UE game install (e.g. Warframe's `Tools/Oodle`); place next to `repak.exe` |
| **UE 5.5 Editor (optional)** | Author scene-marker meshes for parking/DPs | Epic Games Launcher |

---

## One-time setup

1. **Extract the game.** Open FModel, point at
   `<Steam>/steamapps/common/Motor Town/MotorTown/Content/Paks`, dump
   `MotorTown.pak` (or the iostore .ucas/.utoc) to disk. You should end up
   with a `MotorTown/Content` directory full of `.uasset`/`.umap` files.
2. **Generate the .usmap.** Run UnrealMappingsDumper / Dumper-7 against a
   running Motor Town session. Save the resulting `MotorTown###P#.usmap`
   somewhere predictable.
3. **Set the four required paths** at the top of `fulltest.bat`. Look for
   the `set "MTMI_*=..."` block and edit:
   - `MTMI_GAME_CONTENT` — the extracted `MotorTown/Content` folder.
   - `MTMI_MAPPINGS` — absolute path to your `.usmap` file.
   - `MTMI_MAPPINGS_TAG` — same as the `.usmap` filename without the
     extension (e.g. `MotorTown718P1`).
   - `MTMI_GAME_PAKDIR` — your `Motor Town/MotorTown/Content/Paks/` folder.

   These propagate to every Python step. Running a Python script standalone
   (without `fulltest.bat`) requires you to `set` them in your shell first
   — the scripts will refuse to run otherwise and tell you exactly which
   one is missing.
4. **Build the C# layer once:** `dotnet build -c Release MTBPInjector` — or
   just run `fulltest.bat`, which builds it in step 0.

If a path is wrong or missing, both the Python scripts and the .bat files
print a multi-line diagnostic explaining what each variable is, what it
should look like, and how to obtain the underlying content. Read those
errors — they are the fastest fix path.

---

## Quick start

```bat
fulltest.bat
```

That's it. The pipeline:

1. **`[0/6] Build`** — `dotnet build` `MTBPInjector` (no-op if up to date).
2. **`[1/6] Clean`** — wipes the mod's `_Generated_/`, `DC/Actors/`, and
   `DeliveryPoint/` folders so prior-run artifacts don't leak into the new
   pak.
3. **`[2/6] Meshes`** — `import_meshes.py` reads `static_meshes.json`
   (exported from the editor by `ue.py`) and routes each entry into either
   `map_work_changes.json` (raw mesh) or as a delivery-point/parking
   marker.
4. **`[3/6] Convert`** — `convert2.py` rewrites a JSON copy of
   `Jeju_World.umap` with the new mesh and marker placements.
5. **`[4/6] Map`** — UAssetGUI `fromjson` rebuilds `Jeju_World.umap` from
   the patched JSON.
6. **`[5/6] Actors`** — `clone_bp_actors.py` walks `delivery_points.json`,
   creates per-DP mod BP classes, generates boosted cargo rows in
   `Cargos_01.uasset`, and clones BP instances into the persistent level
   (and into auto-registered World-Partition cells for far-flung coords).
7. **`[6/6] Pack`** — `modp.bat` runs `repak pack` and copies the resulting
   `zzzz_MapChangeTest_P.pak` into the game's `Paks/` folder.

Selective stage flags: `--skip-meshes`, `--only-actors`, etc. Run
`fulltest.bat --help` for the full list.

---

## delivery_points.json — the user-facing config

> A heavily-commented reference copy lives in `delivery_points.example.json`.
> If you want to start fresh, `cp delivery_points.example.json delivery_points.json`
> and edit. The pipeline only ever reads `delivery_points.json`.

This is the only file you edit for delivery-point work. Top-level
structure:

```json
{
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
  ],

  "MyDP": {
    "label": "My Delivery Point",
    "marker_color": "#3B0764",
    "icon": "/Game/.../ConstructionSite",
    "recipes": [
      {
        "inputs":  {"Fuelx2": 1},
        "outputs": {"CornBox": 3},
        "speed": 5.0,
        "time_seconds": 30.0
      }
    ]
  }
}
```

### `new_cargos` — adding custom cargo variants

The single mechanism for adding new cargo rows to `Cargos_01.uasset`.
Each entry clones a vanilla cargo row into a new id and applies
arbitrary field overrides. Recipes (anywhere in this file or in the
auto-injected vanilla safety-net DPs) reference the new cargo by
`new_id`.

| Key | Type | What it does |
|-----|------|--------------|
| `copy_from` | str | Vanilla cargo whose row gets cloned (template). |
| `new_id` | str | The new row's name. Recipes reference this string. |
| `display_source` | str (optional) | Existing cargo whose StringTable label your new cargo borrows in the mission UI. Defaults to `copy_from`. Custom display labels need a separate StringTable asset that's not yet wired up. |
| `safety_dps` | list[str] | **Required.** Vanilla DP class names that will accept this cargo as input. MT crashes on world load if a cargo has zero vanilla consumers. Pick destinations whose payout leakage is acceptable. |
| Any other key | matches UE field type | Cargo-row field name set verbatim — `PaymentPer1Km`, `BasePayment`, `SpawnProbability`, `PaymentSqrtRatio`, `NumCargoMin`, `NumCargoMax`, `Fragile`, `bUseDamage`, `bAllowStacking`, `bTimer`, `BaseTimeSeconds`, ... see the `_NEW_CARGO_FIELDS` block in `delivery_points.example.json` for the full list with vanilla defaults and types. Run `python import_cargo_data.py` to extract a vanilla cargo dump under `CargoImport/cargos/catalog.json` and copy values 1:1. |

The setter dispatches on the actual UE property type
(Float / Int / Int64 / Bool / Name). Unknown field names print a
warning instead of silently failing. A fractional JSON value on an Int
field also warns rather than truncating quietly.

### The safety-net constraint

Shipping a new cargo row whose `new_id` is referenced by ZERO vanilla
DPs crashes MT on world load. The `safety_dps` list per cargo holds
the minimum vanilla mission-graph footprint needed to keep the
runtime registry consistent — those listed classes will accept the
new cargo as input alongside their vanilla recipes.

That coverage *will* generate paid missions for the new cargo at
those vanilla DPs (the boost leakage). Pick low-traffic
destinations, or set `BasePayment` / per-km values that make sense
even when delivered to a random farm. `Farm_Cabbage_C` and
`Farm_Hemp_C` are reasonable defaults.

### Per-DP fields

Each named entry (e.g. `MyDP`) becomes a delivery point in-game. The
in-game label defaults to the entry KEY with underscores replaced by
spaces, capped at 14 characters.

| Field | What it does |
|-------|--------------|
| `label` | Optional in-game name (max 14 chars). |
| `template` | Vanilla DP class to clone. Default `farm` (Farm_Corn_C). Other classes have shown crashes; add new templates to `bp_registry._TEMPLATES` only after end-to-end validation. |
| `source_class`, `source_actor` | Optional explicit overrides. Use only for experimental clones. |
| `recipes` | List of production recipes (see below). |
| `marker_color`, `icon`, `output_storage_cap` | RESERVED — propagated through the pipeline but not yet wired into game output. |

### Recipe fields

| Field | What it does |
|-------|--------------|
| `inputs` | `{Cargo: Count}` — exact cargo names required as input. Vanilla names from `cargos/cargo_names.txt` OR `new_id` values from the `new_cargos` list. |
| `outputs` | `{Cargo: Count}` — what the DP produces. Same name space as `inputs`. |
| `input_types`, `output_types` | `[Type]` or `{Type: Count}` — accept ANY cargo of the given `EDeliveryCargoType` enum value. Listed in `CargoImport/cargos/types.txt`. |
| `speed` | `ProductionSpeedMultiplier` — 1.0 default, 5.0 = 500%. |
| `time_seconds` | `ProductionTimeSeconds` for one cycle. |

A recipe with no `inputs`/`input_types` is timer-only — the DP
produces its outputs on a clock without needing an inbound delivery.

---

## Repository layout

```
MTMapInjector/
├── README.md                  ← you are here
├── AGENTS.md                  ← deeper notes on UE5 internals + patterns
├── delivery_points.json       ← user-facing DP config (your working copy)
├── delivery_points.example.json ← reference template with full inline docs
├── static_meshes.json         ← scene export (written by ue.py inside the editor)
├── map_work_changes.json      ← intermediate (mesh + marker placements)
│
├── fulltest.bat               ← entry point (paths declared at top)
├── modp.bat                   ← pak + deploy step (called by fulltest)
├── cell_test.bat              ← faster iteration on cell/actor changes only
├── build_and_deploy.bat       ← build + deploy without rebuilding the map
│
├── mt_paths.py                ← env-var resolver (single source of truth)
├── bp_registry.py             ← BP-class templates + delivery_points.json loader
├── clone_bp_actors.py         ← actor clone + boosted-cargo + DP-CDO mutator
├── import_meshes.py           ← static_meshes.json -> map_work_changes.json
├── import_cargo_data.py       ← extract vanilla cargo+DP catalog into CargoImport/
├── convert2.py                ← Jeju_World JSON patcher
├── ue.py                      ← editor-side scene exporter
│
├── MTBPInjector/              ← C# UAssetAPI driver (the actual binary mutator)
├── CargoImport/               ← vanilla catalog ref data (run import_cargo_data.py)
└── MapChangeTest_P/           ← the mod's pak source tree (gets packed each run)
```

---

## Running scripts standalone

Every Python script reads its paths from `mt_paths.py`, which in turn
reads the `MTMI_*` environment variables. To run a single script outside
of `fulltest.bat`, set the vars in your shell first:

```bat
set MTMI_GAME_CONTENT=D:\MT\Output\Exports\MotorTown\Content
set MTMI_MAPPINGS=D:\MT\MotorTown718P1.usmap
set MTMI_MAPPINGS_TAG=MotorTown718P1
set MTMI_GAME_PAKDIR=D:\SteamLibrary\steamapps\common\Motor Town\MotorTown\Content\Paks
python clone_bp_actors.py --config map_work_changes.json --gen-dir ...
```

If any required var is unset or its path doesn't exist, the script exits
with a multi-line help block.

---

## Troubleshooting

**"MTMapInjector pipeline cannot start — required paths are missing."**
A required env var isn't set or doesn't resolve to an existing path. The
error block names every missing variable, what it's for, and how to
obtain it. Edit the top of `fulltest.bat` and re-run.

**Game crashes on world load after adding a `new_cargos` entry.**
Its `safety_dps` list is empty, missing, or points at vanilla DP
classes that aren't loaded. Set it to at least one valid class —
`Farm_Cabbage_C` and `Farm_Hemp_C` are reliable defaults. Without
vanilla DPs accepting the new cargo, MT's mission registry rejects
the world during load.

**`fulltest.bat` errors with `'X' is not recognized as an internal command`.**
The .bat file got LF line endings somehow. Run `unix2dos fulltest.bat` (or
re-checkout from git on Windows so autocrlf restores CRLF).

**`repak` fails with `oodle hash mismatch` or `oo2core_9_win64.dll not found`.**
Drop the matching Oodle dll next to `repak.exe`. The Warframe install
ships a compatible one at
`Tools/Oodle/x64/final/oo2core_9_win64.dll`.

**My mod's changes don't show up in-game.**
Pak load order. Our pak deploys as `zzzz_MapChangeTest_P.pak` to load
after the alphabetically-late mods that shadow `Cargos.uasset`
(`zzProxysOversize*`, `ZZZ_qxZap_*`). If you've installed something even
later in the alphabet, rename our pak's prefix in `modp.bat` to load
after it.

**Cargo display is blank.**
You either omitted `display_source` (or set it to a name that has no
StringTable entry). Set `display_source` to an existing vanilla cargo
whose label you're happy borrowing — typically the same value as
`copy_from`. Distinct labels per variant need a separate-path
StringTable asset that isn't wired up yet.

**Annotating placements.**
Drop a `{"_comment": "..."}` (or any dict whose keys all start with
`_`) anywhere in `map_work_changes.json["delivery_points"]`. The
mesh importer preserves these across re-runs and the actor cloner
silently ignores them.

---

## Status of features

- Done: Delivery-point injection (per-recipe + auto-WP-cell registration).
- Done: Custom cargo variants via `new_cargos` — generic field setter
  covers every Float / Int / Int64 / Bool field on the cargo row, with
  per-cargo `safety_dps` for crash-free deployment.
- Done: Parking / garage / gas pump scene markers.
- Done: Pak load-order workaround (`zzzz_` prefix).
- Done: Path centralization (`mt_paths.py` + `MTMI_*` env vars,
  validation block at the top of `fulltest.bat`).
- Done: `_comment` tolerance in `map_work_changes.json` delivery list.
- Pending: Marker color and icon — propagated through the pipeline but not
  yet mutated into the game's marker actor (see AGENTS.md "Marker / Icon
  Mutation Pending").
- Pending: Output storage cap — lives on a separate
  `MTDeliveryPointInventoryRatio` actor that needs targeted mutation.
- Pending: Distinct boosted-cargo display labels — blocked on shipping a
  separate-path StringTable; modifying vanilla `Cargo.uasset` crashes the
  game.
