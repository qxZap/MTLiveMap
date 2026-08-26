#!/usr/bin/env python3
"""
merge_config.py — ship the console variables the map needs, without
throwing away anyone else's.

Some things the map places only render if a renderer feature is switched
on. Local fog volumes are the case in point: ALocalFogVolume is in MT's
build and the actor injects fine, but nothing draws until
r.SupportLocalFogVolumes is set. MT reads those from
MotorTown/Config/UserEngine.ini inside a pak.

The catch is load order. Our pak is prefixed `zzzz_` so it wins, which
means a bare UserEngine.ini of ours REPLACES the one CapitalistEconomy
ships — silently wiping ~18 economy cvars. So this reads every copy in
the load order, merges them in order, then layers ours on top. Other
mods' settings survive; ours win only for the keys we actually set.

    python merge_config.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from mt_paths import MOD_ROOT, effective_pak_entries

ENTRY = "MotorTown/Config/UserEngine.ini"
OUT = MOD_ROOT / "MotorTown" / "Config" / "UserEngine.ini"

# What this map needs switched on, as {section: {key: value}}.
# Keep this list to things the map genuinely cannot work without —
# it is layered over every other mod's settings, so each entry here is a
# value we take away from the user.
REQUIRED: dict[str, dict[str, str]] = {
    "ConsoleVariables": {
        # Local fog volumes are off by default in a cooked build; without
        # this the actors load and draw nothing.
        "r.SupportLocalFogVolumes": "1",
    },
    # [SystemSettings] is applied at SetBySystemSettingsIni priority, which
    # outranks SetByScalability. That matters here: the game's own
    # BaseScalability.ini turns the ENTIRE volumetric fog system off at the
    # bottom two shadow-quality levels --
    #     [ShadowQuality@0] r.VolumetricFog=0
    #     [ShadowQuality@1] r.VolumetricFog=0
    #     [ShadowQuality@2] r.VolumetricFog=1
    # -- and it is SHADOW quality, not fog quality, that decides. A player on
    # Low or Medium shadows gets no height-fog volumetrics and no Volume-domain
    # materials at all, so the island's fog would silently depend on a setting
    # that has nothing to do with fog. Pin it on instead.
    "SystemSettings": {
        "r.VolumetricFog": "1",
    },
}


def parse_ini(text: str) -> dict[str, dict[str, str]]:
    """Minimal INI reader. Preserves key spelling; last write wins, which
    is what UE does within a single file."""
    out: dict[str, dict[str, str]] = {}
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith((";", "#")):
            continue
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            section = m.group(1)
            out.setdefault(section, {})
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out.setdefault(section, {})[k.strip()] = v.strip()
    return out


def render(cfg: dict[str, dict[str, str]]) -> str:
    parts = []
    for section, kv in cfg.items():
        if not kv:
            continue
        parts.append(f"[{section}]")
        parts.extend(f"{k} = {v}" for k, v in kv.items())
        parts.append("")
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    merged: dict[str, dict[str, str]] = {}
    sources = effective_pak_entries(ENTRY)
    for pak_name, path in sources:
        try:
            cfg = parse_ini(path.read_text(encoding="utf-8", errors="replace"))
        except OSError as e:
            print(f"    {pak_name}: unreadable ({e}) — skipped", file=sys.stderr)
            continue
        n = sum(len(v) for v in cfg.values())
        print(f"    inherit {n:3d} setting(s) from {pak_name}")
        for section, kv in cfg.items():
            merged.setdefault(section, {}).update(kv)

    added = []
    for section, kv in REQUIRED.items():
        for k, v in kv.items():
            prev = merged.get(section, {}).get(k)
            if prev != v:
                added.append(f"{k}={v}" + (f" (was {prev})" if prev is not None else ""))
            merged.setdefault(section, {})[k] = v

    total = sum(len(v) for v in merged.values())
    if args.dry_run:
        print(f"  would write {total} setting(s) to {OUT}")
        print(render(merged))
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(merged), encoding="utf-8")
    print(f"  UserEngine.ini: {total} setting(s) from {len(sources)} pak(s) + "
          f"{len(added)} of ours ({', '.join(added) or 'none new'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
