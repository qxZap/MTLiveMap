#!/usr/bin/env python3
"""
build_materials.py — ship altered physical materials.

    python build_materials.py          # apply materials.json

WHY SNOW DOES NOT GIVE
    Mud and snow both allow digging and both declare a depth range. Mud digs
    at DiggingSpeed 0.5; snow has no DiggingSpeed at all, and an unserialized
    property is its default, which for a float is zero. So snow is a surface
    you drive ON rather than one you sink INTO, however hard you force it.

    Measured from the game's own materials:

        material       DiggingDepth   DiggingSpeed   ResistForce
        PM_Mud         (1, 10)        0.5            3
        PM_MudPuddle   (5, 20)        2              3
        PM_Snow        (1, 5)         absent -> 0    5

    Snow resists at 5 against mud's 3, so matching mud's EFFECTIVE dig rate
    means scaling by that ratio: 0.5 * 5/3 = 0.83. Depth is left at (1, 5),
    half of mud's, so snow sinks at a mud-like rate but bottoms out shallower
    -- which is the difference between snow and mud rather than a compromise.

VANILLA FIRST, THEN A COPY
    Editing PM_Snow itself changes all snow everywhere, which is the fastest
    way to feel whether the number is right. Once it is, the same value moves
    to a new material applied only where it is wanted.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from pathlib import Path

from mt_paths import MOD_CONTENT_ROOT, MAPPINGS, effective_asset

INJECTOR = Path("MTBPInjector/bin/Release/net8.0/MTBPInjector.exe")

REPO = Path(__file__).resolve().parent
CONFIG = REPO / "materials.json"


def _run(args, label):
    r = subprocess.run([str(INJECTOR)] + args, capture_output=True, text=True)
    for line in (r.stdout or "").splitlines():
        if line.strip():
            print(f"  {line}")
    if r.returncode != 0:
        print(f"    {label} FAILED", file=sys.stderr)
        if r.stderr:
            print(r.stderr.rstrip(), file=sys.stderr)
        return False
    return True


def prune_vanilla_overrides(cfg) -> None:
    """Delete shipped copies of VANILLA physical materials we no longer patch.

    Patching a vanilla asset ships a mod-priority override of it, which changes
    that surface everywhere in the game. Deriving a new material instead is the
    whole point -- but the old override does not remove itself, and a build with
    --skip-clean never wipes it. So the pak kept shipping a patched PM_SnowRoad
    long after materials.json stopped asking for one, and every snow road in
    Jeju still dug.

    Only paths OUTSIDE our own DC/ tree are considered: those are vanilla
    identities, and shipping one is always an override.
    """
    keep = {m["asset"].replace("\\", "/") for m in (cfg.get("materials") or [])
            if isinstance(m, dict) and m.get("asset")}
    for f in sorted((MOD_CONTENT_ROOT / "Physics").glob("*.uasset")):
        rel = f"Physics/{f.name}"
        if rel in keep:
            continue
        for ext in (".uasset", ".uexp", ".ubulk"):
            f.with_suffix(ext).unlink(missing_ok=True)
        print(f"    dropped vanilla override {rel} (no longer patched)")


def build_derived(entries) -> bool:
    """Create new materials beside the vanilla ones and point OUR meshes at them.

    Vanilla is never touched. Three steps per entry:

      1. Clone the physical material and RENAME its package. A copy still calls
         itself by its source's path, so without the rename it ships as a
         mod-priority override of the very asset it was derived from.
      2. Clone a Material INSTANCE. A Material carries compiled shaders and
         nothing here can compile one; an instance is pure data that inherits
         its parent's shaders and overrides only PhysMaterial. So the surface
         looks exactly like vanilla and only its physics differ.
      3. Re-point our meshes' material reference. No re-cook, no editor pass.
    """
    ok = True
    for d in entries:
        key = d.get("key") or "?"
        print(f"  [{key}]")
        pm = d.get("physmat") or {}
        mat = d.get("material") or {}
        remap = d.get("remap") or {}

        # 1. physical material
        src = effective_asset(pm["from"] + ".uasset")
        dst = MOD_CONTENT_ROOT / (pm["to"] + ".uasset")
        dst.parent.mkdir(parents=True, exist_ok=True)
        for ext in (".uasset", ".uexp"):
            sp = src.with_suffix(ext)
            if sp.exists():
                dst.with_suffix(ext).write_bytes(sp.read_bytes())
        name = pathlib.PurePosixPath(pm["to"]).name
        pkg = "/Game/" + str(pathlib.PurePosixPath(pm["to"]).parent)
        ok &= _run(["rename-package", "--uasset", str(dst), "--name", name,
                    "--package", pkg, "--mappings", str(MAPPINGS)], "rename-package")
        sets = ",".join(f"{k}={v}" for k, v in (pm.get("set") or {}).items())
        if sets:
            ok &= _run(["set-props", "--uasset", str(dst), "--mappings", str(MAPPINGS),
                        "--set", sets], "set-props")

        # 2. the material. Either we own one already (authored in the editor),
        #    in which case it just needs the physmat wired on; or we derive one.
        if mat.get("existing"):
            target = MOD_CONTENT_ROOT / (mat["existing"] + ".uasset")
            if not target.exists():
                print(f"    {mat['existing']} not shipped yet -- SKIPPED "
                      f"(cook it in the editor, then rebuild)", file=sys.stderr)
                continue
            cmd = ["set-material-physmat", "--uasset", str(target),
                   "--physmat", "/Game/" + pm["to"], "--mappings", str(MAPPINGS)]
            if mat.get("parent"):
                cmd += ["--parent", mat["parent"],
                        "--parent-class", mat.get("parent_class", "Material")]
            ok &= _run(cmd, "set-material-physmat")
            frm = (d.get("remap") or {}).get("from")
            if not frm:
                continue
        tpl = effective_asset(mat["template"] + ".uasset")
        mdst = MOD_CONTENT_ROOT / (mat["to"] + ".uasset")
        mdst.parent.mkdir(parents=True, exist_ok=True)
        tmp = mdst.with_suffix(".template.uasset")
        for ext in (".uasset", ".uexp"):
            sp = tpl.with_suffix(ext)
            if sp.exists():
                tmp.with_suffix(ext).write_bytes(sp.read_bytes())
        mname = pathlib.PurePosixPath(mat["to"]).name
        mpkg = "/Game/" + str(pathlib.PurePosixPath(mat["to"]).parent)
        ok &= _run(["make-material-instance", "--template", str(tmp), "--output", str(mdst),
                    "--name", mname, "--package", mpkg,
                    "--parent", mat["parent"],
                    "--parent-class", mat.get("parent_class", "Material"),
                    "--physmat", "/Game/" + pm["to"], "--mappings", str(MAPPINGS)],
                   "make-material-instance")
        for ext in (".uasset", ".uexp"):
            tmp.with_suffix(ext).unlink(missing_ok=True)

        # 3. re-point the meshes
        frm = remap.get("from")
        if frm:
            n = 0
            for folder in (remap.get("folders") or []):
                root = MOD_CONTENT_ROOT / folder
                for f in sorted(root.rglob("*.uasset")):
                    if frm.encode() not in f.read_bytes():
                        continue
                    if _run(["remap-mesh-material", "--uasset", str(f),
                             "--from", frm, "--to", "/Game/" + mat["to"],
                             "--mappings", str(MAPPINGS)], "remap-mesh-material"):
                        n += 1
                    else:
                        ok = False
            print(f"    {n} mesh(es) re-pointed at {mname}")
    return ok


def main() -> int:
    if not CONFIG.exists():
        print("  materials.json absent — no material changes"); return 0
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    entries = [m for m in (cfg.get("materials") or []) if isinstance(m, dict) and m.get("asset")]
    derived = [d for d in (cfg.get("derived") or []) if isinstance(d, dict)]
    if not entries and not derived:
        print("  no materials declared"); return 0

    ok = True
    for m in entries:
        rel = m["asset"]                      # e.g. Physics/PM_Snow.uasset
        src = effective_asset(rel)
        if not src.is_file():
            print(f"    {rel} not found — skipped", file=sys.stderr); ok = False; continue
        dst = MOD_CONTENT_ROOT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        for ext in (".uasset", ".uexp"):
            sp = src.with_suffix(ext)
            if sp.exists():
                dst.with_suffix(ext).write_bytes(sp.read_bytes())
        sets = ",".join(f"{k}={v}" for k, v in (m.get("set") or {}).items())
        if not sets:
            print(f"    {rel}: nothing to set — skipped", file=sys.stderr); continue
        print(f"  {rel}")
        r = subprocess.run([str(INJECTOR), "set-props", "--uasset", str(dst),
                            "--mappings", str(MAPPINGS), "--set", sets],
                           capture_output=True, text=True)
        for line in (r.stdout or "").splitlines():
            if line.strip(): print(f"  {line}")
        if r.returncode != 0:
            print(r.stderr, file=sys.stderr); ok = False
    for pv in (cfg.get("particle_variants") or []):
        src = effective_asset(pv["template"])
        dst = MOD_CONTENT_ROOT / (pv["to"] + ".uasset")
        dst.parent.mkdir(parents=True, exist_ok=True)
        # the .uexp carries the emitters; copy it beside the output first so the
        # writer has somewhere to put the serialised exports
        sxp = src.with_suffix(".uexp")
        if sxp.exists():
            dst.with_suffix(".uexp").write_bytes(sxp.read_bytes())
        ok &= _run(["make-particle-variant", "--template", str(src), "--output", str(dst),
                    "--name", pathlib.PurePosixPath(pv["to"]).name,
                    "--package", "/Game/" + str(pathlib.PurePosixPath(pv["to"]).parent),
                    "--color", pv.get("color", "1,1,1")]
                   + (["--material", pv["material"]] if pv.get("material") else [])
                   + (["--spawn-scale", str(pv["spawn_scale"])] if pv.get("spawn_scale") else [])
                   + ["--mappings", str(MAPPINGS)], "make-particle-variant")

    for fx in (cfg.get("fx_map_entries") or []):
        src = effective_asset(fx["asset"])
        dst = MOD_CONTENT_ROOT / fx["asset"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            for ext in (".uasset", ".uexp"):
                sp = src.with_suffix(ext)
                if sp.exists():
                    dst.with_suffix(ext).write_bytes(sp.read_bytes())
        ok &= _run(["add-map-entry", "--uasset", str(dst), "--prop", fx["prop"],
                    "--key", fx["key"], "--object", fx["object"],
                    "--object-class", fx.get("object_class", "ParticleSystem"),
                    "--mappings", str(MAPPINGS)], "add-map-entry")

    prune_vanilla_overrides(cfg)
    if derived:
        ok = build_derived(derived) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
