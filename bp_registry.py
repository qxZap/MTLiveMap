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

from mt_paths import GAME_CONTENT, CELLS_DIR, JEJU_MAIN


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
    # Container Export/Import endpoint — supports BOTH cargo pickup AND
    # drop, unlike the drop-only ComonDrop. Cloned straight into the main
    # map's persistent level so it gets the same load context as the four
    # vanilla ContainerDropper instances already in Jeju.
    "DeliveryPoint": {
        "bp_path":          "/Game/Objects/Mission/Delivery/DeliveryPoint/Container_ExportImport",
        "bp_class":         "Container_ExportImport_C",
        "source_umap":      JEJU_MAIN,
        "source_actor":     "ContainerDropper",
        "preload_bp":       GAME_CONTENT / "Objects/Mission/Delivery/DeliveryPoint/Container_ExportImport.uasset",
        "inject_into_main": True,
    },
    # Standalone farm endpoint — fully self-contained pickup + drop, no
    # InputInventoryShare chaining to siblings (unlike Factory_*). Each
    # placed instance is its own production loop.
    "FarmCorn": {
        "bp_path":          "/Game/Objects/Mission/Delivery/DeliveryPoint/Farm_Corn",
        "bp_class":         "Farm_Corn_C",
        "source_umap":      JEJU_MAIN,
        "source_actor":     "CornFarm_2",
        "preload_bp":       GAME_CONTENT / "Objects/Mission/Delivery/DeliveryPoint/Farm_Corn.uasset",
        "inject_into_main": True,
    },
    # Diagnostic: clone of Farm_Corn with a per-instance ProductionConfigs
    # override — accepts 50t transformers as input, 5x speed. If MT honors
    # instance overrides for this property we can author custom recipes
    # without touching the BP class.
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


# ----------------------------------------------------------------------
# delivery_points.json — JSON-driven custom delivery points.
#
# Scene placeholders named `Delivery_<NAME>` map to the entry under
# `<NAME>` in delivery_points.json. Each entry is converted into a
# normal REGISTRY entry under the key `Delivery_<NAME>` at import time
# so the rest of the pipeline picks it up unchanged. Missing entries
# are logged and skipped (the placeholder is treated as an unknown).
# ----------------------------------------------------------------------
import hashlib as _hashlib
import json as _json
import sys as _sys
from pathlib import Path as _Path

_DP_PATH = _Path(__file__).with_name("delivery_points.json")
_DP_BP_FOLDER = "Objects/Mission/Delivery/DeliveryPoint"

# Default base BP cloned for every JSON-defined delivery point. Farm_Corn_C
# is standalone (no InputInventoryShare chaining), accepts arbitrary recipe
# overrides via CDO mutation, and clones cleanly through the persistent-level
# inject path. Per-entry override is intentionally NOT exposed in
# delivery_points.json — keeps the JSON purely user-intent.
# Known-good vanilla delivery-point templates the framework can clone.
# Each entry pairs a BP class with a specific vanilla instance whose
# byte layout cloning has been verified end-to-end. Adding a new entry
# requires testing — some MTDeliveryPoint subclasses (e.g. Container_-
# ExportImport_C, ComonDrop_C, Factory_*) have transitive dependencies
# that crashed cell-streaming or save-game persistence in our tests.
# `farm` is the proven default.
_TEMPLATES: dict[str, tuple[str, str]] = {
    # template_key      -> (source_class,           source_actor)
    "farm":               ("Farm_Corn_C",           "CornFarm_2"),
}
_DEFAULT_TEMPLATE = "farm"
_DEFAULT_SOURCE_CLASS, _DEFAULT_SOURCE_ACTOR = _TEMPLATES[_DEFAULT_TEMPLATE]

# Cargo / cargo-type allowlists pulled from CargoImport so we can validate
# recipe entries at registry-load time and surface bad data with a clear
# log line instead of a silent in-game no-op.
_CARGO_NAMES_PATH = _Path("CargoImport/cargos/cargo_names.txt")
_CARGO_TYPES_PATH = _Path("CargoImport/cargos/types.txt")

