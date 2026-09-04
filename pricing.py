#!/usr/bin/env python3
"""
pricing.py — price the island's custom cargo from weight, licence batch and
the real distance between the points that trade it.

    python pricing.py            # show the table, change nothing
    python pricing.py --write    # write BasePayment back into delivery_points.json

WHY IT IS COMPUTED HERE AND NOT IN GAME
---------------------------------------
MT can pay by distance itself: cargo rows carry PaymentPer1Km and the game
multiplies it by the ROAD distance it computes between the two points. That
calculation only finds a road when the route is on the vanilla road network.
The island is not on it, so per-km pays close to nothing there -- which is
exactly the "very far away and barely pays" symptom. Everything therefore has
to land in BasePayment, which is flat and always paid.

But BasePayment is one number per CARGO ROW, not per route. So the distance a
cargo travels has to be resolved at build time from the recipe graph: for each
cargo, look at every delivery point that produces it and every point that
consumes it, and measure the real world-space gap. The player will always run
the cheapest pair available, so the SHORTEST producer->consumer run sets the
price. Every longer haul of the same cargo then pays the same, which is the
honest trade-off for a per-row field -- and it means no route can be farmed by
picking the short one.

THE MODEL
---------
    pay = kg**WEIGHT_EXP * RATE * batch * (1 + km / KM_DOUBLES)

  WEIGHT_EXP  the GAME's own weight curve, fitted from its cargo rows
  RATE        the island premium -- ours, set well above what vanilla pays
  batch       licence tier 1-5, i.e. how big a rig the load needs
  km          shortest producer->consumer run on the island, in kilometres
  floor       FLOOR, so nothing is ever pocket change

The exponent is measured, not chosen. Fitting MT's PaymentPer1Km against the
weights it ships gives payout ~ kg^0.63 -- a 30 t transformer is worth about
10x a 800 kg fuel load, not 37x. Per kilogram that is steeply REGRESSIVE:
0.375 coins/km/kg for fuel, 0.017 for a 30 t container. Any flat per-kg rate
disagrees with the game by an order of magnitude at the top of the range.

So the SHAPE comes from the game and only the LEVEL is ours. Raising RATE
makes the island pay better than the mainland without distorting what the
game considers a load to be worth relative to any other load.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
DP_JSON = REPO / "delivery_points.json"
CATALOG = REPO / "CargoImport" / "cargos" / "catalog.json"
WEIGHTS = REPO / "CargoImport" / "cargos" / "weights.tsv"

# ---- the knobs -------------------------------------------------------------
# Weight curve, taken from the game rather than invented. Fitting MT's own
# PaymentPer1Km against the weights it ships gives payout ~ kg^0.63: the game
# pays a 30 t transformer about 10x a 800 kg fuel load, not 37x. Per kilogram
# that is steeply regressive -- 0.375 coins/km/kg for fuel down to 0.017 for a
# 30 t container -- which is the opposite of a flat per-kg rate.
#
# The old model was linear to 5 t then sqrt above, a two-piece guess that was
# progressive where the game is regressive and needed a hand-tuned knee.
# One exponent matching the game's own curve replaces both.
WEIGHT_EXP  = 0.63
RATE        = 300.0    # coins per kg^0.63 at batch 1 on a zero-length run
# Doubled from 150 on 2026-09-03. Hauling on Arini is longer and rougher than
# on Jeju's road network, and the old level made a full container worth less
# than a short shuttle between two adjacent yards.
FLOOR       = 1000     # no delivery ever pays less than this
KM_DOUBLES  = 5.0      # a run this long doubles the pay

# OVERSIZED LOADS. Weight alone underprices these badly: a 250 kL tank and a
# 20 MVA transformer weigh what a container weighs but take a specialist rig,
# block a lane, and cannot be stacked. The weight curve cannot see volume, so
# it is applied here instead of pretending kg captures it.
# TERRAIN. Distance is not difficulty. The dish tower sits at the top of the
# island and Dorna is up the valley behind it -- getting a loaded rig to either
# is the hardest driving on Arini, and a straight-line kilometre says nothing
# about that. `difficulty` on a delivery point multiplies what arriving there
# pays, so the premium lands on hauls that earn it.
#
# The premium SCALES WITH WEIGHT, because that is what the difficulty actually
# is. A 30 t transformer up to the dish tower is the hardest run on the island;
# 800 kg of water over the same road is a normal drive, and paying it a climb
# premium just makes a short haul farmable. So a load at or above HEAVY_KG gets
# the full multiplier and anything lighter gets a proportional share of it.
DEFAULT_DIFFICULTY = 1.0
HEAVY_KG = 10_000.0    # a steel coil: the weight at which a climb is properly hard


def terrain_mult(difficulty: float, kg: float) -> float:
    if difficulty <= 1.0:
        return 1.0
    share = min(1.0, kg / HEAVY_KG)
    return 1.0 + (difficulty - 1.0) * share

OVERSIZE_MULT = 10.0
OVERSIZE = {"Transformer_20MVAX", "Tank_250kLX"}
DEFAULT_KG  = 500.0    # cargo with no weight anywhere in the game data

# Licence batch by cargo type: what size of vehicle the load actually needs.
# CargoType comes straight from the game's cargo rows.
BATCH_BY_TYPE = {
    "SmallPackage": 1, "Food": 1, "Garbage": 1,
    "LargePackage": 2, "Furniture": 2, "FinalProduct": 2,
    "Sand": 3, "Stone": 3, "Coal": 3, "Concrete": 3, "Wood": 3,
    "Log": 4, "MilitarySupply": 4,
    "Container": 5,
}
# Tanker loads. The game files the lot under CargoType "None" together with
# ordinary pallets, so weight alone would rate an 800 kg fuel load as a B2 van
# job. Anything that needs a tank needs a tanker, and a tanker is a B5 licence.
TANKER = {"Fuel", "Oil", "CrudeOil", "Milk", "LiquidNitrogen", "JetFuel",
          "MoltenPlastic", "Water"}
# Fallback when neither of the above applies: bracket on weight.
WEIGHT_BRACKETS = [(500, 1), (1500, 2), (3500, 3), (10000, 4)]

UU_PER_KM = 100000.0   # Unreal units per kilometre


def load_weights() -> dict[str, float]:
    """name -> max weight in kg. The game ships a min and a max; the max is
    what a full load actually weighs, so that is what gets paid for."""
    out: dict[str, float] = {}
    if not WEIGHTS.exists():
        return out
    for line in WEIGHTS.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2].strip():
            try:
                out[parts[0].strip()] = float(parts[2])
            except ValueError:
                pass
    return out


def batch_for(name: str, row: dict, kg: float) -> int:
    if name in TANKER or row.get("copy_from") in TANKER:
        return 5
    t = row.get("CargoType")
    if t in BATCH_BY_TYPE:
        return BATCH_BY_TYPE[t]
    for limit, b in WEIGHT_BRACKETS:
        if kg <= limit:
            return b
    return 5


# What one cargo slot's worth of space is, in kg. MEASURED: the median
# kg-per-slot across every vanilla row that declares both (VolumeSize is 1.0
# on all of them, so this is just the median vanilla cargo weight). It is the
# break-even point -- a load denser than this is paid for its mass, a load
# lighter than this is paid for the space it ties up.
KG_PER_SLOT = 1_700.0


def chargeable_kg(kg: float, volume: float) -> float:
    """What a load costs to move: the greater of what it weighs and what it
    displaces.

    A truck fills by weight or by space, whichever runs out first, so paying
    purely by mass underpays anything bulky and light -- a dinghy is 50 kg and
    takes up a boat's worth of deck. This is the freight trade's chargeable
    weight, and it is a max() rather than a product on purpose: a load that is
    both heavy AND bulky already gets paid for the heavy part, and multiplying
    the two would bill it twice for one trip.
    """
    if volume and volume > 0:
        return max(kg, volume * KG_PER_SLOT)
    return kg


def weight_value(kg: float) -> float:
    """What a load is worth by weight, on the game's own curve.

    RATE is deliberately well above what vanilla pays: the island is a harsh
    place to reach and every run out here should be worth more than the same
    run in Jeju. The SHAPE is the game's, the LEVEL is ours."""
    return kg ** WEIGHT_EXP


