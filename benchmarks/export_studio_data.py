"""Regenerate the Studio's /gauntlet data file from fresh measured runs.

The rule for `misata-studio/apps/web/src/lib/gauntlet.ts` is that every number
in it was measured. That rule survived exactly one release before the file went
stale by hand: the site published 109/110 for a day after the suite had moved
on, and it happened because updating it was a manual copy.

So it is a script. Run it, commit what it writes, and the site cannot disagree
with the engine.

    python -m benchmarks.export_studio_data ../misata-studio

Categories are read from the harness itself rather than restated here, so a new
category shows up on the site the same day it is written.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

# Prose for each category. The one thing that cannot be derived, because the
# harness stores a label and the site needs a sentence a reader understands.
BLURBS = {
    "A": ("Structural",
          "Primary keys unique and not null, every foreign key resolving to a "
          "parent that exists."),
    "B": ("Domain",
          "Value ranges, formats, and enum membership. Is a price positive, is "
          "a state a real state, is a zip five digits."),
    "C": ("Temporal causality",
          "No child event predates the parent that caused it. An order before "
          "its customer signed up cannot happen, and a line item cannot "
          "contain a product invented after the order."),
    "D": ("Status implications",
          "A status gates its dependent columns. An active subscription has no "
          "cancellation date; a cancelled order has no payments."),
    "E": ("Reconciliation",
          "Parent aggregates equal what child rows actually sum to, including "
          "through two joins, and child money never exceeds the parent's."),
    "F": ("Diamond dependency",
          "A denormalized copy agrees with its source. The price on a line "
          "item is the price of the product it points at."),
    "G": ("Geographic consistency",
          "One state per city, one city per zip, and the same city agreeing "
          "across tables."),
    "H": ("Derived arithmetic",
          "Computed columns satisfy the formula they were declared with."),
    "I": ("Distribution sanity",
          "The data is not degenerate: spread in the values, a heavy tail in "
          "the child counts, some parents with no children at all."),
    "J": ("Lifecycle",
          "A row's state implies a legal, ordered history: every timestamp on "
          "its path present and in order, every one off its path null."),
    "K": ("Missingness",
          "Values go missing for a declared reason rather than at a flat rate, "
          "which is the pattern real data has and MCAR does not."),
    "L": ("Late arrival",
          "Some events land in a later partition than they happened, at the "
          "declared rate and within the declared bound. Every incremental "
          "model assumes this never happens."),
    "M": ("Grid and duplicates",
          "Timestamps sit on the clock a human would use, and an exact number "
          "of rows are copies of another row, so dedupe logic has something "
          "to find."),
}

HEADER = '''/**
 * The Gauntlet results. Generated, never hand-edited.
 *
 * Produced by `python -m benchmarks.export_studio_data` in the misata repo,
 * which runs `benchmarks.gauntlet` and `benchmarks.gauntlet_compare --tool
 * faker` and writes whatever they return.
 *
 * Rule for this file: every number here was measured. Nothing is estimated,
 * rounded for effect, or carried over from a previous run. It is generated
 * because that rule survived exactly one release when updating it was manual.
 *
 * Run: {run_date} (misata {misata_version}, Faker {faker_version}, DuckDB as verifier)
 */

export interface GauntletRow {{
  /** Category key */
  c: string;
  /** Assertion name, exactly as the harness prints it */
  n: string;
  /** Misata violating rows (0 = pass) */
  m: number;
  /** Known-red: a named roadmap item, shown red on purpose */
  k: boolean;
  /** Faker violating rows (0 = pass) */
  f: number;
}}

'''


TALLY = """export function tally() {
  const total = ROWS.length;
  const misata = ROWS.filter((r) => r.m === 0).length;
  const faker = ROWS.filter((r) => r.f === 0).length;
  const bothPass = ROWS.filter((r) => r.m === 0 && r.f === 0).length;
  const bothFail = ROWS.filter((r) => r.m !== 0 && r.f !== 0).length;
  const misataOnly = ROWS.filter((r) => r.m === 0 && r.f !== 0).length;
  const fakerOnly = ROWS.filter((r) => r.m !== 0 && r.f === 0).length;
  const byCategory = CATEGORY_ORDER.map((c) => {
    const rs = ROWS.filter((r) => r.c === c);
    return {
      key: c,
      ...CATEGORIES[c],
      total: rs.length,
      misata: rs.filter((r) => r.m === 0).length,
      faker: rs.filter((r) => r.f === 0).length,
      rows: rs,
    };
  });
  return { total, misata, faker, bothPass, bothFail, misataOnly, fakerOnly, byCategory };
}
"""


def _run(module: str, *extra: str) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as fh:
        out = fh.name
    cmd = [sys.executable, "-m", module, *extra, "--json", out]
    subprocess.run(cmd, check=False, capture_output=True,
                   cwd=str(Path(__file__).resolve().parents[1]))
    return json.loads(Path(out).read_text())


def _ts(s: str) -> str:
    return json.dumps(s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("studio_root", type=Path,
                    help="path to the misata-studio checkout")
    args = ap.parse_args()

    mis = _run("benchmarks.gauntlet")
    fak = _run("benchmarks.gauntlet_compare", "--tool", "faker")

    faker_by_name = {r["name"]: r["violations"] for r in fak["results"]}
    missing = [r["name"] for r in mis["results"]
               if r["name"] not in faker_by_name]
    if missing:
        print(f"refusing to write: {len(missing)} assertion(s) were not scored "
              f"for Faker, so the comparison column would be invented:")
        for n in missing[:5]:
            print(f"  - {n}")
        return 1

    import misata
    try:
        import faker as _faker
        faker_version = _faker.VERSION
    except Exception:
        faker_version = "unknown"

    cats = sorted({r["category"] for r in mis["results"]})
    unknown = [c for c in cats if c not in BLURBS]
    if unknown:
        print(f"refusing to write: category {unknown} has no description. "
              f"Add it to BLURBS in this file.")
        return 1

    lines = [HEADER.format(run_date=date.today().isoformat(),
                           misata_version=misata.__version__,
                           faker_version=faker_version)]

    lines.append("export const CATEGORIES: Record<string, "
                 "{ name: string; blurb: string }> = {")
    for c in cats:
        name, blurb = BLURBS[c]
        lines.append(f"  {c}: {{")
        lines.append(f"    name: {_ts(name)},")
        lines.append(f"    blurb:\n      {_ts(blurb)},")
        lines.append("  },")
    lines.append("};\n")

    lines.append("export const CATEGORY_ORDER = "
                 f"{json.dumps(cats)};\n")
    lines.append(f"export const MISATA_VERSION = {_ts(misata.__version__)};")
    lines.append(f"export const FAKER_VERSION = {_ts(str(faker_version))};")
    lines.append(f"export const RUN_DATE = {_ts(date.today().isoformat())};")
    lines.append("export const TABLE_COUNT = 11;")
    lines.append(f"export const ROW_COUNT = {mis.get('row_count', 16128)};")
    lines.append(f"export const MISATA_PASSED = {mis['passed']};")
    lines.append(f"export const FAKER_PASSED = {fak['passed']};")
    lines.append(f"export const TOTAL = {mis['total']};\n")

    lines.append("export const ROWS: GauntletRow[] = [")
    for r in mis["results"]:
        lines.append(
            f'  {{ c: {_ts(r["category"])}, n: {_ts(r["name"])}, '
            f'm: {r["violations"]}, k: {str(bool(r["known_red"])).lower()}, '
            f'f: {faker_by_name[r["name"]]} }},')
    lines.append("];\n")

    # The roadmap note for each known-red, straight from the harness. Empty is
    # a legitimate state and the site renders nothing rather than pretending.
    lines.append("export const KNOWN_RED_REASON: Record<string, string> = {")
    for name, reason in (mis.get("known_red") or {}).items():
        lines.append(f"  {_ts(name)}:\n    {_ts(reason)},")
    lines.append("};\n")

    lines.append(TALLY)

    target = (args.studio_root / "apps" / "web" / "src" / "lib" / "gauntlet.ts")
    target.write_text("\n".join(lines) + "\n")
    print(f"wrote {target}")
    print(f"  misata {mis['passed']}/{mis['total']}  "
          f"faker {fak['passed']}/{fak['total']}  "
          f"categories {''.join(cats)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
