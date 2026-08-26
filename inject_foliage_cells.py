#!/usr/bin/env python3
"""
inject_foliage_cells.py — ship foliage as instanced cells, not actors.

One StaticMeshActor per foliage instance is unshippable: each costs >=2
UObjects against UE's hard 2,162,688 cap, so ~3.4M instances crash the
game on load (see AGENTS.md "Foliage Instance Transform Model"). As
InstancedFoliageActor cells the same instances cost ~12 UObjects per
256 m tile, because instances are transforms in a buffer.

This groups the editor's foliage export by actor-partition tile, and for
each tile emits a WP cell holding an IFA whose FISMC carries the tile's
instances. Cells are registered in MainGrid exactly like the BP-actor
cells already are.

    python inject_foliage_cells.py --main-in <umap> --main-out <umap> \
        --gen-dir <mod _Generated_> [--limit N] [--mesh-filter SM_x]

--limit caps how many tiles are emitted (--limit 1 is the single-cell
render proof). Run it BETWEEN build.bat's cell stage and its mesh
injection, so the registrations land in the small map.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import subprocess
import sys
from pathlib import Path

from mt_paths import (CELLS_DIR, MAPPINGS, WORK_DIR, REPO_ROOT_P, MOD_CONTENT_ROOT,
                      IMPORT_OFFSET_X, IMPORT_OFFSET_Y, IMPORT_OFFSET_Z,
                      remap_asset_path)
from clone_bp_actors import cell_spec, make_cell_name, register_cells_batch

INJECTOR = REPO_ROOT_P / "MTBPInjector" / "bin" / "Release" / "net8.0" / "MTBPInjector.exe"
SHARDS = REPO_ROOT_P / "static_meshes_parts"

# UE's actor-partition grid for foliage. Vanilla Jeju uses 25600 for every
# single IFA — see AGENTS.md. Don't change this without re-deriving it.
GRID = 25600.0

# A minimal vanilla foliage cell: 1 IFA + 1 root + exactly 1 FISMC and no
# foreign actors, so cloning it drags nothing else into the map. Its name is
# 25 chars, which RegisterCell's byte-rename requires (equal length).
FOLIAGE_TEMPLATE = "ABCFGRNDLFUV5MG84AKVMPYBD"

# Per-mesh settings captured by ue.py. Collision comes from each MESH's own
# BodySetup.DefaultInstance — the preset set in the Static Mesh editor — so
# a mesh cooked with no collision is pass-through and one cooked solid
# blocks, per mesh, with no override list to maintain. Cull distances come
# from the foliage component, which is where those actually live.
SETTINGS_FILE = SHARDS / "foliage_settings.json"

# Only used when a mesh has NO collision setting at all from ue.py, which
# means a stale export. Warned about loudly rather than applied quietly.
SOLID_PROFILE = "BlockAll"

# Outward padding on each foliage cell's reported content bounds, in uu.
# One grid tile (25600) makes a cell stream in a full tile early, so its trees
# are resident before they enter view. 0 disables. Set MTMI_FOLIAGE_CELL_PAD.
CELL_PAD = float(os.environ.get("MTMI_FOLIAGE_CELL_PAD", "25600"))

# asset_path -> collision profile, read from the cooked mesh at build time.
# Authoritative over foliage_settings.json: that file is an editor snapshot
# and goes stale the moment a mesh is re-cooked without re-exporting.
mesh_collision: dict[str, str] = {}


def read_shipped_collision(mesh_paths: dict, im) -> dict:
    """Ask the injector what each shipped mesh says about its own collision.

    One subprocess for the whole set. A mesh we cannot read is simply absent
    from the result, and comp_settings falls back to the editor snapshot.
    """
    disk_to_asset = {}
    for apath in set(mesh_paths.values()):
        rel = im.game_path_to_disk(apath) if apath else None
        if not rel:
            continue
        p = MOD_CONTENT_ROOT / (rel + ".uasset")
        if p.is_file():
            disk_to_asset[str(p)] = apath
    if not disk_to_asset:
        return {}
    listing = WORK_DIR / "mesh_collision_list.txt"
    listing.parent.mkdir(parents=True, exist_ok=True)
    listing.write_text("\n".join(disk_to_asset), encoding="utf-8")
    r = subprocess.run([str(INJECTOR), "mesh-collision", "--list", str(listing),
                        "--mappings", str(MAPPINGS)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"    WARNING: mesh-collision failed ({r.returncode}) — falling back "
              f"to the editor snapshot for collision", file=sys.stderr)
        if r.stderr:
            print(r.stderr.strip()[:500], file=sys.stderr)
        return {}
    out = {}
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not parts[1]:
            continue
        apath = disk_to_asset.get(parts[0])
        if apath:
            out[apath] = parts[1]
    solid = sum(1 for v in out.values() if v != "NoCollision")
    print(f"  collision read from {len(out)} shipped mesh(es): "
          f"{solid} solid, {len(out) - solid} pass-through")
    return out

# Fallback instance cull distances, applied ONLY when the editor exported 0.
# Default 0 = pass the editor's value through untouched, so 0 keeps its UE
# meaning of "never cull" and foliage draws to the horizon. That is the
# intended look here, and Nanite makes the distant geometry affordable.
# Set these to e.g. 20000/50000 (the vanilla foliage values) to reinstate a
# fade instead. A non-zero editor value always wins over both.
CULL_START_DEFAULT = int(os.environ.get("MTMI_FOLIAGE_CULL_START", "0"))
CULL_END_DEFAULT   = int(os.environ.get("MTMI_FOLIAGE_CULL_END", "0"))

# Per-mesh cull overrides: "substr:start:end,substr:start:end".
# Grass does not need the same draw distance as a tree, and grass is where
# the geometry is: the merged Clump meshes hold 16/64/256/1024 blades EACH,
# so ~870k clump instances are ~217M drawn meshes. Halving grass draw
# distance quarters the grass area on screen, which is the cheapest large
# win available without repainting.
CULL_OVERRIDES = []
for _rule in os.environ.get("MTMI_FOLIAGE_CULL_OVERRIDES", "").split(","):
    _p = _rule.split(":")
    if len(_p) == 3 and _p[0].strip():
        try:
            CULL_OVERRIDES.append((_p[0].strip().lower(), int(_p[1]), int(_p[2])))
        except ValueError:
            pass

# Meshes promoted to persistent-level StaticMeshActors by import_meshes
# (MTMI_FOLIAGE_AS_ACTORS). Same env var on both sides so the two paths
# can't disagree about who owns a mesh.
AS_ACTORS = tuple(
    x.strip().lower()
    for x in os.environ.get("MTMI_FOLIAGE_AS_ACTORS", "").split(",")
    if x.strip()
)


def resolve_cull(mesh_path: str, src: dict) -> tuple[int, int]:
    """The cull pair a mesh will actually ship with.

    One function because there used to be two routes to this answer and they
    disagreed. The build applied the per-mesh overrides; the margin check below
    read only foliage_settings.json and the flat default, so it judged a build
    against numbers that build was not using -- and cried "2.4s is not long
    enough" about a pak whose cells carried 55,000, worth 7.8s. A check that
    reports on values other than the shipped ones is worse than no check.
    """
    cs = src.get("instance_start_cull_distance") or 0
    ce = src.get("instance_end_cull_distance") or 0
    cs = cs if cs > 0 else CULL_START_DEFAULT
    ce = ce if ce > 0 else CULL_END_DEFAULT
    low = (mesh_path or "").lower()
    for sub, ostart, oend in CULL_OVERRIDES:
        if sub in low:
            return ostart, oend
    return cs, ce


def load_settings() -> dict:
    """asset_key -> {collision_profile_name, instance_*_cull_distance, ...}."""
    if not SETTINGS_FILE.is_file():
        print(f"  WARNING: {SETTINGS_FILE.name} missing — re-run ue.py to capture "
              f"your foliage settings — collision and materials cannot be "
              f"resolved without it.", file=sys.stderr)
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  WARNING: could not read {SETTINGS_FILE.name}: {e}", file=sys.stderr)
        return {}


def _cull_test(mesh: str, z_local: float, cull, rng) -> bool:
    """True if this instance should be dropped from the build.

    Z is the EDITOR-space value straight out of the export, deliberately:
    that's the number you read off the viewport, so a sea level of -145 in
    the editor is -145 here. The world offset is applied afterwards.

    Feathering fades removal out over a band above zmax so the treeline
    isn't a razor-straight cut at exactly the waterline.
    """
    meshes, zmax, feather = cull
    if not meshes or zmax is None:
        return False
    low = mesh.lower()
    if not any(m in low for m in meshes):
        return False
    if z_local <= zmax:
        return True
    if feather <= 0:
        return False
    over = z_local - zmax
    return over < feather and rng.random() < (1.0 - over / feather)


def load_tiles(mesh_filter: str | None, cull=((), None, 0.0)) -> tuple[dict, dict, dict]:
    """Group every foliage instance by (tile, mesh). Streamed line by line —
    the export runs to millions of entries and must never be json.load'ed
    whole. Instances are held as bare tuples, not dicts: at 3.4M entries the
    dict form costs several GB for no benefit."""
    groups: dict[tuple, list] = collections.defaultdict(list)
    paths: dict[str, str] = {}
    # Fixed seed: the feather band must be reproducible, or every rebuild
    # would eat a slightly different set of trees.
    rng = random.Random(1337)
    culled = collections.Counter()
    # Folders as PAINTED, before any remap — the remap guard needs to know
    # what the level actually contains, not what we rewrote it to.
    src_folders: collections.Counter = collections.Counter()
    for shard in sorted(SHARDS.glob("fol_*.jsonl")):
        with open(shard, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                e = json.loads(line)
                # Group by the full asset PATH. Two mesh folders (Nature =
                # winter, NatureGreen = green) hold identically-named meshes,
                # so keying by asset_key silently merged them and shipped one
                # folder for both -- 1.3M winter instances rendered green.
                key = remap_asset_path(e.get("asset_path", "")) or e.get("asset_key")
                if mesh_filter and e.get("asset_key") != mesh_filter:
                    continue
                # Handled by import_meshes as persistent-level actors so they
                # can never pop in — must not also become cell foliage, or
                # they'd ship twice.
                if AS_ACTORS and any(a in str(e.get("asset_key","")).lower() for a in AS_ACTORS):
                    continue
                if _cull_test(str(e.get("asset_key","")), e["Z"], cull, rng):
                    culled[str(e.get("asset_key",""))] += 1
                    continue
                x = e["X"] + IMPORT_OFFSET_X
                y = e["Y"] + IMPORT_OFFSET_Y
                z = e["Z"] + IMPORT_OFFSET_Z
                tile = (int(x // GRID), int(y // GRID), int(z // GRID))
                groups[(tile, key)].append((
                    x, y, z,
                    e.get("Pitch", 0.0), e.get("Yaw", 0.0), e.get("Roll", 0.0),
                    e.get("ScaleX", 1.0), e.get("ScaleY", 1.0), e.get("ScaleZ", 1.0)))
                ap_raw = e.get("asset_path", "")
                if "/" in ap_raw:
                    src_folders[ap_raw.rsplit("/", 2)[-2]] += 1
                paths.setdefault(key, key)
    if culled:
        print(f"  culled {sum(culled.values()):,} instance(s) below Z={cull[1]} "
              f"(feather {cull[2]}): "
              + ", ".join(f"{k} {v:,}" for k, v in culled.most_common()))
    return groups, paths, src_folders


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--main-in", required=True)
    ap.add_argument("--main-out", required=True)
    ap.add_argument("--gen-dir", required=True)
    ap.add_argument("--limit", type=int, default=0, help="max tiles to emit (0 = all)")
    ap.add_argument("--mesh-filter", help="only this asset_key (proof runs)")
    ap.add_argument("--cull-meshes", default="",
                    help="comma-separated substrings; instances of matching "
                         "meshes below --cull-zmax are dropped from the build. "
                         "Non-destructive: your level is untouched.")
    ap.add_argument("--cull-zmax", type=float, default=None,
                    help="EDITOR-space Z at/below which matching instances are "
                         "dropped (e.g. -145 for sea level).")
    ap.add_argument("--cull-feather", type=float, default=0.0,
                    help="soften the cut: removal probability fades from 1 at "
                         "--cull-zmax to 0 this many units above it.")
    args = ap.parse_args()

    def comp_settings(mesh: str) -> dict:
        """Everything we stamp onto this mesh's component.

        Collision comes from the MESH and nothing else. ue.py reads the
        mesh's own BodySetup.DefaultInstance -- the collision preset set in
        the Static Mesh editor -- so a mesh cooked with no collision is
        pass-through and one cooked solid blocks. There is deliberately no
        override list: this is a framework, and a per-mesh setting the
        author already made is a better answer than a list of exceptions
        every user has to maintain.

        Values are always stated explicitly, never left to inherit: extra
        IFAs are cloned from the primary FISMC after it has been mutated,
        so an unset field would silently pick up the previous mesh's.
        """
        # `mesh` is the full asset path. ue.py keys settings by path too,
        # but an export made before that change keys by short name — accept
        # both so a stale settings file still resolves.
        src = settings.get(mesh)
        if src is None:
            short = mesh.rsplit("/", 1)[-1].split(".")[0]
            src = settings.get(short)
            if src is not None and not _warned_legacy:
                print(f"    note: foliage_settings.json is keyed by mesh NAME "
                      f"(pre-path export). Two folders sharing a name cannot be "
                      f"told apart — re-run ue.py for per-folder settings.",
                      file=sys.stderr)
                _warned_legacy.append(True)
        src = src or {}
        # The cooked mesh wins. The editor snapshot is only a fallback for
        # meshes the injector could not read.
        prof = mesh_collision.get(mesh) or src.get("collision_profile_name")
        if not prof:
            print(f"    WARNING: {mesh} has no collision setting from the cooked "
                  f"mesh or ue.py — defaulting to {SOLID_PROFILE}", file=sys.stderr)
            prof = SOLID_PROFILE
        out = {"collision": prof}
        cs, ce = resolve_cull(mesh, src)
        out["cull_start"] = str(cs)
        out["cull_end"] = str(ce)
        mats = src.get("override_materials")
        if mats:
            out["materials"] = json.dumps(mats)
        return out

    if not INJECTOR.is_file():
        print(f"MTBPInjector not built: {INJECTOR}", file=sys.stderr)
        return 1
    if not (CELLS_DIR / f"{FOLIAGE_TEMPLATE}.umap").is_file():
        print(f"foliage template cell missing: {FOLIAGE_TEMPLATE}", file=sys.stderr)
        return 1

    gen_dir = Path(args.gen_dir)
    gen_dir.mkdir(parents=True, exist_ok=True)

    cull = (tuple(m.strip().lower() for m in args.cull_meshes.split(",") if m.strip()),
            args.cull_zmax, args.cull_feather)
    groups, mesh_paths, src_folders = load_tiles(args.mesh_filter, cull)
    if not groups:
        print("  no foliage entries — nothing to do")
        return 0

    # A remap rewrites paths blindly. If its DESTINATION folder is already
    # painted in the level, the two sets collapse into one and the
    # distinction you authored by hand is silently destroyed — e.g.
    # NatureGreen/=Nature/ turned every green tree white. Refuse rather
    # than ship 2.3M wrong instances.
    for rule in os.environ.get("MTMI_MESH_REMAP", "").split(","):
        if "=" not in rule:
            continue
        src_f, dst_f = (x.strip().strip("/").split("/")[-1] for x in rule.split("=", 1))
        if src_f in src_folders and dst_f in src_folders:
            print(
                f"\n  ERROR: MTMI_MESH_REMAP says {src_f} -> {dst_f}, but BOTH are"
                f" painted in the level ({src_folders[src_f]:,} and"
                f" {src_folders[dst_f]:,} instances)."
                f"\n  Applying it would collapse them into one set and lose the"
                f" distinction you authored."
                f"\n  Clear MTMI_MESH_REMAP in .env, or remove one set from the"
                f" level.", file=sys.stderr)
            return 1

    # Ship the meshes our cells reference. import_meshes only copies assets
    # for entries it actually processes, and the foliage entries are dropped
    # there (--skip-foliage) precisely because we place them here instead —
    # so nothing else copies these. Without it a cell points at a mesh that
    # is not in the pak and its instances render nothing.
    import import_meshes as im
    script_dir = str(REPO_ROOT_P)

    # Re-exporting from the editor while a build runs silently splices two
    # different scenes into one pak: the mesh stage already read the old
    # shards, this stage would read the new ones. Stage 2 writes
    # map_work_changes.json when it finishes, so any shard newer than that
    # file arrived mid-build.
    stage2 = WORK_DIR / "map_work_changes.json"
    if stage2.is_file():
        cutoff = stage2.stat().st_mtime
        fresh = [p.name for p in SHARDS.glob("*.jsonl") if p.stat().st_mtime > cutoff]
        if fresh:
            print(f"  ERROR: the editor export changed mid-build — {len(fresh)} shard(s) "
                  f"written after the mesh stage finished ({', '.join(sorted(fresh)[:4])}"
                  f"{'...' if len(fresh) > 4 else ''}).", file=sys.stderr)
            print(f"         This pak would mix meshes from the old scene with foliage "
                  f"from the new one. Re-run build.bat with the editor export finished.",
                  file=sys.stderr)
            return 1

    settings = load_settings()
    _warned_legacy: list = []
    shipped = collections.Counter()
    for key, apath in sorted(mesh_paths.items()):
        rel = im.game_path_to_disk(apath) if apath else None
        if not rel:
            shipped["no path"] += 1
            print(f"    WARNING: no asset_path for {key}", file=sys.stderr)
            continue
        shipped[im.copy_asset_to_mod(rel, script_dir)] += 1
    print("  meshes: " + ", ".join(f"{v} {k}" for k, v in sorted(shipped.items())))

    # Collision is read from the mesh we are about to SHIP, not from the
    # editor snapshot in foliage_settings.json. Re-cook a tree with a new
    # collision box and the change reaches the game on the next build --
    # no scene re-export, and nothing quietly reverting your edit.
    mesh_collision.update(read_shipped_collision(mesh_paths, im))

    # State the resolved mesh set explicitly, every build. The seasonal remap
    # is an .env value, so without this the only way to find out which set
    # shipped is to load the game and look at a tree — and a stale or cleared
    # MTMI_MESH_REMAP silently produces a different map from the same export.
    folders = collections.Counter()
    for key in sorted(mesh_paths):
        ap = mesh_paths[key]
        folders[ap.rsplit("/", 1)[0] if "/" in ap else "?"] += 1
    # INVARIANT: instances must stop drawing BEFORE their cell unloads.
    # WP unloads a cell past MTMI_WP_LOADING_RANGE; if foliage is still
    # drawing at that distance it vanishes in one hard pop, and looking back
    # at a cell you just left shows bare ground. Cull end below the loading
    # range makes the fade happen while the cell is still resident.
    _lr = os.environ.get("MTMI_WP_LOADING_RANGE", "").strip()
    if _lr:
        try:
            lr = float(_lr)
            worst = max((resolve_cull(mesh_paths[k], settings.get(k) or {})[1]
                         for k in mesh_paths), default=0)
            if worst == 0:
                print(f"  foliage never culls (cull end 0) — draws to the horizon "
                      f"and pops out when its cell unloads at {lr:,.0f}. Raise "
                      f"MTMI_WP_LOADING_RANGE to push the pop further out, or set "
                      f"MTMI_FOLIAGE_CULL_END to fade instead.")
            elif worst >= lr:
                print(f"  WARNING: cull end {worst:,.0f} >= loading range {lr:,.0f}. "
                      f"Foliage still draws when its cell unloads, so it will pop "
                      f"out instead of fading. Lower the cull or raise "
                      f"MTMI_WP_LOADING_RANGE.", file=sys.stderr)
            else:
                # Headroom in SECONDS, because uu does not say whether it is
                # enough. It is the whole window a cell has to come off the pak
                # between becoming eligible and becoming visible, and what
                # spends that window is the player's speed. 6,800 uu read like
                # a pass and is 2.4 s at 100 km/h -- too short, which is how
                # foliage ended up arriving in front of the car fully grown.
                head = lr - worst
                secs = head / 2777.8          # 100 km/h in uu/s
                print(f"  draw/stream margin: cull ends {worst:,.0f}, "
                      f"cell unloads {lr:,.0f} ({head:,.0f} uu = {secs:.1f}s "
                      f"at 100 km/h)")
                if secs < 5.0:
                    print(f"  WARNING: {secs:.1f}s is not long enough to stream "
                          f"a cell in. Foliage will appear already grown rather "
                          f"than fading up. Lower MTMI_FOLIAGE_CULL_END or the "
                          f"per-mesh overrides, or raise MTMI_WP_LOADING_RANGE.",
                          file=sys.stderr)
        except ValueError:
            pass

    print("  mesh set:")
    for folder, n in sorted(folders.items(), key=lambda kv: -kv[1]):
        print(f"      {n:>3} mesh(es)  {folder}")

    # Override materials are referenced by the COMPONENT, not the mesh, so
    # copy_cooked_dependencies (which follows mesh refs) never sees them.
    # Unshipped, the game silently falls back to the mesh's own material.
    matpaths = set()
    for key in mesh_paths:
        for m in (settings.get(key) or {}).get("override_materials") or []:
            if m.get("path"):
                matpaths.add(m["path"])
    if matpaths:
        ms = collections.Counter()
        for ap in sorted(matpaths):
            rel = im.game_path_to_disk(ap)
            if rel:
                ms[im.copy_asset_to_mod(rel, script_dir)] += 1
        print("  override materials: " + ", ".join(f"{v} {k}" for k, v in sorted(ms.items())))
        if ms["missing"] or ms["unset"]:
            print("  ERROR: override material(s) missing from game and cooked output "
                  "— foliage would render with the wrong material", file=sys.stderr)
            return 1
    if shipped["missing"] or shipped["unset"]:
        print("  ERROR: foliage meshes missing from both game and cooked output "
              "— their instances would render nothing", file=sys.stderr)
        return 1

    ordered = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    total = sum(len(v) for _, v in ordered)
    print(f"  {total:,} instance(s) in {len(ordered):,} (tile, mesh) group(s)"
          + (f" [mesh={args.mesh_filter}]" if args.mesh_filter else ""))

    # ONE cell per tile, carrying every mesh type in that tile as its own IFA.
    # Not negotiable: WP keys a runtime cell by grid coords, and every mesh of
    # a tile resolves to the same key, so one-cell-per-(tile,mesh) collides and
    # the map keeps only the last. Measured: 2,164 of 27,613 cells reachable,
    # ~8% of the foliage rendering.
    by_tile: dict[tuple, list] = collections.defaultdict(list)
    for (tile, mesh), inst in ordered:
        by_tile[tile].append((mesh, inst))
    # Limit AFTER grouping — densest tiles first — so a capped run still
    # exercises real multi-mesh cells instead of one mesh per tile.
    if args.limit:
        keep = sorted(by_tile, key=lambda t: -sum(len(i) for _, i in by_tile[t]))[:args.limit]
        by_tile = {t: by_tile[t] for t in keep}
    print(f"  -> {len(by_tile):,} cell(s), one per tile "
          f"(avg {sum(len(v) for v in by_tile.values())/len(by_tile):.1f} mesh types each)")

    scratch = WORK_DIR / "foliage_inst"
    scratch.mkdir(parents=True, exist_ok=True)
    for old in scratch.glob("*.jsonl"):
        old.unlink()

    def write_jsonl(path: Path, inst: list) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            for r in inst:
                fh.write('{"X":%r,"Y":%r,"Z":%r,"Pitch":%r,"Yaw":%r,"Roll":%r,'
                         '"ScaleX":%r,"ScaleY":%r,"ScaleZ":%r}\n' % r)

    specs, jobs = [], []
    for tile, meshes in by_tile.items():
        name = make_cell_name(f"fol|{tile}")
        cx, cy = (tile[0] + 0.5) * GRID, (tile[1] + 0.5) * GRID
        spec = cell_spec(name, cx, cy, gen_dir)
        spec["template-cell"] = FOLIAGE_TEMPLATE
        # Real content bounds over EVERY mesh in the tile. The IFAs span a
        # 25600 tile but the runtime cell is 12800 wide, so the default
        # (cell-sized) bounds would cull the overhang at cell edges — exactly
        # the "missing patches" failure.
        allx = [r[0] for _, inst in meshes for r in inst]
        ally = [r[1] for _, inst in meshes for r in inst]
        # Streaming decides a cell is relevant from its BOUNDS. Report bounds
        # padded outward and the cell is pulled in before you reach it, which
        # is the cheap version of "load the neighbouring cells too" -- no extra
        # cells registered, each one just claims to start earlier. Trees then
        # finish streaming before they are close enough to notice appearing.
        # Costs resident memory: every cell stays loaded PAD further out.
        spec["cb-min-x"] = f"{min(allx) - CELL_PAD}"; spec["cb-max-x"] = f"{max(allx) + CELL_PAD}"
        spec["cb-min-y"] = f"{min(ally) - CELL_PAD}"; spec["cb-max-y"] = f"{max(ally) + CELL_PAD}"
        specs.append(spec)

        (mesh0, inst0), rest = meshes[0], meshes[1:]
        jl0 = scratch / f"{name}.jsonl"
        write_jsonl(jl0, inst0)
        job = {
            "cell": str(gen_dir / f"{name}.umap"),
            "tx": str(tile[0]), "ty": str(tile[1]), "tz": str(tile[2]),
            "instances": str(jl0),
        }
        if mesh_paths.get(mesh0):
            job["mesh"] = mesh_paths[mesh0]
        job.update(comp_settings(mesh0))
        extra = []
        for k, (mesh, inst) in enumerate(rest):
            jlk = scratch / f"{name}_{k + 1}.jsonl"
            write_jsonl(jlk, inst)
            ex = {"mesh": mesh_paths.get(mesh, ""), "instances": str(jlk)}
            ex.update(comp_settings(mesh))
            extra.append(ex)
        if extra:
            job["extra"] = json.dumps(extra)
        jobs.append(job)

    print(f"  registering {len(specs):,} cell(s)...")
    if not register_cells_batch(args.main_in, args.main_out, specs):
        print("  cell registration FAILED", file=sys.stderr)
        return 1

    missing = [j["cell"] for j in jobs if not Path(j["cell"]).is_file()]
    if missing:
        print(f"  registration produced no file for {len(missing)} cell(s), "
              f"e.g. {missing[0]}", file=sys.stderr)
        return 1

    spec_path = WORK_DIR / "foliage_cells_spec.json"
    spec_path.write_text(json.dumps(jobs), encoding="utf-8")
    r = subprocess.run([
        str(INJECTOR), "make-foliage-cell",
        "--spec", str(spec_path),
        "--mappings", str(MAPPINGS),
    ], text=True)
    if r.returncode != 0:
        print("  foliage cell emission FAILED", file=sys.stderr)
        return r.returncode
    print(f"  {len(jobs):,} foliage cell(s) in {gen_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
