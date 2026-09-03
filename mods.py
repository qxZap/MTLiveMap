#!/usr/bin/env python3
"""
mods.py -- which mods are installed, and what each build layer may see.

    python mods.py                 # what is installed, and which layers can build
    python mods.py --layer vanilla # print the env for that layer (build.bat uses this)

WHY A LAYER IS A SET OF EXCLUSIONS
    mt_paths resolves every vanilla asset through the installed paks, so any mod
    overriding Cargos.uasset silently becomes our baseline. Building the plain
    release on a machine with Capitalist Economy installed would compute prices
    against ITS table and ship them to players who do not have it.

    So a layer is defined by what it must NOT see. `--layer vanilla` hides every
    other mod; `--layer proxy` hides all but Proxy. The mechanism is the
    MTMI_EXCLUDE_PAKS that mt_paths already honours -- this only names the sets.

WHAT IT CANNOT DO
    Detect a mod that ships no pak, or tell two mods apart when one pak's name
    contains the other's (`match` is a filename substring). It reports what it
    matched so a wrong guess is visible rather than silent.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

from mt_paths import GAME_PAKDIR

CONFIG = pathlib.Path(__file__).resolve().parent / "mods.json"


def load():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    return cfg.get("mods") or {}, cfg.get("layers") or {}


def installed(mods) -> dict[str, list[str]]:
    """mod key -> the pak filenames that matched it."""
    paks = sorted(p.name for p in pathlib.Path(GAME_PAKDIR).glob("*.pak"))
    found: dict[str, list[str]] = {}
    for key, m in mods.items():
        pats = m.get("match") or []
        hits = [p for p in paks if any(x.lower() in p.lower() for x in pats)]
        if hits:
            found[key] = hits
    return found


def exclusions(layer_key: str, mods, layers) -> list[str]:
    """The MTMI_EXCLUDE_PAKS fragments for a layer."""
    layer = layers.get(layer_key)
    if layer is None:
        raise SystemExit(f"  no layer '{layer_key}'. Known: {', '.join(layers)}")
    keys = list(layer.get("skip") or [])
    # our own output is never a source, whatever the layer says
    keys += [k for k, m in mods.items() if m.get("always_skip")]
    out: list[str] = []
    for k in keys:
        out += (mods.get(k) or {}).get("match") or []
    return out


def active_layer() -> str:
    """Which layer this build is for. Default vanilla -- the safe one, because
    a layer that sees another mod must be asked for explicitly."""
    return os.environ.get("MTMI_LAYER", "vanilla").strip() or "vanilla"


def visible_mods(layer_key: str | None = None) -> set[str]:
    """Mod keys this layer is allowed to build against."""
    mods, layers = load()
    layer_key = layer_key or active_layer()
    layer = layers.get(layer_key) or {}
    skipped = set(layer.get("skip") or [])
    skipped |= {k for k, m in mods.items() if m.get("always_skip")}
    return {k for k in mods if k not in skipped}


def wants(entry, layer_key: str | None = None) -> bool:
    """True when an entry belongs in this layer.

    `requires` names mod keys from mods.json. No `requires` means it is part of
    the island proper and ships in every layer. This is what keeps Proxy's
    cargo out of the base pak, where those rows do not exist for most players
    and every route referencing them would dangle.
    """
    if not isinstance(entry, dict):
        return True
    need = entry.get("requires")
    if not need:
        return True
    if isinstance(need, str):
        need = [need]
    return set(need) <= visible_mods(layer_key)


def main() -> int:
    mods, layers = load()
    have = installed(mods)

    if "--layer" in sys.argv:
        key = sys.argv[sys.argv.index("--layer") + 1]
        if key not in layers:
            print(f"  no layer '{key}'. Known: {', '.join(layers)}", file=sys.stderr)
            return 1
        missing = [r for r in (layers[key].get("requires") or []) if r not in have]
        if missing:
            print(f"  layer '{key}' needs {missing}, which is not installed here",
                  file=sys.stderr)
            return 1
        # --mod-name prints the pak identity instead of the exclusions, so
        # build.bat can ask for either without parsing.
        if "--mod-name" in sys.argv:
            print(layers[key].get("mod_name", ""))
        else:
            print(",".join(exclusions(key, mods, layers)))
        return 0

    print("  installed:")
    for key, m in mods.items():
        hits = have.get(key)
        mark = "yes" if hits else "no "
        print(f"    [{mark}] {m.get('label', key):<26} {hits[0] if hits else ''}")
        for extra in (hits or [])[1:]:
            print(f"           {'':<26} {extra}")
    print("\n  layers:")
    for key, l in layers.items():
        need = l.get("requires") or []
        blocked = [r for r in need if r not in have]
        state = "BLOCKED, needs " + ", ".join(blocked) if blocked else "can build"
        print(f"    {key:<18} -> {l.get('mod_name'):<22} {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
