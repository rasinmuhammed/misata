# Adversarial Review — Round 2 (a different, fresh reviewer)

**Status:** brick 6. A second hostile pass, deliberately reading what Round 1 could
not: the *new* baseline code written to answer Round 1, the *actual* multi-seed numbers
now produced, and the claims as they now stand. New issues only — no victory lap.
Every item is checked against code/output, not asserted. Severity as before.

> Round-1 blockers (B1 condensation confound, B2 trivial-AME) are genuinely resolved.
> Round 2 finds problems *created by* those fixes, plus things nobody examined yet.

> **RESOLUTION LOG (Round-2 fix pass).**
> - **B3 RESOLVED** — SDV now seeded (torch+numpy+random) in the adapter; DET measured
>   over 3 same-seed pairs, not 1. **Key honest finding:** once seeded, *both* SDV
>   synthesizers are reproducible (GaussianCopula is a deterministic fitted model;
>   CTGAN is reproducible under `torch.manual_seed` — verified 11260.78==11260.78).
>   ⇒ **The "imitation is non-deterministic" claim was FALSE and is RETRACTED.** The
>   real differentiator is conformance (AME) + cold-start (CSC), not determinism.
>   `capabilities.deterministic` for SDV corrected True.
> - **B4 RESOLVED** — GaussianCopula's zero-variance AME (0.213) is *correct*: it is a
>   deterministic model, not a single-draw artifact. CTGAN's high variance is real
>   torch stochasticity; with seeding it is now reproducible per seed. Claim reframed:
>   imitation conformance is *uncontrolled / untargetable* (and, for the deep model,
>   high-variance run-to-run pre-seeding), vs engine AME≈0 — what the data supports.
> - **M5 PARTIAL/HONEST** — constraints added to 3 tasks with *semantic* caps (amount>0,
>   domain ceilings), NOT tuned to break the baseline. Honest outcome: NaiveRescale
>   breaches caps on SaaS (CSAT=0) but not fintech/ecommerce (their inflation stays
>   under the generous ceilings). Claim corrected to: NaiveRescale *cannot guarantee*
>   CSAT (fails when rescale inflates past a cap); engine satisfies by construction on
>   all tasks. We do NOT tune caps to manufacture failures.
> - **M6 RESOLVED** — SaaS curve is now non-monotone (100k→40k dip→120k); AME must
>   track shape. Misata AME still 0; verified.
> - **M7 RESOLVED** — formatter prints tiny AME in scientific notation (e.g. 1.46e-16),
>   never a fake 0.000.
> - **D5/D6/D7** — pending (markers, HMA-vs-GC explanation, one real public dataset).

---

## BLOCKERS

### B3 — Determinism is now measured with `det_check` *off* for 9/10 seeds, and the SDV "DET=0" is partly an artifact of our own adapter
Two compounding problems, both in code I just read:

1. **Our SDV adapter never sets a random seed.** `SDVBaseline.generate` calls
   `GaussianCopulaSynthesizer(md); fit; sample` with **no `random_state`**. Verified:
   two fresh GaussianCopula instances on the same data produce *identical* output (it is
   effectively deterministic), yet CTGAN does not — but **neither is seeded by us**.
   So our reported `DET` for SDV measures "does SDV happen to be reproducible with no
   seed control," not "is it reproducible under a fixed seed." A reviewer: *"You didn't
   control SDV's randomness; your determinism claim is uncontrolled."*
2. **CTGAN `DET=0.000` is computed from a single same-seed pair** (the `det_check=sd==0`
   optimization). One pair is not evidence of non-determinism; it could be one unlucky
   draw. The headline "CTGAN cannot reproduce its own output" rests on **n=1**.

*Why blocker:* determinism (DET) is one of our six core metrics and a central
selling-point vs learned methods. Right now it is (a) uncontrolled for the competitor
and (b) n=1 for the damning case.

*Fix:* set SDV's `random_state`/seed wherever the API allows (CTGAN accepts seeding via
torch; GaussianCopula via numpy state) and **measure DET as a property over ≥3 same-seed
pairs** for every baseline, reported honestly. If CTGAN is non-deterministic *even when
seeded*, that is the real, defensible claim — but we must show it, not infer from one
pair. If it IS reproducible when seeded, we must drop the non-determinism claim entirely.

### B4 — The reference-mode result has collapsed to near-nothing under multi-seed
Round 1's striking single-seed table (CTGAN AME 0.698, GaussianCopula 0.213) now reads,
over 10 seeds: **GaussianCopula 0.213 (no ±, suspicious), CTGAN 0.615 ± 0.526.** That
**±0.526 is enormous** — the CTGAN AME ranges roughly [0.09, 1.14]. So "imitation
misses the target" is, for CTGAN, *not statistically distinguishable* from sometimes
nearly hitting it. And GaussianCopula showing **exactly 0.213 with zero variance across
10 seeds** is a red flag: either it is deterministic (then why is it under "stochastic"
baselines?) or our multi-seed loop is **not actually varying SDV's seed** (it isn't —
see B3: we never pass the seed to SDV). The latter is almost certainly true.

