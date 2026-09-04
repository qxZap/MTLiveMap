#!/usr/bin/env python3
"""prune_unused_assets.py -- drop staged assets nothing in the pak refers to.

    python prune_unused_assets.py <mod content dir>            # report only
    python prune_unused_assets.py <mod content dir> --apply    # delete them

WHY THIS EXISTS
    build.bat's clean step wipes three folders: _Generated_, DC/Actors and the
    DeliveryPoint tree. Everything else in the staging tree accumulates. A mesh
    painted into the scene once and deleted a week later keeps shipping
    forever, because nothing ever removes it -- the pak only grows.

HOW IT DECIDES
    The MAP is the root. A cell that places a mesh names that mesh's package,
    a mesh names its materials, a material names its textures. So the set of
    things that matter is the transitive closure of package names reachable
    from the maps and the data assets, and anything staged outside that
    closure is unreachable at runtime.

    References are found by scanning each file's bytes for /Game/ package
    paths rather than by parsing exports. That is deliberate: it catches SOFT
    references -- a cargo row's ActorClass, a blueprint's asset pointer -- that
    an import-table walk would miss entirely, and it fails in the safe
    direction. A stray string that merely looks like a package path keeps an
    asset alive; it never deletes a live one.

WHAT IT WILL NOT TOUCH
    Maps, DataAsset, the DeliveryPoint classes, Config and UI are roots, not
    candidates. Neither is anything reachable from them.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Package paths as they appear inside cooked assets. The trailing character
# class stops at the FName terminator, and duplicated Object.Object suffixes
# ("/Game/X/SM_Y.SM_Y") are trimmed to the package.
PKG = re.compile(rb"/Game/([A-Za-z0-9_/\-]+)")

# Trees that are roots by definition: the map places actors, the data assets
# drive the economy, the BP classes are the delivery points, UI is the world
# map, Config is engine settings. None of these are candidates for removal.
ROOT_DIRS = ("Maps", "DataAsset", "Objects", "UI", "Config")

# Only these carry references worth scanning. .ubulk is bulk pixel/vertex data
# with no names in it, and it is where the megabytes are.
SCAN_SUFFIX = (".uasset", ".uexp", ".umap")


def package_of(rel: str) -> str:
    """'DC/Meshes/Nature/SM_Tree_05' from any of its file forms."""
    return rel.rsplit(".", 1)[0] if "." in rel.rsplit("/", 1)[-1] else rel


def refs_in(path: Path) -> set[str]:
    try:
        data = path.read_bytes()
    except OSError:
        return set()
    out = set()
    for m in PKG.finditer(data):
        p = m.group(1).decode("ascii", "ignore")
        # "/Game/DC/Meshes/SM_X.SM_X" -> "DC/Meshes/SM_X"; the regex already
        # stops at the dot, so this only trims a trailing slash.
        out.add(p.rstrip("/"))
    return out


def stem_key(p: Path, content: Path) -> str:
    return p.relative_to(content).with_suffix("").as_posix()


def closure(content: Path) -> tuple[set[str], dict[str, list[Path]]]:
    """(reachable package names, package -> files on disk)."""
    files: dict[str, list[Path]] = {}
    for p in content.rglob("*"):
        if p.is_file():
            files.setdefault(stem_key(p, content), []).append(p)

    frontier = {k for k in files
                if any(k == d or k.startswith(d + "/") for d in ROOT_DIRS)}
    seen: set[str] = set()
    while frontier:
        key = frontier.pop()
        if key in seen:
            continue
        seen.add(key)
        for f in files.get(key, ()):
            if f.suffix.lower() not in SCAN_SUFFIX:
                continue
            for r in refs_in(f):
                if r not in seen and r in files:
                    frontier.add(r)
    return seen, files


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    content = Path(sys.argv[1])
    if not content.is_dir():
        print(f"  no content dir at {content}", file=sys.stderr)
        return 1
    apply = "--apply" in sys.argv

    seen, files = closure(content)
    dead = {k: v for k, v in files.items() if k not in seen}
    if not dead:
        print("  every staged asset is reachable from the map")
        return 0

    total = sum(f.stat().st_size for v in dead.values() for f in v)
    print(f"  {len(dead)} unreachable asset(s), {total / 1048576:,.1f} MB")
    import collections
    by_dir = collections.Counter()
    for k, v in dead.items():
        by_dir[k.rsplit("/", 1)[0] if "/" in k else "."] += sum(f.stat().st_size for f in v)
    for d, sz in by_dir.most_common(10):
        print(f"    {sz / 1048576:>8.1f} MB  {d}")

    if not apply:
        print("\n  (report only -- pass --apply to delete)")
        return 0
    n = 0
    for v in dead.values():
        for f in v:
            f.unlink(missing_ok=True)
            n += 1
    for d in sorted((p for p in content.rglob("*") if p.is_dir()),
                    key=lambda p: len(p.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()
    print(f"\n  deleted {n} file(s), {total / 1048576:,.1f} MB")
    return 0


def _selfcheck() -> None:
    """A mesh the map places survives with its material; an orphan does not."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        c = Path(td)
        def w(rel: str, body: bytes = b""):
            p = c / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body)
        w("Maps/Jeju/Jeju_World.umap", b"junk/Game/DC/Meshes/SM_Used\x00more")
        w("DC/Meshes/SM_Used.uasset", b"mat/Game/DC/Materials/MI_Used\x00")
        w("DC/Meshes/SM_Used.ubulk", b"\x00" * 10)
        w("DC/Materials/MI_Used.uasset", b"tex/Game/DC/Textures/T_Used\x00")
        w("DC/Textures/T_Used.uasset", b"leaf")
        w("DC/Meshes/SM_Orphan.uasset", b"nobody refers to me")
        w("DC/Meshes/SM_Orphan.ubulk", b"\x00" * 99)
        seen, files = closure(c)
        dead = {k for k in files if k not in seen}
        assert dead == {"DC/Meshes/SM_Orphan"}, dead
        # the used chain, including the bulk sibling, is untouched
        for k in ("DC/Meshes/SM_Used", "DC/Materials/MI_Used", "DC/Textures/T_Used"):
            assert k in seen, k
        print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        raise SystemExit(main())
