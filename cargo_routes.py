#!/usr/bin/env python3
"""
cargo_routes.py -- every haul on the island, and what it pays.

    python cargo_routes.py            # -> cargo_routes.html

WHAT IT ANSWERS
    "If I take X from A to B, what do I get?" -- which is the question the
    delivery-point config cannot answer on its own, because a cargo's price
    lives on the CARGO ROW while the distance lives between two POINTS.

    Reads the same loaders the build uses (economy_report, pricing), so the
    numbers here are the numbers the game ships. Regenerate after moving a
    delivery point or re-running pricing.py, or the page quietly goes stale.

PAY IS FLAT
    BasePayment is paid whatever the distance -- per-km payment needs a road
    spine the island does not have, so distance only feeds the price when it is
    SET, never when it is paid. Pay/km is therefore not a rate a driver earns;
    it is a diagnostic. A 0.1 km run paying 50,000 is a hole in the economy, and
    two adjacent points that feed each other are a money printer.
"""
from __future__ import annotations

import html
import json
import pathlib

import economy_report as E
import pricing as P

OUT = pathlib.Path(__file__).resolve().parent / "cargo_routes.html"

# A loop is only a problem when it is SHORT AND LUCRATIVE. Galati <-> Braila is
# a two-way trade across the island and entirely legitimate; GroceryBag loops
# over 1.1 km for 362 coins and nobody will farm that. What breaks the economy
# is a high flat fee over a distance you can drive in seconds.
#
# Set from the island's own distribution, not picked: the median route earns
# 3,635/km and p90 is 37,468, so 100,000 is roughly 27x typical. Below that and
# you are flagging ordinary short hauls; the real offenders sit at 128,614 and
# 723,588.
# 100,000 was set by eye and sat above every route anyone actually objected
# to -- a 30 t tower on a 2 km run bills 694,000/km, but so does steel at
# 75,000, and neither tripped it.
ABUSE_RATE = 50_000
# ...and it has to be CLOSE. A loop is not the test: Braila <-> Galati trades
# both ways across 12 km and is exactly what the island is for, while a 2 km
# one-way haul paying 500,000 is farmable whether or not anything comes back.
# So: near AND lucrative, with loops reported separately as information.
NEAR_KM = 3.0


def collect(layer: str | None = None):
    import os
    if layer:
        os.environ["MTMI_LAYER"] = layer
    import importlib
    importlib.reload(E)
    d, cat, custom, dps = E.load()
    co = E.coords(dps)
    prod, cons = E.build(dps, cat, custom, co)
    kgs = P.load_weights()

    # MaxStorage on the destination: how much of this cargo the point will hold
    # before it stops accepting. A generous fee is worthless if the yard fills
    # after two runs, so this belongs next to the price.
    def storage(key):
        v = dps.get(key)
        return int(v["output_storage_cap"]) if isinstance(v, dict) and v.get("output_storage_cap") else None

    def label(key):
        v = dps.get(key)
        if isinstance(v, dict) and v.get("label"):
            return str(v["label"])
        return key.replace("_", " ")

    rows = []
    for name in sorted(set(list(prod) + list(cons))):
        base, perkm = E.price(name, cat, custom)
        c = custom.get(name) or {}
        kg = float(c.get("weight_kg") or kgs.get(name)
                   or kgs.get(c.get("copy_from", "")) or 0)
        for a in sorted({p for p, _ in prod.get(name, [])}):
            for b in sorted({q for q, _ in cons.get(name, [])}):
                if a == b or a not in co or b not in co:
                    continue
                km = E.km(co, a, b)
                pay = int(base + perkm * km)
                rows.append({
                    "cargo": name,
                    "from": label(a), "to": label(b),
                    "km": round(km, 2), "kg": kg, "pay": pay,
                    "store": storage(b),
                    "perkm": int(pay / km) if km >= 0.05 else None,
                    "custom": name in custom,
                })
    # A loop is two points that feed each other. Flat pay plus a short loop is
    # a money printer: shuttle back and forth without ever leaving the yard.
    pairs = {(r["from"], r["to"]) for r in rows}
    for r in rows:
        r["loop"] = (r["to"], r["from"]) in pairs
        r["abuse"] = bool(r["perkm"] and r["perkm"] > ABUSE_RATE and r["km"] < NEAR_KM)
    rows.sort(key=lambda r: -r["pay"])

    # Trade that leaves or enters the island has only one end here, so it forms
    # no producer-to-consumer row and was invisible on this page -- which is
    # most of what the compat layers add. Jeju's construction sites, mines and
    # farms ask for 30 of Proxy's cargos that nothing in the world produces;
    # Arini makes them. These price on Proxy's own per-km rate, not ours, so
    # there is no flat figure to show -- the distance sets it.
    global OFFSHORE
    OFFSHORE = []
    for name in sorted(set(list(prod) + list(cons))):
        if name in custom:
            continue          # ours end to end; already a row above
        here_p = {p for p, _ in prod.get(name, [])}
        here_c = {q for q, _ in cons.get(name, [])}
        if here_p and not here_c:
            OFFSHORE.append({"cargo": name, "dir": "out",
                             "where": ", ".join(sorted(label(k) for k in here_p))})
        elif here_c and not here_p:
            OFFSHORE.append({"cargo": name, "dir": "in",
                             "where": ", ".join(sorted(label(k) for k in here_c))})
    return rows