def _load_set(path: _Path) -> set[str]:
    if not path.exists(): return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}

_VALID_CARGO_NAMES = _load_set(_CARGO_NAMES_PATH)
_VALID_CARGO_TYPES = _load_set(_CARGO_TYPES_PATH)

# Direct boosted-cargo name pattern: '<vanilla_cargo>x<int>' or
# '<vanilla_cargo>x<int>p<frac>' (e.g. Fuelx5, CornPalletx2p5). Used in
# delivery_points.json recipes to reference a boosted variant by name
# without the `boosted` magic key, e.g. `outputs: {"Fuelx5": 1}`.
# clone_bp_actors.detect_boosted_cargo_refs() scans recipes for these
# names, auto-creates the row in Cargos_01.uasset, and lets the recipe
# reference flow through unchanged.
import re as _re
_BOOSTED_CARGO_RE = _re.compile(r"^(?P<base>.+?)x(?P<intpart>\d+)(?:p(?P<fracpart>\d+))?$")

def parse_boosted_name(name: str) -> tuple[str, float] | None:
    """Return (base_cargo, multiplier) if name matches the boosted pattern
    AND the base is a known vanilla cargo. Returns None for plain names
    or names whose base isn't a real cargo (treats them as typos)."""
    m = _BOOSTED_CARGO_RE.match(name)
    if not m: return None
    base = m.group("base")
    if _VALID_CARGO_NAMES and base not in _VALID_CARGO_NAMES: return None
    mult = float(m.group("intpart"))
    if m.group("fracpart"):
        mult += float(m.group("fracpart")) / (10 ** len(m.group("fracpart")))
    return (base, mult)


