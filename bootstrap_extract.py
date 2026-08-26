#!/usr/bin/env python3
"""
bootstrap_extract.py — populate `vanilla_extract/MotorTown/Content` with
just the vanilla files the rest of the pipeline reads, straight from the
game's own .pak. No external extraction tool, no pre-extracted tree.

Two source modes:

  MODE REPAK  (default — self-contained)
    Uses the vendored tools/repak.exe + the Motor Town pak AES key
    (mt_paths.MT_AES_KEY, overridable via MT_AES_KEY in .env) to extract
    directly from the game's encrypted MotorTown-Windows.pak. Nothing to
    install — the only requirement is that the game is installed.

  MODE FMODEL  (opt-in — for users who already have an FModel export)
    Set MT_FMODEL_EXPORT in .env to the folder FModel extracts into
    (e.g. 'D:/FModel/Output/Exports/MotorTown/Content'). This script
    then copies the curated subset from there instead of touching the
    game pak. Useful if you've already extracted and don't want to
    re-read the 3GB pak.

Per-feature bundles make it cheap to refresh just the slice you touched:

  python bootstrap_extract.py            # default bundles
  python bootstrap_extract.py cargos     # just the cargo data
  python bootstrap_extract.py cargos delivery_cdos
"""
from __future__ import annotations

import argparse
import os
import json
import shutil
import subprocess
import sys
from pathlib import Path

# Import after defining REPO_ROOT so mt_paths can read the same .env.
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))
from mt_paths import _DOTENV, MT_GAME_DIR, GAME_CONTENT, REPAK, MT_AES_KEY  # noqa: E402


# Per-feature bundles. Each is a list of glob patterns RELATIVE to
# MotorTown/Content/.
#
# Each bundle carries two views of the same files:
#   globs    — Path.glob() patterns for FModel mode (copy-from-tree).
#   includes — paths passed to `repak unpack --include`. repak accepts
#              both a specific file (Cargos.uasset) and a directory
#              prefix (DeliveryPoint), and extracts directories
#              recursively (pulling the .uexp/.ubulk siblings for free).
#
# _Generated_ cells are the largest contributor by far, so they get
# their own bundles a user can skip when they only want the cargo system.
BUNDLES: dict[str, dict[str, list[str]]] = {
    "cargos": {
        "globs": [
            "DataAsset/Cargos.uasset", "DataAsset/Cargos.uexp",
            "DataAsset/Cargos_01.uasset", "DataAsset/Cargos_01.uexp",
            "DataAsset/Cargos_Deprecated.uasset", "DataAsset/Cargos_Deprecated.uexp",
            "DataAsset/StringTables/Cargo.uasset",
            "DataAsset/StringTables/Cargo.uexp",
        ],
        "includes": [
            "DataAsset/Cargos.uasset", "DataAsset/Cargos.uexp",
            "DataAsset/Cargos_01.uasset", "DataAsset/Cargos_01.uexp",
            "DataAsset/Cargos_Deprecated.uasset", "DataAsset/Cargos_Deprecated.uexp",
            "DataAsset/StringTables/Cargo.uasset",
            "DataAsset/StringTables/Cargo.uexp",
        ],
    },
    "delivery_cdos": {
        "globs": [
            "Objects/Mission/Delivery/DeliveryPoint/*.uasset",
            "Objects/Mission/Delivery/DeliveryPoint/*.uexp",
        ],
        "includes": ["Objects/Mission/Delivery/DeliveryPoint"],
    },
    "map_persistent": {
        "globs": ["Maps/Jeju/Jeju_World.umap", "Maps/Jeju/Jeju_World.uexp"],
        "includes": ["Maps/Jeju/Jeju_World.umap", "Maps/Jeju/Jeju_World.uexp"],
    },
    # Just the hand-picked vanilla WP cell clone_bp_actors uses as a
    # template for newly-registered mod cells.
    "map_cells": {
        "globs": [
            "Maps/Jeju/Jeju_World/_Generated_/0V18V8JBXKXUL8YILWZKCSMB4.umap",
            "Maps/Jeju/Jeju_World/_Generated_/0V18V8JBXKXUL8YILWZKCSMB4.uexp",
        ],
        "includes": [
            "Maps/Jeju/Jeju_World/_Generated_/0V18V8JBXKXUL8YILWZKCSMB4.umap",
            "Maps/Jeju/Jeju_World/_Generated_/0V18V8JBXKXUL8YILWZKCSMB4.uexp",
        ],
    },
    # The complete WP cell tree (~12k files, ~2.7GB). Fetched lazily by
    # clone_bp_actors on the first run that needs a cell beyond the
    # template, so most users never pull this explicitly.
    "map_cells_all": {
        "globs": [
            "Maps/Jeju/Jeju_World/_Generated_/*.umap",
            "Maps/Jeju/Jeju_World/_Generated_/*.uexp",
        ],
        "includes": ["Maps/Jeju/Jeju_World/_Generated_"],
    },
}

