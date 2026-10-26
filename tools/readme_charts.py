"""Render the README's charts as light and dark SVGs from measured results.

    python tools/readme_charts.py            # rerun the Gauntlet for both tools
    python tools/readme_charts.py --cached   # reuse the last run's JSON

Writes docs/assets/readme/{curve,gauntlet,detection,history,bricks}-{light,dark}.svg.

- curve: the README's own quickstart YAML, generated and summed by month and
  channel, against the totals the certificate derives from it;
- gauntlet: `benchmarks.gauntlet` and `benchmarks.gauntlet_compare --tool faker`;
- detection: benchmarks/results/summary.json;
- history: the demo-tenant recipe, every subscription grouped by the
  timestamps it carries;
- bricks: the declaration registry.

No measured number is typed into this file.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import warnings
from html import escape
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "assets" / "readme"
CACHE = ROOT / "benchmarks" / "results"

SECTIONS = {
    "A": "Keys and nulls", "B": "Value domains", "C": "Time ordering",
    "D": "Status implies fields", "E": "Cross-table totals", "F": "Diamond joins",
    "G": "Geography", "H": "Arithmetic", "I": "Distributions", "J": "Lifecycles",
    "K": "Missingness", "L": "Late arrivals", "M": "Grids and duplicates",
}

# Validated with the dataviz palette checker against both surfaces.
THEMES = {
    "light": {"surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "rule": "#e4e3df",
              "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a",
              "brick": "#f0efec", "on_s1": "#ffffff"},
    "dark": {"surface": "#1a1a19", "ink": "#f0efec", "ink2": "#c3c2b7", "rule": "#383835",
             "s1": "#3987e5", "s2": "#d95926", "s3": "#199e70",
             "brick": "#262624", "on_s1": "#0b0b0b"},
}
FONT = "font-family=\"ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif\""
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"


def _gauntlet(cached: bool) -> Tuple[Dict[str, Tuple[int, int]], Dict[str, Tuple[int, int]]]:
    runs = {"misata": ["-m", "benchmarks.gauntlet"],
            "faker": ["-m", "benchmarks.gauntlet_compare", "--tool", "faker"]}
    scores = {}
    for name, args in runs.items():
        path = CACHE / f"gauntlet_{name}.json"
        if not (cached and path.is_file()):
            subprocess.run([sys.executable, *args, "--json", str(path)], cwd=ROOT,
                           check=True, capture_output=True)
        results = json.loads(path.read_text())["results"]
        per: Dict[str, List[int]] = {}
        for r in results:
            held = int(r["violations"] == 0 and not r["error"])
            per.setdefault(r["category"], [0, 0])
            per[r["category"]][0] += held
            per[r["category"]][1] += 1
        scores[name] = {k: (v[0], v[1]) for k, v in per.items()}
    return scores["misata"], scores["faker"]


def _bar(x: float, y: float, w: float, h: float, fill: str) -> str:
    """A bar square at the baseline with a 4px rounded data end."""
    if w <= 0:
        return ""
    r = min(4.0, w, h / 2)
    return (f'<path d="M{x:.1f},{y:.1f} h{w - r:.1f} a{r},{r} 0 0 1 {r},{r} '
            f'v{h - 2 * r:.1f} a{r},{r} 0 0 1 -{r},{r} h-{w - r:.1f} z" fill="{fill}"/>')


def gauntlet_svg(theme: str, misata: Dict, faker: Dict) -> str:
    t = THEMES[theme]
    width, left, bar_w, row, top = 680, 168, 410, 30, 56
    keys = sorted(misata)
    height = top + row * len(keys) + 16
    m_total = sum(v[0] for v in misata.values())
    f_total = sum(v[0] for v in faker.values())
    total = sum(v[1] for v in misata.values())
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="t d" {FONT}>',
           '<title id="t">The Gauntlet: assertions held per section</title>',
           f'<desc id="d">Misata holds {m_total} of {total} SQL assertions; a Faker script '
           f'with the same columns holds {f_total}.</desc>',
           f'<rect width="{width}" height="{height}" rx="8" fill="{t["surface"]}"/>']
    lx = left
    for label, colour in ((f"Misata  {m_total} of {total}", t["s1"]),
                          (f"Faker script  {f_total} of {total}", t["s2"])):
        out.append(f'<rect x="{lx}" y="20" width="10" height="10" rx="2" fill="{colour}"/>')
        out.append(f'<text x="{lx + 16}" y="29" font-size="12.5" fill="{t["ink"]}">'
                   f'{escape(label)}</text>')
        lx += 190
    for i, key in enumerate(keys):
        y = top + i * row
        held_m, n = misata[key]
        held_f = faker.get(key, (0, n))[0]
        if i:
            out.append(f'<line x1="16" x2="{width - 16}" y1="{y - 3}" y2="{y - 3}" '
                       f'stroke="{t["rule"]}" stroke-width="1"/>')
        out.append(f'<text x="{left - 12}" y="{y + 15}" font-size="12" text-anchor="end" '
                   f'fill="{t["ink2"]}">{escape(SECTIONS.get(key, key))}</text>')
        for j, (held, colour) in enumerate(((held_m, t["s1"]), (held_f, t["s2"]))):
            by = y + 3 + j * 10
            w = bar_w * held / n
            out.append(_bar(left, by, w, 8, colour))
            out.append(f'<text x="{left + w + 6:.1f}" y="{by + 7.5}" font-size="10.5" '
                       f'fill="{t["ink2"]}">{held}/{n}</text>')
    out.append(f'<line x1="{left}" x2="{left}" y1="{top - 4}" y2="{height - 14}" '
               f'stroke="{t["ink2"]}" stroke-width="1"/>')
    out.append("</svg>")
    return "\n".join(out)


DETECTORS = [
    ("misata_schema", "Misata, declared schema", "blind"),
    ("misata_story", "Misata, from a sentence", "blind"),
    ("faker_script", "Faker script", "blind"),
    ("sdv_copula", "SDV, fitted to the real data", "fitted"),
    ("misata_mimic", "Misata mimic, fitted", "fitted"),
]


def detection_svg(theme: str, realism: Dict) -> str:
    t = THEMES[theme]
    data = realism["datasets"]
    width, left, right, row, top = 680, 214, 640, 40, 60
    lo, hi = 0.5, 0.85
    height = top + row * len(DETECTORS) + 40

    def x(v: float) -> float:
        return left + (right - left) * (v - lo) / (hi - lo)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="t d" {FONT}>',
           '<title id="t">How easily a classifier tells generated data from real</title>',
           '<desc id="d">Detection AUC, mean of five seeds; 0.5 means indistinguishable. '
           + "; ".join(f"{label}: Olist {data['olist'][k]['detect_auc']['mean']:.2f}, "
                       f"taxi {data['taxis'][k]['detect_auc']['mean']:.2f}"
                       for k, label, _ in DETECTORS) + ".</desc>",
           f'<rect width="{width}" height="{height}" rx="8" fill="{t["surface"]}"/>']
    lx = left
    for label, colour in (("Olist orders", t["s1"]), ("NYC taxi trips", t["s2"])):
        out.append(f'<circle cx="{lx + 5}" cy="25" r="5" fill="{colour}"/>')
        out.append(f'<text x="{lx + 16}" y="29" font-size="12.5" fill="{t["ink"]}">{label}</text>')
        lx += 150
    out.append(f'<text x="{right}" y="29" font-size="11" text-anchor="end" fill="{t["ink2"]}">'
               f'lower is better</text>')
    for tick in (0.5, 0.6, 0.7, 0.8):
        tx = x(tick)
        dash = ' stroke-dasharray="3 3"' if tick == 0.5 else ""
        out.append(f'<line x1="{tx:.1f}" x2="{tx:.1f}" y1="{top - 8}" '
                   f'y2="{top + row * len(DETECTORS) - 8}" stroke="{t["rule"]}" '
                   f'stroke-width="1"{dash}/>')
        out.append(f'<text x="{tx:.1f}" y="{top + row * len(DETECTORS) + 8}" font-size="11" '
                   f'text-anchor="middle" fill="{t["ink2"]}">{tick:.1f}</text>')
    out.append(f'<text x="{x(0.5) + 4:.1f}" y="{top + row * len(DETECTORS) + 26}" '
               f'font-size="11" fill="{t["ink2"]}">0.5: a classifier cannot tell them from '
               f'real rows</text>')
    for i, (key, label, kind) in enumerate(DETECTORS):
        y = top + i * row + 10
        out.append(f'<text x="{left - 14}" y="{y + 4}" font-size="12" text-anchor="end" '
                   f'fill="{t["ink"]}">{escape(label)}</text>')
        out.append(f'<text x="{left - 14}" y="{y + 18}" font-size="10.5" text-anchor="end" '
                   f'fill="{t["ink2"]}">{"sees no real data" if kind == "blind" else "sees the real data"}</text>')
        for j, (ds, colour) in enumerate((("olist", t["s1"]), ("taxis", t["s2"]))):
            v = data[ds][key]["detect_auc"]["mean"]
            cy = y - 2 + j * 12
            cx = x(v)
            out.append(f'<circle cx="{cx:.1f}" cy="{cy}" r="5" fill="{colour}" '
                       f'stroke="{t["surface"]}" stroke-width="2"/>')
            out.append(f'<text x="{cx + 9:.1f}" y="{cy + 4}" font-size="10.5" '
                       f'fill="{t["ink2"]}">{v:.2f}</text>')
    out.append("</svg>")
    return "\n".join(out)


def _generate(schema):
    import misata

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return misata.generate_from_schema(schema)


def _curve_data() -> Dict:
    """The quickstart as the README prints it, generated and summed."""
    import pandas as pd

    from misata.attestation import derive_invariants
    from misata.yaml_schema import load_schema_file

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    spec = re.search(r"```yaml\n(# misata\.yaml\n.*?)```", readme, re.S).group(1)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "misata.yaml"
        path.write_text(spec)
        schema = load_schema_file(path)
    curve, split = schema.outcome_curves[0], schema.group_shares[0]
    df = _generate(schema)[curve.table]
    month = pd.to_datetime(df[curve.time_column]).dt.month.rename("month")
    cells = df.groupby([month, df[split.group_column]])[curve.column].sum().unstack(fill_value=0)

    declared: Dict[int, float] = {}
    shares: Dict[Tuple[int, str], float] = {}
    for inv in derive_invariants(schema):
        if inv.kind == "outcome_curve_period":
            declared[int(re.search(r"month:(\d+)", inv.id).group(1))] = float(inv.expected)
        elif inv.kind == "group_share_period":
            group, period = inv.id.split(".")[2:4]
            shares[int(period[-2:]), group] = float(inv.expected)
    groups = list(split.shares)
    gap = max([abs(round(cells.loc[m].sum() - v, 2)) for m, v in declared.items()]
              + [abs(round(cells.loc[m, g] - v, 2)) for (m, g), v in shares.items()])
    total = float(cells.to_numpy().sum())
    return {"months": sorted(declared), "declared": declared, "groups": groups,
            "cells": {m: {g: float(cells.loc[m, g]) for g in groups} for m in declared},
            "realised": {g: float(cells[g].sum()) / total for g in groups},
            "gap": gap, "checked": len(declared) + len(shares)}


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def curve_svg(theme: str, data: Dict) -> str:
    t = THEMES[theme]
    colours = [t["s1"], t["s2"], t["s3"]]
    width, height, left, right, top, base = 680, 300, 64, 664, 72, 240
    peak = max(data["declared"].values())
    step = 100_000
    ymax = step * -(-peak * 1.15 // step)

    def y(v: float) -> float:
        return base - (base - top) * v / ymax

    slot = (right - left) / len(data["months"])
    bar = slot * 0.6
    labelled = {data["months"][0], data["months"][len(data["months"]) // 2 - 1],
                data["months"][-1]}
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="t d" {FONT}>',
           '<title id="t">Declared monthly revenue against generated revenue</title>',
           '<desc id="d">Twelve monthly totals and a channel split declared in the quickstart '
           'YAML, and the generated orders summed by month and channel. '
           + "; ".join(f"{MONTHS[m - 1]} declared {data['declared'][m]:,.2f}, generated "
                       f"{sum(data['cells'][m].values()):,.2f}" for m in data["months"])
           + f". Largest gap: {data['gap']:.2f}.</desc>",
           f'<rect width="{width}" height="{height}" rx="8" fill="{t["surface"]}"/>']
    lx = left
    for group, colour in zip(data["groups"], colours, strict=False):
        label = f"{group} {data['realised'][group]:.1%}"
        out.append(f'<rect x="{lx}" y="20" width="10" height="10" rx="2" fill="{colour}"/>')
        out.append(f'<text x="{lx + 16}" y="29" font-size="12.5" fill="{t["ink"]}">'
                   f'{escape(label)}</text>')
        lx += 104
    out.append(f'<line x1="{lx}" x2="{lx + 18}" y1="25" y2="25" stroke="{t["ink"]}" '
               f'stroke-width="2"/>')
    out.append(f'<text x="{lx + 24}" y="29" font-size="12.5" fill="{t["ink"]}">'
               f'declared monthly total</text>')
    tick = 0
    while tick <= ymax:
        ty = y(tick)
        out.append(f'<line x1="{left}" x2="{right}" y1="{ty:.1f}" y2="{ty:.1f}" '
                   f'stroke="{t["rule"] if tick else t["ink2"]}" stroke-width="1"/>')
        out.append(f'<text x="{left - 8}" y="{ty + 4:.1f}" font-size="11" text-anchor="end" '
                   f'fill="{t["ink2"]}">{tick // 1000:,.0f}k</text>')
        tick += step
    for i, m in enumerate(data["months"]):
        bx = left + i * slot + (slot - bar) / 2
        cum = 0.0
        groups = data["groups"]
        for j, (group, colour) in enumerate(zip(groups, colours, strict=False)):
            v = data["cells"][m][group]
            top_y, bottom_y = y(cum + v), y(cum) - (2 if j else 0)
            h = bottom_y - top_y
            if j == len(groups) - 1:
                r = min(4.0, h / 2, bar / 2)
                out.append(f'<path d="M{bx:.1f},{bottom_y:.1f} v{-(h - r):.1f} '
                           f'a{r},{r} 0 0 1 {r},{-r} h{bar - 2 * r:.1f} a{r},{r} 0 0 1 {r},{r} '
                           f'v{h - r:.1f} z" fill="{colour}"/>')
            else:
                out.append(f'<rect x="{bx:.1f}" y="{top_y:.1f}" width="{bar:.1f}" '
                           f'height="{h:.1f}" fill="{colour}"/>')
            cum += v
        dy = y(data["declared"][m])
        out.append(f'<line x1="{bx - 5:.1f}" x2="{bx + bar + 5:.1f}" y1="{dy:.1f}" '
                   f'y2="{dy:.1f}" stroke="{t["ink"]}" stroke-width="2" stroke-linecap="round"/>')
        if m in labelled:
            out.append(f'<text x="{bx + bar / 2:.1f}" y="{dy - 9:.1f}" font-size="11" '
                       f'text-anchor="middle" fill="{t["ink"]}">'
                       f'{data["declared"][m]:,.2f}</text>')
        out.append(f'<text x="{bx + bar / 2:.1f}" y="{base + 16}" font-size="11" '
                   f'text-anchor="middle" fill="{t["ink2"]}">{MONTHS[m - 1]}</text>')
    out.append(f'<text x="{left}" y="{height - 16}" font-size="11.5" fill="{t["ink2"]}">'
               f'Largest gap between declared and generated, over {data["checked"]} monthly '
               f'totals and month-by-channel cells: {data["gap"]:.2f}</text>')
    out.append("</svg>")
    return "\n".join(out)


def _history_data() -> Dict:
    """The demo tenant's subscriptions, grouped by the timestamps each carries."""
    from misata.yaml_schema import load_schema_file

    schema = load_schema_file(ROOT / "examples" / "usecases" / "demo-tenant" / "misata.yaml")
    lc = schema.lifecycles[0]
    df = _generate(schema)[lc.table]
    columns = [lc.start_column, *lc.timestamp_columns()]
    owner = {lc.timestamp_of(s): s for s in lc.state_names() if lc.timestamp_of(s)}
    routes = []
    for state in lc.state_names():
        for route, _ in lc.routes_to(state):
            sig = lc.signature(route)
            mask = df[lc.state_column] == state
            for col in columns[1:]:
                mask &= df[col].notna() == (owner[col] in sig)
            mask &= df[lc.start_column].notna()
            routes.append({"route": route, "count": int(mask.sum()),
                           "set": [True] + [owner[c] in sig for c in columns[1:]]})
    routes.sort(key=lambda r: (lc.state_names().index(r["route"][-1]), len(r["route"])))
    return {"columns": columns, "routes": routes, "total": len(df),
            "other": len(df) - sum(r["count"] for r in routes)}


