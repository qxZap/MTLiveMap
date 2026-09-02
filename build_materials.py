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
import subprocess
import sys
from pathlib import Path

from mt_paths import MOD_CONTENT_ROOT, MAPPINGS, effective_asset

INJECTOR = Path("MTBPInjector/bin/Release/net8.0/MTBPInjector.exe")

REPO = Path(__file__).resolve().parent
CONFIG = REPO / "materials.json"


def main() -> int:
    if not CONFIG.exists():
        print("  materials.json absent — no material changes"); return 0
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    entries = [m for m in (cfg.get("materials") or []) if isinstance(m, dict) and m.get("asset")]
    if not entries:
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
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
