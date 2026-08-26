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

## Requirements

A fresh clone needs only four things. Everything else — repak,
UAssetGUI, the Oodle dll, and the pak AES key — ships inside the repo.

| Need | Why | Where |
|------|-----|-------|
| **Motor Town installed** | Source for the vanilla content (extracted on demand) | Steam |
| **This repo cloned** | The framework + vendored tools (`tools/`) | — |
| **Python 3.10+ and .NET 8 SDK** | Pipeline + the C# UAssetAPI layer | python.org / dotnet.microsoft.com |
| **A `.usmap` for your MT version** | UAssetAPI needs it to parse NormalExports | Generate with UnrealMappingsDumper / Dumper-7, or grab a community release |
| **UE 5.5 Editor** *(optional)* | Authoring scene-marker meshes | Epic Games Launcher |

The game's `MotorTown-Windows.pak` is AES-encrypted. The key is public
(it ships in [qxZap/ZMTLoader](https://github.com/qxZap/ZMTLoader)), so
the bundled `tools/repak.exe` extracts the pak directly — **no FModel,
no manual extraction step.**

---

## One-time setup

1. **`cp .env.example .env`** and open it in any editor.
2. **Point `MTMI_MAPPINGS`** at your `.usmap` file. That's the only
   required value — `MT_GAME_DIR` auto-detects from common Steam install
   paths, and the AES key + tools are built in.
3. **Bootstrap the local cache:**
   ```
   python bootstrap_extract.py
   ```
   This extracts just the cargo data, vanilla DP CDOs, the persistent
   Jeju map, and one template WP cell **straight from the game's pak**
   into `<repo>/vanilla_extract/` (~285MB). The full ~2.7GB WP cell
   tree is pulled **lazily on the first pipeline run that needs it** —
   you don't have to think about it. Re-runs are idempotent.
4. **(Editor-side only)** If you're going to author scene meshes in the
   UE editor, run `python install_editor.py` once. It persists
   `MTMI_REPO_ROOT` as a user-level env var so the editor's Python
   runtime knows where to write `static_meshes.json`, and prints the
   exact Python-console one-liner to invoke `ue.py`.
5. **Build the C# layer once:** `dotnet build -c Release MTBPInjector`
   — or just run `build.bat`, which builds it in step 0.

If anything's misconfigured, every script prints a multi-line
diagnostic naming the missing piece, what it's for, and how to obtain
it. Read those errors — they are the fastest fix path.

### Already have an FModel export?

If you've already extracted the content with FModel and would rather
not re-read the 3GB pak, point `MT_FMODEL_EXPORT` at the export folder
in `.env` and run `python bootstrap_extract.py --fmodel`. The result in
`vanilla_extract/` is identical.

---

## Quick start

```bat
build.bat
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
   creates per-DP mod BP classes, generates new cargo rows in
   `Cargos_01.uasset`, and clones BP instances into the persistent level
   (and into auto-registered World-Partition cells for far-flung coords).
   Auto-fetches missing WP cells from the game pak on first need.
7. **`[6/6] Pack`** — `modp.bat` runs `repak pack` and copies the resulting
   `zzzz_MapChangeTest_P.pak` into the game's `Paks/` folder.

Selective stage flags: `--skip-meshes`, `--only-actors`, etc. Run
`build.bat --help` for the full list.

---

## Build times (rough ETAs)

Measured on an NVMe SSD, mid-range desktop. Yours will vary, but the
shape holds: **one stage dominates.**

A normal **warm build** (vanilla data already extracted) is **~4 minutes**,
almost entirely in the BP-injection stage:

| Stage | Time |
|-------|------|
| `[0]` dotnet build (incremental) | ~3 s |
| `[clearance]` pak fingerprint check | ~0.1 s |
| `[1]` clean | instant |
| `[2]` import_meshes | ~0.1 s |
| `[3]` convert2 (patch map JSON) | ~6 s |
| `[4]` UAssetGUI fromjson (rebuild umap) | ~5 s |
| `[5]` **clone_bp_actors (BP injection)** | **~3.5–4 min** |
| `[6]` modp (repak pack + deploy, 385 MB) | ~1 s |
| `[7]` verify_build (integrity) | ~0.5 s |

`clone_bp_actors` is ~93% of the time because it re-serializes the
82k-export persistent `Jeju_World.umap` twice (read + write) to inject
the delivery-point actors. This is inherent to static injection. Use
`build.bat --skip-actors` when iterating on cargo/recipe changes that
don't move any delivery points — that drops the build to **~15 s**.

**First run / after a game update** adds a one-time extraction pass.
It's fast (repak + AES is parallel):

| Operation | Time |
|-----------|------|
| bootstrap cargos + DP CDOs + persistent map + template cell | ~2 s |
| bootstrap full WP cell tree (2.7 GB, lazy — only when needed) | ~5 s |
| cold map-cache (UAssetGUI tojson, first time) | ~4 s |
| first dotnet compile (cold) | ~30–60 s |

After the first build the pak fingerprint is cached, so the clearance
step is a ~0.1 s no-op until the game actually updates — at which point
it detects the change, says so, and re-extracts only what's stale.

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

Build-time-only keys are told apart from UE field names by their SHAPE:
a key containing an underscore, or written entirely in lowercase, is
ours and never reaches the setter. UE cargo fields are PascalCase, and
its booleans always have a capital after the `b` (`bUseDamage`). Adding
a new knob does not mean editing `Program.cs`.

### `pricing.py` — what a delivery is worth

Prices are computed, not hand-written:

    pay = taper(kg) * 10/kg * batch * (1 + km / 5)     floor 1,000

`kg` is the cargo's max weight from the game's own data, `batch` is the
licence tier the load needs (1–5, derived from `CargoType` with tankers
forced to B5), and `km` is the **shortest** producer→consumer run for
that cargo, measured from where the points actually sit. Weight is
linear to 5 t and square-root above, so a 30 t transformer is expensive
without out-earning a day of pallet work.

`BasePayment` is one number per *cargo row*, not per route, so the
distance has to be resolved at build time from the recipe graph. The
shortest run sets the price because that is the run a player will
choose; longer hauls of the same cargo pay the same.

Distance cannot be left to the game here. MT's own `PaymentPer1Km`
multiplies by the **road** distance it computes, and that calculation
only finds a road on the vanilla network — which the island is not on.
That is why a long island haul of a vanilla cargo pays nearly nothing.

    python pricing.py            # show the table, change nothing
    python pricing.py --write    # write BasePayment into delivery_points.json

Writing the numbers back into the JSON keeps them visible in `git diff`
rather than conjured during a build. Three optional keys on a cargo
entry override the derivation: `weight_kg`, `batch`, and `base_payment`
(which skips the model entirely — Pezzi is contraband, priced by what it
is rather than what it weighs). The run also lists every vanilla row on
an island route that pays per-km with a zero base, i.e. every cargo that
will feel underpaid out there.

### Mod-aware cargo base

The cargo step doesn't blindly mutate the vanilla `Cargos_01.uasset`. It
resolves the copy the **game actually loads** — if an installed pak (e.g.
an economy mod) overrides that asset, the last one in load order becomes
the base our new rows are added to, so our late-loading pak stacks on top
of it instead of reverting it. The chosen source is printed each build
(`[mt_paths] DataAsset/Cargos_01.uasset: using mod override from X.pak`).
Check any asset with `python mt_paths.py DataAsset/Cargos_01.uasset`.

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

## Naming your placeholders

Everything the pipeline places comes from what you name an actor in the
editor. The placeholder mesh itself is never shipped — only its transform is
read — so a cube is fine.

| Placeholder name | What you get |
|------------------|--------------|
| `Spawn_<Row>` | that vehicle, parked and takeable |
| `Dealership_<Row>` | same thing, alternate spelling |
| `DeliveryPoint_<Key>` | economy point, configured under `<Key>` in `delivery_points.json` |
| `Delivery_Point_<Key>` | same, underscore variant |
| `Garage`, `GasStation`, `ParkingLarge`, `ParkingSmall`, `FarmCorn` | the matching vanilla BP actor |

`<Row>` is the vehicle's **DataTable row name** — what the game calls it, and
what `unlock_vehicles.py` reports. Not the asset filename: the pipeline reads
the row's `VehicleClass` out of the vehicle tables to find the actor, so rows
whose asset is named differently (`Police_01` -> `Police`, `Trailer_30ft_Log_01`
-> `Trailer_9m_Log_01`) just work. Tables are read mod-aware, so a vehicle
another mod adds needs no code change.

`<Key>` is free-form; it only has to match a key in `delivery_points.json`.

### The map pipeline

Three commands, in order. The first runs in the editor's Python console, the
other two in a normal terminal:

```python
exec(open(r"D:\MTLiveMap\map.py").read())      # in the UE editor
```
```bat
python worldmap.py cutout --water              # island on transparency
python worldmap.py compose                     # island onto the vanilla map
```

The vanilla map comes from your **FModel export** — `T_WorldMap_Jeju.png` lands
beside the `.uasset`, so exporting the game is the only step and the result is
one-to-one with what ships. Point `MT_FMODEL_EXPORT` in `.env` at that folder
(or `MTMI_GAME_CONTENT`, if the pipeline already reads the export directly).

`worldmap.py extract` decodes the BC1 texture itself and needs no FModel, but
**its colours are not trustworthy** — the texture is stored linear (`SRGB=False`)
and the decode does not account for it, so the result looks washed out and
fringed. It is a fallback, not the recommended path.

| Step | Output | What it does |
|------|--------|--------------|
| `map.py` | `map.png`, `map_bounds.json` | orthographic top-down render of your level, plus the world rectangle it covers |
| `cutout --water` | `map_cutout.png` | sea and sky keyed to transparency |
| `extract` | `worldmap_vanilla.png` | the game's own 4096x4096 map, decoded from BC1 |
| `compose` | `worldmap_arini.png` | the island pasted onto the vanilla map, positioned by arithmetic |

**Run `map.py` alongside `ue.py` whenever the scene changes.** They are separate
because the scene export takes minutes on a foliage pass and the map takes
seconds, but they read the same level and go stale together.

#### Why `--water` exists

An exact-colour key cannot remove lit water. Measured on a real capture, the sea
was 48% of the frame spanning `R 0-39, G 21-81, B 43-118` — a family of shades,
because it reflects the sky. What is constant is the SHAPE of the colour: blue
clearly ahead of green, green clearly ahead of red, red near zero. Terrain is
the opposite, so the rule separates them and needs nothing from the editor.

An Unlit flat material also works and is cleaner if you want the water VISIBLE
but keyable. Pure green is safe: measured against a real render, nothing comes
near `(0,255,0)` — green never even dominates a pixel, and the greenest thing on
the island is a dull sage `(142,194,121)`.

#### Where the island lands, and why it is arithmetic

The game's world map covers a fixed world square, recovered from `script.js` in
this repo's first commits:

```
X -1280000 .. 920000        537.109375 uu per pixel
Y  -320000 .. 1880000       (2200000 / 4096)
```

`compose` converts `map_bounds.json` from editor space to world space using the
pipeline's own import offset, then to map pixels with those constants. No
eyeballing, no dragging in an image editor.

Two things it will tell you:

- **Scaling far from 1.0** means the capture resolution does not match the map.
  `MATCH_GAME_SCALE` in `map.py` derives the resolution so one captured pixel is
  one map pixel; set it False only for a standalone picture you want to zoom into.
- **"runs off the map"** is real, not a bug. The game's map stops at that world
  square, and 13 of the island's 35 delivery points sit outside it — Braila Port
  by 4.2 km west, Beach Lumbering 1.9 km south. Those parts cannot be drawn.

#### Cooking the map back into the game

The final PNG must be imported and cooked under the game's own name,
`T_WorldMap_Jeju`, so the mod's copy overrides it. Three texture settings must
match the vanilla asset or the map breaks in ways that look unrelated to the
image:

| Setting | Value | What goes wrong otherwise |
|---|---|---|
| X-axis Tiling Method | **Clamp** | defaults to Wrap: the map repeats endlessly across the screen |
| Y-axis Tiling Method | **Clamp** | same |
| sRGB | **unchecked** | the vanilla texture is linear; leaving sRGB on shifts every colour |

Check them by dumping the vanilla asset and yours side by side:

```bat
MTBPInjector inspect-export --cell <T_WorldMap_Jeju.uasset> --mappings <usmap> --limit 3
```

Vanilla shows `AddressX = TA_Clamp`, `AddressY = TA_Clamp`, `SRGB = False`. A
property ABSENT from your cook means it is at the engine default, which is
Wrap and sRGB-on — both wrong here.

Also watch the file set. Vanilla ships one inline `.uexp` of 8.4 MB with no
mips. A default cook produces a STREAMED texture — `.ubulk` plus `.uptnl` — and
`.uptnl` is optional streaming data that shipped games keep in a separate
optional pak. Turn mips and streaming off so the data inlines like the original.

#### compose or expand?

`compose` keeps the vanilla world rectangle. Markers stay correct because the
game's own bounds still describe the image. Part of the island is cropped.

`expand` grows the rectangle so the whole island fits. It also **breaks every
marker on the map**, vanilla ones included, unless the game's copy of the bounds
is moved to match — and it can be. They live in
`DataAsset/GameResource.uasset`, at `DriveMaps[0].WorldMap`:

| Field | Vanilla | Expanded |
|---|---|---|
| `WorldMapTexture` | `T_WorldMap_Jeju` | unchanged |
| `WorldMapLocation` | (-180000, 780000, 100000) | (-493885, 558554, 100000) |
| `WorldMapSize` | 2200000 | 2827770 |

Centre and size, **not** four corners — which is why an earlier scan of all
38,450 cooked files for the min/max values found only coincidental hits. The
vanilla pair reproduces the old rectangle exactly: -180000 ± 1100000 gives
-1280000..920000.

```bat
MTBPInjector set-worldmap --uasset <GameResource.uasset> --mappings <usmap> ^
    --center-x -493885 --center-y 558554 --size 2827770
```

`expand` prints the command with the right numbers for whatever it just built,
so the two cannot drift. Both paths are usable; `expand` is the one that shows
the whole island.

#### The sea has two shades, and one is a seam

Measured from the FModel export, the vanilla sea is two colours differing only
in green:

```
(27, 56, 93)  #1B385D   37.8%   inner
(27, 53, 93)  #1B355D   27.9%   outer, and the colour of all four corners
```

The boundary between them reads as a faint ring. `compose` flattens the outer to
the inner by default so a composited island does not sit across that seam;
`--keep-sea-border` leaves it alone.

`#1B385D` is also the colour to use for a water material meant to blend into the
vanilla map.

`MAP_Y_DOWN` in `worldmap.py` is True because the texture's Y runs opposite to
the tile scheme `script.js` used. world (0,0) is the middle of Jeju and Jeju
sits at the top of the map: Y-down puts (0,0) at pixel (2383, 596), Y-up puts it
at (2383, 3500) near the bottom.

### A top-down PNG of your map

Run this in the editor's Python console:

```python
exec(open(r"D:\MTLiveMap\map.py").read())
```

It writes two files beside the mesh shards:

| File | What it is |
|------|------------|
| `map.png` | the level rendered from directly above, 4096x4096 |
| `map_bounds.json` | the world rectangle it covers, and the uu-per-pixel scale |

The second one is what makes it a map rather than a picture — without it no
coordinate can be placed on the image:

    px = (X - min_x) / uu_per_px
    py = (max_y - Y) / uu_per_px

Y is flipped because UE's +Y and an image's +down point opposite ways.

Nothing to install: it uses an orthographic SceneCapture2D and a render target,
both already in the editor. It is a SEPARATE script from `ue.py` on purpose —
the scene export takes minutes on a full foliage pass, while this takes seconds
and you will re-run it far more often, after moving a road or adding a town.

Resolution, padding and a height cutoff are constants at the top of `map.py`,
meant to be edited. The cutoff is for when one buried or far-flung prop zooms
the whole frame out.

### Which way a spawned vehicle faces

A spawner placeholder's **Yaw** sets the parked vehicle's heading. Position,
Pitch, Roll and Yaw are read; **scale is discarded** — the placeholder mesh is
never shipped, so the pipeline has no use for it.

That makes scale free, and worth abusing as an authoring aid. Stretch the
placeholder along **X** — say `(4, 1, 1)` on a cube — and it becomes an arrow
pointing the way the vehicle will point, because X is the actor's forward axis
in Unreal. Now you can see the heading of every spawner in the viewport at a
glance instead of reading Yaw off each one, and getting a car facing into a
wall or backwards down a slope stops being something you only discover in game.

Do it on every spawner. It costs nothing at build time — the number never
leaves the editor — and it is the difference between placing a car and aiming
one.

### What is hardcoded, and why

**The mod name is not.** It lives in `.env` as `MTMI_MOD_NAME` and everything
derives from it: the staging folder, the deployed `zzzz_<name>.pak`, and every
path in `build.bat`. To rebrand, change that value and rename the staging
folder to match. The name never appears inside the pak, so the content is
unaffected. No vehicle, mesh or cargo name appears anywhere in framework code.

**The delivery-point clone templates are, deliberately.**
`bp_registry._TEMPLATES` lists the vanilla classes a delivery point can be
cloned from (`farm` -> `Farm_Corn_C` / `CornFarm_2`). That is a curated list of
classes verified to survive cloning — most vanilla DP classes do not, and
`Container_ExportImport_C` and the `Factory_*` family have shown crashes and
persistence problems. Adding one is a data entry once it is proven, and any
individual delivery point can override with `source_class` / `source_actor`.

## Repository layout

```
MTMapInjector/
├── README.md                  ← you are here
├── AGENTS.md                  ← deeper notes on UE5 internals + patterns
├── delivery_points.json       ← user-facing DP config (your working copy)
├── delivery_points.example.json ← reference template with full inline docs
├── .env                       ← your machine-specific config (gitignored)
├── .env.example               ← copy to .env and edit
├── static_meshes.json         ← scene export (written by ue.py inside the editor)
├── map_work_changes.json      ← intermediate (mesh + marker placements)
│
├── build.bat                  ← entry point (the one command you run)
├── modp.bat                   ← pak + deploy step (called by build.bat)
│
├── tools/                     ← vendored repak.exe + UAssetGUI.exe + oodle dll
├── mt_paths.py                ← .env loader + path resolver + auto-detect + AES key
├── bootstrap_extract.py       ← extract vanilla_extract/ from the game pak (repak)
├── install_editor.py          ← persist MTMI_REPO_ROOT for the UE editor
├── bp_registry.py             ← BP-class templates + delivery_points.json loader
├── clone_bp_actors.py         ← actor clone + new-cargo + DP-CDO mutator
├── import_meshes.py           ← static_meshes.json -> map_work_changes.json
├── import_cargo_data.py       ← extract vanilla cargo+DP catalog into CargoImport/
├── convert2.py                ← Jeju_World JSON patcher
├── pricing.py                 ← computes cargo prices from weight/batch/distance
├── economy_report.py          ← writes economy.html at the end of every build
├── ue.py                      ← editor-side scene exporter
├── map.py                     ← editor-side top-down map PNG (separate, seconds)
│
├── vanilla_extract/           ← local copy of game content (gitignored,
│                                 created by bootstrap_extract.py)
├── MTBPInjector/              ← C# UAssetAPI driver (the actual binary mutator)
├── CargoImport/               ← vanilla catalog ref data (run import_cargo_data.py)
└── MapChangeTest_P/           ← the mod's pak source tree (gets packed each run)
```

---

## Running scripts standalone

Every Python script reads its paths from `mt_paths.py`, which loads
`.env` from the repo root on import. As long as `.env` is set up
once, individual scripts work without any extra shell setup:

```bat
python clone_bp_actors.py --config map_work_changes.json --gen-dir ...
python bootstrap_extract.py cargos
python import_cargo_data.py
```

Process env vars still override `.env` if you need a one-shot tweak
(`set MTMI_MAPPINGS=...other.usmap` then run a single script). If
either required path (`MT_GAME_DIR` or `MTMI_MAPPINGS`) is missing or
points at a non-existent path, the script exits with a multi-line
help block.

---

## Troubleshooting

**"MTMapInjector pipeline cannot start — configuration is missing."**
A required path in `.env` (or the process env) is missing or
unresolvable. The error block names every missing variable, what it's
for, and how to obtain it. Edit `.env` and re-run.

**`bootstrap_extract.py` reports no pak found.**
`MT_GAME_DIR` didn't auto-detect your install. Set it in `.env` to the
folder that contains `MotorTown/Content/Paks/MotorTown-Windows.pak`
(Steam → Manage → Browse local files, then one level up from
`MotorTown/`).

**`bootstrap_extract.py` fails decrypting the pak.**
A game update probably rotated the AES key. Get the new key (community
mappings releases / Dumper-7) and set `MT_AES_KEY=0x...` in `.env` to
override the built-in default.

**Game crashes on world load after adding a `new_cargos` entry.**
Its `safety_dps` list is empty, missing, or points at vanilla DP
classes that aren't loaded. Set it to at least one valid class —
`Farm_Cabbage_C` and `Farm_Hemp_C` are reliable defaults. Without
vanilla DPs accepting the new cargo, MT's mission registry rejects
the world during load.

**`build.bat` errors with `'X' is not recognized as an internal command`.**
The .bat file got LF line endings somehow. Run `unix2dos build.bat` (or
re-checkout from git on Windows so autocrlf restores CRLF).

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
- Done: Path centralization — `.env` file + `mt_paths.py` resolver +
  Steam-install auto-detection. No hardcoded paths anywhere.
- Done: Self-contained extraction — vendored `tools/` (repak, UAssetGUI,
  Oodle dll) + built-in pak AES key. `bootstrap_extract.py` pulls a
  local `vanilla_extract/` straight from the encrypted game pak with
  per-feature bundles and lazy bulk-fetch of WP cells on first need. No
  FModel required (FModel stays as an opt-in via `--fmodel`).
- Done: `install_editor.py` persists `MTMI_REPO_ROOT` for the UE
  editor and prints the exact console one-liner to invoke `ue.py`.
- Done: `_comment` tolerance in `map_work_changes.json` delivery list.
- Pending: Marker color and icon — propagated through the pipeline but not
  yet mutated into the game's marker actor (see AGENTS.md "Marker / Icon
  Mutation Pending").
- Pending: Output storage cap — lives on a separate
  `MTDeliveryPointInventoryRatio` actor that needs targeted mutation.
- Pending: Distinct boosted-cargo display labels — blocked on shipping a
  separate-path StringTable; modifying vanilla `Cargo.uasset` crashes the
  game.
