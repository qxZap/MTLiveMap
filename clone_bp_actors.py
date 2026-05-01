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

from bp_registry import REGISTRY, template_for_class
from mt_paths import GAME_CONTENT, CELLS_DIR, JEJU_MAIN, MAPPINGS, VANILLA_CARGOS_01

MAPPINGS = str(MAPPINGS)
INJECTOR = Path("MTBPInjector/bin/Release/net8.0/MTBPInjector.exe")
MOD_CONTENT_ROOT = Path("MapChangeTest_P/MotorTown/Content")
MOD_CARGOS        = MOD_CONTENT_ROOT / "DataAsset" / "Cargos.uasset"
MOD_CARGOS_01     = MOD_CONTENT_ROOT / "DataAsset" / "Cargos_01.uasset"


def load_new_cargos() -> list[dict]:
    """Read delivery_points.json's `new_cargos` list. Each entry is shipped
    verbatim to mutate-cargos as a clone spec — every key besides the few
    reserved ones (copy_from, new_id, display_source, safety_dps, _) is
    treated as a UE cargo-row field name to set on the cloned row. Field
    names match the vanilla cargo struct exactly (PaymentPer1Km,
    BasePayment, SpawnProbability, PaymentSqrtRatio, bUseDamage, etc.) so
    a mod author can dump a vanilla cargo and copy values 1:1."""
    dp_path = Path("delivery_points.json")
    if not dp_path.exists():
        return []
    try:
        cfg = json.loads(dp_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  delivery_points.json parse error: {e}", file=sys.stderr)
        return []
    out = cfg.get("new_cargos") or []
    return [c for c in out if isinstance(c, dict) and c.get("new_id")]


def materialize_new_cargos(new_cargos: list[dict]) -> bool:
    """Build the mod's Cargos_01.uasset from the new_cargos list. Each entry
    is a full row spec — copy_from + new_id + arbitrary field overrides.
    No magic keys, no implicit auto-cloning from recipe shapes — what's in
    the JSON is what ships, so a missing field can't silently default to a
    crash-inducing value."""
    # Wipe stale mod-shipped cargo assets from prior runs. Only Cargos_01
    # is safe to ship; modifying Cargos.uasset or the StringTables crashes
    # MT on world load (re-serialized bytes fail an asset-registry check).
    stale = [
        MOD_CARGOS.with_suffix(".uasset"),
        MOD_CARGOS.with_suffix(".uexp"),
        MOD_CONTENT_ROOT / "DataAsset" / "StringTables" / "Cargo.uasset",
        MOD_CONTENT_ROOT / "DataAsset" / "StringTables" / "Cargo.uexp",
    ]
    if not new_cargos:
        stale += [MOD_CARGOS_01.with_suffix(".uasset"),
                  MOD_CARGOS_01.with_suffix(".uexp")]
        for p in stale:
            if p.exists():
                p.unlink()
                print(f"  cleaned stale {p.name}")
        return True
    for p in stale:
        if p.exists(): p.unlink()

    # Strip pipeline-only keys (safety_dps is consumed by inject step, _ is
    # a doc comment). Everything else passes through verbatim to mutate-
    # cargos's generic field setter.
    spec = [
        {k: v for k, v in c.items() if k != "safety_dps"}
        for c in new_cargos
    ]
    import tempfile
    MOD_CARGOS_01.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump(spec, tf); spec_path = tf.name
    try:
        r = subprocess.run([
            str(INJECTOR), "mutate-cargos",
            "--mappings",   MAPPINGS,
            "--src-uasset", str(VANILLA_CARGOS_01),
            "--dst-uasset", str(MOD_CARGOS_01),
            "--spec",       spec_path,
        ], capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout); print(r.stderr, file=sys.stderr); return False
        for line in r.stdout.splitlines():
            if line.strip(): print(f"  {line}")
    finally:
        try: os.unlink(spec_path)
        except OSError: pass
    return True


def inject_new_cargos_into_safety_dps(new_cargos: list[dict]) -> bool:
    """For each entry in new_cargos that lists `safety_dps`, add the new
    cargo (by new_id) to the inputs of the named vanilla DP classes. This
    is the crash safety net — shipping a new cargo with zero vanilla
    consumers crashes MT on world load. The list is per-cargo and
    explicit; no global default. If safety_dps is omitted or empty for an
    entry, that cargo gets no vanilla coverage and you accept the crash
    risk."""
    # Group required vanilla classes by class name -> list of new cargo
    # ids that need to land in that class's inputs.
    by_class: dict[str, list[str]] = {}
    for c in new_cargos:
        for cls in c.get("safety_dps") or []:
            by_class.setdefault(cls, []).append(c["new_id"])
    if not by_class:
        return True
    import copy, tempfile
    examples_dir = Path("CargoImport/delivery_points")
    if not examples_dir.exists():
        print(f"  [boost] {examples_dir} missing — run import_cargo_data.py first", file=sys.stderr)
        return False
    dp_folder_rel = Path("Objects/Mission/Delivery/DeliveryPoint")
    src_root = GAME_CONTENT
    dst_root = MOD_CONTENT_ROOT
    affected = 0
    for ex_path in sorted(examples_dir.glob("*.example.json")):
        try:
            ex = json.loads(ex_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        cls = ex.get("_source_class")
        if cls not in by_class:
            continue
        recipes = ex.get("recipes") or []
        if not recipes:
            continue
        # Add new cargos to the FIRST inputs map we find (every vanilla
        # DP we ship safety-net coverage to has at least one input recipe).
        full_recipes = copy.deepcopy(recipes)
        target_recipe = next((r for r in full_recipes if isinstance(r, dict)
                              and isinstance(r.get("inputs"), dict)), None)
        if target_recipe is None:
            print(f"  [boost] {cls}: no inputs-recipe to attach new cargos — skipped", file=sys.stderr)
            continue
        for new_id in by_class[cls]:
            target_recipe["inputs"][new_id] = 1
        short = cls[:-2] if cls.endswith("_C") else cls
        src_uasset = src_root / dp_folder_rel / f"{short}.uasset"
        dst_uasset = dst_root / dp_folder_rel / f"{short}.uasset"
        if not src_uasset.exists():
            print(f"  [boost] vanilla {src_uasset.name} missing — skipped", file=sys.stderr)
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
            json.dump(full_recipes, tf); spec_path = tf.name
        try:
            r = subprocess.run([
                str(INJECTOR), "mutate-bp-cdo",
                "--mappings",   MAPPINGS,
                "--src-uasset", str(src_uasset),
                "--dst-uasset", str(dst_uasset),
                "--src-class",  cls,
                "--dst-class",  cls,
                "--recipes",    spec_path,
            ], capture_output=True, text=True)
        finally:
            try: os.unlink(spec_path)
            except OSError: pass
        if r.returncode != 0:
            print(r.stdout); print(r.stderr, file=sys.stderr); return False
        for line in r.stdout.splitlines():
            if line.strip(): print(f"    {line}")
        affected += 1
    print(f"  [boost] safety-net injection touched {affected} vanilla DP(s)")
    return True


def prepare_mod_bp_class(tpl: dict) -> bool:
    """For registry entries that ship a custom BP class:
       1. Byte-clone the source .uasset to the target path under the mod, with
          the source class name byte-replaced by the target class name (both
          must be the SAME LENGTH so file offsets stay valid).
       2. If `production_recipes` is set, invoke MTBPInjector mutate-bp-cdo
          to swap ProductionConfigs in the new BP's CDO.
       Idempotent: regenerates from source each call so registry edits take
       effect immediately."""
    tgt_path  = tpl.get("target_bp_path")
    tgt_class = tpl.get("target_bp_class")
    if not tgt_path or not tgt_class:
        return True

    src_class = tpl["bp_class"]
    src_short = src_class[:-2] if src_class.endswith("_C") else src_class
    tgt_short = tgt_class[:-2] if tgt_class.endswith("_C") else tgt_class
    if len(src_short) != len(tgt_short):
        print(f"  ERROR: byte-rename needs equal length, got "
              f"'{src_short}' ({len(src_short)}) vs '{tgt_short}' ({len(tgt_short)})",
              file=sys.stderr)
        return False

    rel = tgt_path[len("/Game/"):] if tgt_path.startswith("/Game/") else tgt_path
    src_uasset = (Path(str(tpl["preload_bp"][0]) if isinstance(tpl["preload_bp"], (list, tuple))
                       else str(tpl["preload_bp"]))).with_name(src_short + ".uasset")
    dst_uasset = MOD_CONTENT_ROOT / Path(rel).parent / (tgt_short + ".uasset")
    dst_uasset.parent.mkdir(parents=True, exist_ok=True)

    recipes = tpl.get("production_recipes")
    if recipes:
        # Mutate CDO + byte-rename in one step. Source schema is in mappings,
        # so the CDO parses correctly there; rename happens after save.
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
            json.dump(recipes, tf)
            recipes_path = tf.name
        try:
            r = subprocess.run([
                str(INJECTOR), "mutate-bp-cdo",
                "--mappings",   MAPPINGS,
                "--src-uasset", str(src_uasset),
                "--dst-uasset", str(dst_uasset),
                "--src-class",  src_class,
                "--dst-class",  tgt_class,
                "--recipes",    recipes_path,
            ], capture_output=True, text=True)
        finally:
            try: os.unlink(recipes_path)
            except OSError: pass
        if r.returncode != 0:
            print(r.stdout); print(r.stderr, file=sys.stderr); return False
        for line in r.stdout.splitlines():
            if line.strip(): print(f"    {line}")
    else:
        # No recipe override — just byte-clone the BP under the new name.
        needle  = src_short.encode("ascii")
        replace = tgt_short.encode("ascii")
        for ext in (".uasset", ".uexp"):
            s = src_uasset.with_suffix(ext)
            if not s.exists():
                print(f"  ERROR: source BP missing {s}", file=sys.stderr); return False
            (dst_uasset.parent / (tgt_short + ext)).write_bytes(s.read_bytes().replace(needle, replace))
    print(f"  prepared mod BP class {tgt_class} at {tgt_path}")
    return True
# Fallback template cell used when creating a new WP cell for far coords.
# Chosen for a native-only actor list (no BP wrappers to accidentally carry
# over) and enough actor slots to host dozens of injected BP clones in a
# single cell: 35 slots. Clones replace existing Actors-list entries so the
# PersistentLevel body layout stays the size UE's ULevel::Serialize expects.
# Vanilla WP cell used as the byte-clone template for newly-registered
# mod cells. The chosen cell needs:
#   - a LevelExport with at least 1 Actors slot we can replace
#   - small enough that copying it per delivery point is cheap
#   - no DataLayers in its main-map registration (those gate streaming)
# `0V18V8JBXKXUL8YILWZKCSMB4` was hand-picked and meets all three.
# `auto_pick_template_cell()` falls back to scanning the `_Generated_`
# folder if the preferred cell is missing (e.g. game update renamed it).
_PREFERRED_TEMPLATE_CELL = "0V18V8JBXKXUL8YILWZKCSMB4"
_TEMPLATE_CACHE = Path(__file__).with_suffix(".template_cache")

def auto_pick_template_cell() -> str:
    """Return a usable vanilla WP cell name. Order:
       1. Cached result from a prior auto-pick.
       2. The preferred (hand-picked) cell if its .umap still exists.
       3. First scanned cell in size band [4000, 7000] bytes whose byte
          signature begins with a UE5 .umap magic (0xC1832A9E little-endian).
       4. Hardcoded preferred name (will fail later if missing — let it).
    """
    if _TEMPLATE_CACHE.exists():
        cached = _TEMPLATE_CACHE.read_text(encoding="utf-8").strip()
        if cached and (CELLS_DIR / f"{cached}.umap").exists():
            return cached
    pref = CELLS_DIR / f"{_PREFERRED_TEMPLATE_CELL}.umap"
    if pref.exists():
        _TEMPLATE_CACHE.write_text(_PREFERRED_TEMPLATE_CELL, encoding="utf-8")
        return _PREFERRED_TEMPLATE_CELL
    # Scan: small UE5 .umap files in the _Generated_ folder.
    print(f"  [template-cell] preferred '{_PREFERRED_TEMPLATE_CELL}' missing; scanning...", file=sys.stderr)
    UE5_UMAP_MAGIC = b"\x9e\x2a\x83\xc1"
    for p in sorted(CELLS_DIR.glob("*.umap")):
        sz = p.stat().st_size
        if not (4000 <= sz <= 7000): continue
        with open(p, "rb") as f:
            head = f.read(4)
        if head != UE5_UMAP_MAGIC: continue
        name = p.stem
        print(f"  [template-cell] picked '{name}' ({sz}b)", file=sys.stderr)
        _TEMPLATE_CACHE.write_text(name, encoding="utf-8")
        return name
    print(f"  [template-cell] WARNING: no candidate found, falling back to '{_PREFERRED_TEMPLATE_CELL}'", file=sys.stderr)
    return _PREFERRED_TEMPLATE_CELL


TEMPLATE_CELL = auto_pick_template_cell()


def _pick_owner(hits: list[dict]) -> str | None:
    owners = [(int(h["level"]), h["grid"], h["owner"]) for h in hits]
    owners = [(lvl, grid, name) for (lvl, grid, name) in owners
              if (CELLS_DIR / f"{name}.umap").exists() and lvl <= 2]
    if not owners:
        return None
    owners.sort(key=lambda t: (t[0], 0 if t[1] == "MainGrid" else 1))
    return owners[0][2]


def resolve_cells_batch(points: list[tuple[float, float]]) -> list[str | None]:
    """Resolve all (x, y) points against vanilla WP cells in ONE injector
    invocation. Previous per-point calls reloaded the 30 MB mappings + the
    main Jeju_World.umap each time and dominated pipeline runtime."""
    if not points:
        return []
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump([{"x": x, "y": y} for (x, y) in points], tf)
        in_path = tf.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        out_path = tf.name
    try:
        r = subprocess.run(
            [str(INJECTOR), "find-cells-batch",
             "--main", str(JEJU_MAIN),
             "--mappings", MAPPINGS,
             "--spec", in_path,
             "--output", out_path],
            capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout); print(r.stderr, file=sys.stderr)
            return [None] * len(points)
        data = json.loads(Path(out_path).read_text(encoding="utf-8"))
    finally:
        for p in (in_path, out_path):
            try: os.unlink(p)
            except OSError: pass
    return [_pick_owner(entry.get("containing", [])) for entry in data]


def resolve_cell(x: float, y: float) -> str | None:
    """Single-point wrapper (kept for backwards compat); routes through batch."""
    return resolve_cells_batch([(x, y)])[0]


def make_cell_name(seed: str) -> str:
    """Deterministic 25-char [A-Z0-9] name derived from a seed string."""
    h = hashlib.sha1(seed.encode()).hexdigest().upper()
    # Keep 25 alphanumeric chars (vanilla cell names look like base32)
    safe = "".join(c for c in h if c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")[:25]
    return "MOD" + safe[:22]


def entry_seed(e: dict) -> str:
    """Content-hash seed for a BP entry — guarantees a unique cell per actor
    identity (same pose + same BP → same cell name across runs)."""
    return "|".join(str(e.get(k, "")) for k in
                    ("X", "Y", "Z", "Pitch", "Yaw", "Roll",
                     "blueprint_path", "blueprint_class"))


def cell_spec(new_cell: str, x: float, y: float, mod_gen_dir: Path,
              hier_level: int = -1, grid_levels_index: int = 0) -> dict:
    """Spec for one cell registration. Consumed by register-cells-batch so N
    cells land in the main map via a single UAssetAPI load/save."""
    extent = 6400 * (2 ** (hier_level + 1))
    return {
        "template-cell":     TEMPLATE_CELL,
        "new-cell-name":     new_cell,
        "x":                 f"{x}",
        "y":                 f"{y}",
        "extent":            str(extent),
        "grid":              "MainGrid",
        "hier-level":        str(hier_level),
        "grid-levels-index": str(grid_levels_index),
        "cells-dir":         str(CELLS_DIR),
        "mod-cells-dir":     str(mod_gen_dir),
    }


def register_cells_batch(main_in: str, main_out: str, specs: list[dict]) -> bool:
    """Register all pending cells against the main map in one load/save."""
    if not specs:
        return True
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump(specs, tf)
        spec_path = tf.name
    try:
        r = subprocess.run([
            str(INJECTOR), "register-cells-batch",
            "--main",     main_in,
            "--output",   main_out,
            "--mappings", MAPPINGS,
            "--spec",     spec_path,
        ], capture_output=True, text=True)
    finally:
        try: os.unlink(spec_path)
        except OSError: pass
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr, file=sys.stderr)
        return False
    for line in r.stdout.splitlines():
        if line.strip(): print(f"    {line}")
    return True


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

    # Slim delivery_points section — placement data + delivery_key only.
    # The actual config (label, recipes, marker/icon, storage cap) lives in
    # delivery_points.json and was loaded into REGISTRY at import time.
    for dp in cfg.get("delivery_points", []) or []:
        if not isinstance(dp, dict): continue
        # Pure-comment entries: every key starts with '_' (e.g. just a
        # standalone {"_comment": "Noksan dock test rig"}). Silently
        # skipped so authors can annotate the list inline.
        if dp and all(k.startswith("_") for k in dp.keys()):
            continue
        dp_key = dp.get("delivery_key")
        if not dp_key:
            print(f"  delivery_points entry missing delivery_key — skipped"); continue
        reg_key = f"DeliveryPoint_{dp_key}"
        if reg_key not in REGISTRY:
            print(f"  delivery_points: '{dp_key}' not in delivery_points.json — skipped")
            continue
        entries.append({
            "X": dp.get("X"), "Y": dp.get("Y"), "Z": dp.get("Z"),
            "Pitch": dp.get("Pitch", 0.0), "Roll": dp.get("Roll", 0.0), "Yaw": dp.get("Yaw", 0.0),
            "asset_key": reg_key,
            "blueprint_class": REGISTRY[reg_key]["bp_class"],
        })

    if not entries:
        print("No blueprint_actors / delivery_points entries.")
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
    # One actor per cell. Template has 4 slots but spawning multiple BP actors
    # in the same cell has proven brittle (neighbor slots sometimes fail to
    # spawn). 1-per-cell gives reliable placement; we just register more L-1
    # tiles. User OK'd this explicitly.
    MAX_SLOTS_PER_CREATED_CELL = 1

    # DEBUG: set MAX_BP=1 to clone only the first entry.
    _max = int(os.environ.get("MAX_BP", "999999"))
    if _max < len(entries):
        print(f"  [debug] MAX_BP={_max} — limiting from {len(entries)} entries")
        entries = entries[:_max]
    # DEBUG: set BP_SKIP=ParkingSmall,Garage to skip specific BP classes
    _skip = set(k.strip() for k in os.environ.get("BP_SKIP", "").split(",") if k.strip())
    if _skip:
        before = len(entries)
        # Match on either blueprint_class or the short name derived from asset_key
        def _match(e):
            cls = e.get("blueprint_class", "")
            return cls in _skip or any(k in cls for k in _skip)
        entries = [e for e in entries if not _match(e)]
        print(f"  [debug] BP_SKIP={sorted(_skip)} — {before} -> {len(entries)} entries")

    # delivery_points.json `new_cargos` list: each entry clones a vanilla
    # cargo row into a new id and applies arbitrary field overrides
    # (PaymentPer1Km, BasePayment, SpawnProbability, ...). Recipes
    # reference the new ids by name. Per-cargo `safety_dps` lists vanilla
    # DP classes whose inputs the new cargo gets injected into — required
    # because shipping a new cargo with zero vanilla consumers crashes
    # MT on world load.
    new_cargos = load_new_cargos()
    if not materialize_new_cargos(new_cargos): return 1
    if not inject_new_cargos_into_safety_dps(new_cargos): return 1

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

    # Absolute tile (gx, gy) -> cell_name already registered for it. Shared
    # across homes so two entries whose home tiles spill into the same
    # physical neighbor tile reuse the same cell instead of registering twice.
    registered_tiles: dict[tuple[int, int], str] = {}
    # Per-home spiral progress so we deterministically fan out around each home.
    home_rings: dict[tuple[int, int], int] = {}
    # Deferred cell registrations. Flushed in ONE register-cells-batch call
    # after the first pass; registering per-actor was re-serializing the huge
    # Jeju_World.umap N times and dominated pipeline runtime.
    pending_cells: list[dict] = []

    # Materialize any mod-shipped BP classes referenced by entries: byte-clone
    # the source .uasset under the mod folder and (optionally) mutate its CDO.
    # Done once up-front so all clone-batch work that follows uses the final
    # state of the mod assets.
    prepared_keys = set()
    for e in entries:
        k = e.get("asset_key")
        tpl = REGISTRY.get(k) if k else None
        if not tpl or not tpl.get("target_bp_path") or k in prepared_keys: continue
        if not prepare_mod_bp_class(tpl): return 1
        prepared_keys.add(k)

    # Pre-resolve every entry's vanilla-cell membership in a single injector
    # invocation. Previously this was a per-entry subprocess call that each
    # reloaded mappings + Jeju_World.umap.
    resolved_cells = resolve_cells_batch([(e["X"], e["Y"]) for e in entries])

    def pick_cell_for_entry(e, i):
        # Returns (cell_name, is_created)
        bp_class = e.get("blueprint_class", "")
        tpl = template_for_class(bp_class)
        force_new = bool(tpl and tpl.get("force_new_cell"))
        cell = None if force_new else resolved_cells[i]
        if cell is not None:
            return cell, False
        home = (int(e["X"] // 12800), int(e["Y"] // 12800))
        # Try existing tiles already assigned around this home (any ring step
        # previously taken for this home, including step 0 = home tile itself).
        steps_taken = home_rings.get(home, 0)
        for i in range(steps_taken + 1):
            dx, dy = tile_offset(i) if i <= steps_taken else (0, 0)
            tile = (home[0] + dx, home[1] + dy)
            cname = registered_tiles.get(tile)
            if cname and slot_counter.get(cname, 0) < MAX_SLOTS_PER_CREATED_CELL:
                return cname, True
        # All known tiles for this home full — take the next spiral step.
        while True:
            dx, dy = tile_offset(steps_taken)
            tile = (home[0] + dx, home[1] + dy)
            steps_taken += 1
            home_rings[home] = steps_taken
            existing = registered_tiles.get(tile)
            if existing:
                # Tile already registered (by another home's spiral). Reuse if
                # it has room; otherwise keep walking.
                if slot_counter.get(existing, 0) < MAX_SLOTS_PER_CREATED_CELL:
                    return existing, True
                continue
            cx = (tile[0] + 0.5) * 12800.0
            cy = (tile[1] + 0.5) * 12800.0
            new_cell = make_cell_name(entry_seed(e))
            print(f"  [{entry_idx_ref[0]}] home {home} step {steps_taken}: queued L-1 cell '{new_cell}' at tile {tile}")
            pending_cells.append(cell_spec(new_cell, cx, cy, gen_dir))
            registered_tiles[tile] = new_cell
            seeded.add(new_cell)
            return new_cell, True

    # Sentinel for entries injected directly into the persistent level of the
    # main map instead of into a WP cell. clone-batch can target Jeju_World.umap
    # the same way it targets a cell — the underlying actor-clone code only
    # cares about LevelExport semantics, not the package name.
    MAIN_LEVEL_KEY = "__MAIN_LEVEL__"

    entry_idx_ref = [0]
    for i, e in enumerate(entries):
        entry_idx_ref[0] = i
        bp_class = e.get("blueprint_class")
        # Prefer asset_key lookup — multiple registry entries may share the
        # same blueprint_class (FarmCorn + FarmTransformer both Farm_Corn_C),
        # so class-based lookup picks the wrong one.
        key = e.get("asset_key")
        tpl_entry = REGISTRY.get(key) if key else None
        if not tpl_entry:
            tpl_entry = template_for_class(bp_class)
        if not tpl_entry:
            print(f"  [{i}] skipped — no registry entry for {key or bp_class}")
            continue

        # Heavy BPs (delivery points etc.) crash the WP cell-streaming path
        # because cells validate stricter than persistent-level load. Route
        # them straight into Jeju_World.umap — same context as vanilla
        # instances of the class.
        if tpl_entry.get("inject_into_main"):
            print(f"  [{i}] {bp_class} @ ({e['X']}, {e['Y']}, {e['Z']}) -> MAIN persistent level")
            grouped.setdefault(MAIN_LEVEL_KEY, []).append((e, tpl_entry, False, None))
            # WP-coverage shadow: a persistent-level actor only renders when
            # WP streams the area containing its coords. Vanilla cells cover
            # most of Jeju but custom-island / outside-bounds coords aren't
            # streamed unless we register a mod cell there. Reuse the same
            # spiral the parking pipeline uses (auto-dedup by tile).
            if resolved_cells[i] is None:
                home = (int(e["X"] // 12800), int(e["Y"] // 12800))
                if home not in registered_tiles:
                    cx = (home[0] + 0.5) * 12800.0
                    cy = (home[1] + 0.5) * 12800.0
                    new_cell = make_cell_name(f"shadow_{home}")
                    print(f"        [shadow-cell] queuing WP cell '{new_cell}' at tile {home} so the persistent-level actor at ({e['X']}, {e['Y']}) gets streamed")
                    pending_cells.append(cell_spec(new_cell, cx, cy, gen_dir))
                    registered_tiles[home] = new_cell
                    seeded.add(new_cell)
            continue

        cell, needs_create = pick_cell_for_entry(e, i)
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

    # Second pass: build a super-batch job list covering every target cell.
    # Cell registrations AND clone jobs run in ONE injector invocation via
    # register-and-clone so the 30 MB MotorTown.usmap is parsed exactly once
    # for the entire BP phase.
    import json as _json, tempfile
    jobs = []
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
            # Optional: rewrite the cloned actor's class to point at a NEW
            # BP class shipped by the mod (makes the instance a distinct type
            # rather than another copy of the source's class).
            if tpl.get("target_bp_path") and tpl.get("target_bp_class"):
                spec["target_bp_path"]  = tpl["target_bp_path"]
                spec["target_bp_class"] = tpl["target_bp_class"]
            # Tell CloneBatch to synthesize the persistent-level actor
            # metadata blob (label + FGuid) when this entry targets the main
            # map; without it MT's mission/save subsystems can't key the actor.
            if tpl.get("inject_into_main"):
                spec["main_inject"] = True
            # Optional per-instance ProductionConfigs override (delivery-point
            # recipe table). MT may or may not honor instance overrides for
            # this property — if not, we'd need a full BP class clone.
            if tpl.get("production_recipes"):
                spec["production_recipes"] = tpl["production_recipes"]
            if tpl.get("actor_label"):
                spec["actor_label"] = tpl["actor_label"]
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
        # MAIN_LEVEL_KEY routes the clone batch at Jeju_World.umap itself so
        # the cloned actor lands in the persistent level alongside the
        # vanilla instances of its class.
        if cell == MAIN_LEVEL_KEY:
            jobs.append({
                "dst-cell": main_out,  # main-in will already be patched by the
                "output":   main_out,  # register phase by the time clone runs
                "spec":     specs,
            })
        else:
            jobs.append({
                "dst-cell": str(gen_dir / f"{cell}.umap"),
                "output":   str(gen_dir / f"{cell}.umap"),
                "spec":     specs,
            })

    if pending_cells or jobs:
        combined = {
            "main-in":  main_in,
            "main-out": main_out,
            "register": pending_cells,
            "clone":    jobs,
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
            _json.dump(combined, tf)
            spec_path = tf.name
        try:
            r = subprocess.run([
                str(INJECTOR), "register-and-clone",
                "--mappings", MAPPINGS,
                "--spec",     spec_path,
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
