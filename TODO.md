# TODO

Working list. Each item records what is KNOWN (verified, with evidence) versus
what is GUESSED, so nobody re-tests a settled fact. Current to the 2026-08-19
in-game pass.

Solved: 1 (delivery points), 2 (icons), 4 (fog), 6 (pumps and garages).
Open: 3 (heights), 5 (foliage pop), 7 (fences), 8 (economy balance),
9 (odds and ends).

---

## 1. DELIVERY POINTS NOT VISITABLE — SOLVED 14 Aug

All 33 points spawn and are interactable.

**Root cause: only 3 of 33 reached the persistent level's `Actors` array.**
An actor absent from that array is never spawned however perfect its export
is, and the map MARKER still renders because registration is separate from
spawning — hence "a mark with nothing under it". `CloneBatch`'s slot picker
was `else if (dst.Exports[dstLevelIdx] is LevelExport)`, but the first append
converts the level export to a RawExport, so from the second actor onward the
branch was false and 30 actors were dropped with NO error.

Secondary fixes that were also needed:
- `bIsSender`, `bIsReceiver`, `bUseAsDestinationInteraction` are now set on
  every clone. `MTDeliveryPoint` has 51 properties and only `ProductionConfigs`
  was ever written, so every point inherited CornFarm_2's other 50.
- A point must NEVER output what it consumes. `X in -> X out` (commit 8802126)
  killed nine points for three days.

**The lesson:** every file-level check passed the whole time — export, label,
transform, recipes, components were all correct. When the data is right and
the behaviour is wrong, check registration, not the data.

---

## 2. ICONS — SOLVED 14 Aug

**Known**
- SOLVED 14 Aug: all 33 points now spawn (level Actors array fix). Icons are
  the next visible problem: every point shows the corn farm icon because every
  point clones `Farm_Corn_C`.
- `MissionPointType` is at DEFAULT on every vanilla class CDO checked
  (GasStation, Warehouse, Supermarket, Mine_CopperOre, LogSupply, Farm_Corn),
  so the icon is NOT a property we can simply set. It follows the class, or
  the class's gameplay tags.
- Jeju ships **87 delivery point classes** and places at least these:
  `GasStation` (33 instances), `ComonDrop` (13), `Warehouse` (12),
  `ConstructionSite` (10), `LogSupply` (7), `Supermarket` (7),
  `Factory_Cement` (5), `CrudeOil_Refinery_Input` (4), `FastFood_Storage` (4),
  `Mine_CopperOre` (4), `MilitaryBase` (3), `Resident` (113).

- DONE 14 Aug: 9 templates across all 33 points. Two vanilla classes cannot be
  cloned and both kill the build at write time, so the old AGENTS.md warning
  was right, it just never named names: `GasStation_C` fails on `MTFuelPump`
  and `MilitaryBase_C` fails on a child called `Box`. Fuel points use `liquid`
  and get their pump from a separate `GasStation` placeholder.
- A cloned template brings its own SCENERY, and dropping the cloned child
  export does not remove it: these are BP construction-script components, so
  UE rebuilds them from the class at spawn. `LiquidSupplier_C` carries
  `SM_Bld_Silo_Small_01`, which is why tanks appeared at every gas station.
  The framework nulls `StaticMesh` on the cloned component instead:
  `GetBodySetup()` reads through the mesh, so no mesh means no geometry and no
  collision at once. `"keep_template_mesh": true` on a point opts out.
- Matching those components by CLASS was wrong twice over. `InteractionCube`,
  the volume the delivery point is interacted through, is a
  `StaticMeshComponent` with the same class index as the silo, so the first cut
  hid it on all 33 points — every one became a solid invisible block with no
  interaction. It also hid the fuel pumps, garages and parking spaces, which
  are cloned precisely to be seen. Now: opt-in per clone job, delivery points
  only, and matched on the `SM_` asset-naming convention. A component that
  fails the match stays visible, which is the safe way to be wrong.
- The in-game NAME is not one property. Unversioned serialization only writes
  values that differ from the class default, so which name property a vanilla
  instance carries varies by class: `CornFarm_2` has both `MissionPointName`
  and `PointName`, `Warehouse_Ranch` has only `PointName`, and `LogSupply_2`
  has only `MissionPointName`. Patching `PointName` and warning about the rest
  left every LogSupply clone showing its vanilla Jeju name. The framework now
  patches whichever are present and SYNTHESIZES `PointName` when absent, so
  the label belongs to the framework and not to the template a point picked.

