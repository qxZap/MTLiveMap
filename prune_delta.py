#!/usr/bin/env python3
"""prune_delta.py -- strip a compat layer's staging down to what it patches.

    python prune_delta.py <mod content dir>

WHY THIS EXISTS
    A compat layer mounts AFTER the base pak, so every file it ships wins.
    That is the point for the cargo tables and the delivery-point classes,
    and a disaster for anything else: a layer built with foliage skipped
    carried a foliage-less copy of the island's cells, and because it loads
    last, it took the base build's foliage down with it. The paks were also
    ~900 MB of map nobody needed.

    The build still GENERATES a map for a layer -- step 3 writes one on its
    way to producing the Mod* classes -- so the map is removed here rather
    than never made. Pruning after the fact also means a new build step that
    writes somewhere unexpected cannot quietly reintroduce the problem.

WHAT SURVIVES
    DataAsset/**            cargo tables, string table, vehicles
    .../DeliveryPoint/Mod*  the delivery-point classes, whose recipes are the
                            whole reason a layer exists

    The Mod* class name is sha1(delivery point key), identical in every
    layer, so the base map's actors already point at the class shipped here.
    Nothing else needs to travel.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

KEEP_DIRS = ("DataAsset",)
KEEP_GLOBS = ("Objects/Mission/Delivery/DeliveryPoint/Mod*",)


def keepers(root: Path) -> set[Path]:
    keep: set[Path] = set()
    for d in KEEP_DIRS:
        p = root / d
        if p.is_dir():
            keep.add(p)
    for g in KEEP_GLOBS:
        keep.update(p for p in root.glob(g) if p.exists())
    return keep


def prune(root: Path) -> tuple[int, int]:
    """Delete everything outside the keep set. Returns (removed, kept bytes)."""
    keep = keepers(root)
    removed = 0

    def under_keep(p: Path) -> bool:
        return any(p == k or k in p.parents for k in keep)

    # Walk top-down and prune whole subtrees, so a 2 500-file map directory
    # costs one rmtree rather than one unlink per cell.
    def walk(d: Path) -> None:
        nonlocal removed
        for child in sorted(d.iterdir()):
            if under_keep(child):
                continue
            if any(child in k.parents for k in keep):
                walk(child)          # holds a keeper deeper down
                continue
            if child.is_dir():
                n = sum(1 for _ in child.rglob("*") if _.is_file())
                shutil.rmtree(child, ignore_errors=True)
                removed += n
            else:
                child.unlink(missing_ok=True)
                removed += 1

    walk(root)
    # Drop directories the pruning emptied, so the pak has no hollow branches.
    for d in sorted((p for p in root.rglob("*") if p.is_dir()),
                    key=lambda p: len(p.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()
    kept = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    return removed, kept


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"  no staging dir at {root}", file=sys.stderr)
        return 1
    removed, kept = prune(root)
    files = sum(1 for p in root.rglob("*") if p.is_file())
    print(f"  delta: dropped {removed} file(s), kept {files} "
          f"({kept / 1024 / 1024:.1f} MB)")
    if not files:
        print("  nothing left to ship -- the layer would be an empty pak",
              file=sys.stderr)
        return 1
    return 0


def _selfcheck() -> None:
    """A layer that generated a map keeps its data and loses the island."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for rel in ("DataAsset/Cargos_01.uasset",
                    "DataAsset/StringTables/ModCargo.uasset",
                    "Objects/Mission/Delivery/DeliveryPoint/Mod87847F.uasset",
                    "Objects/Mission/Delivery/DeliveryPoint/Farm_Corn.uasset",
                    "Maps/Jeju/Jeju_World.umap",
                    "Maps/Jeju/Jeju_World/_Generated_/cell_0_0.umap",
                    "DC/Physics/PM_Arini_Snow.uasset"):
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x")
        prune(root)
        left = {str(p.relative_to(root)).replace("\\", "/")
                for p in root.rglob("*") if p.is_file()}
        assert left == {
            "DataAsset/Cargos_01.uasset",
            "DataAsset/StringTables/ModCargo.uasset",
            "Objects/Mission/Delivery/DeliveryPoint/Mod87847F.uasset",
        }, left
        assert not (root / "Maps").exists()
        print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        raise SystemExit(main())
