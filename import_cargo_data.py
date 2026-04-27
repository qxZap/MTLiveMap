"""
Stage Motor Town's cargo + delivery-point reference data into a single
folder so authoring delivery_points.json entries is a copy-paste affair
rather than a reverse-engineering one.

Outputs (under CargoImport/):
  cargos/
    catalog.json         every cargo row with the fields you'd touch from
                         a delivery_points.json recipe (Name, CargoType,
                         CargoFlags, payment knobs, ...)
    types.txt            distinct EDeliveryCargoType enum values seen in
                         the catalog. ONLY values from this list are valid
                         in `input_types` / `output_types` of a recipe.
    cargo_names.txt      every cargo row's Name (alpha order). These are
                         the keys for `inputs` / `outputs` cargo maps.
  delivery_points/
    <ClassName>.example.json
                         one file per vanilla delivery-point BP. Contains
                         a delivery_points.json-shaped entry derived from
                         the BP's CDO ProductionConfigs + label hints +
                         marker/icon fields. Drop it into your real
                         delivery_points.json under any name you like and
                         tweak.
  README.md              what each file is, where to find your overrides.

Run from repo root:  python import_cargo_data.py
Re-run any time the game data updates.
"""

from __future__ import annotations
import json, shutil, subprocess, sys, tempfile
from pathlib import Path

GAME_CONTENT = Path(r"D:\MT\Output\Exports\MotorTown\Content")
MAPPINGS     = r"D:\MT\MotorTown718P1.usmap"
UASSETGUI    = "UAssetGUI.exe"

CARGOS_UASSET    = GAME_CONTENT / "DataAsset" / "Cargos.uasset"
DELIVERY_FOLDER  = GAME_CONTENT / "Objects" / "Mission" / "Delivery" / "DeliveryPoint"
OUT_ROOT         = Path("CargoImport")