**The approach: use the `template` field, which already exists**
`bp_registry._TEMPLATES` maps a template key to (source_class, source_actor).
It currently holds only `farm`. Adding entries gives each point the right
class -- and with it the right icon AND semantically correct behaviour --
configured per point in delivery_points.json as `"template": "gasstation"`.

Proposed mapping for our 33:

| Our point | Vanilla class |
|---|---|
| Rusty / Dorna / East Gas Station | `GasStation` |
| Fuel Refinery | `CrudeOil_Refinery_Input` |
| Fuel Storage | `Warehouse` |
| Iron Quarry | `Mine_CopperOre` |
| Beach Lumber, Dorna Lumber, Serpent Wood, Wood Cutting | `LogSupply` |
| Supermarket, Dorna Market, Abandoned Market, Cheese Shop | `Supermarket` |
| Galati Port, Braila Port, South Depot, Water Depot | `Warehouse` |
| Hospital, Alpine Rescue | `MilitaryBase` |
| Cheese Factory, Beer Factory | `Factory_Cement` |
| Grain Silo, South Barn, Valley Trailer | `Farm_Corn` (leave as is) |

**Test it with ONE point first.** AGENTS.md records that
`Container_ExportImport_C`, `ComonDrop_C` and `Factory_*` crashed when cloned
-- but those tests predate the level-slot fix, so the crashes may have been
misdiagnosed. Convert Rusty Gas Station to `GasStation`, build, and look:
different icon and no crash means the whole table can go in.

---

## 3. DELIVERY POINT HEIGHTS

**Known**
- Every point uses its OWN placeholder mesh (`DeliveryPoint_South_Barn`,
  `DeliveryPoint_Cheese_Shop`, ...). Those meshes do not share a pivot height,
  so identical editor placement lands actors at different heights. This is why
  the map looks right but the points do not.
- `z_offset` (uu) per point in `delivery_points.json` nudges one without
  re-authoring the mesh or re-exporting.

**Set so far** (a bus is roughly 12 m = 1200 uu)
| Point | Offset | Reason |
|---|---|---|
| Cheese Factory | none | REMOVED 14 Aug — see below |
| Cheese Shop | none | REMOVED 14 Aug — see below |
| Dorna Gas Station | +200 | below ground |
| Grain Silo | none | already perfect, leave alone |

The cheese offsets were guessed while the actors were not spawning at all, so
they were correcting a symptom of the level-slot bug rather than a real pivot
difference. Once the actors spawned from their true editor placement, -1200
buried them 12 m underground. Before adding an offset, confirm the actor is
actually spawning where the editor put it.

**Next**
- Name the remaining offenders and roughly how far out. "Half a bus up" is
  precise enough — 1200 uu per bus.
- Longer term: give every placeholder the same pivot in the editor and the
  offsets all go to zero.

---

## 4. FOG — SOLVED 17 Aug

Island fog is `LocalFogVolume` actors: **bounded**, so Jeju is untouched.

**Workflow.** Place a `LocalFogVolume` in the editor level, tune it in the
viewport, run `ue.py`. It exports to `static_meshes_parts/fog_volumes.json`
(position, scale, all five float knobs, `FogAlbedo`, `FogEmissive`) and
`inject-static` rebuilds each one as a real actor + component pair in
Jeju_World.umap. Values round-trip exactly. Add more volumes by placing more.

**Two bugs, both in how we BUILT the actor, neither in configuration:**

1. `TemplateIndex = 0` on actor and component — no archetype to construct
   from. Real actors point at their CDO.
2. `ExtrasLen = 0` on the actor. Every actor export in a cooked level carries
   trailing metadata (count, label, FGuid, padding); the reference has 55
   bytes. With none, the loader reads the FOLLOWING export's bytes as this
   actor's metadata — that is the world-load crash. `MakeActorExtras` already
   emitted exactly this layout for delivery points and dealers; the fog path
   just never called it.

Also needed: component `Extras` = 4 zero bytes, `IsInherited=True`,
`bNotAlwaysLoadedForEditorGame=true` on both, and the actor's third SBCD entry
(the component class).

