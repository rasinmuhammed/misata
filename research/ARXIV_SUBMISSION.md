# arXiv submission guide for this paper

Everything you need is in `research/latex/`. The ready-to-upload source archive is
`research/latex/misata_arxiv_submission.tar.gz` (it contains `main.tex`, `body.tex`,
`references.bib`, `main.bbl`, and `pstar_frontier.png`, all at the top level). It has been
test-compiled from scratch the way arXiv compiles it (pdflatex using the embedded `.bbl`,
22 pages, 31 references, no errors). Upload the archive, not the PDF: arXiv prefers LaTeX
source, and the source is what makes your paper indexed and re-typesettable.

---

## 1. Metadata to paste into the arXiv form

**Title**

```
Declarative Outcome-Conformant Synthesis: Exact, Closed-Form Specification Satisfaction and a Conformance Benchmark
```

**Authors**

```
Muhammed Rasin
```

(arXiv asks for authors in "First Last" form, comma-separated. Just `Muhammed Rasin`.)

**Abstract** (plain text; paste as-is)

```
We study a capability the dominant paradigm in synthetic tabular data does not provide:
exact satisfaction of a declared analytical outcome with no source data. Imitation methods
(copulas, GANs, diffusion) learn a real distribution and sample from it, and are judged on
fidelity to real data. A large, practical class of needs is different: generating data with
no source data ("cold start") that reproduces a declared outcome (a revenue curve, a churn
rate, a group share) across a relational schema. Off-the-shelf imitation tools offer no
interface for such targets, and no sampler can hit an exact aggregate, because sampling has
variance. On a real public dataset, off-the-shelf learned synthesizers trained on that very
data miss the declared monthly aggregate by 74 to 86 percent; a per-period steelman cuts the
miss to about 19 percent and still cannot reach 0; a closed-form generator reaches exactly 0.
We name this task outcome-conformant synthesis, argue its evaluation axis is conformance
rather than fidelity, and show the two axes are orthogonal. We contribute: (1) a formal
account showing a widely-used family of exact-aggregate generators is exactly conditional-sum
sampling of a Gamma population (via Lukacs' characterization), with closed-form exactness, a
closed-form marginal CV, and scale-invariance; a controlled experiment maps the boundary,
enforcing the exact aggregate costs at most 0.006 in 1-Wasserstein distance to an arbitrary
external marginal, the rest being shape-family mismatch; (2) SpecBench, to our knowledge the
first benchmark to measure conformance to analytical outcomes for cold-start relational
synthesis; and (3) a closed-form, deterministic reference system. Exact aggregation alone is
trivial; the contribution is conformance jointly with closed-form marginals, integrity,
determinism, and zero source data. We concede fidelity to imitation where real data exists.
```

**Comments** (the one-line note shown under the abstract)

```
22 pages, 1 figure. Benchmark and reference implementation (MIT): <your GitHub URL>
```

Replace `<your GitHub URL>` with your real repository link. This is the only place a repo
URL appears for readers, so put the real one here.

**Categories**

- Primary: `cs.LG` (Machine Learning) — broadest reach for a synthetic-data / benchmark paper.
- Cross-list: `cs.DB` (Databases) — the QAGen / test-data lineage audience.
- Cross-list (optional): `stat.ML`.

If you would rather lead with the database-systems audience, swap them: primary `cs.DB`,
cross-list `cs.LG`. Either is defensible; the paper sits between the two.

**License** — choose one on the form:

- "arXiv.org perpetual, non-exclusive license" (the default). Safest: it does not stop you
  from publishing the same work elsewhere later.
- "CC BY 4.0" if you want maximum reuse/openness. Pick this only if you are sure, since some
  later venues prefer the work not be under CC BY first.

I recommend the default non-exclusive license.

**Optional ACM/MSC class line** (you can leave blank): `H.2.8; I.6.5` (database applications;
model development) is reasonable for the cross-listing.

---

## 2. The one real hurdle: endorsement

arXiv requires a first-time submitter to `cs.LG` (and `cs.DB`) to be *endorsed* before the
first paper in that category is accepted. This is a spam-prevention step, not a quality
review. Two ways through it:

1. **Get auto-endorsed.** If you submit from an email arXiv recognizes as academic, you may
   be auto-endorsed. A personal Gmail will not trigger this, so you will most likely need
   option 2.
2. **Ask an endorser.** When you start a submission, arXiv gives you an endorsement-request
   link and a code. Send it to anyone who has recently published on arXiv in `cs.LG` or
   `cs.DB` (a former professor at Mar Athanasius College, a co-author, a colleague, or anyone
   in the field you can reach). They click the link, and you are endorsed. It takes them 30
   seconds and does not make them responsible for your paper.

Start the submission first; arXiv will tell you exactly whether you need endorsement and show
the request link if you do. Endorsement is per top-level category, so getting endorsed for
`cs.LG` covers future `cs.LG` papers too.

---

## 3. Step-by-step

1. **Create an account** at https://arxiv.org/user/register using your email. Add your ORCID
   if you have one (recommended; it links the paper to you permanently).
2. **Start a new submission**: https://arxiv.org/submit . Agree to the policies.
3. **License**: pick the default non-exclusive license (or CC BY 4.0).
4. **Upload** `misata_arxiv_submission.tar.gz`. Do not unzip it; upload the archive.
5. **Let arXiv process it.** It runs LaTeX on `main.tex` and produces a PDF. Click "View PDF"
   and check it looks exactly like your local `main.pdf` (title page, the P-star figure on
   the experiments page, the tables, the references). If processing errors appear, they will
   name a file and line; tell me and I will fix the source and rebuild the archive.
6. **Metadata**: paste the Title, Authors, Abstract, Comments from Section 1. Set the primary
   category `cs.LG` and cross-list `cs.DB` (and `stat.ML` if you like).
7. **Endorsement**: if prompted, follow Section 2.
8. **Submit.** The paper goes into a holding queue and is announced at the next mailing
   (arXiv announces roughly 20:00 US Eastern, Sunday through Thursday). You get a permanent
   identifier like `arXiv:26xx.xxxxx` and a public URL the moment it is announced.

---

## 4. Pre-flight checklist

- [ ] Author name is final and spelled the way you want it cited (no reordering after posting
      is awkward, though you can post a v2).
- [ ] The real GitHub URL is in the Comments line, and the repo is public (or will be by the
      time it is announced). Also set the real URL in `research/specbench/croissant.json`
      (now set to `github.com/rasinmuhammed/misata`).
- [ ] You are comfortable that the SDV baseline second-decimals are from your macOS run; the
      paper states this platform caveat honestly in Appendix A, so nothing is misrepresented.
      If you want them digit-exact first, run `verify_sdv.py` on your Mac and update the CSVs
      before posting (optional; the conclusion does not change).
- [ ] If you used AI assistance and want to disclose it, add a one-line acknowledgment in the
      paper or note it; arXiv does not require this, but some authors prefer it.
- [ ] You picked a license you are happy with.

---

## 5. After it is live

- You can post updated versions (v2, v3, ...) anytime; arXiv keeps the history. So posting now
  and fixing the SDV digits later in a v2 is completely normal.
- The arXiv link is citable immediately and never expires. That is the whole "published
  without presenting" outcome you wanted.
- If you later decide to submit to a journal that does not require presentation (for example
  TMLR or the Journal of Open Source Software for the library), having the arXiv preprint
  first does not block any of them.
