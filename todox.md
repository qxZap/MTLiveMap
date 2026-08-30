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

       BusStop_<Name>      a bus stop
       Home_<Name>         somewhere people live
       Work_<Name>         somewhere people work
       Zones/<Key>/Border_01, Border_02, ...   a zone's outline, in order

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

| row / name | sold where | notes |
|---|---|---|
| kart_01 | | |
| Trailer_9m_Flat_01 | | |
| Trailer_30ft_Log_01 | | |
| Trailer_01 | | |
| Trailer_30ft_Tanker_01 | | |
| Vulcan | | |
| Bus | | |
| Ambi | | |
| Nimo_Taxi | | |
| Nuke_Taxi | | |
| Trophy_Taxi | | |
| Brutus_FireEngine | | |
| thropy air | | |

Categories still wanted, from the old list: old trailers, cop cars, crany,
rare ones, disabled ones.

---

## Places to build

What, where, how many. "Parking spaces" is a request; "8 parking spaces at the
Arini refinery" is a job.

- [ ] more garages — WHERE, and how many?
- [ ] parking spaces — WHERE, and how many?
- [ ] death road — where does it start and end?
- [ ] marcaje unde e ce (signage) — which places need naming?
- [ ] slope angle — which slope, and what is wrong with it?

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
- [ ] **Bus stops near where people are.** `BusStop_<Name>`. Every stop is
      still out on the bridge and the median walk from a delivery point is
      6 km, which is why stops sit empty even though people spawn and board.
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

- [ ] Foliage is OFF in the current pak — every build since the bus stop work
      has been `--skip-foliage` (696 MB vs ~1146 MB). Say the word for a full
      one.
- [ ] Foliage pop-in on approach.
- [ ] Snow should sink you the way mud does (a NEW cloned material, not an
      edit to the vanilla one) — TODO.md §11.
- [ ] Console variables never reach the game; `merge_config.py` is inert.
- [ ] PARKED: soft limits. 20 attachments per vehicle, ~20 vehicles per
      company. `MaxVehiclePerPlayer` is an Int on `MTServerRuntimeConfig`, so
      it is server config rather than a packaged asset -- the open question is
      whether the singleplayer host reads it, because if it does this is a
      config line and not a mod at all. Attachments have no governing property
      anywhere in the schema, which points at a C++ constant no pak can move.
      Coming back to this later.
- [ ] `Zone Test Gangjung` is a leftover diagnostic stop and can be deleted.
- [ ] Bridge stop 5 sits east of the boundary, so it belongs to Hallim rather
      than Arini.
