#!/usr/bin/env python3
"""
build_vehicles.py — ship the new vehicles declared in vehicles.json.

Each entry clones a base vehicle two ways:

  1. The CLASS asset, byte-renamed into the mod. Byte-rename keeps file
     offsets valid only if the new name is the SAME LENGTH as the old, so the
     shipped class gets a generated same-length name. That name is invisible:
     what you spawn and buy is the ROW name, which is free-form.
  2. The DataTable ROW, with VehicleClass repointed at that class and any
     row_field overrides applied.

Modifications are applied to the cloned class, never the base, so vanilla
vehicles are untouched.
"""
from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path

from mt_paths import MAPPINGS, MOD_CONTENT_ROOT, effective_asset
from unlock_vehicles import discover_tables, vehicle_class_by_row

INJECTOR = Path("MTBPInjector/bin/Release/net8.0/MTBPInjector.exe")
CONFIG   = Path("vehicles.json")


def same_length_name(new_id: str, base_short: str) -> str:
    """A class name the byte-renamer can use: exactly as long as the base's.
    Derived from new_id so it is stable across builds."""
    h = hashlib.sha1(new_id.encode()).hexdigest().upper()
    return (("V" + h)[:len(base_short)])


def run(*args: str) -> bool:
    r = subprocess.run([str(INJECTOR), *args], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.strip(): print(f"    {line}")
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
    return r.returncode == 0


def apply_modifications(entries, row_to_class, tables) -> bool:
    """Modify vehicles the game already ships, in place.

    Different from the `vehicles` list above, which builds a NEW vehicle from
    an existing one. Here the row keeps its name and its class keeps its path,
    so the mod's copy simply overrides vanilla's and every one of these already
    in the world gains the change. That is the point for something like a fuel
    pump on the tanker trailer: nobody wants a second trailer to buy, they want
    the trailer they already own to work.

    The class asset is re-copied from vanilla each build rather than edited in
    place, so the result depends only on vehicles.json and not on what the last
    build happened to leave behind.
    """
    ok = True
    for v in entries:
        row = v.get("row")
        base_path = row_to_class.get(row) if row else None
        if not base_path:
            print(f"    row '{row}' not in any vehicle table - skipped", file=sys.stderr)
            ok = False
            continue
        print(f"  {row} (modified in place)")

        short   = base_path[base_path.rfind("/") + 1:]
        rel_dir = base_path[len("/Game/"):].rsplit("/", 1)[0]
        src     = effective_asset(f"{rel_dir}/{short}.uasset")
        dst_dir = MOD_CONTENT_ROOT / rel_dir
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst     = dst_dir / f"{short}.uasset"
        copied = 0
        for ext in (".uasset", ".uexp", ".ubulk"):
            sp = src.with_suffix(ext)
            if sp.exists():
                (dst_dir / f"{short}{ext}").write_bytes(sp.read_bytes())
                copied += 1
        if not copied:
            print(f"    class asset {short} not found - skipped", file=sys.stderr)
            ok = False
            continue

        row_sets = []
        for m in v.get("modifications") or []:
            t = m.get("type")
            if t == "fuel_pump":
                # Adds MTTankerFuelPumpComponent. bHasFuelPump on the row only
                # advertises the component -- without this the flag does
                # nothing at all, which is the trap worth remembering.
                a = ["vehicle-fuel-pump", "--uasset", str(dst), "--mappings", str(MAPPINGS)]
                fts = m.get("fuel_types") or ["Diesel"]
                a += ["--fuel-types", ",".join(fts)]
                for flag, key in (("--rel-x", "rel_x"), ("--rel-y", "rel_y"), ("--rel-z", "rel_z")):
                    if m.get(key) is not None:
                        a += [flag, str(m[key])]
                if not run(*a):
                    ok = False
            elif t == "cargo_fuel_types":
                # What the tank ACCEPTS, as opposed to what the pump gives out.
                # A hydrant refuses a tanker with "wrong fuel type" until Water
                # is listed here, however the pump is configured.
                a = ["vehicle-cargo-fuels", "--uasset", str(dst), "--mappings", str(MAPPINGS),
                     "--types", ",".join(m.get("types") or ["Water"])]
                if m.get("space_type"):
                    a += ["--space-type", m["space_type"]]
                if not run(*a):
                    ok = False
            elif t == "crane_winch":
                a = ["vehicle-crane-winch", "--uasset", str(dst), "--mappings", str(MAPPINGS)]
                if m.get("name"):  a += ["--name", m["name"]]
                if m.get("crane"): a += ["--crane", m["crane"]]
                if not run(*a):
                    ok = False
            elif t == "all_wheel_drive":
                # Present in the CLONE dispatch but not here, so asking for AWD
                # on an existing vehicle silently hit "unsupported" and the log
                # line that looked like Crany's AWD was actually Vista GTR's,
                # a few lines further down.
                a = ["vehicle-awd", "--uasset", str(dst), "--mappings", str(MAPPINGS)]
                if m.get("each_set_awd"):       a.append("--each-set-awd")
                if m.get("enable_center_diff"): a.append("--center-diff")
                if not run(*a):
                    ok = False
            elif t == "constraint":
                # A hydraulic constraint between two of the vehicle's own
                # components. Crany's boom is driven kinematically and pulls
                # nothing; the wreckers that lift are built from these.
                a = ["vehicle-constraint", "--uasset", str(dst), "--mappings", str(MAPPINGS),
                     "--component1", m["component1"], "--component2", m["component2"]]
                if m.get("name"):           a += ["--name", m["name"]]
                if m.get("angular_speed") is not None:
                    a += ["--angular-speed", str(m["angular_speed"])]
                if not run(*a):
                    ok = False
            elif t == "interactable":
                a = ["vehicle-interactable", "--uasset", str(dst), "--mappings", str(MAPPINGS),
                     "--types", ",".join(m["types"])]
                if m.get("name"):
                    a += ["--name", m["name"]]
                if not run(*a):
                    ok = False
            elif t == "part_slots":
                # Slots are a SET on the row, and a winch is spawned at runtime
                # from a part fitted to one. Crany declares no slots at all,
                # which is why its crane's Winch is forever null.
                for rel in tables:
                    tbl_src = effective_asset(rel)
                    if not tbl_src.is_file():
                        continue
                    probe = subprocess.run(
                        [str(INJECTOR), "dump-table", "--uasset", str(tbl_src),
                         "--mappings", str(MAPPINGS), "--fields", "VehicleClass"],
                        capture_output=True, text=True)
                    if f"{row}	" not in probe.stdout:
                        continue
                    out = MOD_CONTENT_ROOT / rel
                    out.parent.mkdir(parents=True, exist_ok=True)
                    if not out.is_file():
                        for ext in (".uasset", ".uexp"):
                            sp = tbl_src.with_suffix(ext)
                            if sp.exists():
                                out.with_suffix(ext).write_bytes(sp.read_bytes())
                    if not run("set-row-slots", "--uasset", str(out), "--mappings", str(MAPPINGS),
                               "--row", row, "--field", m.get("field", "NotOptionalPartSlots"),
                               "--add", ",".join(m["add"])):
                        ok = False
            elif t == "row_field":
                val = m["value"]
                row_sets.append(f'{m["field"]}={val}')
            else:
                print(f"    unsupported modification '{t}' - skipped", file=sys.stderr)

        if not row_sets:
            continue
        # base == new-id: clone-vehicle-row REPLACES a row that already exists,
        # so naming the row as its own base is an in-place field edit and needs
        # no separate verb. No --class-path: the class keeps its identity.
        placed = 0
        for rel in tables:
            tbl_src = effective_asset(rel)
            if not tbl_src.is_file():
                continue
            probe = subprocess.run(
                [str(INJECTOR), "dump-table", "--uasset", str(tbl_src),
                 "--mappings", str(MAPPINGS), "--fields", "VehicleClass"],
                capture_output=True, text=True)
            if f"{row}\t" not in probe.stdout:
                continue
            out = MOD_CONTENT_ROOT / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            table_in = out if out.is_file() else tbl_src
            if run("clone-vehicle-row", "--uasset", str(table_in), "--output", str(out),
                   "--mappings", str(MAPPINGS), "--base", row, "--new-id", row,
                   "--set", ",".join(row_sets)):
                placed += 1
            else:
                ok = False
        if placed == 0:
            print(f"    WARNING: no table carried row '{row}'", file=sys.stderr)
            ok = False
    return ok



# What the LAST run staged, so this run can remove what it no longer builds.
MANIFEST = MOD_CONTENT_ROOT / ".vehicles_staged.json"


def prune_stale(expected: set[str]) -> None:
    """Delete vehicle assets a previous run staged and this one does not.

    Dropping a `modify` entry stops the build TOUCHING that vehicle -- it does
    not remove the copy already sitting in the staging tree, which is packed
    again regardless. Removing the crashing Crany constraint from vehicles.json
    therefore shipped the crashing Crany anyway, and the build log looked clean
    because the step simply never ran.

    Reverting a change has to remove its artifact, or "reverted" is a claim
    about the config rather than about the pak.
    """
    try:
        old = set(json.loads(MANIFEST.read_text(encoding="utf-8")))
    except Exception:
        old = set()
    for rel in sorted(old - expected):
        d = MOD_CONTENT_ROOT / rel
        if not d.exists():
            continue
        for f in sorted(d.glob("*")):
            if f.is_file():
                f.unlink()
        try:
            d.rmdir()
        except OSError:
            pass
        print(f"  pruned {rel} — staged by an earlier run, not built by this one")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(sorted(expected), indent=2), encoding="utf-8")


