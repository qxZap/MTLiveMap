"""
Centralized path resolution for the MTMapInjector pipeline.

Every script that touches the game content, the .usmap mappings, or the
deployed Paks/ folder reads its paths from here, which in turn pulls
from environment variables. This lets a single edit to fulltest.bat
propagate to every Python step, and keeps user-specific drive letters
out of source code.

Required environment variables (set in fulltest.bat or your shell):

  MTMI_GAME_CONTENT     Folder containing the EXTRACTED vanilla
                        Motor Town content tree. Should resolve to
                        '<root>/MotorTown/Content' with subfolders like
                        'DataAsset/', 'Maps/Jeju/', 'Objects/Mission/',
                        etc. Get it by extracting the game's pak with
                        FModel or UE Viewer and pointing at the Content
                        directory.

  MTMI_MAPPINGS         Path to the .usmap mappings file matching the
                        game's UE engine version. Generated with tools
                        like UnrealMappingsDumper or pulled from a
                        community release. The MTBPInjector C# layer
                        and UAssetGUI both need this.

  MTMI_MAPPINGS_TAG     Engine tag UAssetGUI uses with the .usmap
                        (e.g. 'MotorTown718P1'). Must match the
                        filename of the .usmap (without extension).

  MTMI_GAME_PAKDIR      The game's Paks/ folder where the deployed mod
                        .pak gets copied. Usually
                        'C:/SteamLibrary/steamapps/common/Motor Town/MotorTown/Content/Paks'.

If a script is invoked without one of these set, mt_paths exits
immediately with a multi-line error explaining what is missing, where
to obtain the content, and which env var to set.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REQUIRED = {
    "MTMI_GAME_CONTENT": {
        "kind": "dir",
        "what": "extracted vanilla Motor Town content tree",
        "expect": "a folder ending in '/MotorTown/Content' with DataAsset/, Maps/Jeju/, Objects/Mission/Delivery/ inside",
        "how": (
            "Extract the game's MotorTown.pak (or the iostore .ucas/.utoc) with\n"
            "FModel (https://fmodel.app) or UE Viewer, then point this var at\n"
            "the resulting MotorTown/Content directory."
        ),
    },
    "MTMI_MAPPINGS": {
        "kind": "file",
        "what": ".usmap UAssetAPI mappings file for the current MT build",
        "expect": "a .usmap file (e.g. MotorTown718P1.usmap)",
        "how": (
            "Generate with UnrealMappingsDumper / Dumper-7 / similar against the\n"
            "running game, or grab a community release that matches the MT version\n"
            "you have installed. UAssetAPI fails to parse a NormalExport without it."
        ),
    },
    "MTMI_MAPPINGS_TAG": {
        "kind": "literal",
        "what": "engine tag UAssetGUI uses with --tojson / --fromjson",
        "expect": "a string like 'MotorTown718P1' (the .usmap filename without extension)",
        "how": "Same string as the basename of MTMI_MAPPINGS without the '.usmap' suffix.",
    },
    "MTMI_GAME_PAKDIR": {
        "kind": "dir",
        "what": "the game's Paks/ folder (deploy target)",
        "expect": "a folder containing MotorTown-Windows.pak (and any installed mod paks)",
        "how": (
            "Right-click Motor Town in Steam -> Manage -> Browse local files,\n"
            "then drill into MotorTown/Content/Paks. Paste the absolute path."
        ),
    },
}


def _die(missing: list[tuple[str, str]]) -> None:
    """Print a help block and exit. `missing` is [(env_var, reason), ...]."""
    bar = "=" * 72
    sys.stderr.write(f"\n{bar}\n")
    sys.stderr.write("MTMapInjector pipeline cannot start — required paths are missing.\n")
    sys.stderr.write(f"{bar}\n\n")
    for var, reason in missing:
        meta = _REQUIRED[var]
        sys.stderr.write(f"  [{var}]\n")
        sys.stderr.write(f"    Problem : {reason}\n")
        sys.stderr.write(f"    Wants   : {meta['expect']}\n")
        sys.stderr.write(f"    Purpose : {meta['what']}\n")
        sys.stderr.write(f"    Source  : {meta['how']}\n\n")
    sys.stderr.write(
        "Set these in fulltest.bat at the top of the file (look for the\n"
        "'set \"MTMI_*=...\"' block), or export them in your shell before running\n"
        "individual Python scripts. See README.md for the full setup.\n"
    )
    sys.stderr.write(f"{bar}\n")
    sys.exit(2)


def _resolve() -> dict[str, object]:
    missing: list[tuple[str, str]] = []
    out: dict[str, object] = {}
    for var, meta in _REQUIRED.items():
        raw = os.environ.get(var, "").strip().strip('"')
        if not raw:
            missing.append((var, "environment variable is not set or is empty"))
            continue
        if meta["kind"] == "literal":
            out[var] = raw
            continue
        p = Path(raw)
        if meta["kind"] == "dir":
            if not p.is_dir():
                missing.append((var, f"path '{raw}' does not exist or is not a directory"))
                continue
        elif meta["kind"] == "file":
            if not p.is_file():
                missing.append((var, f"path '{raw}' does not exist or is not a file"))
                continue
        out[var] = p
    if missing:
        _die(missing)
    return out


_RESOLVED = _resolve()

GAME_CONTENT: Path = _RESOLVED["MTMI_GAME_CONTENT"]      # type: ignore[assignment]
MAPPINGS: Path     = _RESOLVED["MTMI_MAPPINGS"]          # type: ignore[assignment]
MAPPINGS_TAG: str  = _RESOLVED["MTMI_MAPPINGS_TAG"]      # type: ignore[assignment]
GAME_PAKDIR: Path  = _RESOLVED["MTMI_GAME_PAKDIR"]       # type: ignore[assignment]

# Convenience derived paths used across scripts.
JEJU_MAIN: Path     = GAME_CONTENT / "Maps" / "Jeju" / "Jeju_World.umap"
CELLS_DIR: Path     = GAME_CONTENT / "Maps" / "Jeju" / "Jeju_World" / "_Generated_"
VANILLA_CARGOS: Path    = GAME_CONTENT / "DataAsset" / "Cargos.uasset"
VANILLA_CARGOS_01: Path = GAME_CONTENT / "DataAsset" / "Cargos_01.uasset"
