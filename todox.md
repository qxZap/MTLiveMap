# todox — what I want, in a form the build can act on

Freeform is fine. This file is read by a human (me), not by the build, so
nothing here has to be valid JSON. The headings exist so a request lands with
enough detail to act on without a round trip.

**The one rule that saves the most time:** say WHERE. A name alone ("more
garages") needs a follow-up question every time. A name plus a place ("garages
at the Arini harbour, 3 of them") does not.

---

## How to say where

Best to worst, all accepted:

1. **A marker mesh in the editor.** Nothing to write here at all — name the
   mesh and it becomes the actor. See `AGENTS.md` → "Editor markers".

   BusStop_<Name></name>      a bus stop
   Home_<Name></name>         somewhere people live
   Work_<Name></name>         somewhere people work
   Zones/<Key></key>/Border_01, Border_02, ...   a zone's outline, in order
2. **A delivery point name** — "next to Alpine_Rescue_Post". Those have known
   coordinates and known-good ground.
3. **World coordinates** — `[-1206928, -49717, 46440]`. Read off the editor
   transform panel, and note only Z differs between editor and world
   (`OFFSET_Z = -22180`); X and Y go straight through.

---

## Vehicles I want buyable

Which vehicle, and where it should be sold. The row ID is what the game calls
it internally — if you only know the in-game name, say that and I will find
the row.

| row / name             | sold where | notes |
| ---------------------- | ---------- | ----- |
| kart_01                |            |       |
| Trailer_9m_Flat_01     |            |       |
| Trailer_30ft_Log_01    |            |       |
| Trailer_01             |            |       |
| Trailer_30ft_Tanker_01 |            |       |
| Vulcan                 |            |       |
| Bus                    |            |       |
| Ambi                   |            |       |
| Nimo_Taxi              |            |       |
| Nuke_Taxi              |            |       |
| Trophy_Taxi            |            |       |
| Brutus_FireEngine      |            |       |
| thropy air             |            |       |

Categories still wanted, from the old list: old trailers, cop cars, crany,
rare ones, disabled ones.

---

## Places to build

What, where, how many. "Parking spaces" is a request; "8 parking spaces at the
Arini refinery" is a job.

- [ ] more garages — WHERE, and how many?
- [ ] parking spaces — WHERE, and how many?
- [X] death road — where does it start and end?
- [ ] marcaje unde e ce (signage) — which places need naming?
- [X] slope angle — which slope, and what is wrong with it?

---

## MINE TO PLACE — the editor work

This is the part only I can do. Everything below is a mesh placed and named
in the editor; the build turns each one into a working actor.

- [ ] **POIs — homes and workplaces.** `Home_<Name>` and `Work_<Name>`.
  Population is literally how many of these sit inside the zone, and
  residents need BOTH: they live at one and work at another, and the
  commute between them is what puts anyone on a bus. 136 are placed
  programmatically at the delivery points right now, four per point, as a
  test rig -- these replace them with real ones in real places.
- [X] **Bus stops near where people are.** DONE 2026-09-02 -- 25 stops, named
  from the OUTLINER LABEL. Confirmed working in game.
- [ ] **Rotate bus stops where they look off.** A stop takes its facing from the
      mesh's Yaw, so turning the marker in the editor turns the shelter. Several
      currently sit at an angle to the road they serve.
- [ ] **Zone borders**, if Arini's square should become a real shape.
  `Zones/Arini/Border_01`, `Border_02`, ... walked in one direction, 3+ of
  them. The mesh is consumed, so a cone works and nothing appears in game.
- [ ] More zones? A new `Zones/<Key>/` folder is the whole setup.

Position, height and facing all come from where the mesh sits. Nothing to
type, and nothing that can drift out of sync with the scene.

---

## Economy

The model is `pricing.py`: `pay = kg^0.63 * 150 * batch * (1 + km/5)`, floor
1,000. The exponent is the GAME's own weight curve, fitted from its cargo
rows -- only the level (150) is ours. Batch is the licence tier, and it
already multiplies exactly as discussed: B2 x2, B3 x3, B4 x4, B5 x5.

- [ ] **19 orphaned vanilla cargos.** BottlePallete, BoxPallete_01, BreadBox,
  BreadPallet, CheeseBox, CheesePallet, Container_20ft_01,
  Container_40ft_01, CopperRodCoil_2t, CornPallet, GlassBottleBox,
  HempPallet, MeatBox, PlasticPipes_6m, PowerBox, RicePallet, SmallBox,
  SunflowerSeed, WoodPlank_14ft_5t. All carry zero BasePayment and rely on
  per-km, which finds no road off the vanilla network -- so hauling any of
  them on Arini pays near nothing. This is the single biggest hole in
  "people who go to the struggle get paid".
  FIX: custom copies priced by the model, recipes swapped to them, Jeju
  left alone. Same pattern as IronOreX / SteelCoilX already use.
- [ ] **4 cargos bypass the model** with hand-set prices: Pezzi 30,000,
  SteelCoilX 50,000, SteelCoilXL 150,000. Decide whether they should be
  computed like everything else.
- [ ] Re-run `python pricing.py` after moving any delivery point: prices are
  derived from the real distance between producer and consumer, so moving
  a point silently makes its price wrong. `stale_prices()` detects it.

## Done

- [X] fog
- [X] massive straight
- [X] deliveries lower height
- [X] minimap
- [X] foliage
- [X] coliziuni tufe
- [X] spawners for vehicles

---

## Still open, carried from the build

- [ ] **Load-time memory: WP LoadingRange was 3x vanilla.** Reported as a
      "leak", but it climbs ON GAME LOAD, which is an allocation spike rather
      than a leak. Vanilla MainGrid LoadingRange is 25,600; ours was 76,800.
      Resident cell count grows with the SQUARE of the range, so that is ~9x
      the streamed content resident at load, across ALL of Jeju and not just
      Arini. Now back to 25,600 (.env MTMI_WP_LOADING_RANGE).

      It was raised to push foliage pop-in further out -- a real problem it
      genuinely helps -- but it sat at 3x through every foliage-free build,
      paying the memory for a benefit that could not apply. When foliage comes
      back, raise it again DELIBERATELY and from 25,600 upward, measuring each
      step. Prefer raising the instance CULL distance over the range: culling
      costs draw calls, residency costs memory, and memory is what crashes
      (see TODO.md section 5).

      IF MEMORY IS UNCHANGED at 25,600, the next suspect is structural: 15,008
      static mesh actors live in the PERSISTENT level, which World Partition
      never unloads, so the whole island is resident from the moment the map
      opens (107,557 exports, 17 MB umap). That is architecture, not a
      setting -- confirm before touching it.

- [ ] Foliage is OFF in the current pak, DELIBERATELY -- `--skip-foliage` is a
  standing choice while mechanics are being tested (699 MB vs ~1205 MB). Say
  the word for a full one. Runtime cost is not the reason: ~248k foliage
  actors measured negligible on FPS. Build time is.
- [ ] Foliage pop-in on approach.
- [ ] Snow should sink you the way mud does. IN PROGRESS.

      THE MISTAKE THAT COST THREE BUILDS: we were patching PM_Snow, and
      NOTHING ON ARINI USES IT. The island's ground is Mat_Road_Snow on 38 of
      64 ground/path meshes, and that material's PhysMaterial is PM_SnowRoad.
      Patches landed correctly on an asset the map never loads.

      PM_SnowRoad is a ROAD surface: friction 0.4, rolling resistance 2, and
      NO digging properties whatsoever. So this is not tuning an existing
      surface, it is giving a road the digging block mud has. And an absent
      property is its default -- zero for a float, false for a bool -- so
      "absent" and "off" are indistinguishable in an unversioned asset.

      Ruled out, each with evidence:
        - SurfaceType is NOT the digging gate. Dirt digs at SurfaceType2,
          Sand at 10, Mud at 11. Snow's 7 is fine and stays.
        - Collision is NOT the problem. The snow road meshes are
          CTF_UseComplexAsSimple, so the render material's physmat applies.
        - Load order is NOT the problem. Only zzzz_Arini_P.pak ships PM_Snow*,
          and it mounts last of 27 paks.
      bIsOffroad is the GATE -- every digging material has it, snow had none.

      Tuning history: (1,5) speed 0.5 resist 5 -> "barely sinking";
      (2,10) speed 2 resist 3 -> "still not sinking"; now (5,20) speed 2
      resist 3, which is PM_MudPuddle's numbers exactly. Depth is the lever:
      snow shipped (1,5) where every mud-family surface runs 10-35.

      STILL TO DO once the feel is right: move these values off VANILLA
      PM_SnowRoad -- which currently makes every snow road in Jeju dig -- onto
      a new material. Agreed approach: Unreal owns the ASSETS (duplicate
      PM_SnowRoad -> /Game/DC/Physics/PM_Arini_Snow, duplicate Mat_Road_Snow ->
      /Game/DC/Materials/Mat_Arini_Snow with its PhysMaterial repointed, swap
      the ground meshes onto it), the PIPELINE owns the NUMBERS via
      materials.json. Rationale: material assignment lives on the mesh and a
      visual material needs a shader cook, so Unreal must own those; a
      physical material is pure data, so keeping it in materials.json means
      retuning is a rebuild rather than a re-cook.
- [ ] Console variables never reach the game; `merge_config.py` is inert.
- [ ] **Number signs are invisible.** SOLVED as far as the pipeline goes: the
      fault is the MESH, and it is not ours.

      Proven by substituting different meshes onto the SAME 31 sign transforms
      (MTMI_DEBUG_MESH_FOR=Sign_Number):
        SM_CraneMobile_01                 VISIBLE
        SM_Prop_Barrier_Sign_01           VISIBLE   (same vanilla folder)
        SM_Prop_Sign_Number_* ours        invisible at 1x and 10x
        SM_Prop_Sign_Number_* VANILLA'S   invisible at 20x (25 m tall)
      So placements, transforms, injection, imports, material and scale are
      all fine -- a crane renders where a 25 m number does not.

      The physical evidence:
        SM_Prop_Sign_Number_1    uasset 1693  uexp 5079   ubulk  1,032
        SM_Prop_Sign_Number_5    uasset 1693  uexp 5079   ubulk  1,032
        SM_Prop_Barrier_Sign_01  uasset 1714  uexp 12700  ubulk 20,640
      Digits 1 and 5 are BYTE-IDENTICAL in size. Different numerals cannot have
      identical geometry, so these are one flat quad reused with different UVs,
      and ~1 KB of bulk data is about four vertices. Folder median is 73,468 B;
      the numbers are smaller than 285 of 296 meshes in it.

      NOT a flat quad -- checked in the editor preview: real 3D geometry, and
      the back face renders black rather than transparent. So the SOURCE asset
      is fine. The editor previews the source; the game loads the COOKED bulk,
      and that is where it dies.

      NOT the material either, and this is conclusive: SM_Prop_Barrier_Sign_01
      and SM_Prop_Sign_Number_1 use the SAME material, /Game/Models/
      PolygonStreetRacer/Materials/MI_SR_Signs_01. One renders, one does not.
      Their cooked exports are structurally identical too -- same properties,
      same single material slot, same layout.

      CONCLUSION: the cooked geometry is stripped. 1,032 B of ubulk against
      the barrier sign's 20,640, and BYTE-IDENTICAL between _1 and _5, which
      different numerals cannot produce. Motor Town's own cook and ours both
      yield the same stripped result, so vanilla's copy fails the same way.

      NEXT: re-import ONE digit from the Synty source FBX as a NEW asset --
      not a duplicate, since duplication carries whatever build setting is
      doing the stripping. Cook it and test. Renders -> re-import the rest.
      Still nothing -> the source is the problem and numbers need a different
      mesh.

      Dead ends, each disproven rather than abandoned: the DC copies' material
      (a standalone Material cooked at 11 KB with no shader map -- real, but
      not the cause); re-parenting to a Material Instance (the instance was
      parented to that same broken Material, so it inherited the same
      nothing); FName "_N" suffix splitting (imports round-trip correctly);
      a broken override of a shared PolygonStreetRacer material (we override
      only one road material).

      METHOD NOTE: the first probe used SM_96_192_Hills_01_Dirt, which is the
      island's own terrain mesh in 982 places. "Do you see hills" was
      meaningless and the yes it produced was false. Three theories were built
      on it. A probe mesh MUST be one that appears nowhere else.

- [ ] PARKED: Crany's winch. Five data attempts: an MTConstraintComponent
      (crashed on exit), the Crane0 part slot (a winch can now be fitted and
      swapped), Crane0_In/Crane0_Out interactables, AWD (works), and binding
      MTCraneComponent.Winch to an added MTWinchComponent. The rope still has no
      tension and in/out is silent. The telling detail: tension refreshes the
      moment the controller is picked up and never changes in between, so it is
      computed on interaction events and nothing drives it per-frame. Pulio and
      Golima winch correctly and have no MTCraneComponent at all -- their
      Blueprints wire the winch themselves. That wiring is graph logic a pak
      cannot author, so this needs an editor with the game's classes loaded,
      comparing Crany's Blueprint against Pulio's.
- [ ] PARKED: soft limits. 20 attachments per vehicle, ~20 vehicles per
  company. `MaxVehiclePerPlayer` is an Int on `MTServerRuntimeConfig`, so
  it is server config rather than a packaged asset -- the open question is
  whether the singleplayer host reads it, because if it does this is a
  config line and not a mod at all. Attachments have no governing property
  anywhere in the schema, which points at a C++ constant no pak can move.
  Coming back to this later.
- [ ] Arini's zone: ONE rectangle now, not 12 tiles. VERIFY IN GAME.

      What went wrong: the Town Status list has ONE ROW PER MTAreaVolume that
      holds residents. The 12-band fill therefore registered as 12 separate
      towns, each with 12 residents, each BLANK -- the tiles carry no AreaName
      by design, since a label per box would caption the map twelve times.
      Meanwhile 'Arini' itself was named correctly (the build logs
      `Patched AreaName -> 'Arini' via ModLabels[Arini]`) but was scale
      [1,1,600] -- a 200x200 box containing nobody -- so it never appeared at
      all. The fill carried the area; the named volume carried only the label.

      Fix: MTMI_ZONE_FILL=0 plus an explicit world/scale, giving one rectangle
      over the marker bounding box. This drops the triangle-centroid label
      point; with a single volume the label sits at the volume centre, ~680 m
      from the centroid on a 13 km island.

      THE Z TRAP: a zone's Z must be set explicitly, NOT left to the markers.
      The marker path averages the border markers' Z, and those cones sit near
      editor zero -- about 68,000 units BELOW the island surface. A volume
      centred there has its ceiling underground (half-height is scale[2]*200/2,
      so 600 -> 60,000), contains nobody, and drops off Town Status entirely.
      Ground level for Arini is Z 48,385. Caught only by reading the shipped
      volume's transform; the build logs it happily and integrity still passes,
      because nothing checks that a zone contains anything.

      Reference for any future zone work, measured from vanilla:
        vanilla town  = AreaName (Text) + AreaVolumeFlags::LargeArea, no ZoneKey
        ours          = AreaName + ZoneKey + AreaVolumeFlags::Zone
        others seen   = RaceTrack (AnsanRing), SmallArea (SatansCabin),
                        and JejuAirport carries AreaName with NO flags at all
      A zone name renders only via a StringTable entry -- inline
      culture-invariant FText does not display in this build. ModLabels
      carries both the bus stops and the zone (26 entries).

- [ ] `Zone Test Gangjung` is a leftover diagnostic stop and can be deleted.
- [ ] Bridge stop 5 sits east of the boundary, so it belongs to Hallim rather
  than Arini.


---

## Mechanics learned (2026-09-02)

**Markers can be named in the OUTLINER now.** `marker_role()` reads the actor
label first and falls back to the mesh's asset name, so `BusStop_<Name>` works
as a rename in the outliner -- no duplicating a mesh asset per stop. This was
found the hard way: 25 buses had been placed and renamed, and named nothing,
because an outliner rename never reaches the mesh's asset path. `ue.py` now
exports `actor_label` on every static mesh entry. Check: `test_marker_role.py`.

**BusStop_ markers are consumed.** The marker mesh is dropped and the stop
actor takes its place. `Home_`/`Work_` markers still render -- those are
houses and offices meant to be looked at. See `MARKER_ONLY_ROLES`.

**set-props can write a Vector2D**, as `Name=(X;Y)` -- a SEMICOLON, because
`--set` splits its pairs on commas. Needed for `DiggingDepth`, which no amount
of float/bool patching could create.

**Two directories are easy to confuse.** `static_meshes_parts/sm_*.jsonl` is
what `ue.py` writes from the editor; `map_work_meshes/mesh_*.jsonl` is what
`import_meshes.py` stages and what the injector actually streams. Reading the
stale one wastes a round trip -- check timestamps before drawing conclusions.

**Build invocation:** run `build.bat` through PowerShell. A backgrounded Bash
task does not inherit the shell's working directory, and `cmd //c build.bat`
cannot resolve it from an MSYS path -- both fail instantly with "not
recognized". The PowerShell NativeCommandError noise around stderr is
harmless.

**Resuming a build.** Steps 1-4 stage into the mod content tree, so a failure
at 5b can resume with
`--skip-clean --skip-meshes --skip-actors --skip-foliage-cells --skip-convert`
instead of redoing 14 minutes. `--skip-clean` is the critical one: without it
step 1 wipes the staged cells.