OFFSHORE: list = []


def offshore_html() -> str:
    if not OFFSHORE:
        return ""
    out = [r for r in OFFSHORE if r["dir"] == "out"]
    inn = [r for r in OFFSHORE if r["dir"] == "in"]
    def block(title, note, items):
        if not items:
            return ""
        rows = "".join(
            f"<tr><td><code>{html.escape(r['cargo'])}</code></td>"
            f"<td>{html.escape(r['where'])}</td></tr>" for r in items)
        return (f"<h3>{title} <span class=t>{len(items)}</span></h3>"
                f"<p class=sub>{note}</p>"
                f"<div class=tablewrap><table><thead><tr><th>Cargo</th>"
                f"<th>On Arini</th></tr></thead><tbody>{rows}</tbody></table></div>")
    return ("<section class=offshore><h2>Trade with Jeju</h2>"
            + block("Made here, wanted there",
                    "Jeju's construction sites, mines and farms ask for these and "
                    "nothing in the game produces them. Pay is Proxy's own per-km "
                    "rate, so the run across the water sets the fee.",
                    out)
            + block("Made there, taken here",
                    "The only cargo Jeju actually produces that Arini buys. "
                    "Same per-km rate on the way over.",
                    inn)
            + "</section>")


CSS = """
:root{
  --paper:#EDF0EF; --card:#F7F9F8; --ink:#12171C;
  --dim:#59676A; --rule:#C9D1CE; --rule-soft:#DDE3E1;
  --amber:#9A6A12; --amber-bg:#F5E9D2; --steel:#3E6C87; --flag:#A33A2A;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#0F1416; --card:#161D20; --ink:#E6ECEA; --dim:#8FA1A3;
  --rule:#2A3438; --rule-soft:#1E272A;
  --amber:#E0A93F; --amber-bg:#33280F; --steel:#7FB3CE; --flag:#E0705C;
}}
:root[data-theme="dark"]{
  --paper:#0F1416; --card:#161D20; --ink:#E6ECEA; --dim:#8FA1A3;
  --rule:#2A3438; --rule-soft:#1E272A;
  --amber:#E0A93F; --amber-bg:#33280F; --steel:#7FB3CE; --flag:#E0705C;
}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);
  font-family:"IBM Plex Sans",system-ui,-apple-system,sans-serif;
  margin:0;padding:0 20px 64px;line-height:1.5}
.wrap{max-width:1080px;margin:0 auto}
header{padding:36px 0 20px;border-bottom:2px solid var(--ink)}
h1{font-family:"Barlow Condensed","Arial Narrow",system-ui,sans-serif;
  font-weight:600;font-size:clamp(30px,5vw,44px);letter-spacing:.01em;
  margin:0;text-transform:uppercase;text-wrap:balance}
.sub{color:var(--dim);font-size:14px;margin:6px 0 0;max-width:62ch}
.stats{display:flex;flex-wrap:wrap;gap:28px;margin:20px 0 0}
.stat .n{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:24px;
  font-variant-numeric:tabular-nums;font-weight:600}
.stat .l{font-family:"Barlow Condensed","Arial Narrow",sans-serif;
  text-transform:uppercase;letter-spacing:.09em;font-size:11px;color:var(--dim)}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:22px 0 14px}
input[type=search]{flex:1 1 240px;min-width:180px;padding:9px 12px;
  border:1px solid var(--rule);border-radius:2px;background:var(--card);
  color:var(--ink);font:inherit;font-size:14px}
input[type=search]:focus-visible,button:focus-visible{outline:2px solid var(--steel);outline-offset:1px}
button{font-family:"Barlow Condensed","Arial Narrow",sans-serif;font-size:13px;
  text-transform:uppercase;letter-spacing:.07em;padding:9px 14px;cursor:pointer;
  border:1px solid var(--rule);background:var(--card);color:var(--ink);border-radius:2px}
button[aria-pressed=true]{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.tablewrap{overflow-x:auto;border:1px solid var(--rule);border-radius:3px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:14px}
th{font-family:"Barlow Condensed","Arial Narrow",sans-serif;text-transform:uppercase;
  letter-spacing:.07em;font-size:12px;color:var(--dim);text-align:left;
  padding:10px 12px;border-bottom:1px solid var(--rule);white-space:nowrap;
  position:sticky;top:0;background:var(--card);cursor:pointer;user-select:none}
th[data-sort]:hover{color:var(--ink)}
th.num,td.num{text-align:right}
td{padding:9px 12px;border-bottom:1px solid var(--rule-soft);vertical-align:baseline}
tr:last-child td{border-bottom:0}
.num{font-family:"IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}
.cargo{font-weight:600}
.route{color:var(--dim);font-size:13px}
.route b{color:var(--ink);font-weight:500}
.pay{color:var(--amber);font-weight:600}
.store{color:var(--steel)}
.tag{font-family:"Barlow Condensed","Arial Narrow",sans-serif;font-size:11px;
  text-transform:uppercase;letter-spacing:.07em;padding:1px 6px;border-radius:2px;
  background:var(--amber-bg);color:var(--amber);margin-left:7px;white-space:nowrap}
.short{color:var(--flag);font-weight:600}
.tag.loop{background:transparent;color:var(--dim);border:1px solid var(--rule)}
.tag.abuse{background:var(--flag);color:var(--paper)}
.tag.lyr{background:transparent;color:var(--steel);border:1px solid var(--steel)}
tr:has(.tag.abuse) td{background:color-mix(in srgb,var(--flag) 7%,transparent)}
.note{margin:16px 0 0;padding:12px 14px;border-left:3px solid var(--flag);
  background:var(--card);font-size:13px;color:var(--dim);max-width:70ch}
.note b{color:var(--ink)}
.note.ok{border-left-color:var(--steel)}
.note ul{margin:9px 0 0;padding-left:18px}
.note li{margin:3px 0}
.note .rate{font-family:"IBM Plex Mono",ui-monospace,monospace;color:var(--flag)}
.note .fix{display:block;margin-top:10px;padding-top:9px;border-top:1px solid var(--rule-soft)}
.empty{padding:28px 12px;color:var(--dim);text-align:center}
/* Offshore trade: same Barlow condensed caps as the masthead, one step down,
   so the section reads as part of the document rather than a bolted-on table. */
.offshore{margin:34px 0 0;border-top:2px solid var(--ink);padding:20px 0 0}
.offshore h2{font-family:"Barlow Condensed","Arial Narrow",sans-serif;
  font-weight:600;font-size:24px;letter-spacing:.02em;text-transform:uppercase;
  margin:0 0 4px}
.offshore h3{font-family:"Barlow Condensed","Arial Narrow",sans-serif;
  font-weight:600;font-size:17px;letter-spacing:.04em;text-transform:uppercase;
  margin:22px 0 0;color:var(--steel);display:flex;align-items:baseline;gap:8px}
.offshore h3 .t{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;
  color:var(--dim);letter-spacing:0}
.offshore .sub{margin:4px 0 10px}
.offshore table{font-size:13px}
.offshore code{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;
  background:var(--amber-bg);color:var(--amber);padding:1px 5px;border-radius:2px}
footer{margin:26px 0 0;color:var(--dim);font-size:12px}
"""