# Default set when invoked without args. Excludes map_cells_all because
# the single preferred template in map_cells is enough for every flow
# we've validated so far; users who hit a missing-cell warning can run
# `python bootstrap_extract.py map_cells_all` to pull the rest.
DEFAULT_BUNDLES = ["cargos", "delivery_cdos", "map_persistent", "map_cells"]
ALL_BUNDLES = list(BUNDLES.keys())
DEST_ROOT = GAME_CONTENT  # vanilla_extract/MotorTown/Content by default

# Extraction state lives at the root of vanilla_extract/. Records the
# game-pak fingerprint each bundle was extracted at, so a game update is
# detected (fingerprint changes) and only stale bundles get re-pulled.
VANILLA_ROOT = DEST_ROOT.parent.parent          # …/vanilla_extract
STATE_FILE   = VANILLA_ROOT / ".bootstrap_state.json"


def _resolve_bundles(requested: list[str]) -> list[str]:
    if not requested:
        return DEFAULT_BUNDLES
    bad = [b for b in requested if b not in BUNDLES]
    if bad:
        sys.stderr.write(f"[bootstrap] unknown bundle(s): {bad}\n")
        sys.stderr.write(f"  known: {ALL_BUNDLES}\n")
        sys.exit(2)
    return requested


def _cfg(name: str) -> str:
    v = os.environ.get(name, "").strip().strip('"').strip("'")
    if v:
        return v
    return _DOTENV.get(name, "").strip().strip('"').strip("'")


# ---------------------------------------------------------------------------
# Game-pak fingerprint + extraction state (delta caching)
# ---------------------------------------------------------------------------
def _find_pak() -> Path | None:
    a = MT_GAME_DIR / "MotorTown" / "Content" / "Paks" / "MotorTown-Windows.pak"
    b = MT_GAME_DIR / "MotorTown" / "Content" / "Paks" / "MotorTown.pak"
    return a if a.is_file() else b if b.is_file() else None


def pak_fingerprint(pak: Path | None = None) -> str:
    """Cheap, content-sensitive fingerprint of the game pak: SHA1 over the
    total size + the first and last 8 MB. A game update rewrites the pak
    (new index, shifted offsets), so this changes whenever the content
    does — without hashing the full 3 GB on every run (~milliseconds)."""
    import hashlib, struct
    if pak is None:
        pak = _find_pak()
    if pak is None or not pak.is_file():
        return ""
    size = pak.stat().st_size
    chunk = 8 * 1024 * 1024
    h = hashlib.sha1()
    h.update(struct.pack("<Q", size))
    with open(pak, "rb") as f:
        h.update(f.read(chunk))
        if size > chunk:
            f.seek(max(0, size - chunk))
            h.update(f.read(chunk))
    return "sha1:" + h.hexdigest()


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        sys.stderr.write(f"[bootstrap] warning: could not write state: {e}\n")


