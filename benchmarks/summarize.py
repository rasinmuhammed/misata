"""Collect every benchmark result into one machine-readable summary.

    python -m benchmarks.summarize realism_seed_dir [realism_seed_dir ...]

Reads ``benchmarks/results/realism_benchmark.json`` plus any extra realism
runs (one directory per seed, each holding a ``realism_benchmark.json``),
``benchmarks/results/validity_benchmark.json`` and the golden fingerprints,
and writes ``benchmarks/results/summary.json``: mean and spread over seeds
for every realism metric, the validity totals, and how to reproduce each.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def _realism_runs(extra_dirs):
    runs = [json.loads((RESULTS / "realism_benchmark.json").read_text())]
    for d in extra_dirs:
        p = Path(d) / "realism_benchmark.json"
        if p.exists():
            runs.append(json.loads(p.read_text()))
    return runs


def summarize_realism(runs):
    out = {"seeds": sorted({r["seed"] for r in runs}), "datasets": {}}
    for ds in runs[0]["datasets"]:
        by_c = {}
        for r in runs:
            for contestant, metrics in r["datasets"][ds]["results"].items():
                for m, v in metrics.items():
                    if m == "seconds" or v is None:
                        continue
                    by_c.setdefault(contestant, {}).setdefault(m, []).append(v)
        out["datasets"][ds] = {
            c: {m: {"mean": round(statistics.mean(v), 3),
                    "min": round(min(v), 3), "max": round(max(v), 3), "n": len(v)}
                for m, v in ms.items()}
            for c, ms in by_c.items()}
    return out


def summarize_validity():
    p = RESULTS / "validity_benchmark.json"
    if not p.exists():
        return None
    raw = json.loads(p.read_text())
    return {case: {g: (r["total"] if "total" in r else {"could_not_run": r["error"]})
                   for g, r in by.items()} for case, by in raw.items()}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    import misata
    golden = json.loads((HERE / "golden_fingerprints.json").read_text())
    summary = {
        "misata_version": misata.__version__,
        "validity": {
            "what": "violations of PK, FK, NOT NULL, UNIQUE (single and composite), CHECK enums, "
                    "ranges and column-to-column rules, and self-reference cycles, counted by a "
                    "pandas checker that shares no code with Misata",
            "reproduce": "python -m benchmarks.validity_bench",
            "doc": "docs/validity-benchmark.md",
            "totals": summarize_validity(),
        },
        "realism": {
            "what": "blind and fitted generators scored against held-out real data; detect_auc 0.5 "
                    "means a classifier cannot tell synthetic from real",
            "reproduce": "python -m benchmarks.realism_bench --seed N",
            "doc": "docs/realism-benchmark.md",
            **summarize_realism(_realism_runs(argv)),
        },
        "reproducibility": {
            "what": "misata.fingerprint hashes of story, dict and DDL schemas; CI requires the same "
                    "hashes on Linux, macOS and Windows",
            "reproduce": "python -m benchmarks.golden",
            "cases": {k: v["__all__"] for k, v in golden["cases"].items()},
        },
    }
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"wrote {RESULTS / 'summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