def shortest_run(cargo: str, prod: dict, cons: dict, co: dict) -> tuple[float, str, str] | None:
    """The cheapest producer->consumer pair for this cargo, in km. That pair
    is the one a player will actually run, so it sets the price."""
    best = None
    for src, _ in prod.get(cargo, []):
        for dst, _ in cons.get(cargo, []):
            if src == dst or src not in co or dst not in co:
                continue
            d = math.dist(co[src], co[dst]) / UU_PER_KM
            if best is None or d < best[0]:
                best = (d, src, dst)
    return best


def price(kg: float, batch: int, km: float, name: str = "", difficulty: float = 1.0) -> int:
    mult = OVERSIZE_MULT if name in OVERSIZE else 1.0
    return max(FLOOR, round(weight_value(kg) * RATE * batch
                            * (1 + km / KM_DOUBLES) * mult
                            * terrain_mult(difficulty, kg)))


def compute() -> tuple[list[tuple], dict, dict, dict]:
    """(display rows, name -> (pay, kg, batch, km, route), catalog, graph)."""
    import economy_report as E  # reuse the coordinate + recipe-graph loaders
    d, cat, custom, dps = E.load()
    co = E.coords(dps)
    prod, cons = E.build(dps, cat, custom, co)
    kgs = load_weights()

    rows, updates = [], {}
    for name in sorted(custom):
        c = custom[name]
        run = shortest_run(name, prod, cons, co)
        km = run[0] if run else 0.0
        kg = float(c.get("weight_kg") or kgs.get(name) or kgs.get(c.get("copy_from", "")) or DEFAULT_KG)
        # Licence tier comes from what the load WEIGHS -- that is what decides
        # the truck you need. Volume decides what you are PAID for the space it
        # ties up. Feeding chargeable weight into both compounded them: a 50 kg
        # dinghy went from a B1 van to a B4 rig and priced at 73x.
        batch = int(c.get("batch") or batch_for(name, c, kg))
        # VolumeSize is the slot count the row declares; absent means one slot.
        kg = chargeable_kg(kg, float(c.get("VolumeSize") or 1.0))
        if "base_payment" in c:      # explicit escape hatch, e.g. contraband
            pay, note = int(c["base_payment"]), "fixed"
        else:
            dest = run[2] if run else None
            diff = float((dps.get(dest) or {}).get("difficulty", DEFAULT_DIFFICULTY)) if dest else 1.0
            pay = price(kg, batch, km, name, diff)
            note = "oversize x10" if name in OVERSIZE else ""
            eff = terrain_mult(diff, kg)
            if eff > 1.001:
                note = (note + " " if note else "") + f"terrain x{eff:.2f}"
        route = f"{run[1]}->{run[2]}" if run else "NO ROUTE"
        rows.append((name, kg, batch, km, pay, route, note))
        updates[name] = (pay, kg, batch, km, route)
    return rows, updates, cat, {"prod": prod, "cons": cons, "custom": custom}