def history_svg(theme: str, data: Dict) -> str:
    t = THEMES[theme]
    routes = data["routes"]
    width, top, row = 680, 64, 28
    cols = [282 + 72 * i for i in range(len(data["columns"]))]
    bar_x, bar_max = cols[-1] + 48, 96
    most = max(r["count"] for r in routes)
    height = top + row * len(routes) + 38
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="t d" {FONT}>',
           '<title id="t">Every subscription carries the history its status implies</title>',
           '<desc id="d">' + "; ".join(
               f"{' to '.join(r['route'])}: {r['count']} rows with "
               + ", ".join(c for c, on in zip(data["columns"], r["set"], strict=True) if on)
               for r in routes) + f". Rows matching no declared route: {data['other']}.</desc>",
           f'<rect width="{width}" height="{height}" rx="8" fill="{t["surface"]}"/>',
           f'<text x="16" y="{top - 26}" font-size="11" fill="{t["ink2"]}">route to the status</text>']
    for cx, col in zip(cols, data["columns"], strict=True):
        out.append(f'<text x="{cx}" y="{top - 26}" font-size="10.5" text-anchor="middle" '
                   f'font-family="{MONO}" fill="{t["ink2"]}">{escape(col)}</text>')
    out.append(f'<text x="{bar_x}" y="{top - 26}" font-size="11" fill="{t["ink2"]}">rows</text>')
    previous = None
    for i, r in enumerate(routes):
        y = top + i * row
        if previous is not None and r["route"][-1] != previous:
            out.append(f'<line x1="16" x2="{width - 16}" y1="{y - row / 2:.1f}" '
                       f'y2="{y - row / 2:.1f}" stroke="{t["rule"]}" stroke-width="1"/>')
        previous = r["route"][-1]
        *before, last = r["route"]
        lead = "".join(f"{escape(s)} → " for s in before)
        out.append(f'<text x="16" y="{y + 4}" font-size="12" fill="{t["ink2"]}">{lead}'
                   f'<tspan fill="{t["ink"]}" font-weight="600">{escape(last)}</tspan></text>')
        for cx, on in zip(cols, r["set"], strict=True):
            if on:
                out.append(f'<circle cx="{cx}" cy="{y}" r="5.5" fill="{t["s1"]}"/>')
            else:
                out.append(f'<circle cx="{cx}" cy="{y}" r="4.5" fill="none" '
                           f'stroke="{t["ink2"]}" stroke-width="1.2"/>')
        w = bar_max * r["count"] / most
        out.append(_bar(bar_x, y - 5, w, 10, t["s1"]))
        out.append(f'<text x="{bar_x + w + 6:.1f}" y="{y + 4}" font-size="11" '
                   f'fill="{t["ink"]}">{r["count"]:,}</text>')
    out.append(f'<text x="16" y="{height - 14}" font-size="11.5" fill="{t["ink2"]}">'
               f'{data["total"]:,} subscriptions. Filled: the timestamp is set. Rows whose '
               f'timestamps match no declared route: {data["other"]}.</text>')
    out.append("</svg>")
    return "\n".join(out)