**The cvars were never the problem.** `r.SupportLocalFogVolumes=1` and
`r.LocalFogVolume=1` are both Constructor defaults.
`ShouldRenderLocalFogVolume` (LocalFogVolumeRendering.cpp:110) needs only those
two plus show-flag Fog, and does NOT need volumetric fog: with
`RenderDuringHeightFogPass=0` and `r.VolumetricFog=0`,
DeferredShadingRenderer.cpp:3005 falls through to an independent
`RenderLocalFogVolume` pass.

Commit b5d5976 deleted this working feature on the inverted inference that "no
ini mentions r.SupportLocalFogVolumes, so it must be off" — the default is 1.

### What actually solved it: a reference

Placing one in the editor and cooking it turned guesswork into a diff. The
cooked actor in the project's own level is the ground truth:

    LocalFogVolume_0          ClassIndex=-8 TemplateIndex=-34
                              CBCD=1 CBSD=1 SBCD=3 SBSD=0  ExtrasLen=55
    LocalFogVolumeComponent   IsInherited=True  ExtrasLen=4
    imports: -8 LocalFogVolume, -9 LocalFogVolumeComponent,
             -34 Default__LocalFogVolume, -35 the CDO's component subobject

Two days went into guessing at this. Twenty minutes went into diffing it.
**When injecting a class the game never places, cook one and diff it FIRST.**

### Dead ends — do not retry

- **Volume-domain materials.** `r.VolumetricFog=0` (SETBY Scalability) in the
  running game, so `ShouldRenderVolumetricFog` is false and there is no froxel
  grid to voxelize into, at any quality or distance. Motor Town also has never
  voxelized a Volume material into fog: of 22,125 cooked assets exactly one
  carries voxelization shaders and it is the engine's stock cloud material.
- **Global `ExponentialHeightFog` tuning.** Works and is visible, but there is
  one per scene and the renderer only reads `ExponentialFogs[0]`, so it changes
  Jeju's weather too. Rejected for that reason. `MTMI_FOG_PROPS` still exists.
- **`SM_Particle_Smoke_01a` / `Mat_Gradient_01`.** Invisible at 30x, 100x, 300x.
  Its shader map carries `FMeshParticleVertexFactory` — an FX material wanting
  per-particle input a static mesh cannot supply.
- **`SM_Generic_Cloud_*` / `Mat_Cloud`.** Also invisible, never explained.

None of it was placement: seven water tanks at the seven coordinates the fog
had occupied were ALL visible, including one 9 m up. An invisible thing and an
absent thing look identical in game — **put the control in first.**

UE 5.5 source is at `D:/Program Files/Epic Games/UE_5.5/Engine/Source`. Reading
it settled in minutes what guessing could not.

---

## 5. FOLIAGE POP

**Known**
- Improved by padding each foliage cell's reported content bounds outward, so
  streaming pulls the cell in before you reach it. Confirmed better in game.
- Cull is 30,000 to 70,000 with cells unloading at 76,800 — 6,800 uu of margin.
- Grass is 29% of 3.45M instances.

**Done**
- `MTMI_FOLIAGE_CELL_PAD` 25600 confirmed better in game.
- Raised to 51200, then ROLLED BACK to 25600 after a game crash. Padding is
  the only recent change that increases runtime memory: every cell claims
  bounds that much larger, so many more stay resident at once with 3.4M
  instances behind them. Unproven as the cause -- Motor Town ships with
  logging off, so there was no crash log to read.

- 25600 LEAKED TOO. Padding is off (`MTMI_FOLIAGE_CELL_PAD=0`). Before padding
  existed the build ran for days without leaking, so zero is the real
  baseline and the 25600 rollback was not the known-good I called it.
- RE-ENABLED 19 Aug, now that the actor work has landed. A full build is
  ~13 min and 1022 MB against ~6 min and 537 MB with `--skip-foliage`. Use the
  flag while iterating on anything that is not foliage; ship with it on.
- 9,192 rock instances are promoted to persistent actors
  (`MTMI_FOLIAGE_AS_ACTORS=Rock`) so a solid rock never streams in on top of a
  moving vehicle.

**Next**
- Re-test padding only after the actor work, and only from 0 upward.
- If more reach is wanted, prefer raising the CULL distance over the pad:
  culling costs draw calls, residency costs memory, and memory is what
  crashes.
- Launch the game via Steam with `-log` in the launch options so the next
  crash leaves something readable.

---

## 6. FUEL PUMPS, GARAGES, PARKING — SOLVED

Working in game. Confirmed 19 Aug.

