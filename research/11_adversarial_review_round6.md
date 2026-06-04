# Adversarial Review — Round 6 (hardcore: out to break the paper)

**Status:** brick 10. This reviewer is hostile by assignment. The paper now makes a
*bold* claim — "a structural limitation of the dominant paradigm" — and bold claims
invite the sharpest knives. I attack the strongest version of the paper, not a strawman.
I do not soften. Severity: **F** = fatal-if-true (could sink it), **S** = serious, **N**
= niggle. Where an attack *fails*, I say so (it tells the author what's bulletproof).

---

## FATAL-IF-TRUE

### F1 — "Imitation cannot ingest a target" is FALSE as stated; conditional generation exists
The central claim is that imitation methods "have no mechanism to ingest a target." A
reviewer who works on generative models will object immediately: **conditional** models
*do* ingest targets. CTGAN itself is *conditional* (the "C"). Diffusion models support
classifier/guidance conditioning. One can train SDV/CTGAN conditioned on the period, or
post-hoc reject/reweight samples to hit an aggregate, or add a moment-matching loss. So
the unqualified claim "imitation structurally cannot conform" is **too strong and
attackable** — a reviewer will say "you didn't try conditional CTGAN or a guided
diffusion baseline; your gap is an artifact of not implementing the obvious fix."

*Why fatal:* the whole reframed headline rests on this being a *structural* impossibility.
It is not structural — it is that *off-the-shelf* imitation tools, used as designed,
don't take aggregate targets. That is a real and useful finding, but it is an
**empirical/engineering** gap, not an **impossibility**.

*Fix (mandatory, choose one):*
(a) **Weaken to what's true:** "off-the-shelf imitation tools provide no interface for
exact aggregate targets, and naive conditioning does not achieve *exact* conformance" —
then SHOW it: implement at least one conditional/guided baseline (conditional CTGAN, or
SDV + rejection/reweighting) and demonstrate it still misses *exact* aggregates (it
will — sampling can't hit an exact sum), which actually *strengthens* the real claim:
exactness, not conformance-in-expectation, is the bar. OR
(b) **Re-scope the claim to "exact" conformance**: imitation can approximate a target in
expectation but cannot hit it *exactly* (closed-form, zero variance), which is the
genuinely defensible structural statement (a sampler cannot produce a deterministic exact
sum). Make "exact vs in-expectation" the axis, not "can vs cannot."
Without this, F1 is the single most likely reason a competent reviewer rejects.

### F2 — The "74–87% miss" may be an artifact of the date-construction, not of imitation
The real-data result depends on `month = 1 + (HouseAge mod 12)` — a mapping *we* chose.
The monthly "targets" are sums over an arbitrary binning of a non-temporal feature. A
reviewer asks: **is SDV missing because it can't conform, or because the "month" signal
is pure noise it correctly ignores?** If `HouseAge mod 12` is essentially random w.r.t.
`MedHouseVal`, then the per-month sums are near-equal, and SDV reproducing the marginal
*should* roughly hit them — yet it misses by 74%. That large miss on a near-uniform
target is *suspicious* and suggests the AME metric may be inflated by how targets are
defined, not by a real conformance failure.

*Why fatal-if-true:* the headline number could be an artifact of an arbitrary,
adversarially-constructed target rather than a real phenomenon.

*Fix (mandatory):* (i) report the *dispersion* of the monthly targets — if they are
near-equal, a 74% miss needs explaining; (ii) verify AME is computed against the same
period definition for all generators (a column-aliasing bug here would be catastrophic);
(iii) ideally use a dataset with a *genuine* temporal column (real dates), so "month" is
not our construction. Until F2 is closed, the primary real-data result is not trustworthy.

---

## SERIOUS

### S1 — Misata and NaiveRescale are identical on every real-data metric; the paper's own honesty undercuts its tool
On the real task, Misata = NaiveRescale = AME 0, same FIVR, same DET, same `input=schema`,
and the paper concedes no marginal advantage there. A reviewer: **"On the one real
dataset, your contribution is indistinguishable from a five-line rescale script."** The
paper is honest about this, but honesty doesn't make it less damaging — the *system*
contribution evaporates on real data, leaving only the benchmark + the negative result
about imitation. *Fix:* accept that the contribution on real, non-curated data is the
*benchmark and the paradigm finding*, not the tool; make the tool's value explicit where
it actually exists (curated-domain NL convenience + the closed-form guarantees + speed),
and don't let the reader conclude "rescale would have done it."

### S2 — Every "exact AME=0" is true by Prop 1 *for tasks we accept*; the benchmark cannot be failed by the proposing method
By construction Misata attains AME=0 on any task admitted to the suite (Prop 1), and we
"verify AME=0 achievable before inclusion." A reviewer calls this **a benchmark its
author cannot lose.** That is the classic self-serving-benchmark allergy. *Fix:* include
tasks the engine *cannot* do (e.g. a joint two-metric target, a cross-FK aggregate, an
arbitrary fixed external marginal under exact sum — the P★ case) and report Misata's
*failure* there. A benchmark where the proposing tool sometimes loses is 10× more
credible. Right now there is no task in the suite Misata does not ace.

### S3 — "Conformance not fidelity" reframing may be re-labeling, not discovery
A skeptical reviewer: the field already knows constraint-satisfaction (QAGen) and
fidelity (SDV) are different goals. Is "conformance vs fidelity" a genuine new axis or a
rebranding of "constraint-based vs learning-based generation," which is decades old? *Fix:*
sharpen what is *new* — not the existence of constraint-based generation, but (i) the
*analytical-outcome* target class (curves/rates/shares on metric columns, vs QAGen's query
cardinalities) and (ii) the *benchmark* that measures it across paradigms. Claim the
benchmark and the target class, not the dichotomy.

### S4 — The math contribution, honestly, is small
Prop 0 is "Dirichlet = normalized Gammas conditioned on sum" (a 1955 textbook fact).
Prop 4 scale-invariance is "multiplying by T/Σ scales the sample" — almost a tautology.
A theory reviewer will say the §3 "characterization" is *exposition of known facts*, not
a contribution. The paper already concedes "no new theorem," but then leans on the math
as C1. *Fix:* demote C1 from "formal characterization" (sounds like new theory) to
"correct *attribution and analysis* of an existing engine" — its value is *clarity and
honesty*, and the genuinely non-obvious bit (condensation explains why the shape-fixing
choice matters) should be the one highlighted sentence.

---

## NIGGLES

- **N1** CTGAN AME 0.867 ± 0.107 (3 seeds) vs GC/HMA 0.739 — the *deep* model does
  *worse* than the simple copula. Reviewers may ask why; pre-empt (CTGAN overfits the
  marginal, copula is smoother) or they'll assume a config error.
- **N2** The 2×2 table's top-right cell "undefined (nothing to resemble)" — a reviewer
  notes you *can* define cold-start fidelity (resemble a *class* of data). Minor, but the
  cell is glib.
- **N3** "First benchmark for conformance" — "first" claims are dangerous; soften to
  "to our knowledge, the first benchmark that measures outcome-conformance across the
  cold-start/data-available × fidelity/conformance quadrants."

---

## Attacks that FAILED (these are bulletproof — keep them prominent)
- The retraction apparatus: I tried to spin "they retracted 4 claims" as instability; it
  reads instead as rigor. Cannot break it.
- E8 case study: a real SQLite DB with the outcome verified in SQL is concrete and
  unattackable. Strongest single artifact.
- Determinism + closed-form + 7–11× speed: real, measured, uncontested.
- The honesty about NaiveRescale tying AME: damaging to the tool, but unattackable as
  integrity — and it correctly redirects the contribution to the benchmark.

---

## Verdict — the hardcore read
The reframe to "structural limitation of the dominant paradigm" **over-reached** and
created the biggest vulnerability yet (F1): the limitation is *off-the-shelf/exactness*,
not *structural/impossibility*. Fix F1 (re-scope to "exact conformance," add a
conditional baseline) and F2 (validate the real-data target is not an artifact), add S2
(tasks Misata fails), and the paper is genuinely solid — a benchmark + an honest,
*correctly-scoped* negative result + a fast deterministic reference tool. Leave F1/F2 and
a sharp reviewer sinks it on "overclaim" and "artifact."

**Priority:** F1 (re-scope to exact-conformance; add 1 conditional baseline) →
F2 (validate/replace the real-data target construction) → S2 (add tasks the tool fails) →
S1/S3/S4 (scope the contribution claims) → N1–N3.

**Honest stance:** Rounds 1–5 made it true and interesting; Round 6 says the *interesting*
reframe pushed one claim past what's defensible. Pull that one claim back to "exact, not
structural," and you have something both interesting AND unbreakable on that axis. That is
better than an exciting claim that a reviewer dismantles in the first paragraph.

---

## RESOLUTION LOG (Round-6 fix pass — the final cleanup)

- **F1 RESOLVED (re-scoped, the honest way).** Dropped "imitation structurally cannot
  conform." Re-scoped the whole claim to **exact vs in-expectation**: off-the-shelf tools
  have no target interface, and crucially *no sampler can hit an exact aggregate*. Added
  a **per-period conditional-SDV steelman** (the reviewer's obvious fix) and ran it: it
  improves 0.739→**0.189** but never reaches 0. Exactness is the structural divide.
  Abstract, §1.1, the 2×2, and the E5 reading all rewritten accordingly.
- **F2 RESOLVED (validated, not assumed).** Checked the real-data targets: CV≈0.30, one
  bin ~2×, `HouseAge mod 12` ~uncorrelated with value (r=−0.03) — targets are NOT
  near-uniform, so the 74–87% miss is a genuine per-bin-structure failure (verified
  per-month, e.g. month 05: 7103 vs 3810), not a degenerate-target artifact. Stated in
  the E5 reading.
- **S2 RESOLVED.** Added **E10 / P★**: exact sum + arbitrary external Pareto marginal.
  Misata hits the sum but FAILS the marginal-match (W1=0.78) — a task the proposing
  method loses, reported as such. The benchmark can now be failed.
- **S4 RESOLVED.** C1 demoted from "formal characterization" to "correct attribution and
  analysis" — value is clarity/honesty, not new theorems (which we never claimed).
- **S1/S3, N1–N3:** acknowledged in text (NaiveRescale tie → contribution is benchmark +
  paradigm finding on real data; "conformance vs fidelity" sharpened to the analytical-
  outcome target class + the benchmark; CTGAN-worse-than-copula noted).

**Final stance.** Round 6 caught the one overclaim that Round 5's "make it impressive"
push introduced. It is now pulled back to **exact-conformance**, which is interesting AND
unbreakable on that axis, evidenced by a steelman that tries imitation's best and still
can't reach 0. The benchmark contains a task the tool fails. This is the honest stopping
point: the claims match the evidence, and the evidence is real.
