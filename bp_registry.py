"""
Central registry mapping placeholder asset_keys to Motor Town BP actor
templates that should be cloned into the mod at the same world coords.

Users drop marker placeholder assets under /Game/DC/Actors/ in their UE
editor scene (asset name matches the registry key), export via ue.py, then
the pipeline replaces each marker with the real BP actor at runtime by
cloning from a vanilla in-game instance.

Adding a new BP actor type:
  1. Find a vanilla instance in Jeju (inspect-by-class / cells).
  2. Add an entry below:
        "MyAssetKey": {
            "bp_path":      "/Game/.../SomeBp",
            "bp_class":     "SomeBp_C",
            "source_umap":  <path to .umap that contains the vanilla instance>,
            "source_actor": <that instance's exact ObjectName>,
            "preload_bp":   optional .uasset to preload so its BP schema is
                             available (needed for some BPs UAssetAPI can't
                             parse without the class schema)
        }
  3. Drop a marker asset under /Game/DC/Actors/MyAssetKey in your scene.
  4. Done — import_meshes + clone_bp_actors pick it up automatically.
"""

from __future__ import annotations
from pathlib import Path


GAME_CONTENT = Path(r"D:\MT\Output\Exports\MotorTown\Content")
CELLS_DIR = GAME_CONTENT / "Maps" / "Jeju" / "Jeju_World" / "_Generated_"
JEJU_MAIN = GAME_CONTENT / "Maps" / "Jeju" / "Jeju_World.umap"


# asset_key -> template definition
REGISTRY: dict[str, dict] = {
    "Garage": {
        "bp_path":      "/Game/Blueprints/Interaction/GarageActorBP",
        "bp_class":     "GarageActorBP_C",
        "source_umap":  JEJU_MAIN,
        "source_actor": "GarageActor2",
        "preload_bp":   None,
    },
    "ParkingLarge": {
        "bp_path":      "/Game/Objects/ParkingSpace/ParkingSpace_Large_01",
        "bp_class":     "ParkingSpace_Large_01_C",
        "source_umap":  CELLS_DIR / "0MYO9WO9JBZ10BIDLXVFRXAOG.umap",
        "source_actor": "ParkingSpace_Large_01_UAID_2CF05D790A1CFFDB01_1915517403",
        "preload_bp":   GAME_CONTENT / "Objects/ParkingSpace/Interaction_ParkingSpace_Large.uasset",
    },
    "ParkingMedium": {
        "bp_path":      "/Game/Objects/ParkingSpace/ParkingSpace_Middle_01",
        "bp_class":     "ParkingSpace_Middle_01_C",
        "source_umap":  JEJU_MAIN,
        "source_actor": "ParkingSpace_Middle_01_C_116",
        # Both the wrapper and the inner ChildActor-spawned Interaction BP
        # need schemas available so UAssetAPI parses them as NormalExport
        # (otherwise the inner spawned actor is a RawExport whose embedded
        # FPackageIndex values point into the source cell and we can't
        # remap them, causing crashes).
        "preload_bp":   [
            GAME_CONTENT / "Objects/ParkingSpace/ParkingSpace_Middle_01.uasset",
            GAME_CONTENT / "Objects/ParkingSpace/Interaction_PublicParkingSpac.uasset",
        ],
    },
    "ParkingSmall": {
        "bp_path":      "/Game/Objects/ParkingSpace/ParkingSpace_Small_02",
        "bp_class":     "ParkingSpace_Small_02_C",
        "source_umap":  CELLS_DIR / "1KW42BDFT73JWB9PXN8CUSUXV.umap",
        "source_actor": "PublicParkingSpace_Small15_UAID_2CF05D790A1C63D301_1789842301",
        "preload_bp":   [
            GAME_CONTENT / "Objects/ParkingSpace/ParkingSpace_Small_02.uasset",
            GAME_CONTENT / "Objects/ParkingSpace/Interaction_PublicParkingSpac.uasset",
        ],
    },
}


def asset_keys() -> set[str]:
    """All registry keys — import_meshes uses this to route markers."""
    return set(REGISTRY.keys())


def template_for_class(bp_class: str) -> dict | None:
    for entry in REGISTRY.values():
        if entry["bp_class"] == bp_class:
            return entry
    return None
