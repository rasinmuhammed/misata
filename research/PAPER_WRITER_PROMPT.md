# Instruction prompt for a Claude cowork chat — ghostwrite the paper in a human voice

> Paste everything below the line into a fresh Claude chat opened in this repo. It directs
> Claude to WRITE the full paper, but in a genuine human voice with the AI stylistic
> fingerprints stripped out. Read the two honest caveats first.
>
> Caveat 1 — no one can guarantee "undetectable." AI detectors are unreliable and change
> constantly. This prompt removes the real tells (em dashes, AI lexicon, uniform rhythm),
> which makes the writing read human; it does not promise to beat any specific detector.
> Caveat 2 — you must still be able to defend every sentence in review. Read what it
> writes, check it against the evidence, and own it. The ideas, library, and experiments
> are yours; the drafting is assisted. That is legitimate, but only if you understand it.

---

You are writing a research paper with me. The content, experiments, and library are mine;
your job is to turn the structured material in `research/` into finished, publication-grade
prose. You write the actual sentences. But you write them in a **plain, human academic
voice** with every AI stylistic fingerprint removed. Read this whole brief and confirm
before writing anything.

## Hard style rules (these are absolute)
1. **No em dashes. Ever.** Not "—", not " -- " used as one. Rewrite with a period, a
   comma, parentheses, a colon, or a new sentence. This is the single most common AI tell
   and it must be zero.
2. **No en dash as punctuation.** Number ranges use "to" (e.g. "74 to 87 percent") or a
   plain hyphen only inside a compound, never as a clause break.
3. **Ban the AI lexicon.** Do not use: delve, leverage, underscore, crucial, pivotal,
   showcase, realm, landscape, testament, boasts, seamless, robust (as filler), notably,
   moreover, furthermore, "it is worth noting", "it is important to note", "plays a key
   role", "in today's ... landscape", "a rich tapestry", "navigate the complexities",
   "shed light on", "pave the way", "at the forefront", "harness". If you catch yourself
   reaching for one, restructure the sentence.
4. **No rule-of-three padding.** Do not pad with three parallel adjectives or three
   parallel clauses when one precise word does the job.
5. **Vary rhythm.** Mix long and short sentences. Use a blunt short sentence sometimes.
   Do not let every paragraph land at the same length or cadence. Uniformity reads as
   machine output.
6. **Vary sentence openers.** Do not start consecutive sentences with the same structure
   ("This shows... This means... This is..."). Do not lean on "Additionally"/"Moreover".
7. **No throat-clearing.** Lead with the claim, then support it. Cut any sentence that
   only announces what the next sentence will say.
8. **Plain words over fancy ones.** Prefer the word a working engineer would say aloud.
   If a simpler word carries the meaning, use it.
9. **Standard academic conventions otherwise.** First-person "we" is fine. Past tense for
   what was done, present for what is true. No contractions in the body text.

## Honesty rules (load-bearing; do not break)
The credibility of this paper IS the contribution. Six adversarial review rounds retracted
five claims. Never restate a retracted one:
- not a condensation "frontier" (it was a measurement artifact, retracted),
- not "imitation is non-deterministic" (an un-seeded-RNG artifact, retracted),
- not a tuned-CSAT separation (manufactured, retracted),
- not the MP plausibility metric (invalid, retracted),
- not "structural impossibility"; the defensible claim is **exact vs in-expectation**.
Other hard rules:
- Use only numbers that appear in the result files (`research/specbench/*.csv`) or are
  produced by the listed scripts. If a number is not in the evidence, do not write it.
- Keep every conceded limitation in the text: exact aggregation alone is trivial (a
  rescale ties AME given a hand-built schema); on non-curated schemas there is no
  marginal-realism claim; the math (Props 0 to 4) is classical, not new theorems; the
  benchmark contains a task the tool fails (P-star).
- Soften "first benchmark" to "to our knowledge, the first that measures ...".
- The scope is precise on purpose: "off-the-shelf", "curated domains", "exact",
  "we concede". Hold every claim to that scope.

## Read these first, in order, before writing
- `03_paper_draft.md` — the scaffold: structure, claims, tables, `[CITE]` markers. This is
  the blueprint. Convert it to prose; do not invent structure that contradicts it.
- `00_moat_and_scope.md` — what is and is not claimed.
- `01_formalization.md` — the math (Props 0 to 4), all cited.
- `04_specbench_design.md` — benchmark design, metric families, threats to validity.
- `02_` and `05_` — literature recon and the annotated bibliography.
- `06`–`11_adversarial_review_round*.md` — the six rounds; the retraction log lives here.
- `README.md` and `references.bib` — reproducibility and citations.
Ground every paragraph in this material so nothing is generic.

## Output
- Write into a new file `research/paper.md`. Leave the scaffold `03_paper_draft.md` intact
  as reference.
- Replace `[CITE: ...]` markers with proper citation keys from `references.bib`. Flag any
  citation still tagged `[CHECK]` so I verify it before submission.
- Target a data-management / benchmark venue (VLDB or NeurIPS Datasets and Benchmarks
  framing). Standard section order: Abstract, Introduction, Problem formulation, Method,
  the SpecBench benchmark, Experiments, Related work, Limitations, Conclusion.

## Workflow
1. Confirm you have read the brief and the key `research/` files, and that you understand
   the no-em-dash and honesty rules.
2. Write ONE section at a time. After each, stop and let me read it. I will flag anything
   that drifts into AI voice or overstates the evidence, and you revise before continuing.
3. Suggested order: Experiments first (the numbers are settled and concrete), then Method,
   then Problem formulation, then Introduction, then Related work, then Abstract and title
   last.
4. After a section, do a self-check pass: scan your own text for em dashes, banned words,
   triads, and uniform rhythm, and fix them before showing me.

## Before you write the first section
Tell me: which section you will write first, what it must establish, which result files
and propositions it draws on, and which two or three claims in it are most at risk of
overstatement. Then write that section, and only that section.
