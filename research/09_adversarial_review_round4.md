# Adversarial Review — Round 4 (fresh reviewer, post-D8/M9)

**Status:** brick 8. Fourth hostile pass. Reads the state after Round-3 fixes + the D8
real-dataset task + the M9 shape check. New issues only. The bar now: this work has been
honest to a fault — Round 4 asks whether the *scope of the claim* still matches the
*scope of the evidence*, and scrutinizes the new code (the Misata NL→schema fallback) as
fresh attack surface. Severity tags as before.

> Rounds 1–3 removed four false claims. Round 4's uncomfortable theme: the honest fixes
> have quietly **narrowed the contribution to a point where the framing oversells the
> evidence** — not by stating falsehoods, but by emphasis. See B6.

---

## BLOCKER

### B6 — The title/abstract still promise "natural-language" as a pillar, but the evidence shows the NL path is the weakest, most domain-gated part
The paper is titled around *outcome-conformant relational synthesis* and the abstract's
C3 sells "maps a **natural-language** or declarative specification." But the accumulated
evidence now says:
- On the 18 curated domains, NL works — but those domains are **hand-authored priors**,
  not a general NL→schema capability. (D3/external-validity, never fully resolved.)
- On the **one genuinely arbitrary schema** we tested (D8, California Housing), the NL
  path **failed outright** (AME=∞, unknown domain) and only the *declarative-schema*
  fallback conformed. We labeled that `input=schema` honestly — which means **on real,
  non-curated data, Misata's NL claim does not hold**, and its conformance there is via
  the same hand-built-schema route NaiveRescale uses.

So the defensible contribution is narrower than the framing: *given a schema + outcome
targets (NL OR hand-built), the engine produces exact, deterministic, integrity-
preserving conformant data in closed form, and uniquely so among cold-start methods on
its curated domains.* The "from a sentence" headline is true **only inside the curated
domain set** — which is a library feature, not a general scientific capability.

*Fix (framing-to-evidence alignment, mandatory):* either
(a) **re-title/re-scope** around *declarative* outcome-conformant synthesis, present NL
as a convenience layer over the curated domains (clearly bounded), and make the
**closed-form exact-conformance engine + the conformance benchmark** the contribution; or
(b) if NL generality is to remain a pillar, **evidence it** — show NL→schema working on
N unseen schemas, which today it does not. Given the honest D8 result, (a) is the
truthful path. This is a blocker because title/abstract claims must match what the
experiments support, and right now the strongest-sounding claim is the least-supported.

---

## MAJOR

### M11 — The declarative fallback uses a generic lognormal(μ=0.5,σ=0.5); on real data its *marginal* will be wrong even though AME=0
The new `_generate_from_explicit_spec` hard-codes
`distribution_params={"lognormal", μ=0.5, σ=0.5}` for the metric. On California Housing
the real `MedHouseVal` marginal is nothing like that lognormal. So Misata will hit the
monthly **sums** exactly (AME=0) but its **per-row distribution** on the real task is an
arbitrary default — i.e. exactly the "conforms to aggregate, wrong marginal" critique we
leveled at NaiveRescale (R2). On the real-data task, Misata and NaiveRescale are then
*both* "right sum, wrong marginal," and we have **no metric in the table that
distinguishes them there** (MP was retracted as invalid in R3). *Fix:* acknowledge that
on non-curated data the engine's marginal realism depends on a supplied distribution;
either fit the metric distribution from the reference table (making it a fair
reference-mode generator) or state plainly that marginal realism is a *curated-domain*
property, not a general one.

### M12 — Reference-mode now has TWO tasks but the headline number (SDV AME≈0.21) comes from the synthetic one; the real one may tell a different story
The strong quantitative claim ("SDV misses by 21% even trained on target-consistent
data") is from `revenue_reference_mode`, whose "real" data we generated. On the actual
real dataset (California Housing), SDV's AME was ~0.74 in a quick check — *worse*, which
helps the claim, but the spread and the fact that the curve there is the *real* monthly
structure (not a clean ramp) means the number must be reported from the **real** task as
primary, with the synthetic one demoted to a controlled illustration. *Fix:* lead
reference-mode results with California Housing; report `revenue_reference_mode` as a
controlled sanity check, not the headline.

### M13 — Five tasks, of which only ONE is multi-table; "relational" is still thin
The title says *relational*. Of the suite: 3 single-fact-table curve tasks, 1 integrity
task, 2 reference tasks (single table). Only `ecommerce_integrity` exercises FK, and HMA
(the relational learned baseline) only runs on a single-table reference. The relational
claim rests on FIVR=0-by-construction on essentially one task. *Fix:* add ≥2 genuinely
multi-table tasks where a learned relational baseline (HMA) can realistically break FK,
so FIVR earns its headline place (carries over D9 from R3, still open).

---

## MODERATE

### D10 — `prop5_curve.py` / `prop5_summary.csv` filenames still say "prop5" after the result became Prop. 4
Cosmetic but a reviewer browsing the repo sees `prop5_*` producing a "Prop. 4" figure —
looks like leftover/confusion. *Fix:* rename to `scale_invariance_*` for clarity.

### D11 — The suite's AME=0 tasks were "verified AME=0 achievable before inclusion"
This is good practice but also a subtle selection effect: we only include curve tasks the
engine can already hit exactly. A reviewer could call this teaching-to-the-test. *Fix:*
state explicitly that AME=0 is a *proven property* (Prop. 1) for any schema+curve the
engine accepts, so inclusion-verification is confirming applicability, not cherry-picking
favorable tasks — and show one task where targets are *infeasible* (e.g. demand exceeds
row-count×max) and the engine reports it rather than silently missing.

### D12 — No wall-clock/scaling story despite "closed-form, no training" being a selling point
We claim closed-form efficiency vs CTGAN's 50s training, but report only single small-n
timings. *Fix:* a throughput-vs-rows curve (Misata vs SDV) makes the efficiency claim
concrete; it's cheap and strengthens a real advantage.

---

## What Round 4 confirms is solid
- The honesty apparatus (4 rounds, documented retractions) is now itself a contribution
  and a credibility moat.
- Prop. 0 + Prop. 4 + Prop. 1/2/3: the mathematical core is correct and well-cited.
- D8 was done *right*: a real dataset, an honest negative finding about NL gating,
  correctly labeled. That single act of not-faking is worth more than a faked win.
- M9: AME provably captures shape (per-period 0.79/0.48/0.81). Clean.

## Verdict
The work is now **honest and correct but over-framed**: the title/abstract lead with
"natural-language" and "relational," which are the two *least* evidenced parts (B6, M13),
while the genuinely strong, proven parts (closed-form exact conformance; the
conformance benchmark; scale-invariance; the honest frontier) are undersold. This is
fixable entirely by **re-scoping the claims to match the evidence** — declarative-first,
NL as a bounded convenience, relational as future work or backed by more multi-table
tasks. No new experiments are *required* for B6 (it's a framing fix), but M11–M13 each
need either a wording concession or a modest experiment.

**Priority:** B6 (re-scope title/abstract to declarative; bound the NL claim) →
M12 (lead reference-mode with the real dataset) → M11 (concede/​fix marginal on
non-curated data) → M13 (more multi-table tasks) → D10–D12.

**Meta-note for the author:** after four rounds the right next step may not be a Round 5
— it is to *write the honest paper to the scope the evidence supports* and stop
expanding claims. The evidence supports a solid systems/benchmark contribution. The
danger now is not dishonesty (that's been drilled out) but scope-creep in the framing.