def _derive_target_class(key: str, source_class: str) -> tuple[str, str]:
    """Generate a unique mod BP class name for a delivery point key.
    Byte-rename requires the new class string to be the same length as the
    source's, so we hash the key into the trailing characters and prefix
    with 'Mod' for readability."""
    src_short = source_class[:-2] if source_class.endswith("_C") else source_class
    h = _hashlib.sha1(key.encode()).hexdigest().upper()
    safe = "".join(c for c in h if c in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    prefix = "Mod"
    fill = max(0, len(src_short) - len(prefix))
    short = (prefix + safe)[:len(src_short)]
    cls = short + "_C"
    path = f"/Game/{_DP_BP_FOLDER}/{short}"
    return cls, path


def _derive_actor_label(key: str, max_len: int = 14) -> str:
    """Convert 'My_Cool_Delivery_Point' -> 'My Cool Delivery Point', clipped
    to fit inside the source actor's label byte budget (Farm_Corn vanilla
    label 'NamwonCornFarm' = 14 ASCII bytes). Truncated names show the
    leading prefix in-game."""
    label = key.replace("_", " ")
    return label[:max_len]


def _expand_dp_entry(key: str, cfg: dict) -> dict | None:
    """Materialize a delivery_points.json entry as a REGISTRY-shaped dict.
    The JSON carries user intent (label, recipes, optional visuals) plus
    an OPTIONAL `template` field. Templates pick a vanilla source class
    + source actor; `farm` is the default. Direct overrides via
    `source_class` + `source_actor` are honored for experimental cases."""
    template = cfg.get("template", _DEFAULT_TEMPLATE)
    if template not in _TEMPLATES:
        print(f"  [delivery_points] '{key}': unknown template '{template}', falling back to '{_DEFAULT_TEMPLATE}'", file=_sys.stderr)
        template = _DEFAULT_TEMPLATE
    tpl_src_class, tpl_src_actor = _TEMPLATES[template]
    src_class = cfg.get("source_class", tpl_src_class)
    src_actor = cfg.get("source_actor", tpl_src_actor)
    src_short = src_class[:-2] if src_class.endswith("_C") else src_class
    src_uasset = GAME_CONTENT / _DP_BP_FOLDER / (src_short + ".uasset")
    tgt_class, tgt_path = _derive_target_class(key, src_class)
    tgt_short = tgt_class[:-2]
    mod_uasset = (_Path("MapChangeTest_P/MotorTown/Content") /
                  _DP_BP_FOLDER / (tgt_short + ".uasset"))
    entry = {
        "bp_path":          f"/Game/{_DP_BP_FOLDER}/{src_short}",
        "bp_class":         src_class,
        "source_umap":      JEJU_MAIN,
        "source_actor":     src_actor,
        "preload_bp":       [src_uasset, mod_uasset],
        "inject_into_main": True,
        "target_bp_class":  tgt_class,
        "target_bp_path":   tgt_path,
        "actor_label":      cfg.get("label") or _derive_actor_label(key),
    }
    recipes = cfg.get("recipes") or cfg.get("production_recipes")
    if recipes:
        entry["production_recipes"] = _validate_recipes(key, recipes)
    # Reserved fields propagated for future mutation — see AGENTS.md
    # 'Marker / Icon Mutation (Pending)' / 'InventoryRatio (Pending)'.
    for k in ("marker_color", "icon", "output_storage_cap"):
        if k in cfg: entry[k] = cfg[k]
    return entry


def _validate_recipes(key: str, recipes: list) -> list:
    """Drop unknown cargo names / types from each recipe and log them.
    Loaded set may be empty if the user hasn't run import_cargo_data.py
    yet — in that case we skip validation rather than reject everything."""
    if not _VALID_CARGO_NAMES and not _VALID_CARGO_TYPES:
        return recipes
    cleaned = []
    for i, r in enumerate(recipes):
        if not isinstance(r, dict):
            cleaned.append(r); continue
        out = {k: v for k, v in r.items() if not k.startswith("_")}
        for field in ("inputs", "outputs"):
            m = out.get(field)
            if not isinstance(m, dict): continue
            # Magic keys / generated names are kept:
            #  - 'boosted'           magic key for the side-wide boost
            #  - '<cargo>x<N>[p<F>]' direct boosted-variant cargo name
            #                        (auto-cloned in Cargos_01.uasset)
            bad = [
                n for n in m
                if n != "boosted"
                and n not in _VALID_CARGO_NAMES
                and parse_boosted_name(n) is None
            ]
            for n in bad:
                print(f"  [delivery_points] {key} recipe[{i}].{field}: unknown cargo '{n}' — dropped", file=_sys.stderr)
                m.pop(n)
        for field in ("input_types", "output_types"):
            v = out.get(field)
            if isinstance(v, list):
                out[field] = [t for t in v if t in _VALID_CARGO_TYPES or print(
                    f"  [delivery_points] {key} recipe[{i}].{field}: unknown type '{t}' — dropped", file=_sys.stderr)]
            elif isinstance(v, dict):
                out[field] = {t: c for t, c in v.items() if t in _VALID_CARGO_TYPES or print(
                    f"  [delivery_points] {key} recipe[{i}].{field}: unknown type '{t}' — dropped", file=_sys.stderr)}
        cleaned.append(out)
    return cleaned


def _load_delivery_points():
    if not _DP_PATH.exists(): return
    try:
        cfg = _json.loads(_DP_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [delivery_points.json] parse error: {e}", file=_sys.stderr); return
    for name, dp in cfg.items():
        if name.startswith("_"): continue   # skip _doc, _comment etc.
        # Top-level config knobs (include_pickups, cargo_payment_overrides,
        # cargo_base_overrides, ...) coexist with DP entries — they're
        # consumed by clone_bp_actors directly. Only dict values are DPs.
        if not isinstance(dp, dict): continue
        if name in ("cargo_payment_overrides", "cargo_base_overrides", "cargo_spawn_overrides", "cargo_sqrt_overrides"): continue
        # Scene placeholder convention: DeliveryPoint_<key>
        REGISTRY[f"DeliveryPoint_{name}"] = _expand_dp_entry(name, dp)


_load_delivery_points()


def asset_keys() -> set[str]:
    """All registry keys — import_meshes uses this to route markers."""
    return set(REGISTRY.keys())


def template_for_class(bp_class: str) -> dict | None:
    for entry in REGISTRY.values():
        if entry["bp_class"] == bp_class:
            return entry
    return None
