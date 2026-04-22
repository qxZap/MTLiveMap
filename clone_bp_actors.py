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
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from bp_registry import REGISTRY, CELLS_DIR, JEJU_MAIN, template_for_class

MAPPINGS = r"D:\MT\MotorTown718P1.usmap"
INJECTOR = Path("MTBPInjector/bin/Release/net8.0/MTBPInjector.exe")
# Fallback template cell used when creating a new WP cell for far coords.
# Chosen for a native-only actor list (no BP wrappers to accidentally carry
# over) and enough actor slots to host dozens of injected BP clones in a
# single cell: 35 slots. Clones replace existing Actors-list entries so the
# PersistentLevel body layout stays the size UE's ULevel::Serialize expects.
TEMPLATE_CELL = "0V18V8JBXKXUL8YILWZKCSMB4"


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
                       x: float, y: float, mod_gen_dir: Path,
                       hier_level: int = -1, grid_levels_index: int = 0) -> bool:
    # Each hierarchical level doubles the cell size; extent at level N is
    # 6400 * 2^(N+1). At level -1 we use 6400 (the base).
    extent = 6400 * (2 ** (hier_level + 1))
    cmd = [
        str(INJECTOR), "register-new-cell",
        "--main", main_path,
        "--output", out_path,
        "--mappings", MAPPINGS,
        "--template-cell", TEMPLATE_CELL,
        "--new-cell-name", new_cell,
        "--x", f"{x}",
        "--y", f"{y}",
        "--extent", str(extent),
        "--grid", "MainGrid",
        "--hier-level", str(hier_level),
        "--grid-levels-index", str(grid_levels_index),
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
    # For created cells we replace template slots in-place (can't grow Actors
    # list without bloating per-actor metadata, which UE rejects). Count the
    # slot index per created cell so each actor goes into the next slot.
    slot_counter: dict[str, int] = {}
    MAX_SLOTS_PER_CREATED_CELL = 4  # matches TEMPLATE_CELL's Actors.Count

    # DEBUG: set MAX_BP=1 to clone only the first entry.
    _max = int(os.environ.get("MAX_BP", "999999"))
    if _max < len(entries):
        print(f"  [debug] MAX_BP={_max} — limiting from {len(entries)} entries")
        entries = entries[:_max]
    # DEBUG: set BP_SKIP=ParkingSmall,ParkingMedium to skip specific BP classes
    _skip = set(k.strip() for k in os.environ.get("BP_SKIP", "").split(",") if k.strip())
    if _skip:
        before = len(entries)
        # Match on either blueprint_class or the short name derived from asset_key
        def _match(e):
            cls = e.get("blueprint_class", "")
            return cls in _skip or any(k in cls for k in _skip)
        entries = [e for e in entries if not _match(e)]
        print(f"  [debug] BP_SKIP={sorted(_skip)} — {before} -> {len(entries)} entries")

    # First pass: resolve/create destination cell per entry, group entries by
    # cell. Second pass: run ONE clone-batch call per cell (all clones into
    # that cell happen in a single UAssetAPI load/save).
    grouped: dict[str, list] = {}   # cell_name -> list[(entry, tpl, is_created)]

    # Auto-shard state: when the home L-1 tile fills up, spill into adjacent
    # L-1 tiles (same hier-level, neighbor grid coords). WP streams neighbor
    # tiles together with the home tile, so the actors spawn as if in one
    # big cell — without needing higher hierarchical levels (whose key math
    # in register-new-cell isn't verified).
    # Expanding ring of tile offsets around the home tile. Generated on demand
    # so there's no cap on how many actors can be placed at one island — each
    # extra shard adds MAX_SLOTS_PER_CREATED_CELL slots. Order: center, then
    # rings of increasing Chebyshev distance (1, 2, 3, ...).
    def tile_offset(idx: int) -> tuple[int, int]:
        if idx == 0:
            return (0, 0)
        # Find ring r such that (2r-1)^2 <= idx < (2r+1)^2.
        r = 1
        while (2 * r + 1) ** 2 <= idx:
            r += 1
        local = idx - (2 * r - 1) ** 2       # 0..(8r-1)
        side = 2 * r                          # length of each ring side
        s = local // side                     # which side 0..3
        t = local %  side                     # position along side
        if s == 0: return ( r,     -r + t)    # right
        if s == 1: return ( r - t,  r)        # top
        if s == 2: return (-r,      r - t)    # left
        return (-r + t, -r)                   # bottom

    shards: dict[tuple[int, int], list[str]] = {}  # home_grid -> [cell_name per offset index]

    def pick_cell_for_entry(e):
        # Returns (cell_name, is_created)
        cell = resolve_cell(e["X"], e["Y"])
        if cell is not None:
            return cell, False
        home = (int(e["X"] // 12800), int(e["Y"] // 12800))
        chain = shards.get(home, [])
        # Reuse existing shard with remaining slots
        for cell_name in chain:
            if slot_counter.get(cell_name, 0) < MAX_SLOTS_PER_CREATED_CELL:
                return cell_name, True
        # Create a new L-1 tile at the next ring offset.
        idx = len(chain)
        dx, dy = tile_offset(idx)
        tile_gx, tile_gy = home[0] + dx, home[1] + dy
        # Cell's own center (for WP bounds): middle of that tile.
        cx = (tile_gx + 0.5) * 12800.0
        cy = (tile_gy + 0.5) * 12800.0
        new_cell = make_cell_name(cx, cy)
        print(f"  [{entry_idx_ref[0]}] shard #{idx+1} for home {home}: creating L-1 cell '{new_cell}' at tile ({tile_gx},{tile_gy})")
        nonlocal main_in
        if not register_new_cell(main_in, main_out, new_cell,
                                 cx, cy, gen_dir,
                                 hier_level=-1,
                                 grid_levels_index=0):
            return None, False
        chain.append(new_cell)
        shards[home] = chain
        seeded.add(new_cell)
        main_in = main_out
        return new_cell, True

    entry_idx_ref = [0]
    for i, e in enumerate(entries):
        entry_idx_ref[0] = i
        bp_class = e.get("blueprint_class")
        tpl_entry = template_for_class(bp_class)
        if not tpl_entry:
            print(f"  [{i}] skipped — no registry entry for {bp_class}")
            continue

        cell, needs_create = pick_cell_for_entry(e)
        if cell is None:
            print(f"  [{i}] failed to pick/create cell for ({e['X']},{e['Y']})", file=sys.stderr)
            return 1
        # Seed cell from vanilla once (for existing vanilla cells)
        if not needs_create and cell not in seeded:
            for ext in (".umap", ".uexp"):
                src = CELLS_DIR / f"{cell}{ext}"
                dst = gen_dir / f"{cell}{ext}"
                if src.exists():
                    shutil.copy2(src, dst)
            seeded.add(cell)

        if os.environ.get("SKIP_BP_CLONE") == "1":
            print(f"  [{i}] SKIP_BP_CLONE=1 — cell registered, actor clone skipped")
            continue

        # Bump slot counter for created cells (used by next entry's shard check).
        if needs_create:
            slot_counter[cell] = slot_counter.get(cell, 0) + 1
            assigned_slot = slot_counter[cell] - 1
        else:
            assigned_slot = None

        print(f"  [{i}] {bp_class} @ ({e['X']}, {e['Y']}, {e['Z']}) -> cell {cell}" + (f" slot={assigned_slot}" if assigned_slot is not None else ""))
        grouped.setdefault(cell, []).append((e, tpl_entry, needs_create, assigned_slot))

    # Second pass: one clone-batch per cell (all clones share a single
    # UAssetAPI load/save, preventing integrity drift from repeated saves).
    import json as _json, tempfile
    for cell, items in grouped.items():
        specs = []
        for (e, tpl, is_created, assigned_slot) in items:
            spec = {
                "source_umap":  str(tpl["source_umap"]),
                "source_actor": tpl["source_actor"],
                "x": e["X"], "y": e["Y"], "z": e["Z"],
                "pitch": e.get("Pitch", 0.0),
                "yaw":   e.get("Yaw", 0.0),
                "roll":  e.get("Roll", 0.0),
            }
            pb = tpl.get("preload_bp")
            if pb:
                if isinstance(pb, (list, tuple)):
                    spec["preload_bp"] = ";".join(str(x) for x in pb)
                else:
                    spec["preload_bp"] = str(pb)
            if is_created and assigned_slot is not None:
                spec["slot"] = assigned_slot
            specs.append(spec)
        if not specs:
            continue

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
            _json.dump(specs, tf)
            spec_path = tf.name
        try:
            r = subprocess.run([
                str(INJECTOR), "clone-batch",
                "--mappings", MAPPINGS,
                "--dst-cell", str(gen_dir / f"{cell}.umap"),
                "--output",   str(gen_dir / f"{cell}.umap"),
                "--spec", spec_path,
            ], capture_output=True, text=True)
        finally:
            try: os.unlink(spec_path)
            except OSError: pass

        if r.returncode != 0:
            print(r.stdout)
            print(r.stderr, file=sys.stderr)
            return r.returncode
        for line in r.stdout.splitlines():
            if line.strip(): print(f"      {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
