# Adversarial Review — Round 3 (fresh reviewer, post-honesty-pass)

**Status:** brick 7. Third hostile pass, reading the *final multi-seed numbers* and the
state after Rounds 1–2 stripped the manufactured separators (condensation frontier,
non-determinism, tuned CSAT caps). New issues only. Checked against `/tmp/e5_final.txt`
and the current paper draft.

> Rounds 1–2 made the work *honest*. Round 3's job: now that nothing is inflated, is the
> contribution still *visible*? The uncomfortable answer is mostly no — see B5.

---

## BLOCKER

### B5 — After the honesty pass, the leaderboard no longer separates the contribution from a trivial baseline
The final spec-mode tables (SaaS, fintech, ecommerce) read, for **every** cold-start
baseline:

| | AME | CSAT | FIVR | DET | CSC |
|---|---|---|---|---|---|
| misata | ~0 | 1.0 | 0 | 1 | 1 |
| **naive_rescale** | ~0 | 1.0 | 0 | 1 | 1 |
| faker | 0.82–0.90 | 1.0 | 0 | 1 | 1 |

**Misata and NaiveRescale are now identical on every visible metric.** We *correctly*
removed the tuned cap that faked a CSAT gap (R2), but in doing so we removed the only
column that distinguished the contribution from "Faker + multiply by T/Σ." A reviewer
reads this table and concludes: *the proposed method ties a five-line rescale script.*

This is the deepest problem yet, and it is structural, not cosmetic: **the benchmark as
currently instrumented cannot measure what we claim is the contribution.** We assert the
real difference is (i) consuming an NL spec vs a hand-built schema, and (ii) an
undistorted domain-calibrated marginal — but **neither is a column in E5.** Claims not
in the table do not exist to a reviewer.

*Fix (mandatory, and it is a measurement fix, not a spin fix):*
1. **Add a Marginal-Plausibility metric (MP)** to Family A/B and put it in the main
   table. Operationalize the drift we already measured by hand (NaiveRescale mean
   $150→$76, tail →$1955 vs engine $1221): MP = 1-Wasserstein between the generated
   metric marginal and the **spec-implied reference** (domain-calibrated lognormal at
   the implied mean), normalized. Expectation: Misata MP small; NaiveRescale MP large.
   *This must be run, not asserted — and if NaiveRescale's MP is NOT worse, the
   contribution claim is in real trouble and we need to know.*
2. **Add an "input" column** to E5: `spec=NL` vs `spec=hand-schema`. NaiveRescale and
   Faker require a hand-built schema (every column/FK/period enumerated in our adapter);
   Misata consumes the sentence. This is a real, categorical capability difference that
   belongs in the table, not the prose.

Until B5 is fixed the paper has no defensible headline. (It is fixable — the separating
signal demonstrably exists; it is just not yet instrumented.)

---

## MAJOR

### M8 — The paper draft still contains the two RETRACTED claims verbatim
`03_paper_draft.md` lines ~326–347 still show the **single-seed** numbers (CTGAN AME
0.698, "DET 0", "non-deterministic … cannot reproduce its own output") — the exact
claims R2 proved false and retracted. The draft currently contradicts our own corrected
findings. *Fix:* rewrite E5 from `/tmp/e5_final.txt` (multi-seed, seeded SDV); delete
every "non-deterministic" sentence; SDV DET is now 1.0.

### M9 — Faker AME ≈ 0.82–0.90 is still nearly constant even on the NON-MONOTONE curve
M6 changed SaaS to a non-monotone curve specifically so AME would have to reflect shape.
Faker's AME barely moved (0.821 vs 0.899/0.900 on the monotone tasks). Either (a) the
metric is dominated by the overall scale mismatch and is insensitive to shape — in which
case AME is a weaker discriminator than claimed — or (b) it's fine and the near-equality
is coincidence. *Fix:* decompose AME into per-period errors for the non-monotone task and
show Faker misses the *dip* specifically; if it doesn't, reconsider whether AME captures
shape or just magnitude.

### M10 — All three curve tasks now declare `constraints=1` but CSAT=1.0 for everyone
With only `amount>0` left, CSAT is satisfied by every baseline including the trivial one,
so the column is now pure noise in the table (no discriminative value) yet occupies a
headline slot implying it matters. *Fix:* either find a *genuine* by-construction
constraint the engine guarantees and a rescale cannot (hard to do honestly — see R2), or
**move CSAT to a secondary table** and stop implying it separates methods.

---

## MODERATE

### D8 — Reference-mode still synthetic-on-synthetic (carried over from R2/D7, unfixed)
Still no real public dataset. With B5 removing the spec-mode separation, the
reference-mode result (where Misata's AME=0 genuinely beats SDV's 0.213) becomes *more*
load-bearing — so its "the real data is also ours" weakness now matters more, not less.
*Fix:* one OpenML/UCI dataset in reference-mode is now higher priority.

### D9 — "Faker + hand-wired FK" is labeled relational but our adapter gives it FIVR=0 trivially
We build its FKs by sampling valid parent ids, so FIVR=0 by construction — fine, but then
FIVR=0 across all baselines means that column, too, separates nothing on these tasks. The
FIVR contribution only shows where a baseline actually *can* produce dangling keys (a
learned multi-table method on a hard schema). *Fix:* include a reference-mode multi-table
task where HMA can realistically violate FK, so FIVR earns its place.

---

## What Round 3 confirms is solid
- The honesty itself: Rounds 1–2 retracted two false claims. That is the opposite of
  slop and is the project's strongest credibility signal.
- Prop. 4 scale-invariance + control: still the cleanest result.
- Reference-mode AME (Misata 0 vs SDV 0.213, seeded/deterministic): a real, correct
  separation — now the *primary* surviving quantitative claim.

## Verdict
Rounds 1–2 removed everything false. **Round 3 finds that what remains, while true, is
under-instrumented: the headline spec-mode table no longer shows a gap, because the gap
lives in two axes we measured by hand but never put in the benchmark (marginal
plausibility, NL-vs-schema input).** This is a *measurement* gap, not a *truth* gap — the
separating signal exists (we have the hand numbers). Fix B5 (add MP metric + input
column, run it), M8 (purge retracted claims from the draft), then the contribution is
both true *and* visible. Until then a reviewer would say "ties a trivial baseline."

**Priority:** B5 (instrument MP + input axis, RUN it) → M8 (rewrite E5 with final
numbers, purge retractions) → M9/M10 (AME shape check, demote CSAT) → D8 (real dataset).
