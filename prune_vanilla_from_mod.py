#!/usr/bin/env python3
"""
prune_vanilla_from_mod.py - Remove base-game (vanilla) asset copies from the
mod pak tree.

Earlier builds copied any referenced mesh not found in the sparse
vanilla_extract/ folder into the mod — including vanilla assets (e.g. the
container ship) that already ship in the game pak, bloating the .pak. The
copy step now skips vanilla assets (see import_meshes._is_vanilla), but this
prunes ones shipped by previous builds.

Protected overrides are NEVER touched: the injected Jeju_World map, custom
cargo data, and delivery-point BP classes are intentionally shipped even
though paths under them may also exist in the vanilla pak.

Usage:
    python prune_vanilla_from_mod.py          # dry run (report only)
    python prune_vanilla_from_mod.py --apply  # actually delete
"""
import os
import sys

from import_meshes import _is_vanilla, MOD_CONTENT

# Paths the mod intentionally ships even though they (or their folder) also
# appear in the vanilla pak. Matched as prefixes of the Content-relative path.
PROTECT_PREFIXES = (
    "Maps/",                                    # injected Jeju_World.umap/.uexp
    "DataAsset/",                               # custom Cargos_01 + data tables
    "Objects/Mission/Delivery/DeliveryPoint/",  # custom delivery BP classes
)


def main():
    apply = "--apply" in sys.argv
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root = os.path.join(script_dir, MOD_CONTENT)
    if not os.path.isdir(root):
        print(f"mod content tree not found: {root}")
        return

    deleted = 0
    freed = 0
    kept_custom = 0
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".uasset"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            rel_noext = rel[: -len(".uasset")]
            if rel_noext.startswith(PROTECT_PREFIXES):
                continue
            if not _is_vanilla(rel_noext):
                kept_custom += 1
                continue
            for ext in (".uasset", ".uexp", ".ubulk"):
                sib = full[: -len(".uasset")] + ext
                if os.path.exists(sib):
                    freed += os.path.getsize(sib)
                    if apply:
                        os.remove(sib)
            deleted += 1

    verb = "Pruned" if apply else "Would prune"
    print(f"{verb} {deleted} vanilla asset(s) ({freed / 1e9:.2f} GB); "
          f"kept {kept_custom} custom asset(s).")
    if not apply:
        print("Dry run — pass --apply to delete.")


if __name__ == "__main__":
    main()
