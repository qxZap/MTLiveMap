"""
Centralized path resolution for the MTMapInjector pipeline.

Configuration sources, in priority order (first hit wins):
  1. Process environment variables (highest — useful for one-off overrides
     when invoking a single script standalone).
  2. A `.env` file at the repo root (one KEY=VALUE per line, '#' comments,
     value may be quoted). This is the recommended place to set paths.
  3. Auto-detection: MT_GAME_DIR is probed against the usual Steam install
     locations if neither env nor .env provides it.

Required keys (after auto-detect runs):

  MT_GAME_DIR           Game install directory — the folder Steam writes
                        when you "Browse local files" on Motor Town.
                        Must contain MotorTown/Content/Paks/MotorTown.pak.
                        Used to find both the game's .pak (source for the
                        bootstrap extractor) and the deploy target.

  MTMI_MAPPINGS         Path to the .usmap mappings file matching the
                        installed Motor Town version (e.g.
                        MotorTown718P1.usmap). Generated with
                        UnrealMappingsDumper / Dumper-7.

  MTMI_MAPPINGS_TAG     Engine tag UAssetGUI uses with --tojson/--fromjson
                        (e.g. 'MotorTown718P1'). Defaults to the .usmap
                        filename without extension.

Optional keys:

  MTMI_GAME_CONTENT     Override the extracted-content folder. Defaults to
                        the repo's `vanilla_extract/MotorTown/Content`,
                        which `bootstrap_extract.py` populates from the
                        game's .pak. Set this only if you already have
                        the content extracted elsewhere (e.g. FModel).

  MTMI_REPO_ROOT        Repo checkout directory. Used by `ue.py` inside
                        the UE editor. Auto-resolves to this file's
                        parent if unset.

  MTMI_COOKED_CONTENT   Optional UE editor cooked-output folder for mod
                        authors iterating on meshes in-editor.

If a required path is missing or doesn't resolve to an existing file/dir,
mt_paths writes a multi-line diagnostic to stderr explaining what each
variable is, what shape it should have, and how to obtain the underlying
content, then exits with code 2.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
ENV_FILE  = REPO_ROOT / ".env"


def _load_dotenv(path: Path) -> dict[str, str]:
    """Minimal .env reader — no python-dotenv dependency. KEY=VALUE per
    line, '#' starts a comment (full-line or trailing), value may be
    wrapped in single or double quotes (stripped). Blank lines ignored."""
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            # Strip trailing inline comment (only when value isn't quoted).
            if val and val[0] not in ("'", '"') and "#" in val:
                val = val.split("#", 1)[0].rstrip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                val = val[1:-1]
            if key:
                out[key] = val
    except Exception as e:
        sys.stderr.write(f"[mt_paths] warning: .env read error at {path}: {e}\n")
    return out


_DOTENV = _load_dotenv(ENV_FILE)


def _cfg(name: str, default: str = "") -> str:
    """Process env beats .env. Whitespace and outer quotes trimmed."""
    v = os.environ.get(name, "").strip().strip('"').strip("'")
    if v:
        return v
    v = _DOTENV.get(name, "").strip().strip('"').strip("'")
    return v or default


def _autodetect_game_dir() -> str:
    """Probe well-known Steam install locations. Returns the first match
    that contains MotorTown/Content/Paks/MotorTown.pak; empty string
    if none found. Drive-letter list covers C:..Z: so a non-default
    Steam library on any drive gets picked up."""
    rel = Path("steamapps/common/Motor Town/MotorTown/Content/Paks/MotorTown-Windows.pak")
    rel_alt = Path("steamapps/common/Motor Town/MotorTown/Content/Paks/MotorTown.pak")
    bases = []
    for d in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        bases.append(Path(f"{d}:/SteamLibrary"))
        bases.append(Path(f"{d}:/Steam"))
        bases.append(Path(f"{d}:/Program Files/Steam"))
        bases.append(Path(f"{d}:/Program Files (x86)/Steam"))
    for base in bases:
        for marker in (rel, rel_alt):
            if (base / marker).is_file():
                return str(base / "steamapps/common/Motor Town")
    return ""


def _bundled_mapping() -> str:
    """First .usmap shipped in the repo's mappings/ folder, if any. Lets a
    fresh clone work with zero config — UAssetAPI uses this unless the user
    overrides MTMI_MAPPINGS."""
    mdir = REPO_ROOT / "mappings"
    if mdir.is_dir():
        for f in sorted(mdir.glob("*.usmap")):
            return str(f)
    return ""


MT_GAME_DIR_RAW = _cfg("MT_GAME_DIR") or _autodetect_game_dir()
_MAPPINGS_RAW   = _cfg("MTMI_MAPPINGS") or _bundled_mapping()
_MAPPINGS_TAG_RAW = _cfg("MTMI_MAPPINGS_TAG") or (
    Path(_MAPPINGS_RAW).stem if _MAPPINGS_RAW else ""
)
_GAME_CONTENT_RAW = _cfg("MTMI_GAME_CONTENT") or str(
    REPO_ROOT / "vanilla_extract" / "MotorTown" / "Content"
)
_REPO_ROOT_RAW    = _cfg("MTMI_REPO_ROOT") or str(REPO_ROOT)
_COOKED_RAW       = _cfg("MTMI_COOKED_CONTENT")  # optional, no default


# Validation: only require what every script needs.
#   - MT_GAME_DIR is needed for deploy (Paks folder) AND for bootstrap
#     extraction. mt_paths reports it missing so the user fixes the .env
#     once; downstream scripts get a usable GAME_PAKDIR derived from it.
#   - MTMI_MAPPINGS is required for any UAssetAPI parse.
#   - MTMI_GAME_CONTENT is NOT validated here — bootstrap_extract.py
#     creates it on demand. Scripts that need a specific subpath inside
#     it (e.g. VANILLA_CARGOS_01) will fail at use time if the bootstrap
#     hasn't run; that's a clearer error than mt_paths refusing to import.
def _die(missing: list[tuple[str, str, str]]) -> None:
    bar = "=" * 72
    sys.stderr.write(f"\n{bar}\n")
    sys.stderr.write("MTMapInjector pipeline cannot start — configuration is missing.\n")
    sys.stderr.write(f"{bar}\n\n")
    for var, reason, hint in missing:
        sys.stderr.write(f"  [{var}]\n")
        sys.stderr.write(f"    Problem : {reason}\n")
        sys.stderr.write(f"    Source  : {hint}\n\n")
    sys.stderr.write(
        f"Configuration is read in this order:\n"
        f"  1. process environment\n"
        f"  2. {ENV_FILE}  (recommended — copy .env.example and edit)\n"
        f"  3. auto-detection (only for MT_GAME_DIR)\n\n"
        f"See README.md for the full setup.\n"
    )
    sys.stderr.write(f"{bar}\n")
    sys.exit(2)


_missing: list[tuple[str, str, str]] = []

if not MT_GAME_DIR_RAW:
    _missing.append((
        "MT_GAME_DIR",
        "not set and auto-detection found no MotorTown install on any drive C:-Z:",
        "Set it in .env to your game folder. Steam: right-click Motor Town -> Manage -> Browse local files, then copy the path one level above MotorTown/ (the folder that contains MotorTown/Content/Paks/MotorTown.pak).",
    ))
else:
    p = Path(MT_GAME_DIR_RAW)
    pak_a = p / "MotorTown/Content/Paks/MotorTown.pak"
    pak_b = p / "MotorTown/Content/Paks/MotorTown-Windows.pak"
    if not (pak_a.is_file() or pak_b.is_file()):
        _missing.append((
            "MT_GAME_DIR",
            f"path '{MT_GAME_DIR_RAW}' exists but doesn't contain MotorTown/Content/Paks/MotorTown.pak (or MotorTown-Windows.pak)",
            "Should be the folder Steam shows when you Browse local files — one level above the MotorTown subfolder.",
        ))

if not _MAPPINGS_RAW:
    _missing.append((
        "MTMI_MAPPINGS",
        "not set",
        "Path to the .usmap mappings file matching your Motor Town version. Generated with UnrealMappingsDumper or Dumper-7. Set it in .env.",
    ))
elif not Path(_MAPPINGS_RAW).is_file():
    _missing.append((
        "MTMI_MAPPINGS",
        f"path '{_MAPPINGS_RAW}' does not exist or is not a file",
        "Should point at a .usmap file (e.g. MotorTown718P1.usmap).",
    ))

if _missing:
    _die(_missing)


# Final canonical values exposed to importers.
MT_GAME_DIR: Path  = Path(MT_GAME_DIR_RAW)
GAME_PAKDIR: Path  = MT_GAME_DIR / "MotorTown" / "Content" / "Paks"
MAPPINGS: Path     = Path(_MAPPINGS_RAW)
MAPPINGS_TAG: str  = _MAPPINGS_TAG_RAW
GAME_CONTENT: Path = Path(_GAME_CONTENT_RAW)
REPO_ROOT_P: Path  = Path(_REPO_ROOT_RAW)
COOKED_CONTENT: str = _COOKED_RAW  # may be empty; consumer checks

# Convenience derived paths used across scripts. These live INSIDE
# GAME_CONTENT (which defaults to vanilla_extract/) so a fresh clone
# after running bootstrap_extract.py has every file the pipeline needs.
JEJU_MAIN: Path         = GAME_CONTENT / "Maps" / "Jeju" / "Jeju_World.umap"
CELLS_DIR: Path         = GAME_CONTENT / "Maps" / "Jeju" / "Jeju_World" / "_Generated_"
VANILLA_CARGOS: Path    = GAME_CONTENT / "DataAsset" / "Cargos.uasset"
VANILLA_CARGOS_01: Path = GAME_CONTENT / "DataAsset" / "Cargos_01.uasset"

# Scratch / intermediate working directory. Every pipeline artifact that
# is regenerated each run (the cached vanilla map JSON, the patched map
# JSON, the import_meshes output) lives here instead of cluttering the
# repo. Defaults to a per-OS temp folder; override with MTMI_WORK_DIR.
# Created on import so any importer can write into it immediately.
_WORK_RAW = _cfg("MTMI_WORK_DIR") or str(Path(tempfile.gettempdir()) / "MTMapInjector")
WORK_DIR: Path = Path(_WORK_RAW)
try:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
except Exception as _e:  # pragma: no cover
    sys.stderr.write(f"[mt_paths] warning: could not create WORK_DIR {WORK_DIR}: {_e}\n")

# Canonical intermediate-file paths (all inside WORK_DIR). Scripts and
# build.bat reference these so there's one source of truth.
CACHE_MAP_JSON: Path = WORK_DIR / "Jeju_World_vanilla.json"   # cached vanilla persistent map
PATCHED_MAP_JSON: Path = WORK_DIR / "Jeju_World_patched.json" # convert2 output -> UAssetGUI input
MAP_WORK_JSON: Path  = WORK_DIR / "map_work_changes.json"     # import_meshes output (small)

# Sidecar shard dir for the GIANT static_meshes.imported array. import_meshes
# streams every imported mesh/foliage entry here as JSONL shards (see
# mesh_shards.py) instead of inlining millions of entries into the small
# map_work_changes.json above; convert2 streams them back in. Bounded memory.
MAP_WORK_MESHES_DIR: Path = WORK_DIR / "map_work_meshes"

# Persistent user inputs that stay in the repo root.
STATIC_MESHES_JSON: Path = REPO_ROOT / "static_meshes.json"   # editor export (ue.py), legacy single file
# Sharded editor export (ue.py): a directory of JSONL shards. Preferred over
# the single file — ue.py writes here so a multi-GB export never has to be
# loaded whole. import_meshes reads this if present, else falls back to (and
# auto-splits) STATIC_MESHES_JSON.
STATIC_MESHES_DIR: Path  = REPO_ROOT / "static_meshes_parts"
DEALERSHIPS_JSON: Path   = REPO_ROOT / "dealership_modifications.json"  # hand-authored dealer spawns

# World-placement offset applied by import_meshes.py to every editor-
# exported mesh/actor (your custom build is authored in one spot in the
# editor and shifted into a chosen region of Jeju). Override per-map in
# .env. Defaults match the current "new map" placement.
def _cfgf(name: str, default: float) -> float:
    raw = _cfg(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        sys.stderr.write(f"[mt_paths] warning: {name}='{raw}' is not a number; using {default}\n")
        return default

IMPORT_OFFSET_X: float = _cfgf("MTMI_OFFSET_X", -512003.0)
IMPORT_OFFSET_Y: float = _cfgf("MTMI_OFFSET_Y",  123148.0)
IMPORT_OFFSET_Z: float = _cfgf("MTMI_OFFSET_Z",  -22180.0)
IMPORT_OFFSET_PITCH: float = _cfgf("MTMI_OFFSET_PITCH", 0.0)
IMPORT_OFFSET_ROLL:  float = _cfgf("MTMI_OFFSET_ROLL",  0.0)
IMPORT_OFFSET_YAW:   float = _cfgf("MTMI_OFFSET_YAW",   0.0)

# Vendored third-party tools live in <repo>/tools/ so a fresh clone has
# everything except Python + .NET + a .usmap. repak.exe sits next to
# oo2core_9_win64.dll there so its Oodle decompression works without the
# user copying the dll anywhere. UAssetGUI.exe is the umap<->json tool.
TOOLS_DIR: Path = REPO_ROOT / "tools"
REPAK: Path     = TOOLS_DIR / "repak.exe"
UASSETGUI: Path = TOOLS_DIR / "UAssetGUI.exe"

# Motor Town pak AES decryption key. Public (shipped in the qxZap/
# ZMTLoader repo); needed for repak to read the encrypted game pak.
# A .env value (MT_AES_KEY) overrides this default.
MT_AES_KEY: str = _cfg(
    "MT_AES_KEY",
    "0xD9633F9140D5494AE4A469BDA384896BD1B9644D50D281E64ECFF4900B8E8E80",
)

# ---------------------------------------------------------------------------
# Mod identity. ONE value, set in .env, that everything else derives from:
# the staging folder, the deployed pak's filename, and the name players see
# in their Paks/ folder. Porting a different world means changing this and
# renaming the staging folder to match — no Python edits, no find-and-replace.
#
# The name never appears inside the pak (asset paths are MotorTown/Content/...),
# so changing it is safe for the content: only the folder and filename move.
# ---------------------------------------------------------------------------
_EXCLUDE_PAKS = [x.strip().lower() for x in _cfg("MTMI_EXCLUDE_PAKS").split(",") if x.strip()]
MOD_NAME: str = _cfg("MTMI_MOD_NAME", "MapChangeTest_P")

# Unreal mounts a pak as a PATCH -- able to override base game files -- only
# when the filename ends in "_P". Without it our Jeju_World.umap loses to the
# game's own and the entire world silently disappears, while every build step
# and every integrity check still passes. Learned by renaming the mod to
# "Dobrogea" (no suffix) and watching the island vanish.
if not MOD_NAME.endswith("_P"):
    sys.stderr.write(
        f"[mt_paths] WARNING: MTMI_MOD_NAME='{MOD_NAME}' does not end in '_P'.\n"
        f"           Unreal will mount zzzz_{MOD_NAME}.pak as a base pak rather\n"
        f"           than a patch, so it cannot override the game's map and your\n"
        f"           world will not appear -- silently, with every check passing.\n"
        f"           Rename it to '{MOD_NAME}_P'.\n")

# Staging folder for everything we ship, relative to the repo root.
MOD_ROOT: Path = REPO_ROOT / MOD_NAME
MOD_CONTENT_ROOT: Path = MOD_ROOT / "MotorTown" / "Content"

# Our deployed pak's filename (modp.bat prefixes the mod folder with
# "zzzz_" so it wins load order). Never a source for effective_asset —
# it IS our output.
DEPLOY_PAK_NAME: str = f"zzzz_{MOD_NAME}.pak"


def effective_pak_entries(entry: str) -> list[tuple[str, Path]]:
    """Every installed pak that ships `entry`, in load order, extracted.

    `entry` is a full pak-relative path (e.g. "MotorTown/Config/UserEngine.ini")
    — unlike effective_asset this is not limited to Content/, because the
    files that matter here (config) live outside it.

    Returns [(pak name, extracted path), ...] with the LAST element being the
    one the game currently loads. Callers that need to merge rather than
    replace want the whole list, not just the winner: our pak loads last, so
    shipping a bare copy of a config file silently discards every other mod's
    entries in it.
    """
    out: list[tuple[str, Path]] = []
    if not (GAME_PAKDIR.is_dir() and REPAK.is_file()):
        return out
    entry = entry.replace("\\", "/")
    dst_dir = WORK_DIR / "mod_base" / "_paks"
    dst_dir.mkdir(parents=True, exist_ok=True)
    for pak in sorted(GAME_PAKDIR.glob("*.pak"), key=lambda p: p.name.lower()):
        if pak.name.lower() == DEPLOY_PAK_NAME.lower():
            continue          # our own output is never a source
        args = [str(REPAK)]
        if pak.name.lower() == "motortown-windows.pak":
            args += ["--aes-key", MT_AES_KEY]
        r = subprocess.run(args + ["list", str(pak)], capture_output=True, text=True)
        if r.returncode != 0:
            continue
        if not any(ln.strip().replace("\\", "/") == entry for ln in r.stdout.splitlines()):
            continue
        dst = dst_dir / f"{pak.stem}__{Path(entry).name}"
        with open(dst, "wb") as fh:
            subprocess.run(args + ["get", str(pak), entry],
                           stdout=fh, stderr=subprocess.DEVNULL)
        if dst.exists() and dst.stat().st_size > 0:
            out.append((pak.name, dst))
    return out


def remap_asset_path(asset_path: str) -> str:
    """Rewrite a /Game asset path using MTMI_MESH_REMAP ("from=to,from=to").

    Lets a whole mesh set be swapped without repainting the level — e.g.
    seasonal trees, where DC/Meshes/Nature holds the winter versions of the
    same names in DC/Meshes/NatureGreen.

    Falls back to the original path whenever the remapped asset doesn't
    actually exist, so a partially populated target folder is safe: the
    merged grass clumps have no winter counterpart and must keep pointing
    at the green ones rather than vanish.
    """
    rules = _cfg("MTMI_MESH_REMAP", "")
    if not rules or not asset_path:
        return asset_path
    out = asset_path
    for rule in rules.split(","):
        if "=" not in rule:
            continue
        src, dst = (x.strip() for x in rule.split("=", 1))
        if src and src in out:
            out = out.replace(src, dst)
    if out == asset_path:
        return asset_path
    # /Game/A/B.B -> A/B
    rel = out.split(".", 1)[0]
    rel = rel[len("/Game/"):] if rel.startswith("/Game/") else rel
    for root in (COOKED_CONTENT, str(GAME_CONTENT)):
        if root and Path(root, rel + ".uasset").is_file():
            return out
    return asset_path


def effective_asset(rel: str) -> Path:
    """Return the copy of a cooked asset the GAME actually loads.

    `rel` is a path under MotorTown/Content (e.g.
    "DataAsset/Cargos_01.uasset"). If any installed mod pak ships that
    asset, the last one in UE's load order wins — and that, not the
    vanilla file, is what we must use as the base we mutate. Otherwise
    our late-loading pak would silently revert an economy/cargo mod's
    changes to the same asset.

    Returns a path to the extracted override in WORK_DIR/mod_base/, or
    GAME_CONTENT/rel when no mod overrides it. Sidecars (.uexp/.ubulk)
    are pulled alongside, since UAssetAPI needs them.

    ponytail: load order approximated as a case-insensitive filename
    sort, which is what UE does for loose `_P` paks in Paks/. If MT ever
    grows real chunk/priority ordering, read it from the pak headers.
    """
    vanilla = GAME_CONTENT / rel
    # Building something to SHIP to other people: base it on vanilla, never on
    # whatever mods happen to be installed here. Layering on an installed mod is
    # right for our own island pak, which must not revert someone's economy
    # changes -- but a standalone mod built that way would carry a stranger's
    # edits into everybody's game.
    if _cfg("MTMI_VANILLA_BASE") == "1":
        return vanilla
    if not GAME_PAKDIR.is_dir() or not REPAK.is_file():
        return vanilla

    # Build against ONE named pak instead of whatever wins the local load
    # order. Shipping a compatibility variant means saying exactly which mod it
    # layers on, and load order is the wrong way to say it: it depends on what
    # happens to be installed on this machine, our own island pak included.
    only = _cfg("MTMI_BASE_PAK")
    if only:
        for pak in sorted(GAME_PAKDIR.glob("*.pak"), key=lambda q: q.name.lower()):
            if only.lower() not in pak.name.lower():
                continue
            entry_ = f"MotorTown/Content/{rel}".replace("\\", "/")
            r = subprocess.run([str(REPAK), "list", str(pak)],
                               capture_output=True, text=True)
            if r.returncode != 0 or not any(ln.strip() == entry_ for ln in r.stdout.splitlines()):
                return vanilla          # that pak does not touch this asset
            dst_dir = WORK_DIR / "mod_base" / Path(rel).parent
            dst_dir.mkdir(parents=True, exist_ok=True)
            stem_ = entry_.rsplit(".", 1)[0]
            for e in (ln.strip() for ln in r.stdout.splitlines()):
                if e.rsplit(".", 1)[0] != stem_:
                    continue
                with open(dst_dir / Path(e).name, "wb") as fh:
                    subprocess.run([str(REPAK), "get", str(pak), e],
                                   stdout=fh, stderr=subprocess.DEVNULL)
            sys.stderr.write("[mt_paths] " + rel + ": based on " + pak.name + chr(10))
            return dst_dir / Path(rel).name
        sys.stderr.write("[mt_paths] MTMI_BASE_PAK=" + only + " matched no pak - using vanilla" + chr(10))
        return vanilla

    entry = f"MotorTown/Content/{rel}".replace("\\", "/")
    stem = entry.rsplit(".", 1)[0]
    winner: Path | None = None
    for pak in sorted(GAME_PAKDIR.glob("*.pak"), key=lambda p: p.name.lower()):
        if pak.name.lower() in ("motortown-windows.pak", DEPLOY_PAK_NAME.lower()):
            continue
        # Paks we ship OURSELVES are not a base to build on. The island
        # loads last and ships whole vehicle tables, so without this it
        # quietly absorbs its own sibling mods -- build once with the
        # tanker mod installed and the island starts carrying tanker rows
        # it should have nothing to do with, with no sign of it until
        # someone diffs the tables.
        if any(x in pak.name.lower() for x in _EXCLUDE_PAKS):
            continue
        r = subprocess.run([str(REPAK), "list", str(pak)],
                           capture_output=True, text=True)
        if r.returncode == 0 and any(ln.strip() == entry for ln in r.stdout.splitlines()):
            winner = pak

    if winner is None:
        return vanilla

    dst_dir = WORK_DIR / "mod_base" / Path(rel).parent
    dst_dir.mkdir(parents=True, exist_ok=True)
    listing = subprocess.run([str(REPAK), "list", str(winner)],
                             capture_output=True, text=True).stdout.splitlines()
    for e in (ln.strip() for ln in listing):
        if e.rsplit(".", 1)[0] != stem:
            continue
        out = dst_dir / Path(e).name
        with open(out, "wb") as fh:
            subprocess.run([str(REPAK), "get", str(winner), e],
                           stdout=fh, stderr=subprocess.DEVNULL)
    sys.stderr.write(f"[mt_paths] {rel}: using mod override from {winner.name}\n")
    return dst_dir / Path(rel).name


if __name__ == "__main__":
    # `python mt_paths.py [DataAsset/Cargos_01.uasset]` — show which copy of
    # an asset the pipeline will build on (vanilla vs an installed mod's).
    rel = sys.argv[1] if len(sys.argv) > 1 else "DataAsset/Cargos_01.uasset"
    p = effective_asset(rel)
    assert p.is_file(), f"effective_asset({rel}) -> missing file {p}"
    print(f"{rel} -> {p}  ({p.stat().st_size} bytes)")