def main() -> int:
    # --config so the island's vehicles and the shippable tanker work can live
    # in separate files. They ship as different mods, so keeping them in one
    # config meant every standalone pak had to be carved out of it at build
    # time.
    global CONFIG
    for i, a in enumerate(sys.argv):
        if a == "--config" and i + 1 < len(sys.argv):
            CONFIG = Path(sys.argv[i + 1])
        elif a.startswith("--config="):
            CONFIG = Path(a.split("=", 1)[1])
    if not CONFIG.exists():
        print("  vehicles.json absent — no custom vehicles"); return 0
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    entries = [v for v in (cfg.get("vehicles") or [])
               if isinstance(v, dict) and v.get("base") and v.get("new_id")]
    mods = [v for v in (cfg.get("modify") or [])
            if isinstance(v, dict) and v.get("row")]
    if not entries and not mods:
        print("  no vehicles declared"); return 0

    row_to_class = vehicle_class_by_row()
    tables = discover_tables()

    # Everything this run intends to stage. Anything a previous run left behind
    # and this one does not rebuild gets removed before we start.
    expected = set()
    for v in mods:
        cp = row_to_class.get(v.get("row"))
        if cp:
            expected.add(cp[len("/Game/"):].rsplit("/", 1)[0])
    for v in entries:
        cp = row_to_class.get(v.get("base"))
        if cp:
            expected.add(cp[len("/Game/"):].rsplit("/", 1)[0])
    prune_stale(expected)
    ok = True

    if mods:
        ok = apply_modifications(mods, row_to_class, tables) and ok

    for v in entries:
        base, new_id = v["base"], v["new_id"]
        print(f"  {new_id} (from {base})")
        base_path = row_to_class.get(base)
        if not base_path:
            print(f"    base row '{base}' not in any vehicle table — skipped", file=sys.stderr)
            ok = False; continue

        # --- 1. clone the class asset -----------------------------------
        base_short = base_path[base_path.rfind("/") + 1:]
        new_short  = same_length_name(new_id, base_short)
        rel_dir    = base_path[len("/Game/"):].rsplit("/", 1)[0]
        # /Game-relative for the self-path replace above.
        rel_dir_g  = base_path.rsplit("/", 1)[0]
        src        = effective_asset(f"{rel_dir}/{base_short}.uasset")
        dst_dir    = MOD_CONTENT_ROOT / rel_dir
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst        = dst_dir / f"{new_short}.uasset"
        # Rename ONLY the asset's self-references. A blind replace of the base
        # name is wrong here in two ways, and both produce a car with no body:
        #   /Game/Cars/Models/Vista/Body   the FOLDER is also called Vista
        #   /Game/Cars/Parts/Wheels/Vista_L  the wheels are separate assets
        # Renaming either points the clone at packages that do not exist.
        # Delivery point classes never hit this because their folder is not
        # named after the class.
        pairs = [
            (f"{rel_dir_g}/{base_short}".encode(), f"{rel_dir_g}/{new_short}".encode()),
            (f"Default__{base_short}_C".encode(), f"Default__{new_short}_C".encode()),
            (f"{base_short}_C".encode(),          f"{new_short}_C".encode()),
        ]
        for ext in (".uasset", ".uexp", ".ubulk"):
            sp = src.with_suffix(ext)
            if not sp.exists():
                continue
            b = sp.read_bytes()
            for a, z in pairs:
                b = b.replace(a, z)
            (dst_dir / f"{new_short}{ext}").write_bytes(b)
        print(f"    class {base_short} -> {new_short}")
        new_class_path = f"/Game/{rel_dir}/{new_short}"

        # --- 2. modifications on the CLONE ------------------------------
        row_sets = []
        for m in v.get("modifications") or []:
            t = m.get("type")
            if t == "all_wheel_drive":
                a = ["vehicle-awd", "--uasset", str(dst), "--mappings", str(MAPPINGS)]
                # Default is a spool: one differential, four wheels, no new
                # components. each_set_awd gives front and rear their own;
                # enable_center_diff adds the centre one they both feed, which
                # is the shape vanilla AWD cars actually use.
                if m.get("each_set_awd"):      a.append("--each-set-awd")
                if m.get("enable_center_diff"): a.append("--center-diff")
                if not run(*a):
                    ok = False
            elif t == "row_field":
                row_sets.append(f'{m["field"]}={m["value"]}')
            else:
                print(f"    unsupported modification '{t}' — skipped", file=sys.stderr)

        # --- 3. clone the row into every table that defines the base ----
        placed = 0
        for rel in tables:
            tbl_src = effective_asset(rel)
            if not tbl_src.is_file():
                continue
            probe = subprocess.run(
                [str(INJECTOR), "dump-table", "--uasset", str(tbl_src),
                 "--mappings", str(MAPPINGS), "--fields", "VehicleClass"],
                capture_output=True, text=True)
            if f"{base}\t" not in probe.stdout:
                continue
            out = MOD_CONTENT_ROOT / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            # A table we already rewrote this build (unlock pass) is the input,
            # so the row lands on top of those edits instead of reverting them.
            table_in = out if out.is_file() else tbl_src
            args = ["clone-vehicle-row", "--uasset", str(table_in), "--output", str(out),
                    "--mappings", str(MAPPINGS), "--base", base, "--new-id", new_id,
                    "--class-path", new_class_path]
            if v.get("display_name"):
                args += ["--display-name", v["display_name"]]
            if row_sets:
                args += ["--set", ",".join(row_sets)]
            if run(*args):
                placed += 1
            else:
                ok = False
        if placed == 0:
            print(f"    WARNING: no table carried row '{base}'", file=sys.stderr); ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