*Why blocker:* the reference-mode row is the paper's "imitation cannot conform even with
target-consistent data" centerpiece. As computed, the SDV numbers are **single-draw
constants dressed as 10-seed means**, and the one varying number (CTGAN) has CI so wide
the claim is unsupported.

*Fix:* (a) actually vary SDV's seed per run (B3); (b) report the AME distribution, and
make the claim at the level it actually holds — likely "imitation's conformance is
**uncontrolled** (high variance, no mechanism to target), whereas the engine's is exactly
0," which is true and defensible. Do **not** claim a clean ordering that the variance
does not support.

---

## MAJOR

### M5 — CSAT is exercised on exactly ONE task; the contribution-defending metric is n=1
B2's fix (CSAT separates engine from NaiveRescale) is the linchpin defending the whole
contribution — and it fires on a *single* task (`saas_mrr_curve`) with a *single*
hand-set cap ($1000) that I tuned until it triggered. A reviewer: *"Your key
differentiator is one constraint you reverse-engineered to fail the baseline."*
*Fix:* add hard constraints to ≥3 tasks across domains (e.g. fintech amount cap, age
∈[18,...], price≥cost inequality), show CSAT separation holds broadly, and pick caps
from domain semantics, not from what breaks NaiveRescale.

### M6 — Faker's AME ≈ 0.90 is now suspiciously identical across all curve tasks
0.897, 0.899, 0.900 across SaaS/fintech/ecommerce. That near-constant is not obviously
wrong (a flat random metric vs a steep ramp could give a stable relative error) but it
*looks* like the metric is insensitive to the task — a reviewer will ask whether AME is
actually measuring task-specific conformance or just "ramp vs flat" every time.
*Fix:* report the per-period error profile for one task (show *where* Faker misses), and
add at least one non-monotone target curve (e.g. a mid-year dip) so AME must reflect
shape, not just "flat ≠ ramp." If Faker's AME stays pinned, explain why analytically.

### M7 — "AME = 0.000" exact: is it truly zero, or rounded?
Misata and NaiveRescale both print `0.000`. The formalization concedes an O(1/U)
rounding term and a ≤1/(2m) per-period error. So AME is **not** identically 0 — it is
≤ a half-cent / target ≈ 1e-7. Printing "0.000" overclaims.
*Fix:* report AME in scientific notation (e.g. 3e-8) or state "≤ 1/(2m·T) by Prop. 1";
a reviewer who recomputes and finds 2e-8 where we wrote 0 will distrust everything else.

---

## MODERATE

### D5 — `n/a` is overloaded and will confuse readers
In the table, `n/a` means three different things: "metric undefined for this task"
(CSAT on no-constraint tasks), "baseline structurally cannot run" (SDV cold-start), and
potentially "errored." Distinct concepts, one symbol.
*Fix:* use distinct markers: `—` (not applicable to task), `✗CSC` (incapable),
`ERR` (failure).

### D6 — HMA == GaussianCopula AME (both 0.213) is unexplained
They are different algorithms yet produce the *identical* AME to 3 dp. Likely because
HMA uses a copula for the single fitted table here, but unexamined it looks like a
copy-paste bug. *Fix:* confirm they ran distinctly (different sampled values), and note
why AME coincides, or a reviewer suspects the harness.

### D7 — The reference-mode "real" data is itself synthetic (Gamma draws we wrote)
`_reference_mode_task` builds the "real" table from our own `rng.lognormal`. So SDV is
imitating *our* synthetic data, and the whole reference-mode comparison is
synthetic-on-synthetic. Defensible for a controlled experiment, but a reviewer wants ≥1
**genuinely real public dataset** (UCI/OpenML) in reference-mode or the external
validity of E5 is weak. *Fix:* add one real dataset; derive its spec from its actual
monthly aggregates; run all baselines on it.

---

## What Round 2 did NOT find wrong (genuinely solid)
- The Prop-4 scale-invariance result and its control (B1 fix) hold up — the strongest
  part of the paper now.
- AME=0 ∧ CSAT=0-for-NaiveRescale is a *real* logical separation (modulo M5/M7 rigor).
- The honest cold-start `✗` for SDV on spec-mode is correct and well-recorded.
- Determinism of the *engine* (Misata DET=1) is real and verified independently.

---

## Verdict
Round 1 fixed the conceptual blockers. **Round 2 finds the experiments are not yet
rigorous enough to back the claims:** SDV is unseeded (B3), the reference-mode SDV means
are single draws with one wildly-variant exception (B4), and the contribution-defining
CSAT result is n=1 with a reverse-engineered cap (M5). None is fatal to the *thesis* —
they are all "your evidence is thinner than your claim." That is precisely the gap
between "promising" and "accept."

**Priority:** B3 (seed SDV properly + DET over ≥3 pairs) → B4 (real SDV variance, claim
only what it supports) → M5 (CSAT across ≥3 tasks, semantic caps) → M7 (stop printing
0.000) → D5/D6/D7. After these, a third pass.
