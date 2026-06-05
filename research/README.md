# SpecBench & Outcome-Conformant Synthesis — Reproducibility Package

This directory contains the full research artifact behind the paper *"Declarative
Outcome-Conformant Synthesis: Exact, Closed-Form Specification Satisfaction and a
Conformance Benchmark."* Every number in the paper is regenerable from the commands
below. Nothing here is estimated or hand-edited.

> **Intellectual-honesty note.** This work went through six rounds of adversarial
> self-review (`06`–`11_adversarial_review_round*.md`). Five claims were **retracted**
> when controls or steelman baselines refuted them (a "condensation frontier" that was a
> measurement artifact; a "non-determinism" claim that was an un-seeded-RNG artifact; a
> tuned constraint that faked a separation; an invalid plausibility metric; and an
> over-strong "structural impossibility" framing, re-scoped to *exact vs in-expectation*).
> The benchmark also contains a task the proposing method **fails** (P★). The retraction
> log is part of the artifact, by design.

---

## 1. Layout

| File | What it is |
|---|---|
| `00_moat_and_scope.md` | Scope lock: conformance (not fidelity); what is/ isn't claimed. |
| `01_formalization.md` | The math: Prop 0 (Gamma-conditional identity), 1 (exactness), 2 (marginal CV), 3 (clamp distortion), 4 (scale-invariance). |
| `02_literature_and_verdict.md` | Lit recon; why the theory door is closed; the open seam. |
| `03_paper_draft.md` | The paper draft (structured; prose to be written in author voice). |
| `04_specbench_design.md` | Benchmark methodology, metric families, threats to validity. |
| `05_literature_review.md` | Annotated bibliography (→ `references.bib`). |
| `06`–`11_adversarial_review_round*.md` | Six hostile self-review rounds + resolution logs. |
| `references.bib` | BibTeX; `[VERIFIED]` vs `[CHECK]` tags per entry. |
| `measure.py` | Validates Props 1–3 numerically (no heavy deps). |
| `specbench/` | The runnable benchmark (metrics, baselines, tasks, runner, figures). |

### `specbench/`
| File | What it is |
|---|---|
| `metrics.py` | AME, FIVR, TCV, DET, CSAT, RCE, GDC, MD (+ deprecated MP, kept for the record). |
| `baselines.py` | Adapters: Misata, Faker, NaiveRescale, SDV {GaussianCopula, CTGAN, HMA}, SDV-conditional steelman. |
| `tasks.py` | The task suite (spec-mode, reference-mode, real-data, multi-table, P★ failure). |
| `runner.py` | Runs all baselines × tasks × seeds → `results_e5.csv`. |
| `scale_invariance.py` / `plot_scale_invariance.py` | Prop-4 experiment + figure. |
| `demo_rate_group.py` | E7: rate (RCE) and group-share (GDC) conformance. |
| `case_study.py` | E8: one-sentence spec → SQLite DB → outcome verified in SQL. |
| `throughput.py` | E9: Misata-vs-SDV wall-clock scaling. |
| `run_california.py` | The real-data (California Housing) reference numbers. |

---

## 2. Environments

Two environments, deliberately separated:

**(a) Core (lightweight)** — for the math validation (E1–E4). Just Misata + its deps:
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .            # from repo root; installs Misata
```

**(b) Benchmark (heavy)** — adds SDV (pulls torch) for the cross-paradigm baselines:
```bash
python -m venv .venv_specbench && . .venv_specbench/bin/activate
pip install -r requirements-specbench.txt   # pinned: sdv, faker, scipy, scikit-learn, matplotlib
pip install -e .                             # Misata into the same env
```
SDV/torch are isolated here so Misata's own footprint stays light. All `specbench`
commands below assume env (b) and are run from the repo root with `PYTHONPATH=.`.

Pinned versions (verified): SDV 1.37.0, scikit-learn (California Housing), matplotlib
3.10. Python 3.11/3.12 recommended.

---

## 3. Reproduce every result

```bash
# E1–E4  — proposition validation (env a, no SDV needed)
.venv/bin/python research/measure.py

# E5     — cross-paradigm conformance leaderboard (env b; CTGAN is slow)
PYTHONPATH=. .venv_specbench/bin/python -m research.specbench.runner
#          → writes research/specbench/results_e5.csv

# E6     — Prop-4 scale-invariance (with the unconstrained control) + figure
PYTHONPATH=. .venv_specbench/bin/python -m research.specbench.scale_invariance
PYTHONPATH=. .venv_specbench/bin/python -m research.specbench.plot_scale_invariance
#          → scale_invariance_curve.csv, scale_invariance.png/.pdf

# E7     — rate (RCE) and group-share (GDC) conformance
PYTHONPATH=. .venv_specbench/bin/python research/specbench/demo_rate_group.py

# E8     — end-to-end case study: spec → SQLite → outcome verified in SQL
PYTHONPATH=. .venv_specbench/bin/python research/specbench/case_study.py

# E9     — throughput Misata vs SDV
PYTHONPATH=. .venv_specbench/bin/python research/specbench/throughput.py

# real-data reference numbers (California Housing)
PYTHONPATH=. .venv_specbench/bin/python research/specbench/run_california.py
```

---

## 4. What each experiment shows (one line each)

- **E1** exact aggregate: 0 integer-unit error over 5,000 random trials.
- **E2** marginal CV matches √((n−1)/(nα+1)) to ≤0.1%.
- **E3** clamp-distortion matches the closed-form ratio to 0.00%.
- **E4** NL spec → \$50,000.00 / \$200,000.00 monthly rollups, exact.
- **E5** cold-start: only methods that ingest the target reach AME≈0; SDV cannot run.
- **E6** scale-invariance: constrained marginal ≈ unconstrained control (gap≈0); the
  earlier "condensation frontier" was an artifact, retracted.
- **E7** RCE ≤ 0.008, GDC = 0.005 (vs 0.30 uncontrolled) — conformance beyond curves.
- **E8** PASS: 0 orphan FKs, exact in-DB revenue, 0 non-positive amounts.
- **E9** 7–11× faster than SDV; no infeasible regime (Prop 1 holds for any n≥1).
- **E10 / P★** Misata **fails** the arbitrary-external-marginal task (W1≈0.78) — the
  benchmark can be lost.
- **Real data (California Housing):** off-the-shelf SDV misses by 74–87%; per-period
  conditioned SDV (steelman) still misses (~19%), never exact; closed-form = 0.
- **Multi-table (2- and 3-level):** HMA preserves all FKs (FIVR=0) but misses the outcome
  (AME 0.64–0.78); the engine attains AME=0 *and* FIVR=0.

---

## 5. Honesty ledger (what is conceded)

- Exact *aggregate* satisfaction alone is trivial; a rescale ties it given a hand-built
  schema. The contribution is exactness **jointly** with marginals + integrity +
  determinism + zero-data, plus the benchmark.
- On non-curated schemas Misata uses a declarative path (`input=schema`), not NL; its
  per-row marginal there is a supplied default (no marginal-realism claim).
- The math (Props 0–4) is classical and cited; the contribution is correct attribution,
  the benchmark, and the honest boundary — not a new theorem.