JS = """
const rows = DATA;
let sortKey = 'pay', sortDir = -1, onlyCustom = false, onlyShort = false, onlyLoop = false, onlyAbuse = false, onlyLayer = false, q = '';
const fmt = n => n === null || n === undefined ? '--' : n.toLocaleString('en-US');
const tbody = document.getElementById('body');
const count = document.getElementById('count');

function view(){
  let r = rows.filter(x => {
    if (onlyCustom && !x.custom) return false;
    if (onlyShort && !(x.km < 1)) return false;
    if (onlyLoop && !x.loop) return false;
    if (onlyAbuse && !x.abuse) return false;
    if (onlyLayer && (!x.layer || x.layer === 'base')) return false;
    if (q && !(x.cargo + ' ' + x.from + ' ' + x.to).toLowerCase().includes(q)) return false;
    return true;
  });
  r.sort((a,b) => {
    let x = a[sortKey], y = b[sortKey];
    if (x === null) x = -1; if (y === null) y = -1;
    if (typeof x === 'string') return x.localeCompare(y) * sortDir;
    return (x - y) * sortDir;
  });
  count.textContent = r.length;
  tbody.innerHTML = r.length ? r.map(x => `
    <tr>
      <td><span class="cargo">${x.cargo}</span>${x.custom ? '<span class="tag">Arini</span>' : ''}${x.layer && x.layer !== 'base' ? `<span class="tag lyr">${x.layer}</span>` : ''}</td>
      <td class="route"><b>${x.from}</b> &rarr; <b>${x.to}</b>${x.abuse ? '<span class="tag abuse">farmable</span>' : x.loop ? '<span class="tag loop">two-way</span>' : ''}</td>
      <td class="num ${x.abuse ? 'short' : ''}">${x.km.toFixed(1)}</td>
      <td class="num">${x.kg ? fmt(Math.round(x.kg)) : '--'}</td>
      <td class="num store">${x.store ? fmt(x.store) : '&mdash;'}</td>
      <td class="num pay">${fmt(x.pay)}</td>
      <td class="num">${fmt(x.perkm)}</td>
    </tr>`).join('')
    : '<tr><td colspan="6" class="empty">No hauls match that.</td></tr>';
}

document.querySelectorAll('th[data-sort]').forEach(th => {
  th.addEventListener('click', () => {
    const k = th.dataset.sort;
    if (k === sortKey) sortDir = -sortDir; else { sortKey = k; sortDir = (k === 'cargo' || k === 'from') ? 1 : -1; }
    view();
  });
});
document.getElementById('q').addEventListener('input', e => { q = e.target.value.toLowerCase().trim(); view(); });
const bc = document.getElementById('bcustom'), bs = document.getElementById('bshort');
bc.addEventListener('click', () => { onlyCustom = !onlyCustom; bc.setAttribute('aria-pressed', onlyCustom); view(); });
bs.addEventListener('click', () => { onlyShort = !onlyShort; bs.setAttribute('aria-pressed', onlyShort); view(); });
const bl = document.getElementById('bloop');
bl.addEventListener('click', () => { onlyLoop = !onlyLoop; bl.setAttribute('aria-pressed', onlyLoop); view(); });
const ba = document.getElementById('babuse');
ba.addEventListener('click', () => { onlyAbuse = !onlyAbuse; ba.setAttribute('aria-pressed', onlyAbuse); view(); });
const by = document.getElementById('blayer');
by.addEventListener('click', () => { onlyLayer = !onlyLayer; by.setAttribute('aria-pressed', onlyLayer); view(); });
view();
"""