def to_json(uasset: Path, dst: Path) -> bool:
    """UAssetGUI tojson is async — wait for the file to be (re)written."""
    if dst.exists(): dst.unlink()
    proc = subprocess.Popen(
        [UASSETGUI, "tojson", str(uasset), str(dst), "VER_UE5_5", "MotorTown718P1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    import time
    deadline = time.time() + 30
    while time.time() < deadline:
        if dst.exists() and dst.stat().st_size > 0:
            time.sleep(0.3)  # let the writer flush
            return True
        time.sleep(0.2)
    return False


def prop_value(prop: dict):
    """Pull the simple Value field. For nested struct/array, return a
    summary string the user can hand-copy into delivery_points.json."""
    if prop is None: return None
    return prop.get("Value")


def extract_cargo_catalog(cargos_json: Path) -> dict:
    d = json.loads(cargos_json.read_text(encoding="utf-8"))
    rows = d["Exports"][0]["Table"]["Data"]
    catalog = []
    types_seen = set()
    for r in rows:
        name = r.get("Name")
        fields = {p.get("Name"): p for p in r.get("Value", [])}
        ctype = prop_value(fields.get("CargoType")) or "None"
        types_seen.add(str(ctype))
        catalog.append({
            "Name":              name,
            "CargoType":         str(ctype),
            "VolumeSize":        prop_value(fields.get("VolumeSize")),
            "BasePayment":       prop_value(fields.get("BasePayment")),
            "PaymentPer1Km":     prop_value(fields.get("PaymentPer1Km")),
            "ExportPrice":       prop_value(fields.get("ExportPrice")),
            "ImportPrice":       prop_value(fields.get("ImportPrice")),
            "bAllowStacking":    prop_value(fields.get("bAllowStacking")),
            "MinDeliveryDistance": prop_value(fields.get("MinDeliveryDistance")),
            "MaxDeliveryDistance": prop_value(fields.get("MaxDeliveryDistance")),
            "bDepcreated":       prop_value(fields.get("bDepcreated")),
        })
    return {"catalog": catalog, "types": sorted(types_seen)}


def extract_recipes(cdo: dict) -> list[dict]:
    """Convert a Default__X_C ProductionConfigs into delivery_points.json
    recipe shape. Returns [] if CDO has no parsed ProductionConfigs (asset
    has been unparsed as RawExport — those need manual inspection)."""
    recipes = []
    for p in cdo.get("Data", []):
        if p.get("Name") != "ProductionConfigs": continue
        for cfg in p.get("Value", []):
            inner = {sub.get("Name"): sub for sub in cfg.get("Value", [])}
            r: dict = {}
            def cargo_map(field):
                m = inner.get(field)
                if not m: return {}
                out = {}
                for kv in m.get("Value", []):
                    if not isinstance(kv, list) or len(kv) != 2: continue
                    out[kv[0].get("Value")] = kv[1].get("Value")
                return out
            def type_list(field):
                m = inner.get(field)
                if not m: return []
                out = []
                for kv in m.get("Value", []):
                    if not isinstance(kv, list) or len(kv) != 2: continue
                    raw = kv[0].get("Value", "")
                    out.append(raw.split("::", 1)[1] if "::" in raw else raw)
                return out
            ins  = cargo_map("InputCargos")
            outs = cargo_map("OutputCargos")
            it   = type_list("InputCargoTypes")
            ot   = type_list("OutputCargoTypes")
            speed = prop_value(inner.get("ProductionSpeedMultiplier"))
            tsec  = prop_value(inner.get("ProductionTimeSeconds"))
            if ins:   r["inputs"]       = ins
            if outs:  r["outputs"]      = outs
            if it:    r["input_types"]  = it
            if ot:    r["output_types"] = ot
            if speed not in (None, 1.0): r["speed"]        = speed
            if tsec  not in (None, 0.0): r["time_seconds"] = tsec
            recipes.append(r)
    return recipes


def extract_visuals(cdo: dict) -> dict:
    """Pull marker color / icon / world-map flags from the CDO. Field names
    here are speculative until proven on a vanilla example — kept generic
    so anything DataAsset-y still surfaces in the dump."""
    out = {}
    for p in cdo.get("Data", []):
        nm = p.get("Name", "")
        low = nm.lower()
        if any(k in low for k in ("color", "icon", "marker", "thumbnail", "tex")):
            v = p.get("Value")
            out[nm] = v if not isinstance(v, list) else f"<{p.get('$type','?').split('.')[-1]} len={len(v)}>"
    return out


def build_dp_example(class_name: str, cdo: dict) -> dict:
    label = class_name[:-2] if class_name.endswith("_C") else class_name
    return {
        "_source_class": class_name,
        "label":         label[:14],
        "recipes":       extract_recipes(cdo),
        "visuals_seen":  extract_visuals(cdo),
    }


def main() -> int:
    OUT_ROOT.mkdir(exist_ok=True)
    (OUT_ROOT / "cargos").mkdir(exist_ok=True)
    (OUT_ROOT / "delivery_points").mkdir(exist_ok=True)

    print("[1/3] Extracting cargo catalog...")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_json = Path(tmp) / "cargos.json"
        if not to_json(CARGOS_UASSET, tmp_json):
            print(f"  ERROR: failed to dump {CARGOS_UASSET}", file=sys.stderr); return 1
        catalog_data = extract_cargo_catalog(tmp_json)
    (OUT_ROOT / "cargos" / "catalog.json").write_text(
        json.dumps(catalog_data["catalog"], indent=2), encoding="utf-8")
    (OUT_ROOT / "cargos" / "types.txt").write_text(
        "\n".join(catalog_data["types"]) + "\n", encoding="utf-8")
    (OUT_ROOT / "cargos" / "cargo_names.txt").write_text(
        "\n".join(sorted(c["Name"] for c in catalog_data["catalog"])) + "\n", encoding="utf-8")
    print(f"  {len(catalog_data['catalog'])} cargos, "
          f"{len(catalog_data['types'])} cargo types")

    print("[2/3] Extracting delivery-point examples...")
    bp_files = sorted(p for p in DELIVERY_FOLDER.glob("*.uasset"))
    written = skipped = 0
    with tempfile.TemporaryDirectory() as tmp:
        for bp in bp_files:
            tmp_json = Path(tmp) / (bp.stem + ".json")
            if not to_json(bp, tmp_json):
                print(f"  skip {bp.name}: dump failed", file=sys.stderr); skipped += 1; continue
            try:
                d = json.loads(tmp_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                skipped += 1; continue
            class_name = bp.stem + "_C"
            cdo = next((e for e in d["Exports"] if e.get("ObjectName") == f"Default__{class_name}"), None)
            if cdo is None:
                skipped += 1; continue
            example = build_dp_example(class_name, cdo)
            (OUT_ROOT / "delivery_points" / f"{bp.stem}.example.json").write_text(
                json.dumps(example, indent=2), encoding="utf-8")
            written += 1
    print(f"  {written} examples written, {skipped} skipped")

    print("[3/3] Writing README...")
    (OUT_ROOT / "README.md").write_text(
        "# CargoImport\n\n"
        "Generated by `import_cargo_data.py` — re-run any time game data updates.\n\n"
        "## cargos/\n"
        "- `catalog.json` — every cargo row + payment / volume / type fields. "
        "Names from this list are the keys for `inputs` / `outputs` cargo maps in `delivery_points.json`.\n"
        "- `types.txt` — distinct `EDeliveryCargoType` values. ONLY these are valid "
        "in `input_types` / `output_types`.\n"
        "- `cargo_names.txt` — flat alphabetical list of cargo Names.\n\n"
        "## delivery_points/\n"
        "One `<ClassName>.example.json` per vanilla delivery-point BP. Each file is a\n"
        "ready-to-paste `delivery_points.json` entry — drop it under any KEY (the\n"
        "scene placeholder is `DeliveryPoint_<KEY>`) and adjust.\n\n"
        "`visuals_seen` shows whatever marker/color/icon-shaped fields the CDO\n"
        "actually exposes — use it to identify which knobs the framework can\n"
        "expose next.\n",
        encoding="utf-8")
    print(f"\nDone. See {OUT_ROOT.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