def _bundle_present(bundle: str) -> bool:
    """True if a bundle's files already exist under DEST_ROOT. Used to
    back-fill state for content extracted before fingerprinting existed,
    so an existing install doesn't eat a redundant re-pull on first run."""
    for inc in BUNDLES[bundle]["includes"]:
        p = DEST_ROOT / inc
        if p.is_file():
            return True
        if p.is_dir() and any(p.iterdir()):
            return True
    return False


def stale_bundles(bundles: list[str], fp: str | None = None) -> list[str]:
    """Return the subset of `bundles` whose recorded extraction fingerprint
    doesn't match the current game pak (or that were never extracted).
    Used for delta caching: only re-extract what actually changed.

    Back-fill: if a bundle has no record but the GLOBAL pak fingerprint in
    state matches the current pak AND the bundle's files are already on
    disk, it was extracted from this same pak before fingerprinting was
    added — record it as current instead of forcing a re-pull."""
    if fp is None:
        fp = pak_fingerprint()
    if not fp:
        return list(bundles)
    state = _load_state()
    rec = state.get("bundles", {})
    global_fp = state.get("pak_fingerprint")
    backfilled = False
    out = []
    for b in bundles:
        if rec.get(b) == fp:
            continue
        if b not in rec and global_fp == fp and _bundle_present(b):
            rec[b] = fp
            backfilled = True
            continue
        out.append(b)
    if backfilled:
        state["bundles"] = rec
        state.setdefault("pak_fingerprint", fp)
        _save_state(state)
    return out


# ---------------------------------------------------------------------------
# FModel mode: copy from an already-extracted tree
# ---------------------------------------------------------------------------
def _do_fmodel(src_root: Path, bundles: list[str]) -> int:
    if not src_root.is_dir():
        sys.stderr.write(f"[bootstrap] MT_FMODEL_EXPORT '{src_root}' is not a directory\n")
        return 2
    copied = 0
    skipped = 0
    for bundle in bundles:
        for pattern in BUNDLES[bundle]["globs"]:
            for src in src_root.glob(pattern):
                if not src.is_file():
                    continue
                rel = src.relative_to(src_root)
                dst = DEST_ROOT / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                # Skip if destination is byte-identical (idempotent).
                if dst.is_file() and dst.stat().st_size == src.stat().st_size \
                        and dst.stat().st_mtime >= src.stat().st_mtime:
                    skipped += 1
                    continue
                shutil.copy2(src, dst)
                copied += 1
        print(f"  [{bundle}] done")
    print(f"\n  Copied {copied} files, {skipped} already current.")
    print(f"  Destination: {DEST_ROOT}")
    return 0


# ---------------------------------------------------------------------------
# repak mode: extract straight from the encrypted game pak with the AES key
# ---------------------------------------------------------------------------
def _do_repak(aes_key: str, bundles: list[str]) -> int:
    pak_a = MT_GAME_DIR / "MotorTown" / "Content" / "Paks" / "MotorTown-Windows.pak"
    pak_b = MT_GAME_DIR / "MotorTown" / "Content" / "Paks" / "MotorTown.pak"
    pak = pak_a if pak_a.is_file() else pak_b if pak_b.is_file() else None
    if pak is None:
        sys.stderr.write(f"[bootstrap] no MotorTown.pak found under {MT_GAME_DIR}\n")
        return 2
    if not REPAK.is_file():
        sys.stderr.write(f"[bootstrap] vendored repak missing at {REPAK}\n")
        return 2
    # vanilla_extract = GAME_CONTENT's grandparent (…/MotorTown/Content).
    out_root = DEST_ROOT.parent.parent
    out_root.mkdir(parents=True, exist_ok=True)
    args = [str(REPAK), "--aes-key", aes_key, "unpack", str(pak),
            "--output", str(out_root), "--force",
            "--strip-prefix", "../../../"]
    for bundle in bundles:
        for inc in BUNDLES[bundle]["includes"]:
            args += ["--include", f"MotorTown/Content/{inc}"]
    print(f"  pak     : {pak}")
    print(f"  output  : {out_root}")
    print(f"  bundles : {bundles}")
    r = subprocess.run(args)
    if r.returncode == 0:
        print(f"  [repak] extracted bundles {bundles} OK")
        _record_bundles(bundles, pak_fingerprint(pak))
    return r.returncode


