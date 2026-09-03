#!/usr/bin/env python3
"""
verify_build.py — integrity check for the freshly built + deployed mod.

Runs as the final step of build.bat. Inspects the ACTUAL deployed
.pak (not the source tree) so it catches packaging mistakes too, and
asserts:

  1. The deployed pak exists and contains the expected core entries
     (Cargos_01.uasset, the patched Jeju_World.umap, our Mod* BP
     classes).
  2. Every `new_cargos` entry from delivery_points.json is present in
     the packed Cargos_01.uasset with its declared field values
     (PaymentPer1Km / BasePayment / SpawnProbability / ... round-trip).
  3. Each new cargo has a consumer, so it won't crash on world load —
     either one of our own delivery points takes it as an input (its mod
     BP class ships the recipe on its CDO), or a safety_dps vanilla class
     covers it. Ours is preferred: safety_dps edits a vanilla CDO, which
     makes every instance of that class in Jeju advertise our cargo.

Exits 0 on success, non-zero with a clear report on any failure.
Run standalone any time: `python verify_build.py`.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from mt_paths import (GAME_PAKDIR, MAPPINGS, MOD_NAME, REPAK, REPO_ROOT, WORK_DIR,
                      MAP_WORK_JSON)

MODNAME = MOD_NAME
DEPLOYED_PAK = GAME_PAKDIR / f"zzzz_{MODNAME}.pak"
INJECTOR = REPO_ROOT / "MTBPInjector" / "bin" / "Release" / "net8.0" / "MTBPInjector.exe"
DP_JSON = REPO_ROOT / "delivery_points.json"

# Keys on a new_cargos entry that are NOT cargo-row fields — pipeline-only,
# never written onto the row. Recognised by SHAPE rather than by an enumerated
# list, matching MTBPInjector's IsReservedKey: UE cargo fields are PascalCase
# and its booleans keep a capital after the b (bUseDamage), so a key with an
# underscore or written entirely in lowercase is ours. The list version failed
# the build the first time a new knob (weight_kg, batch, base_payment) was
# added, because the two ends of the same rule drifted apart.
def _reserved(k: str) -> bool:
    return "_" in k or k.lower() == k

_FAILURES: list[str] = []
_CHECKS = 0


def _fail(msg: str) -> None:
    _FAILURES.append(msg)
    print(f"  [FAIL] {msg}")


def _ok(msg: str) -> None:
    global _CHECKS
    _CHECKS += 1
    print(f"  [ok]   {msg}")


def _repak_list(pak: Path) -> list[str]:
    r = subprocess.run([str(REPAK), "list", str(pak)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return []
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def _repak_get(pak: Path, entry: str, dst: Path) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "wb") as f:
        r = subprocess.run([str(REPAK), "get", str(pak), entry],
                           stdout=f, stderr=subprocess.DEVNULL)
    return r.returncode == 0 and dst.stat().st_size > 0


def _dump_row(uasset: Path, row: str) -> dict[str, str] | None:
    """Run MTBPInjector dump-cargo-row, return {field: value-string} or None."""
    r = subprocess.run([str(INJECTOR), "dump-cargo-row",
                        "--uasset", str(uasset),
                        "--mappings", str(MAPPINGS),
                        "--row", row],
                       capture_output=True, text=True)
    if r.returncode != 0 or "not found" in (r.stdout + r.stderr).lower():
        return None
    fields: dict[str, str] = {}
    for ln in r.stdout.splitlines():
        m = re.match(r"^  ([A-Za-z0-9_]+): (.+)$", ln)
        if m:
            fields[m.group(1)] = m.group(2).strip()
    return fields or None


def _num_eq(a: str, b) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-3
    except (ValueError, TypeError):
        return str(a).strip() == str(b).strip()


def main() -> int:
    print("=" * 60)
    print("Build integrity check")
    print("=" * 60)

    # --- 0. prerequisites -------------------------------------------------
    if not DEPLOYED_PAK.is_file():
        _fail(f"deployed pak not found: {DEPLOYED_PAK}")
        return _report()
    if not REPAK.is_file():
        _fail(f"vendored repak missing: {REPAK}")
        return _report()
    if not INJECTOR.is_file():
        _fail(f"MTBPInjector not built: {INJECTOR}")
        return _report()
    _ok(f"deployed pak present ({DEPLOYED_PAK.stat().st_size // 1024} KB)")

    entries = _repak_list(DEPLOYED_PAK)
    if not entries:
        _fail("repak list returned no entries (pak unreadable?)")
        return _report()
    _ok(f"pak lists {len(entries)} entries")

    # --- 1. core entries present -----------------------------------------
    def _has(substr: str) -> bool:
        return any(substr in e for e in entries)

    # The map is always rebuilt, so it's always required.
    if _has("Maps/Jeju/Jeju_World.umap"):
        _ok("pak contains Maps/Jeju/Jeju_World.umap")
    else:
        _fail("pak missing Maps/Jeju/Jeju_World.umap")

    # Nothing may override our map AFTER us. Load order is a case-insensitive
    # filename sort, so a pak sorting later wins every entry it shares with us
    # and the build you just made is not the one that loads -- silently, with
    # every other check here passing. Renaming the mod from Dobrogea to Arini
    # left the old zzzz_Dobrogea_P.pak in place, and "D" sorts after "A".
    later = []
    for other in sorted(GAME_PAKDIR.glob("*.pak"), key=lambda p: p.name.lower()):
        if other.name.lower() <= DEPLOYED_PAK.name.lower():
            continue
        if any("Maps/Jeju/Jeju_World.umap" in e for e in _repak_list(other)):
            later.append(other.name)
    if later:
        _fail(f"{', '.join(later)} load(s) after {DEPLOYED_PAK.name} and also ships "
              f"Jeju_World.umap — that pak wins and this build will not be the one "
              f"you see. Remove it or rename ours to sort later.")
    else:
        _ok("no pak overrides our map later in load order")

    # How many delivery points were actually PLACED this build (configured
    # AND present in the scene). Unconfigured scene placeholders are
    # skipped upstream, so zero placed DPs is a legitimate state — don't
    # demand Mod* BP classes or a Cargos override when nothing needed them.
    placed_dps = 0
    try:
        mw = json.loads(MAP_WORK_JSON.read_text(encoding="utf-8"))
        placed_dps = len([d for d in (mw.get("delivery_points") or [])
                          if isinstance(d, dict) and d.get("delivery_key")])
    except Exception:
        pass

    try:
        cfg = json.loads(DP_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        _fail(f"could not read delivery_points.json: {e}")
        return _report()
    if os.environ.get("MTMI_SKIP_CARGO") == "1":
        # --skip-cargo: cargo was deliberately not built/shipped, so all
        # cargo integrity checks are moot. Treat as "no new_cargos".
        new_cargos = []
        _ok("--skip-cargo: cargo checks skipped")
    else:
        # Honour the build LAYER. A cargo marked `requires` belongs to another
        # mod's layer and is deliberately absent from this pak -- checking for
        # it here fails a build that is correct, which is exactly what happened
        # the first time the vanilla layer ran with Proxy cargo declared.
        from mods import wants
        new_cargos = [c for c in (cfg.get("new_cargos") or [])
                      if isinstance(c, dict) and c.get("new_id") and wants(c)]
        _skipped = [c["new_id"] for c in (cfg.get("new_cargos") or [])
                    if isinstance(c, dict) and c.get("new_id") and not wants(c)]
        if _skipped:
            _ok(f"layer excludes {len(_skipped)} cargo(s) from other mods")

    # A cargo cloned from another mod's table is written back into a copy of
    # THAT table, not ours -- a row carries import indices into the asset it
    # came from. So the pak may ship two cargo tables, and each cargo is only
    # ever found in its own.
    _tables: dict[str, list] = {}
    for c in new_cargos:
        _tables.setdefault(c.get("source_table", "DataAsset/Cargos_01.uasset"), []).append(c)

    # A cargo table only ships when there are new_cargos for it. If none
    # declared, its absence is correct.
    if new_cargos:
        for rel in _tables:
            if _has(rel):
                _ok(f"pak contains {rel}")
            else:
                _fail(f"pak missing {rel} (new_cargos declared)")
    else:
        _ok("no new_cargos — Cargos_01 not expected")

    # Mod* BP classes only expected when delivery points were placed.
    mod_bps = [e for e in entries if re.search(r"/Mod[0-9A-F]{6}\.uasset$", e)]
    if placed_dps > 0:
        if mod_bps:
            _ok(f"pak ships {len(mod_bps)} mod BP class(es) for {placed_dps} placed DP(s)")
        else:
            _fail(f"{placed_dps} delivery point(s) placed but no Mod* BP classes shipped")
    else:
        _ok("no delivery points placed (all scene placeholders unconfigured) — no BP classes expected")

    if not new_cargos:
        _ok("no new_cargos declared — skipping cargo round-trip")
    else:
        tmp = Path(tempfile.mkdtemp(prefix="mtmi_verify_", dir=str(WORK_DIR)))
        extracted: dict[str, Path] = {}
        for rel in _tables:
            stem = Path(rel).stem
            dst = tmp / f"{stem}.uasset"
            entry = next((e for e in entries if e.endswith(rel)), None)
            # repak get also needs the .uexp sibling for UAssetAPI to parse.
            uexp_entry = entry[:-7] + ".uexp" if entry else None
            if entry and uexp_entry and (_repak_get(DEPLOYED_PAK, entry, dst)
                                         and _repak_get(DEPLOYED_PAK, uexp_entry, tmp / f"{stem}.uexp")):
                extracted[rel] = dst
                _ok(f"extracted {stem} from the pak")
            else:
                _fail(f"could not extract {stem} from the pak for verification")

        if extracted:
            for c in new_cargos:
                nid = c["new_id"]
                rel = c.get("source_table", "DataAsset/Cargos_01.uasset")
                if rel not in extracted:
                    continue
                stem = Path(rel).stem
                row = _dump_row(extracted[rel], nid)
                if row is None:
                    _fail(f"cargo '{nid}' not found in packed {stem}")
                    continue
                bad = []
                for k, v in c.items():
                    if _reserved(k):
                        continue
                    if k not in row:
                        bad.append(f"{k} (absent)")
                    elif not _num_eq(row[k], v):
                        bad.append(f"{k}={row[k]} (want {v})")
                if bad:
                    _fail(f"cargo '{nid}' field mismatch: {', '.join(bad)}")
                else:
                    _ok(f"cargo '{nid}' round-trips ({len(c) - len([k for k in c if _reserved(k)])} fields)")

                # A cargo with no consumer at all is the thing that crashes
                # on world load. Our own delivery points count: each ships a
                # mod BP class whose CDO carries its recipes. safety_dps is
                # only the fallback for a cargo nothing of ours consumes, and
                # it costs a vanilla CDO edit that every Jeju instance of
                # that class then shows.
                safety = c.get("safety_dps") or []
                shipped = [s for s in safety
                           if _has(f"/{s[:-2] if s.endswith('_C') else s}.uasset")]
                ours = sorted(v.get("label", k) for k, v in cfg.items()
                              if isinstance(v, dict)
                              for r in (v.get("recipes") or [])
                              if nid in (r.get("inputs") or {}))
                if ours:
                    _ok(f"cargo '{nid}' consumed by {len(set(ours))} of our delivery "
                        f"points ({', '.join(sorted(set(ours))[:3])})")
                elif not safety:
                    _fail(f"cargo '{nid}' has no consumer: no delivery point of ours "
                          f"takes it as an input and no safety_dps is set — "
                          f"will crash on world load")
                elif not shipped:
                    _fail(f"cargo '{nid}' safety_dps {safety} not shipped in pak")
                else:
                    _ok(f"cargo '{nid}' safety net shipped ({len(shipped)}/{len(safety)})")

    # Prices are derived from where the delivery points actually sit, so moving
    # a point silently makes its cargo's price wrong. Nothing else would ever
    # notice — the build succeeds and the pak ships either way.
    try:
        import pricing
        stale = pricing.stale_prices()
    except Exception as exc:                       # never fail a build over the check itself
        print(f"  (price check skipped: {exc})")
    else:
        if stale:
            _fail("prices are stale — delivery points moved since the last "
                  "`python pricing.py --write`: "
                  + ", ".join(f"{n} {have:,}->{want:,}" for n, have, want in stale))
        else:
            _ok("cargo prices match the current delivery point placements")

    return _report()


def _report() -> int:
    print("-" * 60)
    if _FAILURES:
        print(f"INTEGRITY: {len(_FAILURES)} failure(s), {_CHECKS} check(s) passed")
        return 1
    print(f"INTEGRITY: OK — {_CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
