#!/usr/bin/env python3
"""
import_meshes.py - Imports static meshes from static_meshes.json into
map_work_changes.json["static_meshes"]["imported"], applying offsets.
Skips SM_SkySphere. Copies missing assets into the mod pak directory.

Usage:
    python import_meshes.py
"""

import json
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys

from mesh_shards import ShardWriter, iter_entries, has_shards, split_json_file

# ---------------------------------------------------------------------------
# Paths — pulled from env (see mt_paths.py and build.bat)
# ---------------------------------------------------------------------------
# Name a mesh BusStop_My_Cool_Location in the editor and it becomes a station:
# the mesh is placed as usual and a working bus stop actor is dropped on it,
# displayed in game as "My Cool Location".
BUS_STOP_MESH_PREFIX = "BusStop_"


def bus_stop_label(asset_path: str) -> str | None:
    """Station name for a BusStop_* mesh, or None if the mesh is not one.

    Takes a full asset path ("/Game/.../BusStop_My_Cool_Location.BusStop_My_
    Cool_Location") because that is what the shard entries carry -- the object
    name is the part after the last dot, not the last slash.
    """
    obj = asset_path.rsplit("/", 1)[-1].rsplit(".", 1)[-1]
    if not obj.startswith(BUS_STOP_MESH_PREFIX):
        return None
    label = obj[len(BUS_STOP_MESH_PREFIX):].replace("_", " ").strip()
    return label or None

from mt_paths import (GAME_CONTENT as _GAME_CONTENT, COOKED_CONTENT as _COOKED,
                      MOD_CONTENT_ROOT as _MOD_CONTENT_ROOT)
GAME_CONTENT = str(_GAME_CONTENT)
# COOKED_CONTENT is the UE editor's cooked output for THIS mod's Unreal
# project (where editor-cooked .uasset/.ubulk files land before they're
# copied into the mod tree). Optional — only needed when authoring meshes
# in-editor. Resolved by mt_paths (process env OR .env), so a standalone
# `python import_meshes.py` honors .env just like the full build does.
COOKED_CONTENT = str(_COOKED) if _COOKED else ""
MOD_CONTENT = str(_MOD_CONTENT_ROOT)

# ---------------------------------------------------------------------------
# Vanilla-asset detection. An asset that already ships in the base game must
# NOT be re-copied into the mod pak — doing so bloats the pak with redundant
# copies of vanilla meshes/materials (e.g. the container ship) and can even
# shadow the real game asset. The extracted vanilla_extract/ folder is sparse
# (bootstrap only pulls a few bundles), so checking it alone gives false
# negatives. The authority is the real game pak: list it once with the
# vendored repak + AES key and treat every Content path in it as vanilla.
# ---------------------------------------------------------------------------
from mt_paths import REPAK as _REPAK, GAME_PAKDIR as _GAME_PAKDIR, MT_AES_KEY as _MT_AES_KEY

_VANILLA_PAK_SET = None  # frozenset of Content-relative paths (no extension)


def _vanilla_pak_assets():
    """Content-relative asset paths (no extension) present in the base game
    pak. Cached for the run. Empty set if repak/pak unavailable (falls back
    to the vanilla_extract filesystem check only)."""
    global _VANILLA_PAK_SET
    if _VANILLA_PAK_SET is not None:
        return _VANILLA_PAK_SET

    pak = None
    for name in ("MotorTown-Windows.pak", "MotorTown.pak"):
        cand = os.path.join(str(_GAME_PAKDIR), name)
        if os.path.exists(cand):
            pak = cand
            break
    if not pak or not os.path.exists(str(_REPAK)):
        print("  vanilla-pak check unavailable (repak or game pak missing) — "
              "only vanilla_extract/ is used to detect shipped assets")
        _VANILLA_PAK_SET = frozenset()
        return _VANILLA_PAK_SET

    marker = "MotorTown/Content/"
    drop_ext = (".uasset", ".umap", ".uexp", ".ubulk")
    s = set()
    try:
        out = subprocess.run(
            [str(_REPAK), "--aes-key", _MT_AES_KEY, "list", pak],
            capture_output=True, text=True, timeout=600,
        )
        for line in out.stdout.splitlines():
            line = line.strip().replace("\\", "/")
            i = line.find(marker)
            if i == -1:
                continue
            rel = line[i + len(marker):]
            for ext in drop_ext:
                if rel.endswith(ext):
                    rel = rel[:-len(ext)]
                    break
            if rel:
                s.add(rel)
    except Exception as e:
        print(f"  warning: could not list game pak ({e}) — vanilla-pak skip disabled")
    _VANILLA_PAK_SET = frozenset(s)
    print(f"  vanilla game pak: {len(_VANILLA_PAK_SET)} assets (these won't be re-shipped)")
    return _VANILLA_PAK_SET


def _is_vanilla(relative_path):
    """True if the asset already ships in the base game (extracted folder OR
    the game pak) and therefore must not be copied into the mod."""
    if os.path.exists(os.path.join(GAME_CONTENT, relative_path + ".uasset")):
        return True
    return relative_path in _vanilla_pak_assets()

# ---------------------------------------------------------------------------
# Offsets applied to every imported mesh/actor. Your custom build is
# authored in one spot in the editor and shifted into a chosen region of
# Jeju. Configure per-map in .env (MTMI_OFFSET_X/Y/Z and ..._PITCH/ROLL/
# YAW); mt_paths supplies the defaults below for the current "new map".
# ---------------------------------------------------------------------------
from mt_paths import (
    IMPORT_OFFSET_X as OFFSET_X,
    IMPORT_OFFSET_Y as OFFSET_Y,
    IMPORT_OFFSET_Z as OFFSET_Z,
    IMPORT_OFFSET_PITCH as OFFSET_PITCH,
    IMPORT_OFFSET_ROLL as OFFSET_ROLL,
    IMPORT_OFFSET_YAW as OFFSET_YAW,
)

