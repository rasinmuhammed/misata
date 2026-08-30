"""
Contact center interval data: queues and half-hour intervals, staffed and
scored the way a real workforce-management (WFM) system actually does it --
with Erlang C (A.K. Erlang, 1917), not independently randomized volume,
staffing, and service-level columns.

Every number below traces to a real, named formula:

  * Traffic intensity, in Erlangs (the actual unit named after the man):
    A = offered_calls x AHT / interval_length.

  * Probability a call has to wait at all is the Erlang C formula, computed
    via the numerically stable Erlang B recursion (Sundt-Jewell) rather
    than a raw factorial, which overflows past N ~ 170:
        B(0, A) = 1
        B(n, A) = A x B(n-1, A) / (n + A x B(n-1, A))
        C(N, A) = B(N, A) / (1 - (A/N) x (1 - B(N, A)))

  * Average speed of answer (ASA) and service level within a threshold T
    are the standard Erlang C results:
        ASA   = C(N, A) x AHT / (N - A)
        SL(T) = 1 - C(N, A) x exp(-(N - A) x T / AHT)

  * Staffing itself is reverse-solved, not assigned: given a queue's
    declared SLA target (e.g. "80% of calls answered within 20 seconds",
    the industry's most-cited baseline) and an interval's forecast volume,
    agents_staffed is the smallest N for which the Erlang C service-level
    formula actually clears that target -- the same search every commercial
    staffing calculator runs.

  * Abandonment is not bolted on as an unrelated random column. In an
    Erlang C / M/M/N queue, a call that has to wait experiences a wait time
    that is itself exponentially distributed with rate (N x mu - lambda),
    a standard queueing-theory result (Gross & Harris, "Fundamentals of
    Queueing Theory"). Modeling customer patience as a second, independent
    exponential clock turns "does this call abandon" into a race between
    two exponentials, which has a closed form: the abandonment probability
    for a queued call is patience_rate / (patience_rate + wait_rate). This
    is this example's own reasonable extension of the exact Erlang C
    result, not a claim that it reproduces the full Erlang A / Palm model
    -- see "What this is not" below.

What this earns, checked below: agents_staffed isn't a plausible-looking
number sitting next to a volume column. It's the actual output of running
Erlang C backwards, and the service level, wait time, and abandonment rate
that follow from it are recomputable from the raw columns, not asserted.
"""

import math

import numpy as np
import pandas as pd

import misata

RNG_SEED = 17
INTERVAL_SECONDS = 1800  # 30-minute intervals, the standard WFM reporting grain

# Four queues with realistically different traffic, handle times, SLA
# policies, and customer patience -- a sales queue's callers hang up sooner
# than a billing queue's, and its SLA is tighter because a missed sales
# call is a lost lead.
QUEUES = {
    "Billing Support":   {"sla_pct": 0.80, "sla_sec": 20, "patience_sec": 75, "peak_volume": 40, "aht_mean": 300},
    "Technical Support": {"sla_pct": 0.80, "sla_sec": 30, "patience_sec": 90, "peak_volume": 30, "aht_mean": 420},
    "Sales":             {"sla_pct": 0.90, "sla_sec": 15, "patience_sec": 45, "peak_volume": 25, "aht_mean": 240},
    "Retention":         {"sla_pct": 0.75, "sla_sec": 25, "patience_sec": 60, "peak_volume": 15, "aht_mean": 360},
}

OPEN_HOUR = 8
CLOSE_HOUR = 18  # 08:00-18:00, half-hour slots, the last one starting 17:30

# Shrinkage: the standard WFM concept that the Erlang-bare-minimum agent
# count is never who actually staffs a queue. Breaks, training, and
# absenteeism (ICMI's commonly cited planning range is roughly 25-35%)
# mean real schedules staff above the raw Erlang C requirement. Declared
# here as a flat, honest planning assumption -- not an independently cited
# figure the way the Erlang formulas themselves are.
SHRINKAGE = 0.20


