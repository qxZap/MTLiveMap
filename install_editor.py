#!/usr/bin/env python3
"""
install_editor.py — one-time setup for the UE-side exporter.

The Motor Town editor's Python runtime is a separate process from the
shell you run the pipeline from, so it can't see `.env` directly. This
script sets MTMI_REPO_ROOT as a USER-LEVEL env var (Windows `setx`) so
the editor inherits it on next launch, and prints the exact one-liner
to paste into the editor's Python console.

Run once from the repo root:

    python install_editor.py

You only need to re-run if you move the repo to a different folder.

Why MTMI_REPO_ROOT? `ue.py` writes `static_meshes.json` to that path
so the rest of the pipeline can pick it up. Without it the exporter
falls back to a hardcoded `D:/MTLiveMap` and warns.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
UE_SCRIPT = REPO / "ue.py"


def _setx(name: str, value: str) -> int:
    """Persist a user-level env var on Windows. `setx` writes to HKCU
    permanently and survives reboot, but does NOT propagate to processes
    already running — the next UE editor launch picks it up."""
    if os.name != "nt":
        sys.stderr.write(f"[install_editor] non-Windows platform — set {name}={value} in your shell rc manually\n")
        return 0
    # shell=True so setx is found on PATH; setx itself is a Windows builtin.
    r = subprocess.run(["setx", name, value], shell=True)
    return r.returncode


def main() -> int:
    if not UE_SCRIPT.is_file():
        sys.stderr.write(f"[install_editor] ue.py not found at {UE_SCRIPT}\n"
                         f"  Run this script from the MTMapInjector repo root.\n")
        return 1

    print("=" * 72)
    print("MTMapInjector — UE editor setup")
    print("=" * 72)
    print(f"  Repo root   : {REPO}")
    print(f"  ue.py target: {UE_SCRIPT}")
    print()

    rc = _setx("MTMI_REPO_ROOT", str(REPO))
    if rc != 0:
        sys.stderr.write(f"[install_editor] setx failed with exit {rc}\n")
        return rc
    print(f"  MTMI_REPO_ROOT set in user env (effective on next editor launch).")
    print()
    print("From the Motor Town editor's Python console (Window -> Developer Tools ->")
    print("Output Log -> switch the dropdown from Cmd to Python), paste:")
    print()
    print(f"    exec(open(r'{UE_SCRIPT}').read())")
    print()
    print("That writes static_meshes.json into the repo root. Then run build.bat")
    print("from a Windows terminal to take it through the rest of the pipeline.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
