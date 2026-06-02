# Adversarial Review — read this as a hostile Area Chair would

**Status:** brick 5. An intentionally harsh self-review of the research as it stands.
Severity tags: **[BLOCKER]** would cause reject; **[MAJOR]** weak-reject risk;
**[MODERATE]** reviewer will ding; **[MINOR]** polish. Each item has a concrete fix.
Nothing here is rhetorical — every claim is checked against the actual code/proofs.

---

## BLOCKERS (fix before any submission)

### B1 — The Prop-5 figure has a confound that may invalidate its central claim
`prop5_curve.py` generates the "exact" sample with a **Dirichlet(α)** partition whose
α is tuned so its CV matches a target **lognormal**'s CV, then measures 1-Wasserstein
to that lognormal. But a (scaled) Dirichlet marginal is **Beta**, not lognormal. As σ
grows the two families diverge in *shape*, not only in spread. **So the rising MD may
be measuring "Beta vs lognormal family mismatch" — which grows with σ regardless of
any sum constraint — not the condensation effect we attribute it to.** A sharp reviewer
will say the figure does not isolate the phenomenon it claims.

*Why it matters:* this is the paper's headline scientific result (theory makes a
falsifiable prediction; experiment confirms). If the mechanism is confounded, the
contribution collapses to "rescaling distorts heavy tails," which is folklore.

*Fix (mandatory):* add the **missing control** — the *unconstrained* counterpart.
Draw `n` i.i.d. Gamma(α) **without** conditioning on the sum (or i.i.d. from the
target lognormal directly), measure MD to the target, and plot it on the same axes.
The claim is only supported if **constrained MD rises *above* unconstrained MD as σ
grows** — i.e. the *gap* between the two curves is the condensation cost. Report that
gap, not the raw constrained MD. If the gap is flat, the result is a confound and must
be reframed honestly. Either way the paper is stronger for showing the control.

### B2 — No "naive exact-rescale" baseline ⇒ AME = 0 looks trivial and undefended
The E5 headline is Misata AME = 0 where SDV/Faker fail. But **hitting a single
aggregate exactly is trivial** — draw any positive values, multiply by `T/Σ`. A
reviewer will immediately ask: *"Isn't AME = 0 just rescaling? What's the
contribution?"* We currently have **no baseline that achieves AME = 0**, so the
benchmark never demonstrates that the *hard* part is hitting the aggregate **while
preserving marginals, FK integrity, and temporal order simultaneously**.

*Fix (mandatory):* add a **NaiveRescale baseline** — Faker-style realistic draws,
then multiply each period to hit its target. It will score **AME = 0 too**, but should
show worse marginal/integrity behavior (or reveal that naive rescale is actually fine,
which we then must address). This baseline is what turns "we hit 0" into "hitting 0 is
easy; hitting 0 *jointly with R/I/temporal/zero-data* is the contribution." Without
it, the central result is rhetorically defenseless. (This also directly operationalizes
the construct-validity threat already noted in §7 of the design doc.)

---

## MAJOR (weak-reject risk)

### M1 — Three tasks is a demo, not a benchmark
SpecBench currently runs **2–3 hand-built tasks**. The paper's framing ("the first
conformance benchmark") cannot rest on n=3. Reviewers of a *benchmark* paper expect
breadth and diversity as the core deliverable.
*Fix:* build the full 18-domain × 4-config grid the design doc describes (≥40 tasks),
with frozen specs+oracles, and report aggregate statistics, not anecdotes.

### M2 — No relational (multi-table) learned baseline, yet "relational" is the headline
We run only single-table SDV (GaussianCopula, CTGAN). The title says *relational*; the
fair imitation comparator for FK integrity is **SDV HMA** (and ideally RelDiff). Their
absence lets a reviewer say "you avoided the baselines that handle FK."
*Fix:* run SDV **HMASynthesizer** on the multi-table reference tasks; attempt RelDiff
if feasible. Report FIVR for each — this is where our by-construction 0 is meaningful.