def _do_full(aes_key: str) -> int:
    """Extract the ENTIRE game pak into vanilla_extract/ — every asset, no
    --include filtering. Heavier on disk (~GBs) but means any UAssetAPI
    read (clone source actors, transitive references, future features)
    always finds its file locally. Idempotent via the pak fingerprint:
    skips when 'full' is already current for this pak."""
    pak_a = MT_GAME_DIR / "MotorTown" / "Content" / "Paks" / "MotorTown-Windows.pak"
    pak_b = MT_GAME_DIR / "MotorTown" / "Content" / "Paks" / "MotorTown.pak"
    pak = pak_a if pak_a.is_file() else pak_b if pak_b.is_file() else None
    if pak is None:
        sys.stderr.write(f"[bootstrap] no MotorTown.pak found under {MT_GAME_DIR}\n")
        return 2
    if not REPAK.is_file():
        sys.stderr.write(f"[bootstrap] vendored repak missing at {REPAK}\n")
        return 2
    out_root = DEST_ROOT.parent.parent       # …/vanilla_extract
    out_root.mkdir(parents=True, exist_ok=True)
    args = [str(REPAK), "--aes-key", aes_key, "unpack", str(pak),
            "--output", str(out_root), "--force", "--strip-prefix", "../../../"]
    print(f"  pak     : {pak}")
    print(f"  output  : {out_root}")
    print(f"  mode    : FULL (every asset)")
    r = subprocess.run(args)
    if r.returncode == 0:
        print("  [repak] full extraction OK")
        # Mark full + every known bundle current (full is a superset).
        _record_bundles(["full"] + ALL_BUNDLES, pak_fingerprint(pak))
    return r.returncode


def _record_bundles(bundles: list[str], fp: str) -> None:
    """Stamp each freshly-extracted bundle with the pak fingerprint so
    later runs can skip it (delta caching) until the game updates."""
    if not fp:
        return
    state = _load_state()
    state["pak_fingerprint"] = fp
    rec = state.setdefault("bundles", {})
    for b in bundles:
        rec[b] = fp
    _save_state(state)


def _do_check(default_only: bool = True) -> int:
    """Clearance check: compare the current game pak fingerprint to the
    recorded extraction state. Exit 0 if all relevant bundles are current,
    3 if a game update is detected (bundles stale), 4 if never bootstrapped."""
    fp = pak_fingerprint()
    if not fp:
        sys.stderr.write("[bootstrap] cannot fingerprint the game pak (not found?)\n")
        return 2
    state = _load_state()
    prev = state.get("pak_fingerprint")
    bundles = DEFAULT_BUNDLES if default_only else ALL_BUNDLES
    stale = stale_bundles(bundles, fp)
    if not state:
        print("[bootstrap] no extraction state — vanilla data not bootstrapped yet.")
        return 4
    if prev and prev != fp:
        print("=" * 64)
        print("[bootstrap] GAME PAK CHANGED since last extraction.")
        print(f"  was: {prev}")
        print(f"  now: {fp}")
        print("  The cached vanilla data is STALE. Re-extraction required.")
        print("  Run: python bootstrap_extract.py --ensure")
        print("=" * 64)
        return 3
    if stale:
        print(f"[bootstrap] bundles needing extraction: {stale}")
        return 3
    print(f"[bootstrap] vanilla data current (pak {fp[:16]}…).")
    return 0