**Known**
- These are NOT delivery points. They are separate placeholders
  (`GasStation`, `Garage`, `ParkingLarge`, `ParkingSmall`) that clone vanilla
  BP actors. `GasStation` -> `FuelPump_01A_C` is the drive-up refuel pump.
- They clone into World PARTITION CELLS, not the main map, so searching
  Jeju_World.umap for them finds nothing and proves nothing.
- 4 `GasStation` and 3 `Garage` placeholders in the current export;
  `FuelPump2_MOD` in 4 generated cells, `GarageActor2_MOD` in 3.
- Gas stations need this placeholder ALONGSIDE their delivery point:
  `GasStation_C` cannot be cloned as a DP template (it fails the class
  rewrite on `MTFuelPump`), so fuel points use the `liquid` template for the
  icon and get the actual pump from here. See section 2.

**Two traps, both still live**

`cell_spec` extent must stay 6400. It feeds the grid coordinate calculation.
Raised to 25600 on 13 Aug and 2,500 foliage cells collapsed onto a handful of
grid keys — the island's entire foliage stopped rendering. Content BOUNDS are
the safe lever for streaming distance (`MTMI_FOLIAGE_CELL_PAD`); extent is not.

Scenery-hiding must never touch these. They are cloned precisely so their
meshes show up, unlike delivery point templates. The `hide_template_mesh` flag
is set by `bp_registry` for delivery points only; an early cut that keyed off
class alone hid all four pumps, the garages and the parking spaces.

**The RawExport lead was a red herring.** `FuelPump2_MOD` reading as a
RawExport with zero parsed properties, against the vanilla NormalExport with
10, looked like the cause for both pumps and delivery points. It was neither.
Delivery points were the level `Actors` array (section 1) and the pumps came
back with the `cell_spec` revert. Do not re-open it on the strength of that
asymmetry alone.

---

## 7. FENCES

**Known**
- Nothing is missing from the build. Three of four are VANILLA assets the game
  already ships, so the pipeline deliberately does not duplicate them.
  `SM_FenceTypeG_12` is ours, shipped, 14 placed.
- `SM_FenceTypeG_12` sits at Z 46,320, roughly 463 m up.

**Observed**
- Only half of a fence run appears. Merged meshes work, individual ones may not.

**Next**
- Compare a working merged fence against a missing individual one: same
  material, same collision, same cook state?

---

## 8. ECONOMY AND PAYMENTS

**How prices are set — computed, never hand-written**

    pay = taper(kg) * 10/kg * batch * (1 + km / 5)      floor 1,000

`kg` is the cargo's max weight from the game's own data, `batch` is the licence
tier the load needs (1-5, from `CargoType` with tankers forced to B5), and `km`
is the SHORTEST producer-to-consumer run measured from the real placements.
Weight is linear to `TAPER_KG` (5 t) and square-root above.

`BasePayment` is one number per CARGO ROW, not per route, so distance has to be
resolved at build time from the recipe graph. The shortest run sets the price
because that is the run a player will pick; longer hauls of the same cargo pay
the same, and nothing can be farmed by choosing the short one.

Distance cannot be left to the game: `PaymentPer1Km` multiplies by the ROAD
distance MT computes, and that only finds a road on the vanilla network, which
the island is not on.

    python pricing.py            # show the table
    python pricing.py --write    # write BasePayment into delivery_points.json

Numbers land in the JSON so they stay visible in git diff. `weight_kg`, `batch`
and `base_payment` override the derivation per cargo; `base_payment` skips the
model entirely (Pezzi is contraband, priced by what it is). `verify_build`
fails if a delivery point has moved since the last `--write`.

Build-time-only keys are recognised by SHAPE, not an enumerated list: a key
with an underscore or all-lowercase is ours, PascalCase is a UE cargo-row
field. Adding a knob no longer means editing Program.cs.

**Island-grade tiers — the pattern, now proven twice**

Vanilla rows cannot be repriced without changing Jeju. So clone the commodity,
price the clone flat, and switch every island recipe to it. Jeju keeps the
original and is untouched.

Done: `Water`, `Pezzi`, `JetFuel`, `MoltenPlastic`, `LiquidNitrogen`,
`HempBale`, and as of 19 Aug the steel chain — `IronOreX`, `HBeamX`,
`SteelCoilX` cloning `IronOre`, `lHBeam_6m`, `SteelCoil_10t`.

