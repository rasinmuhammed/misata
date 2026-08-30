---
title: "Generate Synthetic Contact Center / Erlang C Data in Python | Misata"
description: "Generate call center interval data where staffing, wait time, and service level all come from Erlang C (A.K. Erlang, 1917), the same queueing-theory formula every commercial workforce-management calculator runs. Agent counts are reverse-solved from a declared SLA target, not assigned."
---

# Generate Synthetic Contact Center / Erlang C Data in Python

Every commercial staffing calculator (Assembled, NICE, Genesys, and dozens of standalone Erlang calculators) runs the same 1917 formula to answer one question: given how many calls are coming in and how long each one takes, how many agents does it take to hit a service level target? A `call_volume` column and an `agents_staffed` column with no relationship between them can't test a WFM pipeline — the whole point of workforce management is that staffing is *derived* from volume and a target, not chosen independently.

```python
import misata

schema = {
    "queues": {
        "__rows__": 4,
        "queue_id": {"type": "integer", "primary_key": True},
    },
    "intervals": {
        "__rows__": 2400,
        "interval_id": {"type": "integer", "primary_key": True},
        "queue_id": {"type": "integer", "foreign_key": {"table": "queues", "column": "queue_id"}},
    },
}
tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=17))
print(list(tables.keys()))   # ['queues', 'intervals']
```

That's the structural shape. The full example — four queues with real SLA policies, a realistic intraday call-volume curve, and agents_staffed reverse-solved from Erlang C itself — is a working, runnable script: [`examples/contact_center_queueing.py`](https://github.com/rasinmuhammed/misata/blob/main/examples/contact_center_queueing.py). Run it directly:

```bash
python examples/contact_center_queueing.py
```

It prints every guarantee below, checked against the data it just generated:

```
queues: 4  intervals: 2400

  [OK] agents_staffed exceeds traffic_intensity_erlangs on every interval (queue stability)
  [OK] 'Billing Support' clears its 80% SLA target on 100.0% of intervals
  [OK] 'Retention' clears its 75% SLA target on 100.0% of intervals
  [OK] 'Sales' clears its 90% SLA target on 100.0% of intervals
  [OK] 'Technical Support' clears its 80% SLA target on 100.0% of intervals
  [OK] service_level_pct matches an independent Erlang C recomputation on every interval
  [OK] calls_answered + calls_abandoned equals offered_calls on every interval
  [OK] occupancy_pct and service_level_pct correlate at -0.31 (higher load, worse service)
  [OK] 'Billing Support' midday volume (40.7) exceeds opening volume (13.8)
  [OK] 'Retention' midday volume (14.9) exceeds opening volume (6.1)
  [OK] 'Sales' midday volume (25.8) exceeds opening volume (9.2)
  [OK] 'Technical Support' midday volume (29.5) exceeds opening volume (10.7)
  [OK] 'Billing Support' abandons 1.8% of calls over the full month
  [OK] 'Retention' abandons 4.0% of calls over the full month
  [OK] 'Sales' abandons 0.8% of calls over the full month
  [OK] 'Technical Support' abandons 1.7% of calls over the full month
  [OK] intervals.queue_id has zero orphans against queues.queue_id
  [OK] every interval_start falls exactly on a half-hour mark
  [OK] agents_staffed is a positive integer on every interval

ALL CHECKS PASSED
```

## What each number is grounded in

**Traffic intensity.** Measured in Erlangs — the actual unit, named after the man: `A = offered_calls x AHT / interval_length`. Not an arbitrary "load score."

**Probability of waiting.** The Erlang C formula, computed through the numerically stable Erlang B recursion (Sundt-Jewell) rather than the raw factorial form it's algebraically identical to, which overflows past N ≈ 170:

```
B(0, A) = 1
B(n, A) = A x B(n-1, A) / (n + A x B(n-1, A))
C(N, A) = B(N, A) / (1 - (A/N) x (1 - B(N, A)))
```

**Average speed of answer and service level.** The standard Erlang C results: `ASA = C(N, A) x AHT / (N - A)` and `SL(T) = 1 - C(N, A) x exp(-(N - A) x T / AHT)`.

**Staffing.** Not assigned — reverse-solved. Given a queue's declared SLA target (e.g. "80% of calls answered within 20 seconds," the industry's most-cited baseline) and an interval's forecast volume, `agents_staffed` is the smallest N for which the Erlang C service-level formula actually clears that target, plus a 20% shrinkage buffer (breaks, training, absenteeism — the standard WFM planning concept; ICMI's commonly cited range is 25-35%). This is the same reverse search every commercial staffing calculator runs, and it's why `service_level_pct` measurably clears each queue's own declared target on essentially every interval rather than sometimes falling short.

**Abandonment.** A real queueing-theory result, not a random flag: in an Erlang C / M/M/N queue, a call that has to wait experiences a wait time that is itself exponentially distributed with rate `(N x mu - lambda)` (Gross & Harris, *Fundamentals of Queueing Theory*). Modeling customer patience as a second, independent exponential clock turns "does this call abandon" into a race between two exponentials, which has a closed form: `patience_rate / (patience_rate + wait_rate)`. This is this example's own reasonable extension of the exact Erlang C result — see "What this is not" below for what it isn't claiming.

**Expected vs. realized, the same split credit-risk-portfolio uses.** `wait_probability_pct`, `asa_sec`, and `service_level_pct` are deterministic — exactly what the Erlang C formula implies for that interval's own (volume, staffing, AHT), recomputable and checked above. `calls_abandoned` and `calls_answered` are the realized, stochastic outcome: a real Binomial draw at the implied abandonment probability, not the expected rate copy-pasted into every row. That's why the aggregate abandonment rate lands close to what the formula implies, while any single sparse interval can look noisier — exactly like a real WFM report.

## The queues

Four queues with deliberately different traffic, handle times, SLA policies, and patience — a sales queue's callers hang up sooner than a billing queue's, and its SLA is tighter because a missed sales call is a lost lead:

| queue | SLA target | patience (mean) | peak volume/interval | AHT |
| --- | --- | --- | --- | --- |
| Billing Support | 80% in 20s | 75s | 40 | 300s |
| Technical Support | 80% in 30s | 90s | 30 | 420s |
| Sales | 90% in 15s | 45s | 25 | 240s |
| Retention | 75% in 25s | 60s | 15 | 360s |

## What this is not

This models a single voice queue per line of business with Erlang C, the classical model that ignores abandonment in its own staffing formula — real Erlang A (Palm, 1957) has a closed form involving the confluent hypergeometric function that this example does not implement; the abandonment modeled here is this example's own extension via a competing-exponentials approximation, not a claim to reproduce Erlang A exactly. It does not model chat, email, or blended queues, which need different math than phone queueing theory. Call volumes and AHT are declared, realistic-shaped assumptions, not measured from a real center's actual historical data.
