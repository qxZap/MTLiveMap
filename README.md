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
  "include_pickups": false,
  "boost_safety_dps": ["Farm_Cabbage_C", "Farm_Hemp_C"],
  "cargo_payment_overrides": { ... },
  "cargo_base_overrides":    { "Fuelx2": 100000 },
  "cargo_spawn_overrides":   { ... },
  "cargo_sqrt_overrides":    { ... },
  "_doc": { "...inline schema docs..." },

  "MyDP": {
    "label": "My Delivery Point",
    "marker_color": "#3B0764",
    "icon": "/Game/.../ConstructionSite",
    "recipes": [
      {
        "inputs":  {"Fuel": 1, "boosted": 5},
        "outputs": {"CornBox": 3},
        "speed": 5.0, "time_seconds": 30.0
      }
    ]
  }
}
```

### Top-level knobs

| Key | What it does |
|-----|--------------|
| `include_pickups` | When **true** (default), every vanilla DP that consumes a source cargo also accepts the boosted variant. When **false**, only the safety-net subset is touched. |
| `boost_safety_dps` | List of vanilla DP class names that always accept the boosted variant. Required because shipping a boosted cargo with zero vanilla consumers crashes MT on world load. Default: `Farm_Cabbage_C`, `Farm_Hemp_C`. **Empty list crashes the game.** |
| `cargo_payment_overrides` | `{Cargo: mult}` — multiplies `PaymentPer1Km` and `BasePayment` of an existing row in place. Cargo name unchanged, vanilla missions inherit the boost. |
| `cargo_base_overrides` | `{Cargo: int}` — sets `BasePayment` to an absolute value. **Critical for offroad** routes where per-km pay doesn't fire. |
| `cargo_spawn_overrides` | `{Cargo: int}` — sets `SpawnProbability` (random mission gen frequency). |
| `cargo_sqrt_overrides` | `{Cargo: float}` — sets `PaymentSqrtRatio` (1.0 default; <1 flattens long-route payouts, >1 amplifies). |

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
| `inputs` | `{Cargo: Count}` — exact cargo names required as input. |
| `outputs` | `{Cargo: Count}` — what the DP produces. |
| `input_types`, `output_types` | `[Type]` or `{Type: Count}` — accept ANY cargo of the given `EDeliveryCargoType` enum value. Listed in `CargoImport/cargos/types.txt`. |
| `speed` | `ProductionSpeedMultiplier` — 1.0 default, 5.0 = 500%. |
| `time_seconds` | `ProductionTimeSeconds` for one cycle. |
| `boosted` | **Magic key inside `inputs` or `outputs`.** Value is the per-km payment multiplier. The framework auto-clones every named cargo on the same side into a `<Source>x<N>` variant in `Cargos_01.uasset` (PaymentPer1Km × N, BasePayment × N) and adds it alongside the source at the same count. Combine with `cargo_base_overrides` for hard-set base pay. |
| Direct boosted name | Reference a boosted cargo by name directly — e.g. `outputs: {"Fuelx2": 1}`. The pattern `<vanilla_cargo>x<int>[p<frac>]` (e.g. `Fuelx2`, `CornPalletx2p5`) auto-creates the row at the implied multiplier. Use when you want ONLY the boosted variant on a side. |

### The boost chain

Read the `_README_BOOST_CHAIN` block at the top of `delivery_points.json`
for the full story. The short version: any boosted cargo you create must
be referenced by at least one vanilla DP (the safety-net DPs in
`boost_safety_dps`), or MT crashes on world load. The boost will leak into
those vanilla DPs' missions — pick destinations whose payout leakage you
can live with, and use `cargo_base_overrides` to keep boost values on the
TF-side reasonable.

---

## Repository layout

```
MTMapInjector/
├── README.md                  ← you are here
├── AGENTS.md                  ← deeper notes on UE5 internals + patterns
├── delivery_points.json       ← user-facing DP config
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

**Game crashes on world load after enabling a boosted cargo.**
Either `boost_safety_dps` is empty, or the cargo isn't referenced by any
vanilla DP in your loaded mod set. Make sure `boost_safety_dps` is
non-empty and the listed classes exist (the defaults `Farm_Cabbage_C` and
`Farm_Hemp_C` always do).

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
Mod-shipped boosted rows reuse the source cargo's StringTable key, so
`Fuelx5` shows as `Fuel` in the mission UI. A separate-path StringTable
asset for distinct boosted labels is on the to-do list.

---

## Status of features

- Done: Delivery-point injection (per-recipe + auto-WP-cell registration).
- Done: Boosted-cargo variants with per-km, base-pay, sqrt, and spawn knobs.
- Done: Parking / garage / gas pump scene markers.
- Done: Pak load-order workaround (`zzzz_` prefix).
- Pending: Marker color and icon — propagated through the pipeline but not
  yet mutated into the game's marker actor (see AGENTS.md "Marker / Icon
  Mutation Pending").
- Pending: Output storage cap — lives on a separate
  `MTDeliveryPointInventoryRatio` actor that needs targeted mutation.
- Pending: Distinct boosted-cargo display labels — blocked on shipping a
  separate-path StringTable; modifying vanilla `Cargo.uasset` crashes the
  game.
