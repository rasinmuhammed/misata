---
title: Load and Performance Test Data at Scale
description: Stream millions of rows with hot keys, a declared daily traffic curve and long-tailed latencies to partitioned Parquet in bounded memory, with every key checked before the test starts.
---

# Load and performance test data

A load test against uniform random data measures the wrong system. Real
traffic has hot keys that hammer one cache shard, an evening peak that is
ten times the overnight trough, and a latency tail that sets the p99. This
recipe declares those shapes and streams the result to Parquet, so the
replay hits the same hot paths production does.

**Who:** platform, SRE and database engineers.
**Time:** about 18 seconds for 2.6 million rows on a laptop.

## The declaration

```yaml
# misata.yaml
name: checkout_load
seed: 3
tables:
  users:
    rows: 100000
    columns:
      user_id: {type: int, unique: true, min: 1, max: 100000}
      region: {type: categorical, choices: [us-east, us-west, eu-west, ap-south], probabilities: [0.4, 0.2, 0.25, 0.15]}
      signed_up_at: {type: date, start: "2023-01-01", end: "2025-10-31"}
  requests:
    rows: 2500000
    columns:
      request_id: {type: int, unique: true, min: 1, max: 100000000}
      user_id: {type: foreign_key, sampling: pareto}
      route: {type: categorical, choices: [cart, checkout, search, product, login], probabilities: [0.18, 0.04, 0.33, 0.4, 0.05]}
      status: {type: categorical, choices: ["200", "304", "404", "429", "500"], probabilities: [0.9, 0.05, 0.03, 0.015, 0.005]}
      latency_ms: {type: float, distribution: lognormal, mean: 120, std: 90, min: 3, max: 30000, decimals: 1}
      requested_at:
        type: datetime
        start: "2025-11-24"
        end: "2025-12-01"
        hour_weights: [1, 1, 1, 1, 1, 2, 3, 5, 7, 8, 8, 8, 9, 9, 8, 8, 8, 9, 11, 13, 14, 12, 7, 3]
relationships:
  - users.user_id -> requests.user_id
```

- `sampling: pareto` on `user_id` makes a few users very busy: the top 1%
  send 22.2% of all requests.
- `hour_weights` is the daily curve, one weight per hour from midnight. The
  output follows it to within a fraction of a percent: 15,925 requests in the
  00:00 hour, 222,964 at 20:00.
- Latency is lognormal: median 95.9 ms, p95 287.6 ms, p99 455.1 ms.

## Run it

```bash
pip install "misata[parquet,duckdb]"
misata explain misata.yaml
misata generate -c misata.yaml -o lake --format parquet --partition-by route --attest
```

`lake/requests/` is Hive-partitioned by `route` (`route=checkout/`,
`route=search/`, ...), one file per route, 65 MB in all. Tables are written
batch by batch, so memory grows far slower than the data: raise `rows` to
the size you need.

## Measured at ten million

`benchmarks/bench_r3_volume.py` streams a 14-table retail schema, ten million
rows in all, and checks every foreign key with DuckDB afterwards:

<!-- stranger: skip, a 40-second benchmark from a source checkout -->
```bash
python benchmarks/bench_r3_volume.py --scale 10 --stream /tmp/r3
```

| Rows | Tables | Time | Peak memory | Foreign key failures |
|---:|---:|---:|---:|---:|
| 1,100,000 (this recipe at 1M requests) | 2 | 7.4 s | 0.88 GB | 0 |
| 2,600,000 (this recipe) | 2 | 17.6 s | 0.93 to 1.1 GB | 0 |
| 5,100,000 (this recipe at 5M requests) | 2 | 35.6 s | 1.15 GB | 0 |
| 10,000,000 (the benchmark) | 14 | 36.3 s | 0.78 GB | 0 |

Measured on an Apple M1 with Misata 0.9.8; peak memory is the resident set
size reported by `time -l` and varies by about 15% between identical runs.
Most of it is the interpreter, pandas and Arrow; quadrupling the rows adds
about 0.3 GB.

## The check

A load test that fails halfway because a request references a missing user
has tested the fixture, not the system. The attestation confirms the keys
and domains before anything is replayed:

```bash
python lake/verify.py
```

```text
ok    6 file(s) match their attested sha256
ok    6 of 6 invariant(s) hold
```

Every `user_id` exists in `users`, both ids are unique, and `region`,
`route` and `status` hold only declared values.

## Replaying it

Order by `requested_at` and feed your load tool, scaling time if you want a
week in an hour. With the DuckDB CLI:

<!-- stranger: skip, uses the duckdb command-line tool -->
```bash
duckdb -c "COPY (SELECT * FROM read_parquet('lake/requests/**/*.parquet', hive_partitioning = true) ORDER BY requested_at) TO 'replay.csv'"
```
