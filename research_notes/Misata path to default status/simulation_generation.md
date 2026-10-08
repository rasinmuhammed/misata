# Simulation-based synthetic data generation: does Misata need it, and in what form?

Scope note: research done 2026-10-03. arxiv.org, pepy.tech and pypistats.org were blocked by the egress proxy, so arXiv claims below come from search-result abstracts/snippets (not full-text reads), and **no PyPI download counts could be retrieved**. GitHub star counts come from the GitHub search API on 2026-10-03.

Local code baseline (read directly from /home/user/misata):
- `misata/lifecycle.py`: state assigned per row by largest-remainder allocation of declared `weights`; timestamps along the path are `rng.integers(1, max_days_per_step*day)` gaps, cumsum'd (lines ~171-185). So dwell time per transition is **uniform on (0, max_days_per_step]**, one global bound (default 30 days, `schema.py` line ~683); there is no per-transition dwell distribution, no branching probability conditioned on history, no arrival process, no resources/capacity.
- `misata/eventlog.py` / `schema.EventLog`: rewrites an event child table so it agrees with the lifecycle path (exactly one event per reached state, ordered, plus legal filler events). This is a *projection* of the lifecycle onto a log, not a generator of cases with timing semantics.
- `misata/stockflow.py`: chains opening + received - shipped = closing per SKU/period, no negative stock, by construction.
- `misata/dynamics.py`: CohortRetention, Missingness (MNAR), LateArrival, TimeGrid, Duplicates, all via largest-remainder allocation ("40% of rows rather than 40% in expectation").
- `LIMITATIONS.md`: "SCD2 and stock-flow trajectories are generated, not declared"; "No learned correlation structure"; "A declared aggregate beats causality on the same row."
- `grep -w xes|ocel` over `misata/*.py` finds no XES or OCEL exporter (only pluralisation helpers matching "xes").
- `misata/simulator.py` is named "DataSimulator" but is a vectorized table generator (topological sort + column generation), not a discrete-event engine.

## Q1. Which synthetic-data use cases genuinely require simulation, and how popular are the tools?

### Takeaway
Simulation is genuinely required only where the *output metric is a consequence of interaction*: queue waits/utilisation under finite resources (call centres, hospitals, BPS/process mining), contagion/network effects (AML rings, epidemics), and multi-step agent behaviour whose plausibility is the point (patient trajectories, fraud typologies). The tools serving these are niche-to-mid popularity (hundreds to ~3.9k GitHub stars), and the most-used outputs are *pre-generated datasets* (PaySim on Kaggle, Synthea exports, AMLworld), not the simulators themselves.