# Which group inside map_work_changes.json["static_meshes"] to write to
TARGET_GROUP = "imported"

from bp_registry import REGISTRY as _BP_REGISTRY, asset_keys as _bp_asset_keys

# Meshes intentionally excluded (never placed as static meshes or BP actors).
# Scaffolding that belongs to the EDITOR scene, not to the game: the sky
# sphere, and the sea plane the island floats in. Both are there so the level
# looks like a world to work in and so map.py has something to photograph --
# the sea plane in particular is what the capture paints magenta and keys out,
# and shipping it put a flat purple sheet across the water in game.
#
# Excluded here rather than fixed in the editor on purpose. The mesh is
# legitimately part of the scene and should stay in it; what is wrong is
# exporting it, so the build is where it gets dropped.
SKIP_KEYS = {"SM_SkySphere", "SM_Env_Unreal_Water_DC"}

# Placeholder asset_keys (from bp_registry) become blueprint_actors entries
# instead of static meshes. Registry keys are the single source of truth.
BP_CLASS_FROM_KEY = {
    key: {"blueprint_path": entry["bp_path"], "blueprint_class": entry["bp_class"]}
    for key, entry in _BP_REGISTRY.items()
}
PARKING_KEYS = _bp_asset_keys()

SRC = "static_meshes.json"
DST = "map_work_changes.json"


def game_path_to_disk(asset_path):
    """
    Convert a UE game path to a relative disk path under Content/.
    e.g. "/Game/Models/Foo/Bar" -> "Models/Foo/Bar"
         "/Engine/Foo/Bar"      -> None (engine asset, skip)
    """
    # Strip .ExportName suffix if present
    dot = asset_path.rfind("/")
    dot_pos = asset_path.find(".", dot)
    if dot_pos != -1:
        asset_path = asset_path[:dot_pos]

    # /Game/ maps to MotorTown/Content/ on disk
    if asset_path.startswith("/Game/"):
        return asset_path[len("/Game/"):]
    return None


_VEHICLE_PATH_CACHE = {}


def resolve_vehicle_path_by_key(veh_key):
    """Find a vehicle BP's /Game path from a Spawn_/Dealership_ placeholder key.

    The key is a DataTable ROW name — what the game itself calls the
    vehicle, and what the roster lists. The row's VehicleClass field names
    the actor to place, so that is the authority and it is asked first:
    a row's asset is often named differently (`Police_01` is
    `/Game/Cars/Models/Police/Police`, `Nuke_Police` is `.../Nuke/NukePolice`,
    `Trailer_30ft_Log_01` is `.../Trailer_9m_Flat_01/Trailer_9m_Log_01`), and
    guessing from the name silently places a spawner that references nothing.

    Tables are read mod-aware, so a vehicle any installed mod adds resolves
    with no code change here.

    A filename scan of the extracted content is the fallback, for an asset
    that ships without a table row at all.

    Returns None if neither finds it (caller skips placing that spawner)."""
    if veh_key in _VEHICLE_PATH_CACHE:
        return _VEHICLE_PATH_CACHE[veh_key]
    path = None
    # Vehicles this mod DECLARES come first. Their row only exists in the mod
    # tree, which the installed-pak lookup below cannot see until the pak has
    # shipped -- so on a first build the spawner would resolve nothing and the
    # placeholder would be silently dropped. vehicles.json knows the answer
    # without needing the table.
    try:
        import json as _j
        from build_vehicles import same_length_name
        _cfg = _j.loads(pathlib.Path("vehicles.json").read_text(encoding="utf-8"))             if pathlib.Path("vehicles.json").exists() else {}
        for _v in (_cfg.get("vehicles") or []):
            if _v.get("new_id") != veh_key:
                continue
            from unlock_vehicles import vehicle_class_by_row as _byrow
            _base = _byrow().get(_v.get("base", ""))
            if _base:
                _short = _base[_base.rfind("/") + 1:]
                path = _base[:_base.rfind("/") + 1] + same_length_name(veh_key, _short)
                print(f"  spawner: '{veh_key}' is mod-declared -> {path}")
            break
    except Exception as _e:
        print(f"  spawner: vehicles.json lookup skipped ({_e})", file=sys.stderr)
    try:
        if path:
            raise StopIteration
        from unlock_vehicles import vehicle_class_by_row
        path = vehicle_class_by_row().get(veh_key)
    except StopIteration:
        pass
    except Exception as e:
        print(f"  spawner: vehicle-table lookup unavailable ({e}) — "
              f"falling back to a filename scan", file=sys.stderr)
    if not path:
        from mt_paths import GAME_CONTENT
        for base in (GAME_CONTENT / "Cars", GAME_CONTENT):
            if not base.is_dir():
                continue
            matches = list(base.rglob(f"{veh_key}.uasset"))
            if matches:
                rel = matches[0].relative_to(GAME_CONTENT).with_suffix("")
                path = "/Game/" + str(rel).replace("\\", "/")
                print(f"  spawner: '{veh_key}' has no vehicle-table row — "
                      f"matched an asset by name instead ({path})")
                break
    _VEHICLE_PATH_CACHE[veh_key] = path
    return path


# Matches /Game package references stored in a cooked .uasset's import/name
# table (UE asset names are restricted to [A-Za-z0-9_], paths use '/').
_GAME_REF_RE = re.compile(rb"/Game/[A-Za-z0-9_/]+")

# Run-wide dedup + counter for dependency assets pulled from cooked output.
_DEP_VISITED = set()
_DEP_COPIED = []


def _extract_game_refs(uasset_path):
    """Return the set of /Game package paths (as Content-relative disk paths,
    no extension) referenced by a cooked .uasset header. Used to follow a
    mesh's material/texture/function dependencies."""
    refs = set()
    try:
        with open(uasset_path, "rb") as f:
            data = f.read()
    except Exception:
        return refs
    for m in _GAME_REF_RE.findall(data):
        p = m.decode("ascii", "ignore")[len("/Game/"):]
        if p:
            refs.add(p)
    return refs