def _erlang_b(n: int, a: float) -> float:
    """Erlang B blocking probability via the Sundt-Jewell recursion --
    numerically stable for any N, unlike the raw A^N / N! formula it's
    algebraically equivalent to."""
    b = 1.0
    for i in range(1, n + 1):
        b = (a * b) / (i + a * b)
    return b


def _erlang_c(n: int, a: float) -> float:
    """Erlang C: probability an arriving call must wait, derived from
    Erlang B. Undefined (queue explodes) once N <= A; callers must keep N > A."""
    b = _erlang_b(n, a)
    rho = a / n
    return b / (1 - rho * (1 - b))


def _required_agents(a: float, aht_sec: float, sla_pct: float, sla_sec: int, cap: int = 300) -> int:
    """The reverse-Erlang staffing search: the smallest N for which this
    interval's own service-level formula clears the queue's declared SLA."""
    n = max(1, math.ceil(a) + 1)
    while n < cap:
        c = _erlang_c(n, a)
        sl = 1 - c * math.exp(-(n - a) * sla_sec / aht_sec)
        if sl >= sla_pct:
            return n
        n += 1
    return cap


def _intraday_multiplier(hour_frac: np.ndarray) -> np.ndarray:
    """A realistic intraday call-volume curve: low at open/close, peaking
    mid-shift, rather than a flat or independently random volume per slot."""
    return 0.35 + 0.65 * np.sin(np.pi * hour_frac)


def build(n_business_days: int = 30, seed: int = RNG_SEED):
    schema = {
        "queues": {
            "__rows__": len(QUEUES),
            "queue_id": {"type": "integer", "primary_key": True},
        },
        "intervals": {
            "__rows__": n_business_days * len(QUEUES) * ((CLOSE_HOUR - OPEN_HOUR) * 2),
            "interval_id": {"type": "integer", "primary_key": True},
            "queue_id": {"type": "integer", "foreign_key": {"table": "queues", "column": "queue_id"}},
        },
    }
    tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=seed))
    return _reconcile(tables, n_business_days, seed)


