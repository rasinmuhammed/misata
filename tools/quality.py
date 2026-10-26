"""Measure code-quality metrics and hold them to a baseline that only goes down.

    python tools/quality.py            # print the metrics
    python tools/quality.py --check    # fail if any metric is worse than the baseline
    python tools/quality.py --update   # lower the baseline to today's numbers

Every metric counts something that should not exist, so lower is better, and
each is measured with an explicit rule selection rather than the project's
lint configuration, so editing that configuration cannot move a number.
``--update`` refuses to raise any metric: the baseline is a ratchet.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "misata"
BASELINE = ROOT / "tools" / "quality_baseline.json"


@dataclass(frozen=True)
class Metric:
    name: str
    description: str
    measure: Callable[[], int]


def _ruff_count(*select: str, extra: List[str] | None = None) -> int:
    cmd = [sys.executable, "-m", "ruff", "check", str(PACKAGE), "--isolated",
           "--output-format", "json", "--exit-zero", "--select", ",".join(select),
           "--target-version", "py310", *(extra or [])]
    done = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=ROOT)
    return len(json.loads(done.stdout or "[]"))


def _mypy_errors() -> int:
    # Without site-packages, third-party modules resolve as missing and are
    # ignored, so the count depends only on this package and the pinned mypy,
    # not on which optional dependencies happen to be installed.
    done = subprocess.run([sys.executable, "-m", "mypy", "--no-site-packages", str(PACKAGE)],
                          capture_output=True, text=True, cwd=ROOT)
    match = re.search(r"Found (\d+) errors?", done.stdout)
    if match:
        return int(match.group(1))
    if "Success" in done.stdout:
        return 0
    raise RuntimeError(f"could not read mypy output:\n{done.stdout[-2000:]}{done.stderr[-2000:]}")


_IMPORT_PROBE = """
import sys
before = set(sys.modules)
import misata
loaded = {name.partition(".")[0] for name in set(sys.modules) - before}
third_party = {
    name for name in loaded
    if name not in sys.stdlib_module_names and name != "misata"
    and not name.startswith("_") and name != "cython_runtime"
}
print(len(third_party))
"""


def _third_party_packages_on_import() -> int:
    """Third-party packages that ``import misata`` loads before any call.

    Counted by top-level package rather than module so the number does not move
    with the Python version's own standard library.
    """
    done = subprocess.run([sys.executable, "-c", _IMPORT_PROBE], capture_output=True,
                          text=True, check=True, cwd=ROOT)
    return int(done.stdout.strip())


def _core_dependencies() -> int:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    return len(project.get("dependencies", []))


_SQL_LINE = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|FROM|JOIN|TABLE|PRAGMA|INTO|COPY)\b")
_HAND_QUOTED = re.compile(r"""(?:'"\{|"\{[^}]*\}"|`\{[^}]*\}`)""")


def _hand_quoted_sql_identifiers() -> int:
    """Lines that wrap an interpolated name in quotes by hand inside SQL.

    Identifiers belong in ``misata.sqlutil.quote_ident``, which escapes the
    quote character; wrapping by hand does not.
    """
    count = 0
    for path in PACKAGE.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if _SQL_LINE.search(line) and _HAND_QUOTED.search(line):
                count += 1
    return count


METRICS: List[Metric] = [
    Metric("lint", "ruff default rules (pyflakes and pycodestyle errors)",
           lambda: _ruff_count("E4", "E7", "E9", "F")),
    Metric("undefined_names", "names used but never defined (F821)",
           lambda: _ruff_count("F821")),
    Metric("complexity_over_40", "functions with cyclomatic complexity above 40",
           lambda: _ruff_count("C901", extra=["--config", "lint.mccabe.max-complexity=40"])),
    Metric("complexity_over_15", "functions with cyclomatic complexity above 15",
           lambda: _ruff_count("C901", extra=["--config", "lint.mccabe.max-complexity=15"])),
    Metric("blind_except", "except Exception without a narrower type (BLE001)",
           lambda: _ruff_count("BLE001")),
    Metric("silenced_exceptions", "try/except/pass and try/except/continue (S110, S112)",
           lambda: _ruff_count("S110", "S112")),
    Metric("zip_without_strict", "zip() that silently truncates on unequal lengths (B905)",
           lambda: _ruff_count("B905")),
    Metric("raise_without_from", "raise inside except without chaining (B904)",
           lambda: _ruff_count("B904")),
    Metric("security", "bandit-class findings, excluding SQL building and non-crypto random",
           lambda: _ruff_count("S", extra=["--ignore", "S110,S112,S311,S608,S101"])),
    Metric("hand_quoted_sql_identifiers", "SQL lines that quote an interpolated name by hand",
           _hand_quoted_sql_identifiers),
    Metric("mypy_errors", "mypy errors across the package", _mypy_errors),
    Metric("third_party_packages_on_import", "third-party packages loaded by `import misata`",
           _third_party_packages_on_import),
    Metric("core_dependencies", "packages installed by a bare `pip install misata`",
           _core_dependencies),
]


def measure() -> Dict[str, int]:
    return {m.name: m.measure() for m in METRICS}


def _table(current: Dict[str, int], baseline: Dict[str, int]) -> str:
    rows = [f"{'metric':<30} {'now':>7} {'baseline':>9}"]
    for m in METRICS:
        base = baseline.get(m.name)
        mark = "" if base is None or current[m.name] <= base else "  WORSE"
        rows.append(f"{m.name:<30} {current[m.name]:>7} {base if base is not None else '-':>9}{mark}")
    return "\n".join(rows)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail when a metric got worse")
    mode.add_argument("--update", action="store_true", help="lower the baseline to today")
    args = parser.parse_args(argv)

    baseline: Dict[str, int] = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    current = measure()
    print(_table(current, baseline))

    worse = [k for k, v in current.items() if k in baseline and v > baseline[k]]
    if args.check:
        if worse:
            print(f"\nquality regressed: {', '.join(worse)}", file=sys.stderr)
            return 1
        return 0
    if args.update:
        if worse:
            print(f"\nrefusing to raise the baseline for: {', '.join(worse)}", file=sys.stderr)
            return 1
        merged = {k: min(v, baseline.get(k, v)) for k, v in current.items()}
        BASELINE.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
        print(f"\nbaseline written to {BASELINE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