### M3 — Single seed everywhere; no error bars, no significance
`measure.py`, `runner.py`, and `prop5_curve.py` use one seed each. Every number in the
paper is a point estimate with no variability. A methods reviewer treats single-seed
results as unverified.
*Fix:* ≥10 seeds for E5 and E6; report mean ± std (or 95% CI). For AME=0 (deterministic
by construction) state it's exact, not averaged. For SDV/CTGAN report the spread —
their variance is itself evidence (esp. CTGAN's non-determinism).

### M4 — The Faker baseline's failure is partly an artifact of my adapter
In `baselines.py` the Faker metric column is drawn `lognormal(scale=100, σ=0.6)` —
an **arbitrary choice in our own code**. Faker's AME (0.735, 1.823) is therefore
partly determined by a scale *we* picked, not by Faker. A reviewer calls this rigging.
*Fix:* either (a) give Faker its fairest shot (let its scale match the spec's implied
mean μ, so only the *temporal shape* is missed), or (b) explicitly state Faker has no
mechanism to read targets, so AME is reported as "no-target-ingestion" qualitatively,
not as a tuned number. Honesty here pre-empts the rigging charge.

---

## MODERATE

### D1 — Prop 0 says "exact sampling"; controlled rounding makes it *approximate*
The proof asserts the Dirichlet construction reproduces the Gamma-conditional law
"exactly," then says rounding "projects onto the grid without changing the sum." True
for the *sum* (Prop 1), but rounding **perturbs the marginal** by O(1/U). So Prop 0's
"exact sampling from the conditional" is exact only pre-rounding; post-rounding it is
O(1/U)-approximate in distribution (though exact in aggregate).
*Fix:* state precisely — "exact in aggregate (Prop 1); the per-row law equals the
Gamma-conditional up to an O(1/U) rounding perturbation (Prop 2 empirics confirm
≤0.1%)." Cheap to fix, removes an easy attack.

### D2 — Construct validity: are we testing SDV on a task it was never built for?
Reference-mode scores SDV on AME against targets it never received. We *say* this is
the point (it can't ingest targets), and the threats section covers it — but the E5
prose must frame it as "demonstrating a structural capability gap," never as "SDV is
bad." The current conclusion sentence ("reach only 0.21–0.70") flirts with the unfair
reading. Tighten to: SDV is not given the targets *because it cannot accept them*; the
number quantifies the gap, not a deficiency on SDV's own objective.

### D3 — Breadth claims not validated by the benchmark
The draft cites "18 domains, 15 locales" (a *library* property) near benchmark claims.
A reviewer may read this as a benchmark-coverage claim it doesn't earn at n=3.
*Fix:* separate clearly — library capability vs SpecBench coverage — and only claim
the coverage the suite actually exercises.

### D4 — MD normalization and finite-sample W1 bias under heavy tails
MD divides 1-Wasserstein by reference IQR. Finite-sample W1 is **biased upward for
heavy tails** and the estimate is noisier as σ grows — which could *itself* inflate
the heavy-tail end of the Prop-5 curve independent of condensation.
*Fix:* use equal, large sample sizes for both arms; bootstrap a CI on each MD point;
consider a bias-corrected or quantile-based distance and show robustness.

---

## MINOR / polish

- **P1** Python 3.14 in `.venv_specbench` is bleeding-edge; pin a mainstream version
  (3.11/3.12) for reproducibility so reviewers can rebuild.
- **P2** ~11 `[CHECK]` citations remain (recent arXiv); confirm each before submission.
- **P3** The Prop-5 σ grid is hand-picked; state why, or sweep uniformly with more points
  around the knee (σ∈[1.2,1.6]) to characterize the transition sharply.
- **P4** No ablation of α (concentration) effect on conformance vs realism; one figure
  would strengthen the "α is a principled knob" claim.

---

## POSITIONING RISK (not a bug, but the deepest threat)

**"This is QAGen for aggregates."** The closest prior work (QAGen, DataSynth) already
does declarative-constraint-driven DB generation. A VLDB reviewer may see our work as
an incremental extension (cardinalities → aggregates/rates) with a tool attached. The
verdict doc acknowledges this; the *paper* must actively defeat it:
- Sharpen the delta: **continuous distributional outcomes + per-row realism guarantee
  (Prop 2/5) + zero-data NL interface + the conformance evaluation paradigm** — none of
  which QAGen addresses (it targets exact intermediate cardinalities via symbolic
  execution, not realistic marginals under aggregate constraints).
- Lead with the **frontier result (Prop 5)** as the intellectual core — QAGen has no
  analogue of the conformance/fidelity impossibility. That is the idea a reviewer
  remembers, and it is genuinely ours-to-frame (built on condensation theory, cited).

---

## Honest overall assessment

**Current state:** a rigorous, honest *skeleton* with correct math, a real (if narrow)
benchmark, and one confounded centerpiece figure. As-is, likely **reject** at a top
venue (B1, B2, M1–M3). **But every blocker is fixable without new theory** — they are
experimental-rigor gaps, not conceptual dead-ends.

**Path to credible submission, in priority order:**
1. Fix B1 (add the unconstrained control to Prop-5) — protects the headline result.
2. Fix B2 (add NaiveRescale baseline) — defends the core contribution.
3. M1 (full task suite), M2 (HMA/relational baseline), M3 (multi-seed + CIs).
4. D1–D4 wording/methodology fixes; P-items; finish citations.
5. Rewrite Related Work to defeat the "QAGen-for-aggregates" read, leading with Prop 5.

If 1–3 are done and the Prop-5 *gap* survives the control (it very likely will, since
condensation is real), this becomes a defensible VLDB-tool / NeurIPS-D&B submission —
and an honest one.