# Copy accounting for the run, so a recook reports what actually moved.
_COPY_STATS = {"updated": 0, "same": 0}


def _sha(path, _buf=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(_buf):
            h.update(chunk)
    return h.digest()


def _copy_if_changed(src, dst):
    """Copy src->dst only when the CONTENT differs. Returns True if written.

    A recook rewrites every cooked file, so mtime always changes while most
    assets are byte-identical — copying blindly churns hundreds of MB through
    the mod tree and dirties them all in git for nothing. Size is checked
    first so the hash only runs on same-size candidates.
    """
    try:
        if os.path.exists(dst):
            if os.path.getsize(src) == os.path.getsize(dst) and _sha(src) == _sha(dst):
                _COPY_STATS["same"] += 1
                return False
        shutil.copy2(src, dst)
        _COPY_STATS["updated"] += 1
        return True
    except Exception:
        return False


def _copy_one(relative_path, script_dir):
    """Copy a single asset's .uasset/.uexp/.ubulk from cooked output into the
    mod tree. Returns True if the .uasset was copied."""
    mod_target = os.path.join(script_dir, MOD_CONTENT, relative_path)
    os.makedirs(os.path.dirname(mod_target), exist_ok=True)
    did = False
    for ext in (".uasset", ".uexp", ".ubulk"):
        src = os.path.join(COOKED_CONTENT, relative_path + ext)
        if os.path.exists(src):
            if _copy_if_changed(src, mod_target + ext) and ext == ".uasset":
                did = True
    return did


def copy_cooked_dependencies(relative_path, script_dir):
    """Follow a cooked asset's /Game references and copy any that are missing
    from the game files but present in cooked output (custom materials, the
    textures/shaders and material functions they reference, etc.), recursively.
    Vanilla deps already in the game files are left alone."""
    if not COOKED_CONTENT:
        return
    stack = [relative_path]
    while stack:
        cur = stack.pop()
        cooked_uasset = os.path.join(COOKED_CONTENT, cur + ".uasset")
        for ref in _extract_game_refs(cooked_uasset):
            if ref in _DEP_VISITED or ref == relative_path:
                continue
            _DEP_VISITED.add(ref)
            # Already shipped in the base game (extracted folder OR game pak)
            # -> nothing to do; don't bloat the mod with a vanilla copy.
            if _is_vanilla(ref):
                continue
            # Only pull custom assets that exist in cooked output (skips
            # /Game refs that resolve to engine/other non-cooked content).
            if not os.path.exists(os.path.join(COOKED_CONTENT, ref + ".uasset")):
                continue
            if _copy_one(ref, script_dir):
                _DEP_COPIED.append(ref)
                stack.append(ref)   # recurse into this dep's own references


def copy_asset_to_mod(relative_path, script_dir):
    """
    If the asset doesn't exist in extracted game files, copy it from
    cooked content (or game content) into the mod pak directory.
    Copies .uasset, .uexp, .ubulk — skips silently if any don't exist.

    Returns a status so main() can summarize:
      'in_game' — already in vanilla content, nothing to do
      'copied'  — copied from cooked output
      'unset'   — not in game and MTMI_COOKED_CONTENT not configured
      'missing' — not in game and not found in cooked output
    A custom mesh that returns 'unset'/'missing' will NOT be in the pak and
    its StaticMeshActor will reference a null mesh in game (access-violation
    crash when that area streams in), so these are tracked and surfaced.
    """
    mod_target = os.path.join(script_dir, MOD_CONTENT, relative_path)

    # Already in the base game (extracted folder OR the real game pak)?
    # Then never ship a copy — the game already has it. This is what keeps
    # vanilla meshes/materials (e.g. the container ship) out of the mod pak.
    if _is_vanilla(relative_path):
        return "in_game"

    # Asset isn't in extracted vanilla content — try the user's editor
    # cooked output. Only relevant when authoring meshes in UE; vanilla-
    # only mods never hit this path.
    if not COOKED_CONTENT:
        return "unset"
    cooked_file = os.path.join(COOKED_CONTENT, relative_path + ".uasset")
    if not os.path.exists(cooked_file):
        print(f"  missing from game AND cooked: {relative_path}")
        return "missing"

    # Default: always re-copy from cooked output, because cooked content can
    # change at any time and a stale mod copy would silently ship the old
    # mesh. --skip-cache-mesh (MTMI_SKIP_CACHE_MESH=1) opts into reusing an
    # existing mod copy for speed when you know cooked is unchanged.
    if os.environ.get("MTMI_SKIP_CACHE_MESH") == "1" and os.path.exists(mod_target + ".uasset"):
        return "cached"

    mod_dir = os.path.dirname(mod_target)
    os.makedirs(mod_dir, exist_ok=True)

    copied = []
    for ext in [".uasset", ".uexp", ".ubulk"]:
        src = os.path.join(COOKED_CONTENT, relative_path + ext)
        dst = mod_target + ext
        if os.path.exists(src):
            _copy_if_changed(src, dst)
            copied.append(ext)

    # Pull the mesh's custom material/shader/texture dependencies from cooked
    # output too — a cooked mesh references materials that aren't in the
    # vanilla game files, so they must ship alongside it or it renders with
    # the wrong/placeholder material in game.
    copy_cooked_dependencies(relative_path, script_dir)

    # Per-asset copy log is noisy; main() prints a summary instead.
    return "copied"


def _iter_source_entries(parts_dir, single_file, skip_foliage=False):
    """Yield raw editor-export entries one at a time (bounded memory).

    Source preference:
      1. Sharded export dir (static_meshes_parts/) — what the new ue.py
         writes. Streamed shard-by-shard.
      2. Legacy single static_meshes.json. If it's large (> 200 MB) it is
         stream-split into shards first (a plain json.load on a multi-GB
         file is exactly the MemoryError this whole change fixes); small
         files are loaded directly.

    skip_foliage: when True, HISM foliage is excluded — the "fol_*" shards
    are not read (or the "foliage" group is skipped in a small legacy file).
    Placed StaticMeshActors ("sm_*" / "actors") are always kept. Used to
    test a far smaller, game-loadable build (millions of foliage actors in
    the persistent level are the suspected world-load crash).
    """
    # Optional foliage downsample: keep only every Nth fol_* entry (actors in
    # sm_* are always kept in full). Lets us fit under UAssetAPI's ~2 GB write
    # limit / test a loadable foliage density in the persistent level.
    every_n = 0
    try:
        every_n = int(os.environ.get("MTMI_FOLIAGE_EVERY_N", "0"))
    except ValueError:
        every_n = 0

    # Foliage that must NEVER pop in. Cells stream by distance, so anything
    # solid enough to crash a vehicle (rocks) can materialise in front of you.
    # Meshes matching these substrings are routed to the persistent level as
    # ordinary StaticMeshActors instead, which is always loaded. Costs ~2
    # UObjects each, so keep the list to genuinely small, hazardous sets.
    as_actors = tuple(
        s.strip().lower()
        for s in os.environ.get("MTMI_FOLIAGE_AS_ACTORS", "").split(",")
        if s.strip()
    )

    def _is_actor_foliage(entry):
        if not as_actors:
            return False
        key = str(entry.get("asset_key", "")).lower()
        return any(a in key for a in as_actors)

    excl = ("fol",) if skip_foliage else None
    if has_shards(parts_dir):
        msg = f"  reading sharded export from {parts_dir}"
        if skip_foliage:
            msg += " (skipping foliage / fol_* shards)"
        elif every_n > 1:
            msg += f" (foliage downsampled: every {every_n}th fol_* entry)"
        print(msg)
        if as_actors:
            print(f"  foliage kept as persistent actors (never pops in): {', '.join(as_actors)}")
        if not skip_foliage and every_n > 1:
            yield from iter_entries(parts_dir, prefix="sm")
            for i, e in enumerate(iter_entries(parts_dir, prefix="fol")):
                if i % every_n == 0:
                    yield e
            return
        yield from iter_entries(parts_dir, exclude_prefixes=excl)
        if skip_foliage and as_actors:
            n = 0
            for e in iter_entries(parts_dir, prefix="fol"):
                if _is_actor_foliage(e):
                    n += 1
                    yield e
            print(f"  +{n:,} foliage instance(s) promoted to persistent actors")
        return
    if not os.path.exists(single_file):
        print(f"  ERROR: no export found — neither {parts_dir} nor {single_file} exists")
        return
    size = os.path.getsize(single_file)
    BIG = 200 * 1024 * 1024  # 200 MB
    if size > BIG:
        print(f"  {single_file} is {size / 1e9:.2f} GB — stream-splitting into "
              f"group-aware shards (one-time, avoids loading it whole)...")
        n = split_json_file(single_file, parts_dir)
        print(f"  split into shards: {n} entries under {parts_dir} (actors=sm_*, foliage=fol_*)")
        yield from iter_entries(parts_dir, exclude_prefixes=excl)
    else:
        with open(single_file, "r", encoding="utf-8") as f:
            src = json.load(f)
        for group_name, items in src.get("static_meshes", {}).items():
            if skip_foliage and group_name == "foliage":
                continue
            if isinstance(items, list):
                yield from items


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # The editor export lives in the repo (sharded static_meshes_parts/, or
    # legacy static_meshes.json). The map_work_changes.json intermediate and
    # the streamed mesh sidecar live in the temp work dir so they don't
    # clutter the repo. Paths come from mt_paths so build.bat, convert2 and
    # clone_bp_actors all agree on them.
    from mt_paths import (
        STATIC_MESHES_JSON, STATIC_MESHES_DIR, MAP_WORK_JSON, MAP_WORK_MESHES_DIR,
    )
    dst_path = str(MAP_WORK_JSON)

    # Re-read the prior intermediate (if any) so hand-added _comment
    # entries and non-regenerated keys survive. Fresh temp = empty base.
    # Guard against a stale, pre-streaming dst that inlined millions of
    # mesh entries — loading that would re-trigger the MemoryError.
    dst = {}
    if os.path.exists(dst_path):
        try:
            if os.path.getsize(dst_path) <= 100 * 1024 * 1024:
                with open(dst_path, "r", encoding="utf-8") as f:
                    dst = json.load(f)
            else:
                print(f"  prior {dst_path} is large — skipping re-read "
                      f"(hand-authored _comment entries won't be preserved this run)")
        except Exception as e:
            print(f"  prior {dst_path} unreadable ({e}) — starting fresh")
            dst = {}

    # The giant static_meshes.imported array is streamed to JSONL sidecar
    # shards, never held in memory. Only the small keyed groups (parking,
    # delivery, dealers) accumulate in lists.
    mesh_writer = ShardWriter(str(MAP_WORK_MESHES_DIR), prefix="mesh")
    parking = []
    # Meshes named BusStop_* -- see the streaming loop below.
    bus_stop_meshes: list[tuple[str, float, float, float, float]] = []
    delivery = []
    placed_dealers = []   # from "Dealership_<VehicleKey>" scene placeholders
    skipped = 0
    copied_paths = set()
    _unset_assets = []    # custom meshes skipped: MTMI_COOKED_CONTENT not set
    _missing_assets = []  # custom meshes skipped: not in game or cooked
    # Delivery-point configuration is the authority for whether a scene
    # placeholder gets placed: bp_registry loads delivery_points.json into
    # the registry at import time, and we check membership below. No need to
    # re-read the JSON here.

    skip_foliage = os.environ.get("MTMI_SKIP_FOLIAGE") == "1"
    if skip_foliage:
        print("  MTMI_SKIP_FOLIAGE=1 — dropping HISM foliage, keeping placed StaticMeshActors only")
    for entry in _iter_source_entries(str(STATIC_MESHES_DIR), str(STATIC_MESHES_JSON), skip_foliage):
            # SKIP_KEYS: completely ignore (unless also in PARKING_KEYS)
            if entry.get("asset_key") in SKIP_KEYS and entry.get("asset_key") not in PARKING_KEYS:
                skipped += 1
                continue

            # Vehicle-spawner placeholder: "Dealership_<VehicleKey>" or the
            # shorter "Spawn_<VehicleKey>" — same behaviour, two spellings.
            # Split ONLY on the first underscore so vehicle keys with their
            # own underscores survive (Spawn_Cotra_20_3L -> "Cotra_20_3L").
            # Places an MTDealerVehicleSpawnPoint for that vehicle at the
            # marker's location; the placeholder's own mesh is NOT shipped or
            # rendered (position marker only — same idea as DeliveryPoint_*).
            _ak = entry.get("asset_key")
            _pfx = next((q for q in ("Dealership_", "Spawn_")
                         if isinstance(_ak, str) and _ak.startswith(q)), None)
            if _pfx and len(_ak) > len(_pfx):
                veh_key = _ak[len(_pfx):]
                veh_path = resolve_vehicle_path_by_key(veh_key)
                if not veh_path:
                    print(f"  spawner: vehicle '{veh_key}' not found in game content "
                          f"(from placeholder '{_ak}') — skipped")
                    continue
                w = bool(entry.get("world_coords", False))
                dox, doy, doz = (0, 0, 0) if w else (OFFSET_X, OFFSET_Y, OFFSET_Z)
                dop, dorr, doyw = (0, 0, 0) if w else (OFFSET_PITCH, OFFSET_ROLL, OFFSET_YAW)
                placed_dealers.append({
                    "vehicle_path": veh_path,
                    "vehicle_key": veh_key,
                    "X": round(float(entry.get("X", 0)) + dox, 4),
                    "Y": round(float(entry.get("Y", 0)) + doy, 4),
                    "Z": round(float(entry.get("Z", 0)) + doz, 4),
                    "Pitch": round(float(entry.get("Pitch", 0)) + dop, 4),
                    "Roll": round(float(entry.get("Roll", 0)) + dorr, 4),
                    "Yaw": round(float(entry.get("Yaw", 0)) + doyw, 4),
                })
                continue  # never ship the placeholder mesh

            # Copy missing assets to mod (once per unique path). Skip DC/Actors
            # placeholders — they're scene-only markers that the BP-clone pass
            # replaces at runtime, so shipping their .uasset adds nothing.
            raw_path = entry.get("asset_path", "")
            rel_path = game_path_to_disk(raw_path)
            if (rel_path and rel_path not in copied_paths
                    and not rel_path.startswith("DC/Actors")):
                status = copy_asset_to_mod(rel_path, script_dir)
                copied_paths.add(rel_path)
                if status == "unset":
                    _unset_assets.append(rel_path)
                elif status == "missing":
                    _missing_assets.append(rel_path)

            # Scene-export coords from ue.py are editor-local — apply the
            # global OFFSETs to get world coords. Hand-authored entries can
            # opt out via "world_coords": true (then X/Y/Z/Pitch/Roll/Yaw
            # are taken verbatim).
            world = bool(entry.get("world_coords", False))
            ox, oy, oz = (0, 0, 0) if world else (OFFSET_X, OFFSET_Y, OFFSET_Z)
            op, orr, oy_ = (0, 0, 0) if world else (OFFSET_PITCH, OFFSET_ROLL, OFFSET_YAW)
            base_entry = {
                "X": round(float(entry.get("X", 0)) + ox, 4),
                "Y": round(float(entry.get("Y", 0)) + oy, 4),
                "Z": round(float(entry.get("Z", 0)) + oz, 4),
                "Pitch": round(float(entry.get("Pitch", 0)) + op, 4),
                "Roll": round(float(entry.get("Roll", 0)) + orr, 4),
                "Yaw": round(float(entry.get("Yaw", 0)) + oy_, 4),
            }

            key = entry.get("asset_key")
            # Accept either prefix form: DeliveryPoint_<KEY> or
            # Delivery_Point_<KEY> (the scene-side underscore separator
            # differs by author preference).
            dp_key = None
            if isinstance(key, str):
                for prefix in ("DeliveryPoint_", "Delivery_Point_"):
                    if key.startswith(prefix):
                        dp_key = key[len(prefix):]
                        break
            if dp_key is not None:
                # Slim entry — only the placement data + the key reference.
                # The actual delivery-point config (label, recipes,
                # marker/icon, storage cap) stays in delivery_points.json.
                # A scene placeholder is only PLACED if its key resolves to a
                # real, registered delivery point. Unconfigured placeholders
                # (and any that collide with non-DP top-level JSON keys like
                # new_cargos / _doc) fall through and are left empty — no
                # actor is created for them. This is what lets you drop a
                # batch of DeliveryPoint_* markers in the editor and only
                # wire up the ones you've actually configured, without the
                # rest breaking the build.
                if f"DeliveryPoint_{dp_key}" in _BP_REGISTRY:
                    dp_entry = dict(base_entry)
                    dp_entry["delivery_key"] = dp_key
                    # Every delivery point uses its OWN placeholder mesh
                    # (DeliveryPoint_South_Barn, DeliveryPoint_Valley_Trailer,
                    # ...), and those meshes do not share a pivot height. A
                    # placeholder whose origin sits at its centre lands the
                    # actor half-buried; one with the origin above the mesh
                    # lands it floating. That is why some points sit perfectly
                    # and others are metres out with identical editor
                    # placement. `z_offset` in delivery_points.json nudges one
                    # without re-authoring the mesh or re-exporting the scene.
                    dz = (_BP_REGISTRY[f"DeliveryPoint_{dp_key}"] or {}).get("z_offset")
                    if dz:
                        dp_entry["Z"] = round(dp_entry["Z"] + float(dz), 4)
                        print(f"  delivery: '{dp_key}' z_offset {float(dz):+.0f} "
                              f"-> Z {dp_entry['Z']:,.0f}")
                    delivery.append(dp_entry)
                else:
                    print(f"  delivery: '{dp_key}' has no config in delivery_points.json — placeholder left empty (skipped)")
            elif key in PARKING_KEYS:
                base_entry.update(BP_CLASS_FROM_KEY[key])
                # Carry the registry key through so clone_bp_actors can look
                # up the exact entry — multiple entries may share the same
                # blueprint_class (e.g. FarmCorn + FarmTransformer both use
                # Farm_Corn_C), so a class-based lookup is ambiguous.
                base_entry["asset_key"] = key
                parking.append(base_entry)
            else:
                base_entry["asset_path"] = raw_path
                base_entry["asset_key"] = entry.get("asset_key", "")
                base_entry["ScaleX"] = float(entry.get("ScaleX", 1.0))
                base_entry["ScaleY"] = float(entry.get("ScaleY", 1.0))
                base_entry["ScaleZ"] = float(entry.get("ScaleZ", 1.0))
                # A mesh named BusStop_<Something> is a station: it keeps its
                # place as scenery AND gets a working stop actor dropped on it,
                # named after the suffix. Collected here rather than by
                # re-reading the shard, so the coordinates are the same ones
                # the mesh itself was written with.
                _label = bus_stop_label(base_entry["asset_path"])
                if _label:
                    bus_stop_meshes.append((
                        _label,
                        base_entry["X"], base_entry["Y"], base_entry["Z"],
                        base_entry.get("Yaw", 0.0),
                    ))
                # Streamed to JSONL sidecar shards instead of held in memory.
                mesh_writer.write(base_entry)

    # --- Hand-placed meshes (fog_placements.json) --------------------------
    # Placing fog by editor export means it lands wherever the scene happens to
    # put it, which is not necessarily anywhere you ever drive. These entries
    # are authored by hand in EDITOR coordinates -- the numbers you read off the
    # transform panel -- and go through the same offset and the same shard
    # stream as everything else, so "put fog here" stops depending on the
    # export. `world: true` on an entry skips the offset for coordinates
    # already read in world space.
    n_placed = 0
    try:
        fog_json = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fog_placements.json")
        if os.path.exists(fog_json):
            with open(fog_json, "r", encoding="utf-8") as f:
                spec = json.load(f)
            default_mesh = spec.get("mesh") or ""
            for e in spec.get("placements") or []:
                if not isinstance(e, dict) or str(e.get("name", "")).startswith("_"):
                    continue
                path = e.get("mesh") or default_mesh
                if not path:
                    print("  [fog] entry with no mesh and no default 'mesh' — skipped", file=sys.stderr)
                    continue
                is_world = bool(e.get("world"))
                sc = float(e.get("scale", 1.0))
                mesh_writer.write({
                    "X": round(float(e["X"]) + (0.0 if is_world else OFFSET_X), 4),
                    "Y": round(float(e["Y"]) + (0.0 if is_world else OFFSET_Y), 4),
                    "Z": round(float(e["Z"]) + (0.0 if is_world else OFFSET_Z), 4),
                    "Pitch": float(e.get("Pitch", 0.0)),
                    "Roll":  float(e.get("Roll", 0.0)),
                    "Yaw":   float(e.get("Yaw", 0.0)),
                    "asset_path": path,
                    "asset_key": e.get("name") or path[(path.rfind("/") + 1):],
                    "ScaleX": sc, "ScaleY": sc, "ScaleZ": sc,
                })
                n_placed += 1
            if n_placed:
                print(f"  [fog] placed {n_placed} hand-authored mesh(es) from fog_placements.json")
    except Exception as exc:
        print(f"  [fog] fog_placements.json ignored: {exc}", file=sys.stderr)

    mesh_writer.close()
    imported_count = mesh_writer.count

    # --- Dealership vehicle spawn points -----------------------------------
    # Hand-authored in dealership_modifications.json (repo root). Each group's
    # entries are offset like static meshes (unless world_coords) and written
    # to dst["dealerships"], which convert2 injects as MTDealerVehicleSpawnPoint
    # actors. Groups/entries whose name starts with '_' are docs and ignored.
    dealerships = {}
    n_dealers = 0
    try:
        from mt_paths import DEALERSHIPS_JSON
        if os.path.exists(DEALERSHIPS_JSON):
            with open(DEALERSHIPS_JSON, "r", encoding="utf-8") as f:
                dsrc = json.load(f)
            for group_name, items in (dsrc.get("dealerships") or {}).items():
                if group_name.startswith("_") or not isinstance(items, list):
                    continue
                out_group = []
                for entry in items:
                    if not isinstance(entry, dict) or (entry and all(k.startswith("_") for k in entry)):
                        continue
                    if not entry.get("vehicle_path"):
                        print(f"  dealership in '{group_name}': entry missing vehicle_path — skipped")
                        continue
                    world = bool(entry.get("world_coords", False))
                    ox, oy, oz = (0, 0, 0) if world else (OFFSET_X, OFFSET_Y, OFFSET_Z)
                    op, orr, oyw = (0, 0, 0) if world else (OFFSET_PITCH, OFFSET_ROLL, OFFSET_YAW)
                    out_group.append({
                        "vehicle_path": entry["vehicle_path"],
                        "vehicle_key": entry.get("vehicle_key", ""),
                        "X": round(float(entry.get("X", 0)) + ox, 4),
                        "Y": round(float(entry.get("Y", 0)) + oy, 4),
                        "Z": round(float(entry.get("Z", 0)) + oz, 4),
                        "Pitch": round(float(entry.get("Pitch", 0)) + op, 4),
                        "Roll": round(float(entry.get("Roll", 0)) + orr, 4),
                        "Yaw": round(float(entry.get("Yaw", 0)) + oyw, 4),
                    })
                if out_group:
                    dealerships[group_name] = out_group
                    n_dealers += len(out_group)
    except Exception as e:
        print(f"  dealership_modifications.json parse error: {e} — no dealers injected")

    # Dealerships placed via "Dealership_<VehicleKey>" scene placeholders
    # (resolved + offset above) join the file-authored ones.
    if placed_dealers:
        dealerships["placed"] = placed_dealers
        n_dealers += len(placed_dealers)

    # Always clear and set — never append. The giant imported-mesh array is
    # NOT inlined here: it's streamed to JSONL sidecar shards (see
    # MAP_WORK_MESHES_DIR). We record a pointer + count instead so convert2
    # streams it back without ever loading map_work_changes.json's mesh data
    # into memory. Keeps this file small even for a 6M-entry export.
    dst["static_meshes"] = {
        "_imported_shards": {
            "dir": str(MAP_WORK_MESHES_DIR),
            "prefix": "mesh",
            "count": imported_count,
        }
    }
    # Bus stops, listed in bus_stops.json so they can be moved without an
    # editor round trip. Coordinates there are WORLD coordinates, copied from
    # the placed bridge tiles, so they go in verbatim.
    #
    # Both ways of "helping" here were wrong. Passing the tiles' editor Z of 815
    # straight through put the stops 222 m up (OFFSET_Z is -22180). Running the
    # full OFFSET_* over them instead moved them off the bridge, because only Z
    # differs between a tile's editor and world coords -- X and Y come through
    # unchanged. Reading the placed tiles and copying them ends the guessing.
    try:
        _bus = json.loads(pathlib.Path("bus_stops.json").read_text(encoding="utf-8"))
    except Exception as _e:
        _bus = None
        print(f"  busstop: bus_stops.json not read ({_e})")
    # Terminal every stop points at via AdditionalDestinations, so passengers
    # spawning out on the bridge have somewhere reachable to go.
    _link = (_bus or {}).get("link_terminal") or ""
    if _bus:
        _bp = _bus.get("bp_path")
        for st in _bus.get("stops") or []:
            w = st.get("world")
            if not (isinstance(w, (list, tuple)) and len(w) >= 3):
                print(f"  busstop: '{st.get('name')}' world must be [X, Y, Z] — skipped")
                continue
            parking.append({
                "X": round(float(w[0]), 4),
                "Y": round(float(w[1]), 4),
                "Z": round(float(w[2]), 4),
                "Pitch": 0.0, "Roll": 0.0,
                "Yaw": round(float(w[3]) if len(w) > 3 else 0.0, 4),
                "world_coords": True,
                "blueprint_path": _bp,
                "blueprint_class": _bp.rsplit("/", 1)[-1] + "_C",
                "asset_key": "BusStop",
                "actor_label": st.get("name") or "",
                "bus_link": _link,
            })
            print(f"  busstop: '{st.get('name')}' at world "
                  f"({w[0]:,.0f}, {w[1]:,.0f}, {w[2]:,.0f})")

    # Stations named by their mesh. Same actor as above, but the position and
    # the label both come from the mesh, so placing one in the editor is the
    # whole workflow -- no coordinates to copy out.
    _bp_default = (_bus or {}).get("bp_path") or "/Game/Objects/Mission/Bus/BusStop_01"
    for label, bx, by, bz, byaw in bus_stop_meshes:
        parking.append({
            "X": bx, "Y": by, "Z": bz,
            "Pitch": 0.0, "Roll": 0.0, "Yaw": byaw,
            "world_coords": True,
            "blueprint_path": _bp_default,
            "blueprint_class": _bp_default.rsplit("/", 1)[-1] + "_C",
            "asset_key": "BusStop",
            "actor_label": label,
            "bus_link": _link,
        })
        print(f"  busstop: '{label}' from mesh at world ({bx:,.0f}, {by:,.0f}, {bz:,.0f})")
    if bus_stop_meshes:
        print(f"  busstop: {len(bus_stop_meshes)} station(s) placed from "
              f"{BUS_STOP_MESH_PREFIX}* mesh names")

    # Zones, from zones.json. World coordinates; size comes from the brush
    # scale rather than from geometry, because the volume is a unit box.
    try:
        _zn = json.loads(pathlib.Path("zones.json").read_text(encoding="utf-8"))
    except Exception as _e:
        _zn = None
        print(f"  zone: zones.json not read ({_e})")
    for z in (_zn or {}).get("zones") or []:
        w = z.get("world")
        if not (isinstance(w, (list, tuple)) and len(w) >= 3):
            print(f"  zone: '{z.get('name')}' world must be [X, Y, Z] — skipped")
            continue
        sc = z.get("scale") or [1000, 1000, 500]
        parking.append({
            "X": float(w[0]), "Y": float(w[1]), "Z": float(w[2]),
            "Pitch": 0.0, "Roll": 0.0, "Yaw": 0.0,
            "world_coords": True,
            "ScaleX": float(sc[0]), "ScaleY": float(sc[1]), "ScaleZ": float(sc[2]),
            "blueprint_path": "/Script/MotorTown",
            "blueprint_class": "MTAreaVolume",
            "asset_key": "AreaVolume",
            "actor_label": z.get("name") or z.get("key") or "Zone",
            "zone_key": z.get("key") or z.get("name"),
        })
        print(f"  zone: '{z.get('name')}' key={z.get('key')} at "
              f"({w[0]:,.0f}, {w[1]:,.0f}, {w[2]:,.0f}) scale {sc}")

    dst.setdefault("blueprint_actors", {})[TARGET_GROUP] = parking
    dst["dealerships"] = dealerships
    # Preserve hand-authored comment entries (dicts whose keys all start
    # with '_') across import_meshes runs. Anyone editing the file by
    # hand to annotate a placement keeps those notes after the next pull.
    prior_comments = [
        x for x in (dst.get("delivery_points") or [])
        if isinstance(x, dict) and x and all(k.startswith("_") for k in x.keys())
    ]
    # Delivery points placed by explicit WORLD coordinates rather than by an
    # editor placeholder. A DP entry in delivery_points.json may carry
    # "world": [X, Y, Z] — useful for dropping one at a measured spot (a
    # bridge landing, a road junction) without an editor round trip. These
    # coords are FINAL: the import offset is not applied, because they were
    # read off the running game, not authored in editor space.
    placed_keys = {d.get("delivery_key") for d in delivery}
    for reg_key, reg in _BP_REGISTRY.items():
        if not reg_key.startswith("DeliveryPoint_"):
            continue
        dp_key = reg_key[len("DeliveryPoint_"):]
        w = reg.get("world")
        if not w or dp_key in placed_keys:
            continue
        if not (isinstance(w, (list, tuple)) and len(w) >= 3):
            print(f"  delivery: '{dp_key}' world must be [X, Y, Z] — skipped")
            continue
        delivery.append({
            "X": round(float(w[0]), 4), "Y": round(float(w[1]), 4),
            "Z": round(float(w[2]), 4),
            "Pitch": 0.0, "Roll": 0.0, "Yaw": float(w[3]) if len(w) > 3 else 0.0,
            "world_coords": True,
            "delivery_key": dp_key,
        })
        print(f"  delivery: '{dp_key}' placed at world ({w[0]:,.0f}, {w[1]:,.0f}, {w[2]:,.0f}) "
              f"— explicit coords, no placeholder needed")

    dst["delivery_points"] = prior_comments + delivery

    # Local fog volumes, authored as real LocalFogVolume actors in the editor
    # and exported to a sidecar by ue.py. MT's build has the engine class
    # (it is in the .usmap) but places none itself, so we rebuild each one
    # at inject time. Radius comes from the actor's scale.
    fog_path = STATIC_MESHES_DIR / "fog_volumes.json"
    fog = []
    if fog_path.is_file():
        try:
            fog = json.loads(fog_path.read_text(encoding="utf-8")) or []
        except Exception as e:
            print(f"  fog: {fog_path} unreadable ({e}) — no fog volumes injected",
                  file=sys.stderr)
    for f_ in fog:
        world = bool(f_.get("world_coords", False))
        fx, fy, fz = (0, 0, 0) if world else (OFFSET_X, OFFSET_Y, OFFSET_Z)
        f_["X"] = round(float(f_.get("X", 0)) + fx, 4)
        f_["Y"] = round(float(f_.get("Y", 0)) + fy, 4)
        f_["Z"] = round(float(f_.get("Z", 0)) + fz, 4)
    dst["fog_volumes"] = fog
    if fog:
        print(f"  fog: {len(fog)} local fog volume(s) from the editor")

    # A configured DP that never got placed is a silent loss: no actor, no
    # marker, and nothing in the log to say so. Happens when the shard export
    # under static_meshes_parts/ is older than delivery_points.json — the
    # placeholder simply isn't in the stream yet. Name the missing ones.
    configured = {k[len("DeliveryPoint_"):] for k in _BP_REGISTRY
                  if k.startswith("DeliveryPoint_")}
    unplaced = sorted(configured - {d.get("delivery_key") for d in delivery})
    if unplaced:
        print(f"  WARNING: {len(unplaced)} configured delivery point(s) had no "
              f"placeholder in the export and were NOT placed: {', '.join(unplaced)}",
              file=sys.stderr)
        print(f"           Re-export the scene from the editor, or give them "
              f"\"world\": [X, Y, Z] in delivery_points.json.", file=sys.stderr)

    with open(dst_path, "w", encoding="utf-8") as f:
        json.dump(dst, f, indent=4, ensure_ascii=False)

    print(f"Imported {imported_count} meshes (streamed to {MAP_WORK_MESHES_DIR}) + {len(parking)} parking lots + {len(delivery)} delivery points + {n_dealers} dealers, skipped {skipped}")
    if _DEP_COPIED:
        print(f"Pulled {len(_DEP_COPIED)} custom material/dependency asset(s) from cooked output")
    if _COPY_STATS["updated"] or _COPY_STATS["same"]:
        print(f"Cooked->mod: {_COPY_STATS['updated']} file(s) updated, "
              f"{_COPY_STATS['same']} already identical (sha256)")
    print(f"Offsets: X={OFFSET_X}, Y={OFFSET_Y}, Z={OFFSET_Z}")
    print(f"Target: {TARGET_GROUP} (cleared and set)")

    # Loud summary for custom meshes that WON'T be in the pak. A placed
    # StaticMeshActor whose mesh is missing references null at load and
    # the game access-violation-crashes when that area streams in — so
    # this must be impossible to miss in the build log.
    if _unset_assets:
        bar = "!" * 64
        print(bar)
        print(f"WARNING: {len(_unset_assets)} custom mesh(es) NOT shipped — MTMI_COOKED_CONTENT is not set.")
        print("These StaticMeshActors will reference a null mesh and can CRASH the")
        print("game (EXCEPTION_ACCESS_VIOLATION) when their area streams in. Set")
        print("MTMI_COOKED_CONTENT in .env to your UE editor's cooked Content folder.")
        for p in _unset_assets[:10]:
            print(f"  - {p}")
        if len(_unset_assets) > 10:
            print(f"  ... and {len(_unset_assets) - 10} more")
        print(bar)
    if _missing_assets:
        bar = "!" * 64
        print(bar)
        print(f"WARNING: {len(_missing_assets)} custom mesh(es) NOT found in game OR cooked output.")
        print("They won't be in the pak; their actors will reference null and may")
        print("crash on stream-in. Re-cook them in the UE editor, or remove them")
        print("from the scene before exporting.")
        for p in _missing_assets[:10]:
            print(f"  - {p}")
        if len(_missing_assets) > 10:
            print(f"  ... and {len(_missing_assets) - 10} more")
        print(bar)


if __name__ == "__main__":
    main()