Two consequences to keep in mind:
- Every new cargo needs a CONSUMER among our own points or MT crashes on world
  load. `verify_build` checks this per cargo.
- It also needs a PRODUCER, or the chain silently stalls. Beams had a consumer
  and no producer until Aerotyne was given `IronOreX -> HBeamX`.

**Known limitation: `km` is straight-line, not road distance**

`pricing.py` measures the gap between two points, not the drive. On flat ground
that is close enough. On the mountain it is not: Abandoned Market to Dorna Beer
Factory is 2.84 km apart and about 38 km of actual road, up 552 m through 20+
sharp switchbacks. The model would price that as a short hop.

There is no road graph available to fix it properly — MT's own road-distance
calc is what fails on this island in the first place. So routes whose drive
bears no relation to their gap get a `base_payment` override, which skips the
model entirely and is honest about being hand-set.

Overridden so far: Pezzi (contraband, priced by what it is), SteelCoilX
(50,000 into Abandoned Market), SteelCoilXL (150,000 up to Dorna).

A per-point road-distance multiplier would be the general fix if this keeps
coming up.

**Open — balance, and it is a judgement call not a bug**

Heavy cargo computes large. Current worst case:

    IronOreX     3,200 kg  B3           134,099
    HBeamX       2,000 kg  B3  9.6 km   175,473
    SteelCoilX  10,000 kg  B4  5.4 km   591,218

The sqrt taper is doing real work on the coil — linear would be 836,000 — but
591k for one delivery is still roughly twelve tanker runs of water and the
biggest payout on the island by a wide margin. Lowering `TAPER_KG` to ~3 t
brings it to about 400k without touching anything lighter. `TAPER_KG` and
`RATE_PER_KG` in pricing.py are the two knobs, and a re-run reprices
everything consistently.

**Open — 19 vanilla rows still pay per-km with a zero base**

BottlePallete, BoxPallete_01, BreadBox, BreadPallet, CheeseBox, CheesePallet,
Container_20ft_01, Container_40ft_01, CopperRodCoil_2t, CornPallet,
GlassBottleBox, HempPallet, MeatBox, PlasticPipes_6m, PowerBox, RicePallet,
SmallBox, SunflowerSeed, WoodPlank_14ft_5t.

They pay close to nothing on the island. `python pricing.py` regenerates the
list. The containers and `CopperRodCoil_2t` are the biggest earners left and
the obvious next tier candidates.

**Confirmed in game:** a flat-priced run does pay. That was open for days.

---

## 9. SMALLER OPEN ITEMS

- **Console variables never reach the game.** A cvar dump from the running
  game shows our shipped `UserEngine.ini` has no effect at all:
  `mh.cargoStackMaxVehicleHeight` ships 840 and reads 420 (`Constructor`),
  `mh.aISpeederSpawnRatio` ships 400 and reads 100. Every cvar the build
  merges is inert, INCLUDING the CapitalistEconomy settings it inherits
  mod-aware, so `merge_config.py` has never done anything. Most likely UE
  loads config from the physical filesystem before paks mount, which would
  mean writing the merged ini into the game's own Config folder at deploy
  rather than only into the pak. Nothing depends on it today — fog turned out
  not to need it — but a whole feature is silently dead.
- `r.VolumetricFog` is 0 (SETBY Scalability) in the running game. Only matters
  if Volume-domain materials are ever revisited; local fog volumes do not care.
- `Farm_Corn` is read from vanilla while Proxy's Oversized Cargo overrides it.
  The pipeline is mod-aware for cargo and vehicles but not for the delivery
  point blueprint. One-line fix, but it changes what all 33 points clone.
### Map PNG — researched 21 Aug

**Getting a picture of the island: DONE.** `ue.py export_map_png(OUTPUT_DIR)`
spawns an orthographic SceneCapture2D above the level, renders into a
TextureRenderTarget2D and exports a PNG. No plugin, no external tool, no
coding — every API used is BlueprintCallable, which is why Python can drive
it. Opt-in via `MTMI_EXPORT_MAP=1` or called by hand from the editor console,
because the capture spawns an actor in the level and a normal export does not
need a picture every time.

It also writes `map_bounds.json`: the world rectangle the PNG covers and the
uu-per-pixel scale. That is the difference between a picture and a map —
without it no coordinate can be placed on the image.

    px = (X - min_x) / uu_per_px
    py = (max_y - Y) / uu_per_px      Y flips: UE +Y vs image +down