def _reconcile(tables: dict, n_business_days: int, seed: int) -> dict:
    rng = np.random.default_rng(seed + 1)

    queues = tables["queues"].copy()
    queue_ids = queues["queue_id"].sort_values().to_numpy()
    names = list(QUEUES.keys())
    queues = queues.set_index("queue_id").loc[queue_ids].reset_index()
    queues["queue_name"] = names
    for field in ("sla_pct", "sla_sec", "patience_sec"):
        queues[field] = [QUEUES[n][field] for n in names]
    tables["queues"] = queues[["queue_id", "queue_name", "sla_pct", "sla_sec", "patience_sec"]]

    # Business days only -- a B2B support line doesn't staff for a Saturday
    # that doesn't exist in its call pattern.
    business_days = pd.bdate_range(start="2026-05-04", periods=n_business_days)
    slots_per_day = (CLOSE_HOUR - OPEN_HOUR) * 2
    slot_offsets = np.arange(slots_per_day) * 30  # minutes past OPEN_HOUR:00

    rows = []
    for day in business_days:
        for slot in range(slots_per_day):
            ts = day + pd.Timedelta(hours=OPEN_HOUR, minutes=int(slot_offsets[slot]))
            hour_frac = slot / (slots_per_day - 1)
            for _, q in queues.iterrows():
                rows.append((q["queue_id"], ts, hour_frac))

    intervals = pd.DataFrame(rows, columns=["queue_id", "interval_start", "hour_frac"])
    intervals.insert(0, "interval_id", np.arange(1, len(intervals) + 1))

    q_by_id = queues.set_index("queue_id")
    peak_volume = intervals["queue_id"].map(q_by_id["queue_name"].map(lambda n: QUEUES[n]["peak_volume"]))
    aht_mean = intervals["queue_id"].map(q_by_id["queue_name"].map(lambda n: QUEUES[n]["aht_mean"]))
    sla_pct = intervals["queue_id"].map(q_by_id["sla_pct"])
    sla_sec = intervals["queue_id"].map(q_by_id["sla_sec"])
    patience_sec = intervals["queue_id"].map(q_by_id["patience_sec"])

    multiplier = _intraday_multiplier(intervals["hour_frac"].to_numpy())
    lam = peak_volume.to_numpy() * multiplier
    offered_calls = rng.poisson(lam)
    offered_calls = np.maximum(offered_calls, 1)  # a queue with zero calls in a business-hours slot isn't modeled here

    # Interval-level AHT itself varies call to call -- modeled as a mild
    # normal spread around the queue's declared mean, not a fixed constant.
    aht_sec = np.clip(rng.normal(aht_mean.to_numpy(), aht_mean.to_numpy() * 0.08), 60, None).round().astype(int)

    n = len(intervals)
    intensity = offered_calls * aht_sec / INTERVAL_SECONDS
    agents = np.zeros(n, dtype=np.int64)
    wait_prob = np.zeros(n)
    asa = np.zeros(n)
    service_level = np.zeros(n)

    sla_pct_arr = sla_pct.to_numpy()
    sla_sec_arr = sla_sec.to_numpy()
    for i in range(n):
        a = intensity[i]
        base_n = _required_agents(a, aht_sec[i], sla_pct_arr[i], sla_sec_arr[i])
        nn = math.ceil(base_n * (1 + SHRINKAGE))
        agents[i] = nn
        c = _erlang_c(nn, a)
        wait_prob[i] = c
        asa[i] = c * aht_sec[i] / (nn - a)
        service_level[i] = 1 - c * math.exp(-(nn - a) * sla_sec_arr[i] / aht_sec[i])

    occupancy = intensity / agents

    # Abandonment: a race between the Erlang-C-implied wait-clearing rate
    # and an exponential patience clock -- see the module docstring.
    wait_rate = (agents - intensity) / aht_sec
    patience_rate = 1.0 / patience_sec.to_numpy()
    p_abandon_if_queued = patience_rate / (patience_rate + wait_rate)
    expected_abandon_rate = wait_prob * p_abandon_if_queued

    # The realized outcome is a real stochastic draw at that implied rate,
    # not the expected rate copy-pasted into every row -- the same
    # expected-vs-realized split the credit-risk-portfolio example uses
    # for expected_loss vs realized_loss.
    calls_abandoned = rng.binomial(offered_calls, np.clip(expected_abandon_rate, 0, 1))
    calls_answered = offered_calls - calls_abandoned

    intervals["offered_calls"] = offered_calls
    intervals["aht_sec"] = aht_sec
    intervals["agents_staffed"] = agents
    intervals["traffic_intensity_erlangs"] = intensity.round(2)
    intervals["occupancy_pct"] = (occupancy * 100).round(1)
    intervals["wait_probability_pct"] = (wait_prob * 100).round(1)
    intervals["asa_sec"] = asa.round(1)
    intervals["service_level_pct"] = (service_level * 100).round(1)
    intervals["expected_abandon_rate_pct"] = (expected_abandon_rate * 100).round(1)
    intervals["calls_answered"] = calls_answered
    intervals["calls_abandoned"] = calls_abandoned
    intervals["realized_abandon_rate_pct"] = (calls_abandoned / offered_calls * 100).round(1)
    intervals = intervals.drop(columns=["hour_frac"])

    tables["intervals"] = intervals
    return tables


