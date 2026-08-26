#!/usr/bin/env python3
"""
economy_report.py — write the island economy out as a readable page.

Generated from delivery_points.json + the vanilla cargo catalog, so it can
never drift from what the build actually ships. Answers the only question
that matters while you are sat in a truck: where do I get X, and who buys it.

    python economy_report.py [-o economy.html]
"""
from __future__ import annotations

import argparse
import collections
import glob
import html
import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parent
DP_JSON = REPO / "delivery_points.json"
CATALOG = REPO / "CargoImport" / "cargos" / "catalog.json"
SHARDS = REPO / "static_meshes_parts"


def load():
    d = json.loads(DP_JSON.read_text(encoding="utf-8"))
    cat = {r["Name"]: r for r in json.loads(CATALOG.read_text(encoding="utf-8"))}
    custom = {c["new_id"]: c for c in d.get("new_cargos") or []}
    dps = {k: v for k, v in d.items() if isinstance(v, dict) and "recipes" in v}
    return d, cat, custom, dps


def coords(dps) -> dict:
    """World XY per delivery point, from the editor placeholders + any
    explicit "world" override. Missing coords just drop the distance column
    rather than failing the report."""
    try:
        from mt_paths import IMPORT_OFFSET_X as OX, IMPORT_OFFSET_Y as OY
    except Exception:
        OX = OY = 0.0
    co = {}
    for f in glob.glob(str(SHARDS / "sm_*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                if "elivery" not in line:
                    continue
                r = json.loads(line)
                k = r.get("asset_key", "")
                for p in ("DeliveryPoint_", "Delivery_Point_"):
                    if k.startswith(p):
                        co[k[len(p):]] = (r["X"] + OX, r["Y"] + OY)
    for k, v in dps.items():
        if isinstance(v.get("world"), list):
            co[k] = tuple(v["world"][:2])
    return co


def price(name, cat, custom):
    """(flat, per_km). Our cargo is flat; vanilla still scales by distance."""
    r = cat.get(name) or custom.get(name) or {}
    return r.get("BasePayment", 0), r.get("PaymentPer1Km", 0)


def build(dps, cat, custom, co):
    prod = collections.defaultdict(list)
    cons = collections.defaultdict(list)
    for k, v in dps.items():
        for r in v["recipes"]:
            for c, n in (r.get("outputs") or {}).items():
                prod[c].append((k, n))
            for c, n in (r.get("inputs") or {}).items():
                cons[c].append((k, n))
    return prod, cons


def km(co, a, b):
    if a not in co or b not in co:
        return None
    return math.dist(co[a], co[b]) / 100000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=str(REPO / "economy.html"))
    args = ap.parse_args()

    d, cat, custom, dps = load()
    co = coords(dps)
    prod, cons = build(dps, cat, custom, co)
    lab = {k: v.get("label", k.replace("_", " ")) for k, v in dps.items()}
    e = html.escape

    rows = []
    for c in sorted(set(prod) | set(cons)):
        flat, per_km = price(c, cat, custom)
        mine = c in custom
        srcs = sorted({lab[k] for k, _ in prod[c]})
        dsts = sorted({lab[k] for k, _ in cons[c]})
        # Best-paying run for this cargo, so the table answers "worth it?".
        best = ""
        if flat and not per_km:
            best = f"{flat:,} flat"
        else:
            far = None
            for s, _ in prod[c]:
                for t, _ in cons[c]:
                    if s == t:
                        continue
                    dist = km(co, s, t)
                    if dist and (far is None or dist > far[0]):
                        far = (dist, s, t)
            if far:
                best = f"{per_km * far[0] + flat:,.0f} over {far[0]:.1f} km"
            elif per_km:
                best = f"{per_km:,.0f}/km"
        rows.append((c, mine, srcs, dsts, best))

    def cargo_table():
        out = []
        for c, mine, srcs, dsts, best in rows:
            tag = ' <span class="tag">mod</span>' if mine else ""
            out.append(
                f"<tr><td class=c>{e(c)}{tag}</td>"
                f"<td>{e(', '.join(srcs)) or '<em>imported from Jeju</em>'}</td>"
                f"<td>{e(', '.join(dsts)) or '<em>nobody</em>'}</td>"
                f"<td class=n>{e(best)}</td></tr>")
        return "\n".join(out)

    def dp_cards():
        out = []
        for k in sorted(dps, key=lambda x: lab[x]):
            recs = []
            for r in dps[k]["recipes"]:
                i = r.get("inputs") or {}
                o = r.get("outputs") or {}
                fmt = lambda m: ", ".join(f"{n}&times;{v}" for n, v in m.items())
                left = fmt(i) if i else '<em class="free">nothing &mdash; it just grows</em>'
                boost = ' <span class="tag hot">5&times;</span>' if r.get("speed", 1) >= 5 else ""
                recs.append(f"<li>{left} &rarr; <b>{fmt(o)}</b>"
                            f" <span class=t>{r['time_seconds']:.0f}s</span>{boost}</li>")
            out.append(f'<article><h3>{e(lab[k])}</h3><ul>{"".join(recs)}</ul></article>')
        return "\n".join(out)

    n_custom = len(custom)
    # A freight docket, not a brochure: cool paper stock, haulage green,
    # safety orange reserved for the one thing that means "this runs hot".
    page = f"""<title>Island Freight Manifest</title>
<style>
:root {{
  --paper:#f1f3f0; --card:#fafbf9; --ink:#141817; --muted:#5c6663;
  --line:#d4d9d4; --rule:#b9c0b9; --accent:#1d6b58; --hot:#bd4f18;
  --chip:#e4e8e3; --focus:#1d6b58;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --paper:#101413; --card:#181d1b; --ink:#e4e9e5; --muted:#8e9994;
    --line:#272e2b; --rule:#39423e; --accent:#54c1a2; --hot:#e2865c;
    --chip:#222826; --focus:#54c1a2;
  }}
}}
:root[data-theme="dark"] {{
  --paper:#101413; --card:#181d1b; --ink:#e4e9e5; --muted:#8e9994;
  --line:#272e2b; --rule:#39423e; --accent:#54c1a2; --hot:#e2865c;
  --chip:#222826; --focus:#54c1a2;
}}
* {{ box-sizing:border-box }}
body {{ background:var(--paper); color:var(--ink); margin:0;
  font:16px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased }}
.wrap {{ max-width:1120px; margin:0 auto; padding:3.5rem 1.25rem 6rem;
  display:flex; flex-direction:column; gap:2.75rem }}
header {{ display:flex; flex-direction:column; gap:.5rem;
  border-bottom:3px double var(--rule); padding-bottom:1.5rem }}
.eyebrow {{ font-size:.7rem; font-weight:700; letter-spacing:.22em;
  text-transform:uppercase; color:var(--accent) }}
h1 {{ font-size:clamp(1.9rem,4vw,2.6rem); margin:0; letter-spacing:-.025em;
  font-weight:800; text-wrap:balance }}
.stats {{ display:flex; flex-wrap:wrap; gap:.4rem 1.75rem; margin:.35rem 0 0;
  padding:0; list-style:none; font-size:.85rem; color:var(--muted) }}
.stats b {{ color:var(--ink); font-variant-numeric:tabular-nums;
  font-size:1.05rem; margin-right:.3rem }}
section {{ display:flex; flex-direction:column; gap:1rem }}
h2 {{ font-size:.78rem; text-transform:uppercase; letter-spacing:.18em;
  color:var(--muted); margin:0; font-weight:700 }}
.find {{ display:flex; align-items:baseline; gap:.75rem; flex-wrap:wrap }}
input {{ flex:1 1 16rem; min-width:0; font:inherit; font-size:.95rem;
  padding:.55rem .8rem; color:var(--ink); background:var(--card);
  border:1px solid var(--line); border-radius:5px }}
input::placeholder {{ color:var(--muted) }}
input:focus-visible {{ outline:2px solid var(--focus); outline-offset:1px }}
.scroll {{ overflow-x:auto }}
table {{ border-collapse:collapse; width:100%; min-width:680px; font-size:.9rem }}
thead th {{ position:sticky; top:0; background:var(--paper); text-align:left;
  font-size:.68rem; font-weight:700; letter-spacing:.14em; text-transform:uppercase;
  color:var(--muted); padding:.55rem .7rem; border-bottom:2px solid var(--rule) }}
tbody td {{ padding:.5rem .7rem; border-bottom:1px solid var(--line);
  vertical-align:top }}
tbody tr:hover td {{ background:var(--card) }}
td.c {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  font-size:.85rem; white-space:nowrap }}
td.n {{ text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums;
  color:var(--muted) }}
td.n b {{ color:var(--ink); font-weight:600 }}
em {{ color:var(--muted); font-style:italic }}
.tag {{ display:inline-block; font-size:.62rem; font-weight:700;
  text-transform:uppercase; letter-spacing:.1em; background:var(--chip);
  color:var(--muted); padding:.12rem .4rem; border-radius:3px;
  vertical-align:.08em; margin-left:.35rem }}
.tag.hot {{ background:var(--hot); color:#fff }}
.grid {{ display:grid; gap:.85rem;
  grid-template-columns:repeat(auto-fill,minmax(290px,1fr)) }}
article {{ background:var(--card); border:1px solid var(--line);
  border-left:3px solid var(--accent); border-radius:4px; padding:.9rem 1.05rem;
  display:flex; flex-direction:column; gap:.55rem }}
article h3 {{ margin:0; font-size:.95rem; font-weight:700; letter-spacing:-.01em }}
article ul {{ margin:0; padding:0; list-style:none; display:flex;
  flex-direction:column; gap:.4rem; font-size:.85rem }}
article li {{ padding-left:.85rem; position:relative; line-height:1.45 }}
article li::before {{ content:""; position:absolute; left:0; top:.55em;
  width:5px; height:1px; background:var(--rule) }}
.t {{ color:var(--muted); font-size:.75rem; font-variant-numeric:tabular-nums }}
.free {{ color:var(--accent); font-style:normal; font-weight:600 }}
.empty {{ color:var(--muted); font-size:.9rem; padding:1rem 0 }}
[hidden] {{ display:none !important }}
</style>
<div class="wrap">
<header>
  <span class="eyebrow">Motor Town &middot; Island</span>
  <h1>Freight Manifest</h1>
  <ul class="stats">
    <li><b>{len(dps)}</b> delivery points</li>
    <li><b>{len(rows)}</b> cargo types</li>
    <li><b>{n_custom}</b> ours</li>
  </ul>
</header>

<section>
  <div class="find">
    <h2>Where do I get it &middot; who buys it</h2>
    <input id="q" type="search" placeholder="Filter by cargo or place &mdash; try water"
           aria-label="Filter cargo and delivery points">
  </div>
  <div class="scroll"><table>
    <thead><tr><th>Cargo</th><th>Load at</th><th>Drop at</th><th>Pays</th></tr></thead>
    <tbody id="cargo">
{cargo_table()}
    </tbody>
  </table></div>
  <p class="empty" id="none" hidden>Nothing matches that.</p>
</section>

<section>
  <h2>Every delivery point</h2>
  <div class="grid" id="places">
{dp_cards()}
  </div>
</section>
</div>
<script>
// One box filters both views: in a truck you want the answer, not navigation.
var q = document.getElementById("q");
var rows = [].slice.call(document.querySelectorAll("#cargo tr"));
var cards = [].slice.call(document.querySelectorAll("#places article"));
var none = document.getElementById("none");
q.addEventListener("input", function () {{
  var t = q.value.trim().toLowerCase();
  var shown = 0;
  rows.forEach(function (r) {{
    var hit = !t || r.textContent.toLowerCase().indexOf(t) !== -1;
    r.hidden = !hit;
    if (hit) shown++;
  }});
  cards.forEach(function (c) {{
    c.hidden = !!t && c.textContent.toLowerCase().indexOf(t) === -1;
  }});
  none.hidden = shown > 0;
}});
</script>"""
    Path(args.out).write_text(page, encoding="utf-8")
    print(f"  economy report -> {args.out} ({len(dps)} DPs, {len(rows)} cargos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
