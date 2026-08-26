#!/usr/bin/env python3
"""
unlock_vehicles.py — make every vehicle the game ships obtainable.

Motor Town hides a chunk of its own fleet behind `bHidden` / `bDisabled`
on the Vehicles* DataTables: the kart, the trophy truck, four full-size
trailers, Crany, Goliath4-DB. The models are all there, no player can
reach them. This clears those flags and drops the role/part gating, so
the shop lists everything and any part fits anything.

MOD AWARENESS IS THE POINT. Our pak loads last, so if we built these
tables from vanilla we would silently revert any economy mod that edits
the same rows — CapitalistEconomy ships thirteen of the fifteen tables
and has already unlocked them. Every table is therefore read through
`effective_asset`, i.e. the copy the game actually loads, and our changes
land on top of whatever the user already runs.

Police vehicles are left locked on purpose: the map hands those out via
spawn points, which is more interesting than buying one.

    python unlock_vehicles.py [--include-police] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from mt_paths import (GAME_PAKDIR, MAPPINGS, MOD_CONTENT_ROOT, MT_AES_KEY, REPAK, REPO_ROOT_P,
                      WORK_DIR, effective_asset)

INJECTOR = REPO_ROOT_P / "MTBPInjector" / "bin" / "Release" / "net8.0" / "MTBPInjector.exe"
MOD_CONTENT = MOD_CONTENT_ROOT
TABLE_DIR = "DataAsset/Vehicles"

# Our own output is never an input — it would compound every build.
OURS = "zzzz_MapChangeTest"


def discover_tables() -> list[str]:
    """Every Vehicles* table any installed pak ships, as Content-relative
    paths. Mods may add tables vanilla never had, so this is a scan of the
    whole load order rather than a hardcoded list."""
    found: set[str] = set()
    if not (GAME_PAKDIR.is_dir() and Path(REPAK).is_file()):
        print("  repak or Paks/ unavailable — cannot discover vehicle tables",
              file=sys.stderr)
        return []
    for pak in sorted(GAME_PAKDIR.glob("*.pak"), key=lambda p: p.name.lower()):
        if pak.name.startswith(OURS):
            continue
        r = subprocess.run([str(REPAK), "--aes-key", MT_AES_KEY, "list", str(pak)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            continue
        for line in r.stdout.splitlines():
            e = line.strip().replace("\\", "/")
            if f"/{TABLE_DIR}/" in e and e.endswith(".uasset"):
                found.add(e.split("MotorTown/Content/", 1)[-1])
    return sorted(found)


_ROW_TO_CLASS: dict[str, str] | None = None


def vehicle_class_by_row() -> dict[str, str]:
    """DataTable row name -> the vehicle BP's /Game path.

    A row's name is NOT always its asset's name: row `Police_01` points at
    `/Game/Cars/Models/Police/Police`, `Nuke_Police` at `.../Nuke/NukePolice`,
    `Trailer_30ft_Log_01` at `.../Trailer_9m_Flat_01/Trailer_9m_Log_01`.
    Anything resolving vehicles by filename misses those, so ask the table.

    Read through the same effective (mod-aware) tables as the unlock pass,
    and cached for the process.
    """
    global _ROW_TO_CLASS
    if _ROW_TO_CLASS is not None:
        return _ROW_TO_CLASS
    out: dict[str, str] = {}
    if INJECTOR.is_file():
        for rel in discover_tables():
            src = effective_asset(rel)
            if not src.is_file():
                continue
            r = subprocess.run([str(INJECTOR), "dump-table", "--uasset", str(src),
                                "--mappings", str(MAPPINGS), "--fields", "VehicleClass"],
                               capture_output=True, text=True)
            if r.returncode != 0:
                continue
            for line in r.stdout.splitlines():
                p = line.split("\t")
                if len(p) == 2 and p[0].strip() and p[1].strip():
                    out.setdefault(p[0], p[1])
    _ROW_TO_CLASS = out
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-police", action="store_true",
                    help="also unlock police vehicles (default: leave them "
                         "unbuyable, reachable only from a spawn point)")
    ap.add_argument("--ai-mult", default=os.environ.get("MTMI_VEH_AI_MULT", "0.25"))
    ap.add_argument("--ai-mult-offroad", default=os.environ.get("MTMI_VEH_AI_MULT_OFFROAD", "0.4"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not INJECTOR.is_file():
        print(f"  MTBPInjector not built: {INJECTOR}", file=sys.stderr)
        return 1

    tables = discover_tables()
    if not tables:
        print("  no vehicle tables found — nothing to unlock")
        return 0
    print(f"  {len(tables)} vehicle table(s) in the load order")

    out_dir = MOD_CONTENT / TABLE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for rel in tables:
        # effective_asset returns the copy the GAME loads: a mod's version
        # when one overrides it, vanilla otherwise. Building on that is what
        # keeps us additive instead of destructive.
        src = effective_asset(rel)
        if not src.is_file():
            print(f"    {rel}: no readable source — skipped", file=sys.stderr)
            continue
        dst = out_dir / src.name
        if args.dry_run:
            print(f"    would rewrite {rel} from {src}")
            continue
        cmd = [str(INJECTOR), "unlock-vehicles",
               "--uasset", str(src), "--output", str(dst),
               "--mappings", str(MAPPINGS),
               "--ai-mult", str(args.ai_mult),
               "--ai-mult-offroad", str(args.ai_mult_offroad)]
        if args.include_police:
            cmd.append("--include-police")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"    {rel}: unlock failed\n{r.stderr.strip()[:400]}", file=sys.stderr)
            return 1
        for line in r.stdout.splitlines():
            if line.strip():
                print(line.rstrip())
        # UAssetAPI writes the .uexp beside the .uasset; both must ship.
        total += 1
    print(f"  vehicle tables rewritten: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