Framing is squared before capture. A non-square world rect stretched into a
square PNG makes every derived coordinate wrong.

**The world-to-texture transform, recovered 21 Aug.** `script.js` from this
repo's first commits carries it:

    minX -1280000   maxX  920000
    minY  -320000   maxY 1880000

A 22 km square, which over 4096 px is **537.1 uu per pixel**. Unverified, but it
makes a testable prediction rather than needing measurement: 13 of 35 delivery
points fall outside that rect, off the west and south edges — Braila Port by
4.2 km, Rusty Gas Station by 3.1 km, Beach Lumbering 1.9 km south. Open the
in-game map and look for Braila Port; missing or edge-clamped confirms it.

**PLANNED: derive the capture resolution from that scale.** To composite the
island into the game's map at its native quality, `map.py` should not use a
round 4096 — it should render at the span divided by 537.1 uu/px, so one
captured pixel equals one map pixel. For the current 14,712 m island that is
about 2,740 px. Rendering finer wastes time and gets downsampled; rendering
coarser is visibly soft against vanilla terrain. Make SIZE optionally derived:
`SIZE = span / UU_PER_MAP_PIXEL`.

**Replacing the IN-GAME map: not done, but the target is identified.**
`UI/InGame/Map/WorldMap/T_WorldMap_Jeju` is the game's own world map:
4096x4096 BC1, and its .uexp is 8,388,751 bytes against 4096*4096/2 =
8,388,608 for the pixels, so the format is certain. Replacing that texture is
how the island appears on the in-game map.

What is still missing is the world-to-texture transform. The binary names an
`MTWorldMapArea` but it is not in the .usmap (Blueprint, not C++), and no
`mh.*` cvar carries map bounds — only `mapIconSmoothInterpSpeed`,
`minimapBaseRange` and friends. Two ways to settle it:
  - Empirical: two known world positions identified as pixels on the extracted
    texture solves scale and offset outright.
  - The game ships `PolygonNature/Materials/Misc/M_OceanForWorldMapGeneration`,
    a material that exists only to generate that map. Whatever process uses it
    knows the bounds.

**Related history**: the original live map (first commits, `map.js`) was
Leaflet on `CRS.Simple` over a 16x16 grid of 256px tiles, with
`worldToLatLng` still an identity stub. So the transform was never solved
then either.
- 31 stale orphan assets in the mod tree that no longer come from any cook.
- Unverified in game since they were built: the computed prices, the `Arini`
  names on the four LogSupply points, and the gas stations having no invisible
  wall after the silo fix.

---

## 11. SNOW SHOULD SINK YOU, THE WAY MUD DOES

Mud already has it: accelerate hard in it and the vehicle digs in, ending up
below the surface and losing traction. That is a physical-material property,
not something the mesh does, and snow has none of it -- you drive over snow as
if it were tarmac.

Give snow the same behaviour. Both materials sit next to each other with the
road ones, so the first job is reading mud's and diffing it against snow's to
find which parameter governs sinking.

Prefer a NEW material cloned from the game's, altered, rather than editing the
vanilla one. Snow is everywhere on this island, so a change to the shipped
material is not testable in isolation and not revertible without a rebuild --
and every other mod touching that material would fight ours. Same reasoning as
the tanker mod: the standalone copy is the testable one.

Not started. Worth doing after the bus stops land.

## 10. HOW THIS PROJECT GOES WRONG

Three separate multi-day hunts ended the same way, so it is worth naming.

**An invisible thing and an absent thing look identical in game.** Fog was
debugged for two days on the assumption that the actors were reaching the
world. Seven water tanks at the seven coordinates the fog had occupied were
all visible, which ruled out placement in one build and should have been the
FIRST build, not the eighth. Put the control in first.

**A file-level check passing means nothing about runtime.** All 33 delivery
points had correct exports, labels, transforms and recipes while 30 of them
never spawned. Registration is not data.

**When injecting a class the game never places, cook one and diff it.**
`LocalFogVolume` cost two days and two world-load crashes building the actor
from first principles. A real one placed in the editor and cooked found both
bugs — a missing archetype and missing export metadata — in twenty minutes.

**Do not reason from an ini's silence.** `r.SupportLocalFogVolumes` was
declared impossible because no shipped ini mentioned it. Its default is 1.
Working code was deleted on that inference and had to be restored.
