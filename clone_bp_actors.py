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
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from bp_registry import REGISTRY, CELLS_DIR, JEJU_MAIN, template_for_class

MAPPINGS = r"D:\MT\MotorTown718P1.usmap"
INJECTOR = Path("MTBPInjector/bin/Release/net8.0/MTBPInjector.exe")
# Fallback template cell (small L-1 MainGrid cell with minimal content) used
# when we have to create a new WP cell for far coords.
TEMPLATE_CELL = "0W5HFJERQNYIKT4TIFEZBU4PD"


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
    # Filter to cells that have a .umap file on disk and are small enough to
    # stream (L10 / Landscape catch-alls at center 0,0 with ext=6.5M don't
    # spawn runtime BP actors we inject into them).
    owners = [(lvl, grid, name) for (lvl, grid, name) in owners
              if (CELLS_DIR / f"{name}.umap").exists() and lvl <= 2]
    if not owners:
        return None
    owners.sort(key=lambda t: (t[0], 0 if t[1] == "MainGrid" else 1))
    return owners[0][2]


def make_cell_name(x: float, y: float) -> str:
    """Deterministic 25-char [A-Z0-9] name derived from coords — safe identifier."""
    h = hashlib.sha1(f"{x:.2f}_{y:.2f}".encode()).hexdigest().upper()
    # Keep 25 alphanumeric chars (vanilla cell names look like base32)
    safe = "".join(c for c in h if c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")[:25]
    return "MOD" + safe[:22]


def register_new_cell(main_path: str, out_path: str, new_cell: str,
                       x: float, y: float, mod_gen_dir: Path) -> bool:
    cmd = [
        str(INJECTOR), "register-new-cell",
        "--main", main_path,
        "--output", out_path,
        "--mappings", MAPPINGS,
        "--template-cell", TEMPLATE_CELL,
        "--new-cell-name", new_cell,
        "--x", f"{x}",
        "--y", f"{y}",
        "--extent", "6400",
        "--grid", "MainGrid",
        "--hier-level", "-1",
        "--grid-levels-index", "0",
        "--cells-dir", str(CELLS_DIR),
        "--mod-cells-dir", str(mod_gen_dir),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr, file=sys.stderr)
    else:
        for line in r.stdout.splitlines():
            if line.strip(): print(f"    {line}")
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--gen-dir", required=True, help="Mod _Generated_ directory")
    ap.add_argument("--main-in", help="Jeju_World.umap to modify for new cells")
    ap.add_argument("--main-out", help="Output Jeju_World.umap after new-cell registrations")
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

    main_in = args.main_in
    main_out = args.main_out or main_in
    created_cells: dict[tuple[int, int], str] = {}

    for i, e in enumerate(entries):
        bp_class = e.get("blueprint_class")
        tpl_entry = template_for_class(bp_class)
        if not tpl_entry:
            print(f"  [{i}] skipped — no registry entry for {bp_class}")
            continue

        cell = resolve_cell(e["X"], e["Y"])
        needs_create = cell is None
        if needs_create:
            # Dedupe by cell grid coord so multiple actors in the same island
            # share one created cell instead of re-registering.
            grid_key = (int(e["X"] // 12800), int(e["Y"] // 12800))
            if grid_key in created_cells:
                cell = created_cells[grid_key]
                print(f"  [{i}] reusing cell '{cell}' for ({e['X']}, {e['Y']})")
            else:
                cell = make_cell_name(e["X"], e["Y"])
                print(f"  [{i}] no existing WP cell — creating new cell '{cell}' at ({e['X']}, {e['Y']})")
                if not main_in:
                    print("     need --main-in to register new cells", file=sys.stderr)
                    return 1
                if not register_new_cell(main_in, main_out, cell, e["X"], e["Y"], gen_dir):
                    return 2
                created_cells[grid_key] = cell
                seeded.add(cell)
                # Point subsequent registrations at the freshly-written map
                main_in = main_out
        # Seed cell from vanilla once (for existing vanilla cells)
        elif cell not in seeded:
            for ext in (".umap", ".uexp"):
                src = CELLS_DIR / f"{cell}{ext}"
                dst = gen_dir / f"{cell}{ext}"
                if src.exists():
                    shutil.copy2(src, dst)
            seeded.add(cell)

        # Debug toggle: set SKIP_BP_CLONE=1 env to register the cell only (no
        # BP actor content inside it). Useful to test whether the cell
        # registration itself is valid.
        import os
        if os.environ.get("SKIP_BP_CLONE") == "1":
            print(f"  [{i}] SKIP_BP_CLONE=1 — cell registered, actor clone skipped")
            continue

        cmd = [
            str(INJECTOR), "clone-cross-cell",
            "--mappings", MAPPINGS,
            "--source-cell", str(tpl_entry["source_umap"]),
            "--source-actor", tpl_entry["source_actor"],
            "--dst-cell", str(gen_dir / f"{cell}.umap"),
            "--output", str(gen_dir / f"{cell}.umap"),
            "--x", f"{e['X']}",
            "--y", f"{e['Y']}",
            "--z", f"{e['Z']}",
        ]
        if tpl_entry["preload_bp"]:
            cmd += ["--preload-bp", str(tpl_entry["preload_bp"])]
        print(f"  [{i}] {bp_class} @ ({e['X']}, {e['Y']}, {e['Z']}) -> cell {cell}")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout)
            print(r.stderr, file=sys.stderr)
            return r.returncode
        for line in r.stdout.splitlines():
            if line.strip(): print(f"      {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