def stale_prices() -> list[tuple[str, int, int]]:
    """(cargo, stored BasePayment, computed) for every row whose price no
    longer matches where its delivery points sit. Empty when all is well."""
    _, updates, _, g = compute()
    out = []
    for name, (pay, *_rest) in updates.items():
        have = int(g["custom"][name].get("BasePayment", 0))
        if have != pay:
            out.append((name, have, pay))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="write the computed BasePayment back into delivery_points.json")
    args = ap.parse_args()

    rows, updates, cat, g = compute()
    prod, cons, custom = g["prod"], g["cons"], g["custom"]

    w = max(len(r[0]) for r in rows)
    print(f"{'cargo'.ljust(w)}  {'kg':>7} {'B':>2} {'km':>6} {'pay':>9}  route")
    for n, kg, b, km, pay, route, note in rows:
        print(f"{n.ljust(w)}  {kg:7.0f} B{b} {km:6.2f} {pay:9,}{'*' if note else ' '} {route}")
    print(f"\n  pay = kg^{WEIGHT_EXP:g} * {RATE:g} * batch * (1 + km/{KM_DOUBLES:g}), floor {FLOOR:,}"
          f"\n  exponent is the game's own weight curve, {RATE:g} is the island premium"
          f"\n  * = fixed price, not computed")

    # Vanilla rows carried on island routes. These cannot be repriced without
    # changing Jeju, and a zero-base per-km row pays almost nothing out here.
    thin = []
    for c in sorted(set(prod) | set(cons)):
        if c in custom:
            continue
        r = cat.get(c) or {}
        if not r.get("BasePayment") and r.get("PaymentPer1Km"):
            thin.append(c)
    if thin:
        print(f"\n  {len(thin)} vanilla row(s) on island routes pay per-km with zero base, so they "
              f"pay near nothing here:\n    {', '.join(thin)}")

    if not args.write:
        print("\n(dry run — pass --write to apply)")
        return 0

    # Rewrite in place so the numbers stay visible in the JSON and in git diff,
    # rather than being conjured at build time where nobody can see them.
    src = DP_JSON.read_text(encoding="utf-8")
    doc = json.loads(src)
    for entry in doc.get("new_cargos") or []:
        u = updates.get(entry.get("new_id"))
        if not u:
            continue
        pay, kg, batch, km, route = u
        entry["BasePayment"] = pay
        entry["PaymentPer1Km"] = 0
        entry["_"] = (f"{kg:.0f} kg on a B{batch} rig over {km:.2f} km ({route}) "
                      f"= {pay:,} flat. Computed by pricing.py — do not hand-edit.")
    # ensure_ascii matches how the file is already written, so the diff shows
    # the prices that changed and not every em-dash in the documentation.
    DP_JSON.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {len(updates)} cargo price(s) to {DP_JSON.name}")
    return 0


def _selfcheck() -> None:
    assert abs(price(800, 5, 5) - 2 * price(800, 5, 0)) <= 1    # KM_DOUBLES doubles it
    assert price(1, 1, 0) == FLOOR                              # floor holds
    # Regressive per kg, like the game: 37x the weight is ~10x the pay.
    r = price(30000, 1, 0) / price(800, 1, 0)
    assert 8 < r < 13, r
    assert batch_for("Fuel", {"CargoType": "None"}, 800) == 5    # tanker beats weight
    assert batch_for("SmallBox", {"CargoType": "SmallPackage"}, 5) == 1
    assert batch_for("Mystery", {}, 30000) == 5                 # weight fallback
    print("pricing selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        raise SystemExit(main())