### Cited Findings
- GitHub stars as of 2026-10-03: Mesa (ABM, Python) 3,871 stars / 1,321 forks — [mesa/mesa](https://github.com/mesa/mesa); Synthea (Java patient simulator) 3,372 stars / 947 forks, 259 open issues — [synthetichealth/synthea](https://github.com/synthetichealth/synthea); NetLogo 1,187 — [NetLogo/NetLogo](https://github.com/NetLogo/NetLogo); PM4Py 1,045 — [process-intelligence-solutions/pm4py](https://github.com/process-intelligence-solutions/pm4py); salabim 406 — [salabim/salabim](https://github.com/salabim/salabim); IBM AMLSim 399 stars, 52 open issues — [IBM/AMLSim](https://github.com/IBM/AMLSim); AgentPy 387 — [jofmi/agentpy](https://github.com/jofmi/agentpy); Ciw (queueing networks) 175 — [CiwPython/Ciw](https://github.com/CiwPython/Ciw); PaySim 134 — [EdgarLopezPhD/PaySim](https://github.com/EdgarLopezPhD/PaySim); Simod 55 — [AutomatedProcessImprovement/Simod](https://github.com/AutomatedProcessImprovement/Simod); Prosimos 14 — [AutomatedProcessImprovement/Prosimos](https://github.com/AutomatedProcessImprovement/Prosimos); ShadowTraffic examples 52 — [ShadowTraffic/shadowtraffic-examples](https://github.com/ShadowTraffic/shadowtraffic-examples). For comparison, SDV (declarative/learned tabular synth) has 3,568 — [sdv-dev/SDV](https://github.com/sdv-dev/SDV).
- SimPy's canonical home is GitLab (team-simpy), so GitHub stars are not comparable; PyPI shows SimPy 4.1.2 released 2026-05-24, MIT, requires Python >= 3.8 — [PyPI simpy](https://pypi.org/project/simpy/).
- PaySim: Multi-Agent Based Simulation calibrated on a sample of real mobile-money logs from an African country; Kaggle dataset ~6.3M transactions over 744 hourly steps (30 days), 0.13% fraud (8,213 cases); Kaggle "dataset of the week" April 2018 — [Kaggle paysim1](https://www.kaggle.com/datasets/ealaxi/paysim1); [PaySim EMSS 2016 paper](https://www.msc-les.org/proceedings/emss/2016/EMSS2016_249.pdf).
- AMLworld (IBM Research + ETH Zurich, NeurIPS 2023 Datasets & Benchmarks): agent-based generator modelling placement/layering/integration and eight laundering patterns, propagating a "laundering" tag for perfect ground truth, which real data cannot provide — [NeurIPS 2023 paper](https://proceedings.neurips.cc/paper_files/paper/2023/file/5f38404edff6f3f642d6fa5892479c42-Paper-Datasets_and_Benchmarks.pdf); follow-up on hybrid real+synthetic AML training data — [arXiv 2509.18499](https://arxiv.org/pdf/2509.18499).
- Prosimos: open-source BPS engine that discovers simulation models from event logs and supports what-if analysis; distinguishing feature is *differentiated resources* (individual performance/availability calendars rather than homogeneous pools) — [Prosimos, Springer BPM](https://link.springer.com/chapter/10.1007/978-3-031-26886-1_23); [Does differentiated resources make a difference?](https://arxiv.org/pdf/2208.07928). Later work adds probabilistic availability calendars and multitasking — [arXiv 2410.16941](https://arxiv.org/html/2410.16941v1); data-aware BPS — [arXiv 2408.13666](https://arxiv.org/pdf/2408.13666).
- OCEL 2.0 is the object-centric event log standard (events linked to multiple typed objects) — [OCEL 2.0 spec](https://arxiv.org/pdf/2403.01975). New synthetic OCEL 2.0 logs are still being hand-built for tool evaluation (inventory management; manufacturing with predictive maintenance) — [Zenodo: two synthetic OCEL 2.0 evaluation logs](https://zenodo.org/records/22140119).
- ShadowTraffic ships a `stateMachine` function: tracks current state per generator and advances over time; "nearly all real-world data streams are defined not just by a single kind of event, but by sequences of things that happen over time" — [ShadowTraffic stateMachine docs](https://docs.shadowtraffic.io/functions/stateMachine/).
- Clickstream generation is mostly ad-hoc scripts: Tasman Analytics built a Faker-based generator for "realistic, non-linear user journeys" — [Tasman](https://www.tasman.ai/news/how-to-generate-fake-user-data-for-testing); clksim clickstream simulator — [ceteri/clksim](https://github.com/ceteri/clksim); Retentioneering advertises "Markov chain simulation" for clickstream/event-log analytics — [retentioneering-tools](https://github.com/retentioneering/retentioneering-tools).

### Inferences
- Use cases split into two tiers. **Tier A (needs real simulation):** wait-time / SLA / utilisation analytics (call centres, ED triage, warehouse picking), BPS what-if, AML/fraud network typologies, epidemic/patient trajectories. **Tier B (needs only plausible sequences + timing):** ecommerce sessions/clickstreams, customer journeys, order/ticket lifecycles, IoT state changes, process-mining *tool testing* logs. Tier B is far larger for Misata's audience (analytics engineers, dbt/test-data users) and is reachable with Markov/semi-Markov allocation, no event engine.
- The popular artefacts are datasets, and their users rarely re-run the simulator; that suggests demand is for *data with simulation-like properties*, not for a simulator API.
- Misata's star-scale peers are SDV/Synthea (~3.4-3.6k); dedicated BPS engines (Prosimos 14, Simod 55) are research tools with tiny direct user bases, so "process simulation" demand is academic-heavy.

### Gaps
- No PyPI download counts (pepy/pypistats blocked). SimPy, Mesa, PM4Py monthly downloads unknown here.
- PLG2, BIMP and PM4Py's own simulation module were not investigated in depth (PM4Py offers playout/simulation of Petri nets per general knowledge, but not verified in this session).
- IBM/AMLworld and SynthAML repo stats not retrieved (repo search returned nothing for those names).

## Q2. How do existing simulation-based generators work, and what do users complain about?

### Takeaway
They are hand-built agent/state-machine models with parameters calibrated (loosely) to real samples. The recurring complaint is the same in every domain: the simulator encodes the author's simplifications so crisply that the data contains **artefacts a model can trivially learn** (PaySim leakage, Synthea's 100% amputation rate), plus slow performance and difficulty hitting specific aggregate targets.

### Cited Findings
- Synthea validation (clinical quality measures): reliable for demographics and probability of services, but limited at modelling heterogeneous outcomes after care; does not model deviations in care — [BMC Med Inform Decis Mak 2019](https://link.springer.com/article/10.1186/s12911-019-0793-0); original method paper — [JAMIA 2018](https://academic.oup.com/jamia/article/25/3/230/4098271).
- Reported Synthea artefacts (attribution among these sources is from a merged search summary; treat as "reported in" the set): ~20% of 2-5-year-olds generated with Type 2 diabetes; 100% of Synthea T2D patients with at least one amputation; 100% of asthma patients on the same inhaler; disease modules treated in isolation without comorbidity interaction; no transcription errors / messiness of real EHRs — [OHDSI 2024 "Evaluating Synthea" poster](https://www.ohdsi.org/wp-content/uploads/2024/10/41-Wagner-Evaluating_Synthea-Clair-Blacketer.pdf); [JAMIA Open 2023 synthetic medication data](https://academic.oup.com/jamiaopen/article/6/3/ooad052/7223896); [arXiv 2507.21123 GenAI for Synthea modules](https://arxiv.org/pdf/2507.21123).
- PaySim complaints: many transactions with nonzero amounts but zero before/after balances (counterparty-bank accounts imputed as 0) — [arXiv 2312.00586](https://arxiv.org/html/2312.00586v1); `amount == oldbalanceOrg` identifies 8,034 of 8,213 frauds (97.8%) with zero false positives because the simulated fraudster empties the account; for TRANSFER fraud 99.29% have `newbalanceDest == 0` vs 0.21% of legit — [label-leakage audit repo](https://github.com/namanphogat0003-commits/fraud-detection-pipeline); see also [diogo-moitinho/fraud-detection-project](https://github.com/diogo-moitinho/fraud-detection-project).
- SimPy performance complaint: a 60-million-event cache simulation "took couple of hours" — [team-simpy GitLab issue #112](https://gitlab.com/team-simpy/simpy/-/work_items/112). SimPy processes run in a single thread; performance scales with number of components and tick granularity — [EuroPython 2020 "Boosting simulation performance with Python"](https://ep2020.europython.eu/media/conference/slides/9k2qHA7-boosting-simulation-performance-with-python.pdf).
- BPS evaluation itself is contested: recent work argues for utility-based evaluation of simulated logs rather than distance-to-real-log metrics — [arXiv 2505.22316 "Rethinking BPS"](https://arxiv.org/pdf/2505.22316); event-log augmentation techniques compared experimentally — [arXiv 2511.01896](https://arxiv.org/pdf/2511.01896); ground-truth approach for assessing process mining techniques using generated data — [arXiv 2501.14345](https://arxiv.org/pdf/2501.14345).
- AMLSim has 52 open issues and PaySim is Java with 3 open issues and low activity — [IBM/AMLSim](https://github.com/IBM/AMLSim); [PaySim](https://github.com/EdgarLopezPhD/PaySim).

### Inferences
- The PaySim and Synthea failure modes are exactly the class Misata's audit/coherence layer targets (impossible or trivially-separable histories). A simulation engine does not prevent them; a *coherence audit over simulated output* would have flagged "100% of X have Y" and "label determined by one equality". Misata's competitive angle is "simulation-like data, audited", not "another simulator".
- Simulators are slow and opaque to tune toward a target ("I need 2% fraud and this monthly curve"); users iterate parameters by trial and error. Misata already solves that half.

### Gaps
- No direct user-forum threads (Reddit/StackOverflow) complaining about SimPy/Mesa for data generation were retrieved within the tool budget.
- AMLworld-specific critiques not found.

## Q3. What does simulation give that declarative allocation cannot, and vice versa? Can they be combined?

### Takeaway
Simulation's unique value is **emergent, coupled quantities**: waits that rise non-linearly with load, utilisation, abandonment, contagion, and sequence plausibility conditioned on history. Allocation's unique value is **exact targets, determinism, speed and editability**. They combine cleanly if Misata draws a line: *counts and marginals are allocated exactly; within-case timing and resource-coupled waits are simulated; then a calibration/raking step reconciles*. Synthetic-population practice (IPF then ABM) is the established precedent.

### Cited Findings
- Synthetic population practice: IPF reweights seed microdata so marginals match aggregate constraints while preserving dependence structure; two-step "fitting and allocation" with IPU, HIPF, entropy minimisation, generalised raking — [IPF review](https://www.researchgate.net/publication/311731203_Population_Synthesis_Using_Iterative_Proportional_Fitting_IPF_A_Review_and_Future_Research); [JASSS 2021 French municipalities comparison](https://www.jasss.org/24/2/5.html); [ETH IVT report on IPF populations](https://ethz.ch/content/dam/ethz/special-interest/baug/ivt/ivt-dam/vpl/reports/101-200/ab150.pdf); hybrid agent modelling in population simulation — [JASSS 19/1/12](https://www.jasss.org/19/1/12.html).
- Prosimos shows the specific thing allocation cannot produce: resource heterogeneity and availability calendars change cycle times and waits — [arXiv 2208.07928](https://arxiv.org/pdf/2208.07928).
- AMLworld's value proposition is perfect ground truth of *patterns* (cycles, fan-in/out) that propagate through a network — [NeurIPS 2023](https://proceedings.neurips.cc/paper_files/paper/2023/file/5f38404edff6f3f642d6fa5892479c42-Paper-Datasets_and_Benchmarks.pdf).
- Misata's own stance: "the difference between a distribution and a guarantee, and the guarantee is the product" (`misata/dynamics.py` docstring, local) and "A declared aggregate beats causality on the same row" (`LIMITATIONS.md`, local).

### Inferences
- Concretely what Misata lacks today (from local code): (1) per-transition dwell-time distributions (currently uniform up to one global `max_days_per_step`), (2) history-dependent branching (rework loops, retries, k-th attempt), (3) an arrival process tied to a declared curve, (4) capacity-constrained resources producing waits/queues, (5) multi-object (OCEL) events, (6) XES/OCEL export. Items 1-3, 5, 6 need **no event engine**: they are semi-Markov sampling, vectorizable per state group like `lifecycle.py` already is. Only item 4 needs simulation semantics.
- Single-server FIFO waits are a closed-form recursion (Lindley: W_{n+1} = max(0, W_n + S_n - A_{n+1})), cheap in numpy/numba over sorted arrivals; multi-server FIFO (G/G/c) is an O(n log c) heap pass. This is standard queueing theory, not sourced in this session. A full general-purpose DES is only needed for networks with priorities, preemption, shared resources across activities, and calendars, i.e. Prosimos territory.
- Combination patterns, ranked by fit with Misata's guarantee:
  1. **Allocate-then-simulate (recommended):** exact case counts per period (existing curve allocation), exact terminal-state mix (existing largest-remainder), exact event counts per type; simulate only timestamps and resource waits inside those fixed counts. Exactness is preserved for every declared aggregate; waits are declared as *emergent* and reported, not guaranteed.
  2. **Simulate-then-rake:** run a stochastic model, then reweight/subsample/allocate to hit marginals (IPF style). Exact on marginals, but distorts the emergent quantities the simulation was for (dropping cases changes queue load). Use only for non-coupled models.
  3. **Targets as constraints on simulation:** declare "mean wait 4 min, p90 12 min" and solve for service rate/capacity (inverse queueing, e.g. Erlang-C for M/M/c). Feasible for simple queues; makes waits approximately (not exactly) hit in expectation. Should be labelled "calibrated, not exact".
- Misata must tag every output property as `exact` / `calibrated` / `emergent` in its audit report, or the simulation feature will silently undermine the core brand.

### Gaps
- No published evaluation found that compares allocation-based vs simulation-based synthetic event logs on downstream utility; the BPS utility-evaluation paper (2505.22316) could not be read in full.

## Q4. Demand signals (forums, process-mining community, papers 2023-2026)

### Takeaway
Demand is real but concentrated: (a) process mining research continuously needs synthetic logs (XES/OCEL 2.0) with ground truth, (b) fraud/AML ML needs labelled transaction networks, (c) data/analytics engineers want event streams and journeys with sequence semantics (ShadowTraffic's `stateMachine`, ad-hoc clickstream scripts). Very little evidence of analytics engineers asking for SimPy/ABM per se; they ask for *realistic sequences and timing*.

### Cited Findings
- Active 2024-2026 process-mining work on synthetic data: OCEL 2.0 spec (2024) — [arXiv 2403.01975](https://arxiv.org/pdf/2403.01975); scalable data preparation for object-centric PM — [arXiv 2410.00596](https://arxiv.org/html/2410.00596v1); ground-truth assessment approach — [arXiv 2501.14345](https://arxiv.org/pdf/2501.14345); BPS utility evaluation — [arXiv 2505.22316](https://arxiv.org/pdf/2505.22316); event-log augmentation comparison — [arXiv 2511.01896](https://arxiv.org/pdf/2511.01896); SHAP explanations of event logs — [arXiv 2509.08482](https://arxiv.org/pdf/2509.08482); hand-built synthetic OCEL 2.0 logs for a tool evaluation — [Zenodo 22140119](https://zenodo.org/records/22140119). A search summary also noted a study analysing 22,000+ synthetic event logs for discovery-algorithm benchmarking (source not individually identified, treat cautiously).
- Healthcare: LLM-assisted Synthea module development (2025) and LLM multi-agent patient simulation (2026) indicate continued investment in simulation-style synthetic patients — [arXiv 2507.21123](https://arxiv.org/pdf/2507.21123); [SynthAgent arXiv 2602.08254](https://arxiv.org/pdf/2602.08254).
- AML: hybrid real+synthetic training (2025) builds on AMLworld — [arXiv 2509.18499](https://arxiv.org/pdf/2509.18499).
- Commercial: ShadowTraffic markets "simulate production traffic" with stateful generators and state machines — [shadowtraffic.io](https://shadowtraffic.io/); [stateMachine](https://docs.shadowtraffic.io/functions/stateMachine/).
- PaySim remains a heavily used Kaggle benchmark (many 2024-2026 repos/papers still use it, e.g. [arXiv 2604.07952](https://arxiv.org/pdf/2604.07952), [arXiv 2601.21789](https://arxiv.org/pdf/2601.21789)), despite known leakage.
- Practitioner tutorial on DES with SimPy (2024) — [arXiv 2405.01562 "Discrete Event Simulation: It's Easy with SimPy!"](https://arxiv.org/pdf/2405.01562).

### Inferences
- The strongest under-served niche Misata could own: **"OCEL 2.0 / XES logs with declared ground truth"** (declare the process, variant frequencies, rework rate, conformance-violation rate, bottleneck activity; get logs whose ground truth is exact). Process-mining researchers currently hand-build these (Zenodo example) or simulate with tools that cannot guarantee variant counts.
- Second niche: **fraud/AML typologies over time with exact prevalence and no trivial leakage**: a direct answer to the documented PaySim complaints.
- Clickstream/session demand is broad but shallow; semi-Markov journeys with declared funnel conversion (exact) and dwell distributions cover it.

### Gaps
- Could not quantify forum demand (no StackOverflow/Reddit thread counts retrieved). No download data. No survey data on what fraction of synthetic-data users need temporal/sequence behaviour.

## Q5. Is SimPy a good dependency, vs a vectorized custom engine?

### Takeaway
SimPy is MIT, pure-Python, small and stable but thinly maintained (a 2.5-year release gap 2023-11 to 2026-05) and slow at tens of millions of events because it is one Python generator per process, single-threaded. Misata should **not** make SimPy a core dependency; build a small vectorized semi-Markov + queue kernel in numpy, and at most offer SimPy/Ciw/Prosimos as optional adapters.

### Cited Findings
- SimPy release history: 4.0.1 (2020-04), 4.0.2 (2023-07), 4.1.0 (2023-11-06), 4.1.1 (2023-11-13), 4.1.2 (2026-05-24); MIT; Python >= 3.8 — [PyPI simpy](https://pypi.org/project/simpy/) (release dates from PyPI JSON API).
- SimPy 60M-event simulation took hours — [GitLab issue #112](https://gitlab.com/team-simpy/simpy/-/work_items/112); single-threaded process model — [EuroPython 2020 slides](https://ep2020.europython.eu/media/conference/slides/9k2qHA7-boosting-simulation-performance-with-python.pdf).
- salabim is actively released (26.0.6 on 2026-05-29, 26.0.8 on 2026-06-24); PyPI license field empty in the JSON metadata — [PyPI salabim](https://pypi.org/project/salabim/); 406 stars, 0 open issues — [salabim/salabim](https://github.com/salabim/salabim).
- Mesa: 3.5.1 (2026-03-15) and 4.0.0a0 pre-release (2026-03-14), Apache-2.0 — [PyPI mesa](https://pypi.org/project/mesa/); 3,871 stars — [mesa/mesa](https://github.com/mesa/mesa). The 4.0 alpha implies API churn for anyone depending on it.
- Ciw: open queueing network simulation library, 175 stars, 30 open issues — [CiwPython/Ciw](https://github.com/CiwPython/Ciw).
- Vectorized numpy alternatives (cumsum, add.at) avoid Python-loop costs in statistical simulation — [Statology vectorization](https://www.statology.org/3-ways-to-vectorize-your-statistical-simulations-for-100x-speed/).

### Inferences
- Misata's measured envelope (LIMITATIONS.md: 10M-row fact table in ~41 s) is incompatible with a per-entity Python-process engine; a SimPy-backed path would be 1-2 orders of magnitude slower at that scale (inference from the 60M-events-in-hours report, not benchmarked here).
- Determinism: SimPy itself is deterministic given a seeded RNG, but Misata's anchored per-column streams and "edit stability" guarantees would be hard to preserve inside an imperative process loop; a vectorized kernel keyed by Misata's existing stream anchoring keeps those guarantees.
- License-wise all candidates are permissive (SimPy MIT, Mesa Apache-2.0); licensing is not the blocker, performance and determinism are.

### Gaps
- No head-to-head benchmark of SimPy vs salabim vs a numpy Lindley/heap kernel was run in this session.

---

## Recommendation (opinionated)

1. **Do not add a general DES/ABM engine (no SimPy, Mesa or NetLogo backend in core).** Demand for Misata's audience is for sequence and timing *realism*, not for simulation as an API; the simulators' documented failure modes (PaySim leakage, Synthea artefacts) are the problem Misata's audit already solves; and SimPy-style engines break Misata's speed, determinism and edit-stability guarantees.
2. **Add a declarative `Process` (semi-Markov) spec that extends `Lifecycle`** (call it `process:` or `lifecycle.transitions:`):
   - per-transition probabilities, allowing loops/rework with a max-visits bound (history-dependent branching);
   - per-transition dwell-time distributions (lognormal/gamma/empirical, optionally on business-hours calendars via existing `TimeGrid`), replacing the uniform `max_days_per_step`;
   - arrivals driven by an existing declared curve (cases per period exact by largest remainder; intra-period times from a non-homogeneous Poisson draw);
   - **exact** guarantees on case counts, terminal-state mix, variant frequencies, event counts per type, rework rate; dwell distributions labelled **calibrated** (sample moments within tolerance, reported by the audit).
3. **Add an optional, bounded `resources:` block** (capacity c per activity, FIFO, optional abandonment/patience) implemented as a vectorized Lindley recursion (c = 1) or heap pass (c > 1) in numpy/numba. Waits, utilisation and abandonment are **emergent** and reported, never claimed exact; optionally solve capacity from a declared target mean wait (Erlang-C style inverse) and label it calibrated. This covers call centre/hospital/fulfilment demos without a DES dependency.
4. **Exporters: XES and OCEL 2.0** from `EventLog` + process spec, with a ground-truth sidecar (true model, injected deviations, true bottleneck). This targets the clearest underserved research demand.
5. **Fraud/AML typologies as process templates** (fan-out, cycles, mule chains) with exact prevalence and an audit check for single-feature label leakage (the PaySim `amount == oldbalanceOrg` class).
6. **Optional adapters, not dependencies:** `misata[sim]` that can ingest a Prosimos/Simod-discovered BPS model or a SimPy run's event log and then *rake/allocate it to declared targets*, flagging which properties the raking distorted. Build only if users ask.
7. **Audit vocabulary:** every reported property tagged `exact` / `calibrated` / `emergent`, so simulation-flavoured features never dilute the "guarantee is the product" claim.

Priority order by evidence of demand vs effort: (2) semi-Markov process + dwell distributions > (4) XES/OCEL export > (5) fraud typologies + leakage audit > (3) resource queues > (6) adapters.
