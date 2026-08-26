#!/usr/bin/env python3
"""
pack_vehicles.py — build a standalone pak of the vehicles.json changes.

    python pack_vehicles.py                 # everything vehicles.json defines
    python pack_vehicles.py --only modify   # only the in-place changes
    python pack_vehicles.py --only vehicles # only the new vehicles
    python pack_vehicles.py --name TankersFuelPump_P --out ~/Downloads

The island pak carries a whole map. Nothing about "tankers can refuel other
vehicles" needs any of it, and someone who wants that feature should not have
to take an island with it. This builds the vehicle work on its own so it can be
shipped as its own mod.

BUILT ON VANILLA, NOT ON THIS MACHINE'S MODS
    The main build resolves each DataTable through the installed paks, so our
    edits land on top of whatever else is installed and do not revert it. That
    is right for a pak only we load, and wrong for one handed to strangers: the
    tables would carry the local mods' edits along with ours. So this sets
    MTMI_VANILLA_BASE=1 and starts from the game's own files.

TWO VARIANTS, BECAUSE THE TABLES DIFFER
    A vehicle DataTable is shipped whole, not as a patch, so a pak built on
    vanilla will revert an economy mod's rows for anyone running one -- and one
    built on that mod carries its edits to everyone else. There is no single
    pak that is right for both, so ship one each:

      python pack_vehicles.py --base vanilla
      python pack_vehicles.py --base CapitalistEconomy_P \n                              --name TankersFuelPump_CapitalistEconomy_P

    Players install whichever matches what they already run.

    A THIRD is needed to run this ALONGSIDE the island. Arini ships whole
    vehicle tables and sorts last, so it reverts bHasFuelPump on every tanker
    this mod touches -- the class asset still loads, so the pump interaction
    appears and then reports zero capacity and "wrong fuel type", which looks
    like a broken feature rather than a load-order collision:

      python pack_vehicles.py --config vehicles_tankers.json --base Arini_P             --name ZZZZZ_TankersFuelPump_Arini_P

    Built on Arini's own tables, so it keeps Vista_GTR and the unlocks and
    only adds the pumps, and ZZZZZ_ sorts after zzzz_Arini_P.

WHAT ENDS UP IN IT
    Cars/Models/<vehicle>          the modified vehicle classes
    DataAsset/Vehicles/Vehicles*   the tables, for the row fields

    That is the whole feature. No map, no cargo, no delivery points.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="TankersFuelPump_P",
                    help="pak name. Must end in _P for the game to load it.")
    ap.add_argument("--only", choices=["all", "modify", "vehicles"], default="all",
                    help="'modify' = in-place changes (the tanker pumps); "
                         "'vehicles' = newly created vehicles; 'all' = both.")
    ap.add_argument("--out", default=None,
                    help="where to leave the .pak (default: the repo root)")
    ap.add_argument("--config", default="vehicles.json",
                    help="which config to pack (default vehicles.json). The "
                         "tanker pumps live in vehicles_tankers.json.")
    ap.add_argument("--base", default="vanilla", metavar="VANILLA|PAK",
                    help="what the DataTables are built on. 'vanilla' for the "
                         "unmodded game, or part of a pak's filename to layer "
                         "on that mod instead (e.g. CapitalistEconomy_P).")
    args = ap.parse_args()

    if not args.name.endswith("_P"):
        print(f"  '{args.name}' does not end in _P — the game will not load it",
              file=sys.stderr)
        return 1

    cfg_path = REPO / args.config
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    # A trimmed vehicles.json for this pak, so build_vehicles.py needs no flag
    # of its own and the selection lives in exactly one place.
    sel = dict(cfg)
    if args.only == "modify":
        sel["vehicles"] = []
    elif args.only == "vehicles":
        sel["modify"] = []
    n_new = len(sel.get("vehicles") or [])
    n_mod = len(sel.get("modify") or [])
    if not n_new and not n_mod:
        print(f"  nothing selected by --only {args.only}", file=sys.stderr)
        return 1
    print(f"  {args.name}: {n_new} new vehicle(s), {n_mod} modified in place")

    stage = REPO / args.name
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "MotorTown" / "Content").mkdir(parents=True)

    env = dict(os.environ)
    env["MTMI_MOD_NAME"] = args.name          # redirects MOD_CONTENT_ROOT
    if args.base.lower() == "vanilla":
        env["MTMI_VANILLA_BASE"] = "1"
        env.pop("MTMI_BASE_PAK", None)
    else:
        # Named, not load-order. Which pak "wins" depends on what happens to be
        # installed on the machine doing the build -- our own island pak
        # included -- so a compatibility variant has to name what it layers on.
        env.pop("MTMI_VANILLA_BASE", None)
        env["MTMI_BASE_PAK"] = args.base
    print(f"  tables based on: {args.base}")

    backup = cfg_path.with_suffix(".json.packbak")
    shutil.copy2(cfg_path, backup)
    try:
        cfg_path.write_text(json.dumps(sel, indent=2) + "\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(REPO / "build_vehicles.py"),
                            "--config", str(cfg_path)], cwd=REPO, env=env)
        if r.returncode != 0:
            print("  build_vehicles failed", file=sys.stderr)
            return 1
    finally:
        shutil.copy2(backup, cfg_path)        # always restore the real config
        backup.unlink()

    files = sorted(p for p in stage.rglob("*") if p.is_file())
    if not files:
        print("  build produced no files", file=sys.stderr)
        return 1
    print(f"  staged {len(files)} file(s):")
    roots: dict[str, int] = {}
    for f in files:
        rel = f.relative_to(stage / "MotorTown" / "Content")
        roots[str(rel.parent)] = roots.get(str(rel.parent), 0) + 1
    for d, n in sorted(roots.items()):
        print(f"      {n:>3}  {d}")

    repak = REPO / "tools" / "repak.exe"
    r = subprocess.run([str(repak) if repak.is_file() else "repak",
                        "pack", str(stage)], cwd=REPO)
    if r.returncode != 0:
        print("  repak failed", file=sys.stderr)
        return 1

    pak = REPO / f"{args.name}.pak"
    if not pak.is_file():
        print(f"  {pak} not produced", file=sys.stderr)
        return 1
    if args.out:
        dst = Path(os.path.expanduser(args.out))
        dst.mkdir(parents=True, exist_ok=True)
        shutil.move(str(pak), str(dst / pak.name))
        pak = dst / pak.name
    print(f"  wrote {pak}  ({pak.stat().st_size/1024/1024:.1f} MB)")
    print(f"  install: drop it in MotorTown/Content/Paks/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