#: Declarations the DuckDB certificate re-checks, as the invariant kinds
#: misata.attestation.derive_invariants emits for them.
IN_CERTIFICATE = {"outcome_curves", "rate_curves", "group_shares", "waterfalls",
                  "constraints", "lifecycles", "dag_edges", "graph_motifs"}

#: Keys, row rules and relationship guarantees declared in DDL or on a
#: relationship or constraint, all re-checked by the certificate.
FOUNDATION = [("foreign keys", True), ("unique keys", True), ("NOT NULL", True),
              ("CHECK rules", True), ("min_children", True), ("partition_by", True),
              ("balanced_ledger", True)]


def _bricks_data() -> List[Tuple[str, List[Tuple[str, bool]]]]:
    from misata.registry import DECLARATIONS

    arithmetic = [(d.key, d.key in IN_CERTIFICATE) for d in DECLARATIONS if d.linear]
    structure = [(d.key, d.key in IN_CERTIFICATE) for d in DECLARATIONS if not d.linear]
    return [("State, structure, time and texture", structure),
            ("Exact counts and sums", arithmetic),
            ("Keys, rules and relationships", FOUNDATION)]


def bricks_svg(theme: str, courses: List[Tuple[str, List[Tuple[str, bool]]]]) -> str:
    t = THEMES[theme]
    width, left, right, brick_h, gap = 680, 16, 664, 26, 4
    span = right - left

    def rows_of(bricks):
        """Fewest rows the bricks fit in, with the bricks shared evenly."""
        sized = [(name, cert, len(name) * 6.7 + 22) for name, cert in bricks]
        for count in range(1, len(sized) + 1):
            per = -(-len(sized) // count)
            rows = [sized[i:i + per] for i in range(0, len(sized), per)]
            if all(sum(w for *_, w in r) + gap * (len(r) - 1) <= span for r in rows):
                return rows
        return [[b] for b in sized]

    laid = [(title, rows_of(bricks)) for title, bricks in courses]
    height = (70 + brick_h + gap + 10
              + sum(12 + len(rows) * (brick_h + gap) + 10 for _, rows in laid) + 24)
    total = sum(len(b) for _, b in courses)
    certified = sum(c for _, b in courses for _, c in b)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="t d" {FONT}>',
           '<title id="t">The declarations Misata understands today</title>',
           f'<desc id="d">{total} guarantees in three courses, {certified} of them re-checked '
           f'by DuckDB in the certificate. '
           + "; ".join(f"{title}: " + ", ".join(n for n, _ in b) for title, b in courses)
           + ". Above them, an open course for the next declaration.</desc>",
           f'<rect width="{width}" height="{height}" rx="8" fill="{t["surface"]}"/>']
    legend = [("cert", "re-checked by DuckDB in the certificate"),
              ("plain", "refused early, re-checked in process"),
              ("next", "next")]
    lx = left
    for kind, label in legend:
        if kind == "cert":
            out.append(f'<rect x="{lx}" y="19" width="16" height="11" rx="3" fill="{t["s1"]}"/>')
        elif kind == "plain":
            out.append(f'<rect x="{lx + .5}" y="19.5" width="15" height="10" rx="3" '
                       f'fill="{t["brick"]}" stroke="{t["ink2"]}" stroke-width="1"/>')
        else:
            out.append(f'<rect x="{lx + .5}" y="19.5" width="15" height="10" rx="3" fill="none" '
                       f'stroke="{t["ink2"]}" stroke-width="1" stroke-dasharray="3 2"/>')
        out.append(f'<text x="{lx + 22}" y="29" font-size="12" fill="{t["ink"]}">'
                   f'{escape(label)}</text>')
        lx += 22 + len(label) * 6.4 + 22

    y = 62
    out.append(f'<text x="{left}" y="{y}" font-size="11" fill="{t["ink2"]}">'
               f'The next course: what you still script by hand</text>')
    y += 8
    widths = [span * f for f in (0.3, 0.22, 0.26)]
    x = left
    for w in widths:
        out.append(f'<rect x="{x + .5:.1f}" y="{y + .5}" width="{w - gap - 1:.1f}" '
                   f'height="{brick_h - 1}" rx="4" fill="none" stroke="{t["ink2"]}" '
                   f'stroke-width="1" stroke-dasharray="4 3"/>')
        x += w
    y += brick_h + gap + 10
    for title, rows in laid:
        out.append(f'<text x="{left}" y="{y + 4}" font-size="11" fill="{t["ink2"]}">'
                   f'{escape(title)}</text>')
        y += 12
        for bricks in rows:
            natural = sum(w for _, _, w in bricks) + gap * (len(bricks) - 1)
            stretch = (span - gap * (len(bricks) - 1)) / (natural - gap * (len(bricks) - 1))
            x = left
            for name, cert, w in bricks:
                w *= stretch
                if cert:
                    out.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{brick_h}" '
                               f'rx="4" fill="{t["s1"]}"/>')
                    ink = t["on_s1"]
                else:
                    out.append(f'<rect x="{x + .5:.1f}" y="{y + .5}" width="{w - 1:.1f}" '
                               f'height="{brick_h - 1}" rx="4" fill="{t["brick"]}" '
                               f'stroke="{t["ink2"]}" stroke-width="1"/>')
                    ink = t["ink"]
                mono = "_" in name
                family = f' font-family="{MONO}"' if mono else ""
                out.append(f'<text x="{x + w / 2:.1f}" y="{y + 17}" font-size="11.5" '
                           f'text-anchor="middle"{family} fill="{ink}">{escape(name)}</text>')
                x += w + gap
            y += brick_h + gap
        y += 10
    out.append(f'<text x="{left}" y="{height - 14}" font-size="11.5" fill="{t["ink2"]}">'
               f'{total} guarantees today, {certified} of them in the certificate. A new brick '
               f'is laid only when it can be declared, refused and re-checked.</text>')
    out.append("</svg>")
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cached", action="store_true",
                        help="reuse benchmarks/results/gauntlet_*.json")
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    misata, faker = _gauntlet(args.cached)
    realism = json.loads((CACHE / "summary.json").read_text())["realism"]
    curve, history, bricks = _curve_data(), _history_data(), _bricks_data()
    charts = {"curve": lambda theme: curve_svg(theme, curve),
              "gauntlet": lambda theme: gauntlet_svg(theme, misata, faker),
              "detection": lambda theme: detection_svg(theme, realism),
              "history": lambda theme: history_svg(theme, history),
              "bricks": lambda theme: bricks_svg(theme, bricks)}
    for name, render in charts.items():
        for theme in THEMES:
            (OUT / f"{name}-{theme}.svg").write_text(render(theme))
    print(f"wrote {len(charts) * len(THEMES)} charts to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
