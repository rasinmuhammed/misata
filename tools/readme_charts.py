"""Render the README's charts as light and dark SVGs from measured results.

    python tools/readme_charts.py            # rerun the Gauntlet for both tools
    python tools/readme_charts.py --cached   # reuse the last run's JSON

Writes docs/assets/readme/{gauntlet,detection}-{light,dark}.svg. The Gauntlet
chart comes from `benchmarks.gauntlet` and `benchmarks.gauntlet_compare --tool
faker`; the detection chart from benchmarks/results/summary.json. No number is
typed into this file.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
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
              "s1": "#2a78d6", "s2": "#eb6834"},
    "dark": {"surface": "#1a1a19", "ink": "#f0efec", "ink2": "#c3c2b7", "rule": "#383835",
             "s1": "#3987e5", "s2": "#d95926"},
}
FONT = "font-family=\"ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif\""


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
           f'<title id="t">The Gauntlet: assertions held per section</title>',
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
        out.append(f'<line x1="{tx:.1f}" x2="{tx:.1f}" y1="{top - 8}" '
                   f'y2="{top + row * len(DETECTORS) - 8}" stroke="{t["rule"]}" '
                   f'stroke-width="1"{" stroke-dasharray=\"3 3\"" if tick == 0.5 else ""}/>')
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cached", action="store_true",
                        help="reuse benchmarks/results/gauntlet_*.json")
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    misata, faker = _gauntlet(args.cached)
    realism = json.loads((CACHE / "summary.json").read_text())["realism"]
    for theme in THEMES:
        (OUT / f"gauntlet-{theme}.svg").write_text(gauntlet_svg(theme, misata, faker))
        (OUT / f"detection-{theme}.svg").write_text(detection_svg(theme, realism))
    print(f"wrote 4 charts to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
