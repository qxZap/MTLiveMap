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

## Zones and people

New since the zone system works. A zone is what makes residents exist, and
residents are what make bus stops worth having.

- [ ] Bus stops near the delivery points. Currently every stop is on the
      bridge and the median walk from a delivery point is 6 km, which is why
      stops sit empty even though people now spawn and board.
- [ ] More zones? Each needs a `Zones/<Key>/` folder with 3+ `Border_NN`
      markers walked in one direction.
- [ ] How many people should Arini have? Population comes from how many
      Home_/Work_ POIs are inside the zone.

---

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
- [ ] `Zone Test Gangjung` is a leftover diagnostic stop and can be deleted.
- [ ] Bridge stop 5 sits east of the boundary, so it belongs to Hallim rather
      than Arini.