def collect_all():
    """Every layer's hauls in one table.

    A route is tagged with the layer that INTRODUCES it -- the island's own
    hauls are "base" and appear whatever you install, while the rest only exist
    if you run that mod. One page beats one page per layer, because the
    question is usually "what does this cargo pay" rather than "what does this
    layer contain".
    """
    from mods import load as load_mods
    _mods, layers = load_mods()
    base = collect("vanilla")
    seen = {(r["cargo"], r["from"], r["to"]) for r in base}
    for r in base:
        r["layer"] = "base"
    out = list(base)
    for key in layers:
        if key == "vanilla":
            continue
        try:
            rows = collect(key)
        except Exception as e:
            print(f"  layer {key}: {e}")
            continue
        for r in rows:
            k = (r["cargo"], r["from"], r["to"])
            if k in seen:
                continue
            seen.add(k)
            r["layer"] = key
            out.append(r)
    out.sort(key=lambda r: -r["pay"])
    return out


def abuse_html(worst, n_loop) -> str:
    """The callout. Named routes, not a count -- a count is not actionable."""
    if not worst:
        return ('<p class="note ok"><b>Nothing farmable.</b> '
                f'Every haul is either long enough to earn its fee or small '
                f'enough not to be worth repeating. {n_loop} routes run both '
                f'ways, which is trade, not abuse.</p>')
    items = "".join(
        f"<li><b>{r['cargo']}</b> &middot; {r['from']} &rarr; {r['to']} &middot; "
        f"{r['km']:.1f} km for {r['pay']:,} "
        f"(<span class='rate'>{r['perkm']:,}/km</span>)</li>" for r in worst)
    return (f'<div class="note"><b>{len(worst)} routes are farmable.</b> '
            "Pay is flat, so these earn a full load&rsquo;s fee over a distance you "
            "can drive in seconds &mdash; and each has a return leg, so they can be "
            "shuttled indefinitely. Two-way trade is fine on its own; it is the "
            f"combination of short and lucrative (over {ABUSE_RATE:,}/km) that breaks."
            f"<ul>{items}</ul>"
            "<span class=\"fix\">To close one: remove the recipe that pairs those two "
            "points, or move one of them. Raising the price makes it worse.</span></div>")


