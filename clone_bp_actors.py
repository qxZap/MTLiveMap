"""
Read blueprint_actors entries from map_work_changes.json and invoke
MTBPInjector's clone-cross-cell for each, using a vanilla source actor
whose byte layout the engine accepts.

Each BP entry's target cell is resolved automatically from its world
coords via MTBPInjector's find-cell-wp (walks the WP runtime hash and
returns the smallest cell whose spatial bounds contain the coords).

Add a new BP class by extending BP_TEMPLATES: point to a vanilla cell
(or the main Jeju_World.umap) that contains a working instance.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

MAPPINGS = r"D:\MT\MotorTown718P1.usmap"
GAME_CONTENT = r"D:\MT\Output\Exports\MotorTown\Content"
CELLS_DIR = Path(GAME_CONTENT) / "Maps" / "Jeju" / "Jeju_World" / "_Generated_"
JEJU_MAIN = Path(GAME_CONTENT) / "Maps" / "Jeju" / "Jeju_World.umap"
INJECTOR = Path("MTBPInjector/bin/Release/net8.0/MTBPInjector.exe")

# BP class -> (source .umap, source actor name, optional .uasset to preload for schema)
BP_TEMPLATES = {
    "Interaction_ParkingSpace_Large_C": (
        CELLS_DIR / "0MYO9WO9JBZ10BIDLXVFRXAOG.umap",
        "ParkingSpace_Large_01_UAID_2CF05D790A1CFFDB01_1915517403",
        Path(GAME_CONTENT) / "Objects" / "ParkingSpace" / "Interaction_ParkingSpace_Large.uasset",
    ),
    "GarageActorBP_C": (
        JEJU_MAIN,
        "GarageActor2",
        None,
    ),
}


def resolve_cell(x: float, y: float) -> str | None:
    """Ask MTBPInjector which vanilla WP cell contains (x,y). Returns cell name
    (without extension) or None if not found."""
    r = subprocess.run(
        [str(INJECTOR), "find-cell-wp",
         "--main", str(JEJU_MAIN),
         "--mappings", MAPPINGS,
         "--x", f"{x}",
         "--y", f"{y}"],
        capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return None
    # "Cells containing (x, y): N" then rows "  #idx <name> grid=... L<n> pos=(..) ext=.. owner=<cellName>"
    owners = []  # (level, grid, owner)
    mode = None
    for line in r.stdout.splitlines():
        if line.startswith("Cells containing"):
            mode = "containing"; continue
        if line.startswith("Nearest"):
            mode = "nearest"; continue
        if mode == "containing":
            m = re.search(r"grid=(\w+) L(-?\d+).*owner=([A-Z0-9]+)", line)
            if m:
                owners.append((int(m.group(2)), m.group(1), m.group(3)))
    if not owners:
        return None
    # Filter to cells that actually have a .umap file on disk (WP can declare
    # a cell in the runtime hash without a companion .umap if it's empty).
    owners = [(lvl, grid, name) for (lvl, grid, name) in owners
              if (CELLS_DIR / f"{name}.umap").exists()]
    if not owners:
        return None
    # Prefer: (a) smallest level (finest granularity), (b) MainGrid over Landscape
    # for non-terrain actors.
    owners.sort(key=lambda t: (t[0], 0 if t[1] == "MainGrid" else 1))
    return owners[0][2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--gen-dir", required=True, help="Mod _Generated_ directory")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    entries = []
    for group in cfg.get("blueprint_actors", {}).values():
        if isinstance(group, list):
            entries.extend(group)

    if not entries:
        print("No blueprint_actors entries.")
        return 0

    gen_dir = Path(args.gen_dir)
    gen_dir.mkdir(parents=True, exist_ok=True)
    seeded: set[str] = set()

    for i, e in enumerate(entries):
        bp_class = e.get("blueprint_class")
        tpl = BP_TEMPLATES.get(bp_class)
        if not tpl:
            print(f"  [{i}] skipped — no template for {bp_class}")
            continue

        cell = resolve_cell(e["X"], e["Y"])
        if cell is None:
            print(f"  [{i}] skipped — no WP cell contains ({e['X']}, {e['Y']})")
            continue

        # Seed cell from vanilla once
        if cell not in seeded:
            for ext in (".umap", ".uexp"):
                src = CELLS_DIR / f"{cell}{ext}"
                dst = gen_dir / f"{cell}{ext}"
                if src.exists():
                    shutil.copy2(src, dst)
            seeded.add(cell)

        src_cell, src_actor, preload = tpl
        cmd = [
            str(INJECTOR), "clone-cross-cell",
            "--mappings", MAPPINGS,
            "--source-cell", str(src_cell),
            "--source-actor", src_actor,
            "--dst-cell", str(gen_dir / f"{cell}.umap"),
            "--output", str(gen_dir / f"{cell}.umap"),
            "--x", f"{e['X']}",
            "--y", f"{e['Y']}",
            "--z", f"{e['Z']}",
        ]
        if preload:
            cmd += ["--preload-bp", str(preload)]
        print(f"  [{i}] {bp_class} @ ({e['X']}, {e['Y']}, {e['Z']}) -> cell {cell}")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout)
            print(r.stderr, file=sys.stderr)
            return r.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