def _do_ensure(aes: str, fmodel: str, force: bool) -> int:
    """Extract only the DEFAULT bundles that are stale or missing (delta).
    Fast no-op when everything is current. Announces loudly when a game
    update triggered a refresh. This is the build.bat clearance step."""
    fp = pak_fingerprint()
    state = _load_state()
    prev = state.get("pak_fingerprint")
    if fp and prev and prev != fp:
        print("[bootstrap] game pak changed — refreshing stale vanilla data.")
        # A whole-pak change invalidates every bundle, including the lazily
        # pulled cell tree. Drop their markers so they re-pull on demand.
        _save_state({"pak_fingerprint": prev, "bundles": {}})
    need = DEFAULT_BUNDLES if force else stale_bundles(DEFAULT_BUNDLES, fp)
    if not need:
        print(f"[bootstrap] vanilla data current — nothing to extract.")
        return 0
    print(f"[bootstrap] extracting (delta): {need}")
    if (force is False and not aes) and fmodel:
        return _do_fmodel(Path(fmodel), need)
    if aes:
        return _do_repak(aes, need)
    if fmodel:
        return _do_fmodel(Path(fmodel), need)
    sys.stderr.write("[bootstrap] no AES key and no MT_FMODEL_EXPORT — cannot extract.\n")
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(description="Populate vanilla_extract/ straight from the game pak (default) or from an FModel export.")
    ap.add_argument("bundles", nargs="*", help=f"subset of {ALL_BUNDLES} (default: {DEFAULT_BUNDLES})")
    ap.add_argument("--fmodel", action="store_true", help="force FModel copy-from-tree mode (requires MT_FMODEL_EXPORT)")
    ap.add_argument("--full", action="store_true", help="extract the ENTIRE game pak (every asset) so any UAssetAPI read resolves locally; cached by pak fingerprint")
    ap.add_argument("--ensure", action="store_true", help="extract only stale/missing default bundles (delta); no-op when current")
    ap.add_argument("--check", action="store_true", help="report whether vanilla data is current; exit 0 ok / 3 stale / 4 never bootstrapped")
    ap.add_argument("--force", action="store_true", help="re-extract even when fingerprints match")
    args = ap.parse_args()

    fmodel = _cfg("MT_FMODEL_EXPORT")
    aes    = _cfg("MT_AES_KEY") or MT_AES_KEY  # .env override, else built-in key

    if args.check:
        return _do_check()
    if args.full:
        # Full extraction is cache-aware: skip when 'full' is already current
        # for this pak unless --force. A game update invalidates it.
        fp = pak_fingerprint()
        state = _load_state()
        if not args.force and fp and state.get("bundles", {}).get("full") == fp:
            print("[bootstrap] full extraction current — nothing to do.")
            return 0
        if state.get("pak_fingerprint") and fp and state["pak_fingerprint"] != fp:
            print("[bootstrap] game pak changed — re-extracting full tree.")
        print("[bootstrap] mode=REPAK FULL (self-contained, vendored repak + AES key)")
        return _do_full(aes)
    if args.ensure:
        return _do_ensure(aes, fmodel, args.force)

    bundles = _resolve_bundles(args.bundles)
    # Explicit bundle runs honor delta caching too unless --force.
    if not args.force and aes and not args.fmodel:
        skipped = [b for b in bundles if b not in stale_bundles(bundles)]
        bundles = stale_bundles(bundles)
        if skipped:
            print(f"[bootstrap] up-to-date, skipping: {skipped}")
        if not bundles:
            print("[bootstrap] all requested bundles current — nothing to do.")
            return 0

    # FModel only when explicitly requested or when no AES key is available
    # AND an export is configured. The repak path is the self-contained
    # default — it needs only the game install + vendored tools.
    if (args.fmodel or not aes) and fmodel:
        print(f"[bootstrap] mode=FMODEL src='{fmodel}'")
        return _do_fmodel(Path(fmodel), bundles)
    if aes:
        print(f"[bootstrap] mode=REPAK (self-contained, vendored repak + AES key)")
        return _do_repak(aes, bundles)
    if fmodel:
        print(f"[bootstrap] mode=FMODEL src='{fmodel}'")
        return _do_fmodel(Path(fmodel), bundles)
    # Should be unreachable — MT_AES_KEY has a built-in default.
    sys.stderr.write("[bootstrap] no AES key and no MT_FMODEL_EXPORT — cannot extract.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