def render(rows) -> str:
    total = len(rows)
    n_custom = sum(1 for r in rows if r["custom"])
    n_short = sum(1 for r in rows if r["km"] < 1)
    n_loop = sum(1 for r in rows if r.get("loop"))
    n_compat = sum(1 for r in rows if r.get("layer") and r["layer"] != "base")
    n_abuse = sum(1 for r in rows if r.get("abuse"))
    worst = sorted((r for r in rows if r.get("abuse")), key=lambda r: -(r["perkm"] or 0))
    best = max(rows, key=lambda r: r["pay"]) if rows else None
    data = json.dumps(rows, separators=(",", ":"))
    abuse_block = abuse_html(worst, n_loop)
    return f"""<title>Arini Freight Rates</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>{CSS}</style>
<div class="wrap">
<header>
  <h1>Arini Freight Rates</h1>
  <p class="sub">Every producer-to-consumer haul on the island, with what it pays.
     Pay is <b>flat</b> &mdash; a cargo is worth the same however far you take it,
     because per-km payment needs a road spine the island does not have. Distance
     only feeds the price when it is set. Generated from the data the build ships.</p>
  <div class="stats">
    <div class="stat"><div class="n">{total}</div><div class="l">Hauls</div></div>
    <div class="stat"><div class="n">{n_custom}</div><div class="l">Arini hauls</div></div>
    <div class="stat"><div class="n">{html.escape(f"{best['pay']:,}") if best else '--'}</div><div class="l">Best single run</div></div>
    <div class="stat"><div class="n">{n_short}</div><div class="l">Under 1 km</div></div>
    <div class="stat"><div class="n">{n_compat}</div><div class="l">Compat hauls</div></div>
    <div class="stat"><div class="n">{n_loop}</div><div class="l">Two-way</div></div>
    <div class="stat"><div class="n">{n_abuse}</div><div class="l">Farmable</div></div>
  </div>
</header>

<div class="controls">
  <input type="search" id="q" placeholder="Search cargo or delivery point" aria-label="Search">
  <button id="bcustom" aria-pressed="false">Arini cargo only</button>
  <button id="bshort" aria-pressed="false">Under 1 km</button>
  <button id="bloop" aria-pressed="false">Two-way</button>
  <button id="babuse" aria-pressed="false">Farmable</button>
  <button id="blayer" aria-pressed="false">Compat only</button>
</div>

<div class="tablewrap">
<table>
  <thead><tr>
    <th data-sort="cargo">Cargo</th>
    <th data-sort="from">Route</th>
    <th data-sort="km" class="num">km</th>
    <th data-sort="kg" class="num">kg</th>
    <th data-sort="store" class="num" title="MaxStorage at the destination, in units. Blank means the point uses its template default.">Storage</th>
    <th data-sort="pay" class="num">Pays</th>
    <th data-sort="perkm" class="num" title="Not a payout rate -- pay is flat. This is the farm-detector: high means the fee is large for the distance.">Rate check</th>
  </tr></thead>
  <tbody id="body"></tbody>
</table>
</div>

{abuse_block}

{offshore_html()}

<footer>Showing <span id="count">0</span> hauls. Click any column to sort.
Regenerate with <code>python cargo_routes.py</code> after moving a delivery point
or re-running <code>pricing.py</code>.</footer>
</div>
<script>const DATA={data};</script>
<script>{JS}</script>
"""


def main() -> int:
    import sys
    rows = collect_all()
    # Every layer, not just base. The compat layers carry the heaviest cargo on
    # the island, so exempting them from the kill switch meant the two worst
    # routes in the whole economy -- 1,389,668 over 2.0 km -- passed the check
    # clean and shipped.
    bad = [r for r in rows if r["abuse"]]

    # --check is the kill switch: a build can call this and stop, instead of a
    # warning nobody reads. Flat pay means a farmable route cannot be fixed by
    # repricing -- the PAIRING has to go -- so this fails loudly rather than
    # trying to correct itself.
    if "--check" in sys.argv:
        for r in bad:
            print(f"  FARMABLE  {r['cargo']}: {r['from']} -> {r['to']} "
                  f"{r['km']:.1f} km for {r['pay']:,} ({r['perkm']:,}/km)",
                  file=sys.stderr)
        if bad:
            print(f"  {len(bad)} farmable route(s) over {ABUSE_RATE:,}/km", file=sys.stderr)
            return 1
        print("  no farmable routes")
        return 0

    OUT.write_text(render(rows), encoding="utf-8")
    print(f"  {len(rows)} hauls -> {OUT}"
          + (f"  ({len(bad)} FARMABLE)" if bad else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
