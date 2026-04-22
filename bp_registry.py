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
        "bp_path":      "/Game/Objects/GarageActorBP",
        "bp_class":     "GarageActorBP_C",
        "source_umap":  JEJU_MAIN,
        "source_actor": "GarageActor2",
        "preload_bp":   None,
    },
    # Lightweight refuel actor — pump + nozzle interaction only. Final-boss
    # GasStation_C (delivery-point variant) pulls in mission/ownership state
    # too heavy for a cloned cell; FuelPump_01A_C gives the same fueling
    # UX without the transitive footprint.
    "GasStation": {
        "bp_path":      "/Game/Objects/Fuel/FuelPump_01A",
        "bp_class":     "FuelPump_01A_C",
        "source_umap":  JEJU_MAIN,
        "source_actor": "FuelPump2",
        "preload_bp":   GAME_CONTENT / "Objects/Fuel/FuelPump_01A.uasset",
    },
    "ParkingLarge": {
        "bp_path":      "/Game/Objects/ParkingSpace/ParkingSpace_Large_01",
        "bp_class":     "ParkingSpace_Large_01_C",
        "source_umap":  CELLS_DIR / "0MYO9WO9JBZ10BIDLXVFRXAOG.umap",
        "source_actor": "ParkingSpace_Large_01_UAID_2CF05D790A1CFFDB01_1915517403",
        "preload_bp":   GAME_CONTENT / "Objects/ParkingSpace/Interaction_ParkingSpace_Large.uasset",
    },
    "ParkingSmall": {
        # Use the direct Interaction BP (not the ChildActorComponent-wrapper
        # ParkingSpace_Small_02_C). Same structural shape as ParkingLarge
        # which already works — no inner-ChildActor refs to remap.
        "bp_path":      "/Game/Objects/ParkingSpace/Interaction_ParkingSpace_Small",
        "bp_class":     "Interaction_ParkingSpace_Small_C",
        "source_umap":  CELLS_DIR / "0Y7AAM17BE5AI5AAH9BGUE9CG.umap",
        "source_actor": "Interaction_ParkingSpace_Small_C_UAID_345A60416115A7A802_1236712312",
        "preload_bp":   GAME_CONTENT / "Objects/ParkingSpace/Interaction_ParkingSpace_Small.uasset",
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