def verify(tables: dict) -> bool:
    queues = tables["queues"]
    intervals = tables["intervals"].merge(
        queues[["queue_id", "queue_name", "sla_pct", "sla_sec", "patience_sec"]], on="queue_id")

    checks = []

    # 1. Queue stability: staffing always exceeds offered traffic (Erlang C
    # is undefined, and a real queue would collapse, otherwise).
    checks.append(("agents_staffed exceeds traffic_intensity_erlangs on every interval (queue stability)",
                    (intervals["agents_staffed"] > intervals["traffic_intensity_erlangs"]).all()))

    # 2. The staffing search actually clears the queue's own declared SLA
    # target -- the core claim: agents_staffed isn't just a plausible
    # number, it's what Erlang C says is required.
    for name, g in intervals.groupby("queue_name"):
        target = g["sla_pct"].iloc[0] * 100
        met = (g["service_level_pct"] >= target - 0.05).mean()
        checks.append((f"'{name}' clears its {target:.0f}% SLA target on {met:.1%} of intervals",
                        met > 0.98))

    # 3. Recompute service_level_pct independently from the raw columns via
    # the exact Erlang C formula, and check it matches the stored value.
    recomputed_sl = []
    for _, row in intervals.iterrows():
        a = row["traffic_intensity_erlangs"]
        c = _erlang_c(int(row["agents_staffed"]), a)
        sl = 1 - c * math.exp(-(row["agents_staffed"] - a) * row["sla_sec"] / row["aht_sec"])
        recomputed_sl.append(round(sl * 100, 1))
    checks.append(("service_level_pct matches an independent Erlang C recomputation on every interval",
                    np.allclose(intervals["service_level_pct"].to_numpy(), recomputed_sl, atol=0.2)))

    # 4. calls_answered + calls_abandoned reconciles to offered_calls exactly.
    checks.append(("calls_answered + calls_abandoned equals offered_calls on every interval",
                    (intervals["calls_answered"] + intervals["calls_abandoned"] == intervals["offered_calls"]).all()))

    # 5. Higher occupancy really does mean worse service -- the actual
    # Erlang relationship, not two independently random columns.
    corr = intervals["occupancy_pct"].corr(intervals["service_level_pct"])
    checks.append((f"occupancy_pct and service_level_pct correlate at {corr:.2f} (higher load, worse service)",
                    corr < -0.3))

    # 6. The intraday volume curve is real: midday intervals see measurably
    # more calls than the queue's opening slot, not a flat/random spread.
    for name, g in intervals.groupby("queue_name"):
        by_time = g.groupby(g["interval_start"].dt.time)["offered_calls"].mean()
        opening = by_time.iloc[0]
        midday = by_time.iloc[len(by_time) // 2]
        checks.append((f"'{name}' midday volume ({midday:.1f}) exceeds opening volume ({opening:.1f})",
                        midday > opening))

    # 7. Realized abandonment, aggregated per queue over the full month,
    # stays in a believable industry range (most contact centers run
    # 2-8% overall). A single sparse off-peak interval with only 2-3 calls
    # can legitimately show a much noisier rate by chance -- exactly why
    # real WFM tools report abandonment aggregated over a period, not
    # trusted at the single-interval grain, so the check does the same.
    agg_abandon = intervals.groupby("queue_name").apply(
        lambda g: g["calls_abandoned"].sum() / g["offered_calls"].sum(), include_groups=False)
    for name, rate in agg_abandon.items():
        checks.append((f"'{name}' abandons {rate:.1%} of calls over the full month (industry-plausible range)",
                        rate < 0.10))

    # 8. Structural guarantees.
    checks.append(("intervals.queue_id has zero orphans against queues.queue_id",
                    intervals["queue_id"].isin(queues["queue_id"]).all()))
    checks.append(("every interval_start falls exactly on a half-hour mark",
                    (intervals["interval_start"].dt.minute.isin([0, 30])).all()
                    and (intervals["interval_start"].dt.second == 0).all()))
    checks.append(("agents_staffed is a positive integer on every interval",
                    (intervals["agents_staffed"] >= 1).all()))

    all_ok = True
    for label, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {label}")
        all_ok &= bool(ok)
    return all_ok


if __name__ == "__main__":
    tables = build(n_business_days=30, seed=RNG_SEED)
    print(f"queues: {len(tables['queues'])}  intervals: {len(tables['intervals'])}")
    print()
    ok = verify(tables)
    print()
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    raise SystemExit(0 if ok else 1)
