# Scaling Misata to billions of rows: streaming, distributed execution and cross-version determinism

Research note. Network access was limited: numpy.org, duckdb.org, databrickslabs.github.io, thesalmons.org and xuanwo.io were blocked by the egress proxy. Primary docs were read from their **source files on GitHub** (raw.githubusercontent.com), which hold the same text as the rendered sites. Links point to the canonical GitHub source file that was read. Some benchmark numbers come from a **local probe** run in this session. Those are labelled "[local probe]" and come with hardware context. The probe script was `scale_probe.py` in the session scratchpad. It ran on an Intel Xeon @ 2.80GHz with 4 vCPU and 15 GB RAM, using NumPy 2.4.6 and Python 3.11.15.

## 1. Counter-based RNGs and how existing generators make shards independent

### Takeaway
Use NumPy's `Philox`, a counter-based RNG from Random123, keyed per (table, column) through `SeedSequence`. Use `advance()` to jump straight to the start of any row block. A shard can then be generated with nothing more than (seed, table, column, row_start, row_count). Mature generators work the same way: dbldatagen derives every column from a row `id`, and dbgen / tpchgen generate parts independently. Avoid anything whose output depends on partitioning, such as Spark `rand()`.

### Cited Findings
- **Random123 / Philox / Threefry**: these come from Salmon et al., "Parallel Random Numbers: As Easy as 1, 2, 3" (SC'11 best paper). They are counter-based generators built from reduced-strength block ciphers. Threefry is derived from Threefish, and Philox uses wide multiplies. Both are "Crush-resistant", meaning they pass TestU01 SmallCrush, Crush and BigCrush — [Random123 docs](https://www.thesalmons.org/john/random123/releases/latest/docs/CBRNG.html); [paper PDF](https://www.thesalmons.org/john/random123/papers/random123sc11.pdf); [Wikipedia: Counter-based RNG](https://en.wikipedia.org/wiki/Counter-based_random_number_generator)
- **NumPy Philox state**: NumPy's Philox (4x64) holds a 256-bit counter and a 128-bit key. The counter "is incremented by 1 for every 4 64-bit randoms produced". `advance()` moves the counter by any step in [0, 2**256), and different keys give independent sequences. The `key` and `counter` can be set directly, which bypasses SeedSequence — [numpy/_philox.pyx](https://github.com/numpy/numpy/blob/main/numpy/random/_philox.pyx)
- **Philox compatibility guarantee**: the docstring says "`Philox` makes a guarantee that a fixed `seed` will always produce the same random integer stream" — [numpy/_philox.pyx](https://github.com/numpy/numpy/blob/main/numpy/random/_philox.pyx)
- **Philox independent streams**: "Philox has completely independent cycles determined by the seed". The NumPy docs recommend `Philox(key=root_seed + stream_id)` for independent streams, as long as stream IDs are never reused — [NumPy parallel.rst](https://github.com/numpy/numpy/blob/main/doc/source/reference/random/parallel.rst)
- **SeedSequence spawning**: SeedSequence hashes the seed and the spawn-tree path into a 128-bit pool. The chance of any collision among n streams is about n²·2⁻¹²⁸. For one million streams that is about 2⁻⁸⁸. `Generator.spawn(n)` is the convenience form — [NumPy parallel.rst](https://github.com/numpy/numpy/blob/main/doc/source/reference/random/parallel.rst)
- **Seeding with a list of integers**: the documented pattern is `default_rng([worker_id, root_seed])`, with the varying IDs placed *before* the root seed, because `spawn()` appends integers to the seed. `root_seed + worker_id` is explicitly marked "UNSAFE", because runs with nearby root seeds end up sharing worker streams — [NumPy parallel.rst](https://github.com/numpy/numpy/blob/main/doc/source/reference/random/parallel.rst)
- **`jumped()` distances**: PCG64 jumps by (φ−1)·2¹²⁸, and Philox and MT19937 jump by 2¹²⁸ — [NumPy parallel.rst](https://github.com/numpy/numpy/blob/main/doc/source/reference/random/parallel.rst)
- **JAX PRNG**: the design is "Threefry counter PRNG + a functional array-oriented splitting model". It was designed for reproducibility that does not depend on the backend, and to stay the same across `jit` boundaries and devices. JAX deliberately drops NumPy's guarantee that one array call matches the same number of scalar calls ("sequential-equivalent"), so that generation can be vectorised — [JAX JEP 263 PRNG design](https://github.com/jax-ml/jax/blob/main/docs/jep/263-prng.md)
- **dbldatagen (Databricks Labs)**: every column is "generated through some transformation of the `id` column or some other designated `baseColumn`, either by using its value, a hash of its value…". The data is repeatable unless a column is marked `random` with seed −1. `randomSeedMethod='hash_fieldname'` gives each column its own seed from a hash of its name. The same rules plus the same seed in two tables produce the same values, which the docs say allows "multiple tables with referential integrity". Exceptions: ILText, template text and Faker integration are seeded once, so they repeat from run to run but give different values for the same base value. Faker's seeding is not integrated, so "data will not be repeatable run to run" — [dbldatagen repeatable_data_generation.rst](https://github.com/databrickslabs/dbldatagen/blob/master/docs/source/repeatable_data_generation.rst); [rendered docs](https://databrickslabs.github.io/dbldatagen/public_docs/repeatable_data_generation.html)
- **Spark `rand(seed)` / `randn(seed)`**: the docstrings state "The function is non-deterministic in general case" — [pyspark builtin.py](https://github.com/apache/spark/blob/master/python/pyspark/sql/functions/builtin.py)
- **DuckDB `tpch` extension**: `dbgen(sf, children, step)` generates partition `step` out of `children` partitions. Per search snippets of the rendered docs, `dbgen` is single-threaded, and running steps in parallel is not supported. The docs also warn that DuckDB's TPC-H output has "small differences from the official TPC-H specification" and point to `tpchgen-cli` for compliant data — [duckdb-web tpch.md](https://github.com/duckdb/duckdb-web/blob/main/docs/current/core_extensions/tpch.md); [rendered](https://duckdb.org/docs/current/core_extensions/tpch)
- **tpchgen-rs / tpcgen-rs (Rust, DataFusion contrib)**: "multi-core and constant memory use". It aims to "produce the same exact bytes as the reference implementations, both for single and multi-part output", which is checked in CI. Performance comes from avoiding heap allocations, using integer arithmetic instead of floats, and multiple cores with tuned buffers — [tpcgen-rs README](https://github.com/datafusion-contrib/tpcgen-rs); [ARCHITECTURE.md](https://github.com/datafusion-contrib/tpcgen-rs/blob/main/ARCHITECTURE.md)

### Inferences
- Recommended Misata design: `key = SeedSequence([table_id, column_id, root_seed]).generate_state(2, uint64)`, then `bg = Philox(key=key); bg.advance(row_start * draws_per_row / 4)`. **[local probe]** confirmed the mechanics. A block generated after `advance(750_000)` matched elements 3,000,000 to 3,999,999 of the full stream exactly, for both `integers(uint64)` and `random()` doubles.
- The jump only works if each column consumes a fixed number of 64-bit words per row. That holds for `random()` and full-range uint64. Rejection-sampling distributions such as normal (ziggurat), gamma, bounded `integers` with rejection, and Zipf consume a *variable* number of words. Two ways around this:
  - (a) give each row block of fixed size B its own key or counter offset, for example `counter = [block_idx, 0, 0, 0]` or `advance(block_idx * 2**64)`, and generate whole blocks;
  - (b) draw only uniforms and apply inverse-CDF transforms yourself.
  Option (a) is simpler, and it makes the canonical shard unit a fixed-size block (say 2²⁰ rows), independent of how many workers run.
- dbldatagen's "everything is a function of `id`" model is the right mental model for Misata. Each value is f(seed, table, column, row_id), with an RNG block per (column, block) as an efficient way to compute it.

### Gaps
- I could not open the Random123 paper itself (blocked), so its cycles/byte figures are not given here. Search confirmed the Crush-resistance claims only.
- I did not verify how the original TPC-H C dbgen enables `-C/-S` parallel parts internally (it uses per-column seed streams with skip-ahead). No primary source was reachable for this.
- The rendered "Datafaker" and "synth" docs were not reachable. Synth (shuttle-hq) is "100% Rust" and "can scale to millions of rows", and its repository had open issues in 2024 — [shuttle-hq/synth](https://github.com/shuttle-hq/synth). I found no published rows/sec figure for Synth, and I could not confirm whether the repository is archived.

## 2. Foreign keys and fan-out without holding all parents in memory

### Takeaway
Parent-side counts can be computed independently per parent block. The child-to-parent FK is then an inverse-CDF lookup, `searchsorted`, over cumulative weights, or it falls out of a block-wise "children of parent i" layout. Unique keys that look random but need no memory come from a keyed Feistel permutation with cycle-walking.

### Cited Findings
- **dbldatagen multi-table**: referential integrity comes from regenerating the same deterministic key column with the same rules and seed in both tables, without joins or lookups — [dbldatagen multi_table_data.rst](https://github.com/databrickslabs/dbldatagen/blob/master/docs/source/multi_table_data.rst); [repeatable_data_generation.rst](https://github.com/databrickslabs/dbldatagen/blob/master/docs/source/repeatable_data_generation.rst)
- **Feistel + cycle-walking (permuteseq)**: generates "unique, non-sequential, random-looking series of numbers without looking up previous values … encrypt sequence positions with a Feistel cipher and cycle-walking". The output is reproducible with the same key, and an inverse function (`reverse_permute`) exists — [dverite/permuteseq](https://github.com/dverite/permuteseq)
- Feistel networks are bijections. Cycle-walking keeps re-encrypting until the value falls inside the target range, which preserves the format — [Format-preserving encryption (Wikipedia)](https://en.wikipedia.org/wiki/Format-preserving_encryption); [gfc-fpe generalised Feistel for stateless shuffling](https://github.com/kevincharm/gfc-fpe); [Feistel Shuffle notes](https://docs.fairy.dev/theory/feistel-shuffle/)
- **[local probe]** Zipf(s=1.1) FK assignment over 1M parents with `np.searchsorted(cdf, rng.random(N))` ran at about **6.0M child rows/s** on a single core (Xeon 2.8GHz). The CDF array costs 8 MB for 1M parents.

### Inferences
Recommended patterns for Misata:
1. **Fan-out by counts, laid out by parent ("children of parent i are contiguous")**:
   - Draw `count_i` for each parent block from that block's own RNG.
   - Run a prefix sum per block, and keep only the per-block totals: a few KB for a billion parents with 1M-row blocks.
   - Child row r maps to a parent by binary search over the block totals and then within the block.
   - This regenerates exactly, and a child shard only needs the counts of the parent blocks it spans. TPC-H lineitem follows the same shape (1–7 lines per order).
2. **Fan-out by popularity (Zipf over parents, children ordered by time)**: inverse-CDF `searchsorted` over the cumulative weights.
   - For billions of parents, don't materialise the CDF. Use a two-level CDF: per-block weight sums, then sample within the block.
   - Alternatively, use an analytic or approximate inverse of the Zipf rank CDF, such as rejection-inversion (Hörmann & Derflinger). I did not verify a source for this.
   - Then pass the rank through a Feistel permutation, so that "popular" parents are spread across IDs instead of all being IDs 0…k.
3. **Unique random-looking PKs, or unique sampled emails or IDs**:
   - `pk = feistel_permute(row_id, key, domain=N)` is O(1) memory and invertible, and every shard computes its own.
   - A vectorised NumPy Feistel (4+ rounds, with a hash round function on uint64 arrays) should run at tens of M/s. This is unbenchmarked.
4. Avoid `rng.choice(parents, replace=False)` and `np.unique`-based deduplication at scale. Both are global, O(N) memory operations, and their output depends on how the work is split into shards.

### Gaps
- I found no benchmark for a vectorised NumPy Feistel permutation, and no primary source for the count of rounds needed for statistical quality, as opposed to crypto security. A search snippet claimed "4 rounds sufficient for CCA security" (Luby-Rackoff), but I didn't verify it against a primary source.
- I could not reach dbldatagen's docs for its `distribution` / weighted-values mechanics at scale.

## 3. Output formats and throughput

### Takeaway
Generate Arrow RecordBatches per block and stream them to Parquet. Use row groups of at least 128K rows, up to roughly 1M rows or 512MB–1GB; PyArrow's default is min(rows, 1,048,576). Polars streaming and DuckDB are good sinks or consumers. Postgres loads fastest through `COPY … FROM STDIN`, in BINARY format where the types allow. The current state of the art for raw throughput is Rust tpchgen at about 1.4 GB/s on a laptop. Pure-Python fakers are about four orders of magnitude slower than vectorised NumPy.

### Cited Findings
- **Parquet spec recommendation**: "We recommend large row groups (512MB - 1GB)". Larger groups need more buffering on the write path. An "optimized read setup would be: 1GB row groups, 1GB HDFS block size" — [apache/parquet-format README](https://github.com/apache/parquet-format/blob/master/README.md)
- **PyArrow ParquetWriter**: `row_group_size` defaults to "the minimum of the number of rows in the Table/RecordBatch and 1024 * 1024". When writing batches it is capped at 64·1024·1024 — [pyarrow/parquet/core.py](https://github.com/apache/arrow/blob/main/python/pyarrow/parquet/core.py)
- **Polars streaming**: `collect(engine="streaming")` processes data in batches, for datasets larger than memory. The streaming engine "also is more performant than Polars' in-memory engine". Operations that don't support streaming fall back to the in-memory engine — [polars user guide streaming.md](https://github.com/pola-rs/polars/blob/main/docs/source/user-guide/concepts/streaming.md)
- **tpchgen-rs benchmarks** (DataFusion blog, 2025-04-10):
  - TPC-H SF=100 in **72.23 s (1.4 GB/s) on a MacBook Air M3, 16GB**, against about 30 min (0.05 GB/s) for classic `dbgen`.
  - All 36 GB of SF=100 as Parquet in under 2 min, against 44 min for DuckDB on the same machine.
  - On a 22-core GCP VM with 88GB: SF=100 Parquet in 1m14s (tpchgen) against 17m48s (DuckDB). SF=1000 in 10m26s at about 5 GB peak RAM. DuckDB could not run SF=1000 there because it "requires 647 GB of RAM".
  - 3.3 GB/s to disk in some runs ("faster than can be written to an SSD"), and 4 GB/s to /dev/null.
  - Memory is bounded through tokio async streams. They tried Rayon but "could not easily keep memory bounded".
  - Source: [datafusion-site blog post source](https://github.com/apache/datafusion-site/blob/main/content/blog/2025-04-10-fastest-tpch-generator.md)
- **DuckDB dbgen memory**: according to the same blog, DuckDB needs about 71 GB for SF=10, and SF=300 would need about 1.8 TB of RAM. Pre-generated DuckDB TPC-H databases go up to SF3000 (796 GB) — [datafusion blog](https://github.com/apache/datafusion-site/blob/main/content/blog/2025-04-10-fastest-tpch-generator.md); [duckdb-web tpch.md](https://github.com/duckdb/duckdb-web/blob/main/docs/current/core_extensions/tpch.md)
- **Postgres via psycopg 3**:
  - `cursor.copy("COPY … FROM STDIN")` with `write_row()` or `write()` of raw blocks.
  - "Using FORMAT BINARY usually gives a performance boost, but it only works if you can pass exactly the types the server expects" (int vs bigint, for example), and "PostgreSQL is particularly finicky when loading data in binary mode".
  - Pre-formatted text or CSV can be streamed with `copy.write(data)`.
  - Source: [psycopg docs copy.rst](https://github.com/psycopg/psycopg/blob/master/docs/basic/copy.rst)
- **Mimesis vs Faker** (Mimesis's own benchmark):
  - "overall speedup of about 24×" across 47 operations, 20,000 iterations each.
  - Uniqueness on 100K values: Faker peaks 1.22× higher; Mimesis averages 98.5% unique against Faker's 79%. Faker `url` was 46.9% unique.
  - Recorded on a MacBook Pro 14″ M1 Pro, 32GB.
  - Caveat: the timing table's units look inconsistent. It lists 0.012 µs per Person op, which is implausibly fast for Python, and lists the "Complex operations" Faker average in ms against µs for Mimesis. Treat the absolute numbers as suspect and the relative ranking as vendor-reported.
  - Mimesis also documents that lazy schema iteration is about 40–45% faster and 85–99% more memory-efficient than materialising.
  - Sources: [mimesis docs/benchmarks.rst](https://github.com/lk-geimfari/mimesis/blob/master/docs/benchmarks.rst); [mimesis docs/schema.rst](https://github.com/lk-geimfari/mimesis/blob/master/docs/schema.rst)
- **[local probe]** NumPy 2.4.6 on Xeon @ 2.80GHz, single core, 10M doubles via `Generator.random(out=…)`, after warm-up:

  | Bit generator | Throughput |
  |---|---|
  | SFC64 | **314 M/s** |
  | PCG64 | **250 M/s** |
  | PCG64DXSM | **172 M/s** |
  | Philox | **115 M/s** |
  | `standard_normal` | about 68 M/s (cold run) |

  The cold first pass showed much lower PCG64 numbers, about 20 M/s, because of allocation and page-faulting, so warm buffers matter.
- **[local probe]** "First Last" names built by indexing vocab arrays and concatenating with `np.char.add` ran at about **1.66 M names/s**. Faker `name()` ran at about **8.2 K names/s**, roughly 200× slower, on the same machine.

### Inferences
- For Misata: the RNG is not the bottleneck. Even Philox, at about 115 M doubles/s per core, is far faster than string assembly (about 1.7 M/s with `np.char`) and Parquet encoding. Prefer Philox for the random-access guarantee and accept the roughly 2× cost against PCG64.
- Generating text as dictionary-encoded categoricals is likely the biggest throughput win: integer codes into a vocab, written as Arrow `DictionaryArray` / Parquet dictionary pages, without building Python strings. This is inferred and unbenchmarked.
- Suggested pipeline:
  - a block generator yields `pa.RecordBatch`, about 1M rows each;
  - `pq.ParquetWriter` writes one row group per block, or a multiple of it;
  - one file per shard, `table/part-{block:06d}.parquet`;
  - for distributed runs, use `multiprocessing` / Dask / Ray / Spark `mapInArrow`, keyed by block index.
  - Because every block is a pure function of (seed, block_idx), the output is byte-identical no matter how many workers run, provided file boundaries are tied to block boundaries.
- For Spark/Databricks, `mapInArrow` or `mapInPandas` over a DataFrame of block indices keeps Misata's NumPy RNG semantics. Spark `rand()` should not be used, because it is non-deterministic and depends on partitioning.

### Gaps
- I found no reliable rows/sec figures for fakeit, polars-faker or Datafaker in the sources I could reach.
- I could not get rows/sec figures for COPY into Postgres with hardware context from a primary source.
- The DuckDB `COPY … (FORMAT parquet, ROW_GROUP_SIZE …)` defaults were not verified, because duckdb.org was blocked.

## 4. Determinism across versions and platforms

### Takeaway
NumPy guarantees *only* same build, same environment, same machine for `Generator` methods. BitGenerators such as Philox guarantee a stable raw integer stream, and `RandomState` is frozen. Faker gives no guarantee across patch versions, and Hypothesis ties replay blobs to an exact version. Misata should build its own "output compatibility" layer:
- consume only raw uint64 or uniform streams from a BitGenerator;
- implement its own distribution transforms in integer or carefully ordered float code;
- avoid Python `hash()` and unstable sorts;
- stamp every output with an `output_version` and keep old algorithms selectable.

### Cited Findings
- **NumPy policy**: stream compatibility holds only with "the same BitGenerator, with the same seed, perform the same sequence of method calls with the same arguments, on the same build of numpy, in the same environment, on the same machine". The docs give two reasons:
  - different CPUs' floating-point behaviour "can cause differences in certain edge cases that cascade to the rest of the stream";
  - `multivariate_normal` depends on the LAPACK that NumPy links against.
  - Calling `rng.random()` 5 times is not *guaranteed* to equal `rng.random(5)`.
  - Changes that break the stream for `Generator`/`default_rng` are allowed in X.Y feature releases, and correctness fixes even in bugfix releases. `default_rng` may change its default BitGenerator.
  - "BitGenerator classes have stronger guarantees of version-to-version stream compatibility".
  - `RandomState`: "There will be no more modifications … not even to fix correctness bugs", though machine-to-machine caveats still apply.
  - Source: [numpy compatibility.rst](https://github.com/numpy/numpy/blob/main/doc/source/reference/random/compatibility.rst)
- **NEP 19** (Final; created 2018-05-24, updated 2019-05-21, author Robert Kern):
  - BitGenerators "MUST guarantee stream-compatibility" for `.bytes()`, `integers()` and `random()`.
  - A legacy class (RandomState) keeps strict compatibility for uses like unit-test data.
  - Versioning `Generator` was rejected, because "Adding in versioning to maintain stream-compatibility would still only provide the same level of stream-compatibility that we currently do".
  - Source: [NEP 19 source](https://github.com/numpy/numpy/blob/main/doc/neps/nep-0019-rng-policy.rst)
- **Faker**: a seed "produces the same result when the same methods with the same version of faker are called … results are not guaranteed to be consistent across patch versions … make sure you pinned the version of Faker down to the patch number" — [Faker README.rst](https://github.com/joke2k/faker/blob/master/README.rst)
- **Hypothesis**: `@reproduce_failure(version, blob)` errors if used under a different Hypothesis version, because the blob is a serialised internal representation that "is not stable across Hypothesis versions" — [Hypothesis docs: reproducing failures](https://hypothesis.readthedocs.io/en/latest/reproducing.html)
- **Python hash randomisation**: unless `PYTHONHASHSEED` is set to an integer, "a random value is used to seed the hashes of str and bytes objects". The fixed setting exists to "allow a cluster of python processes to share hash values" — [CPython Doc/using/cmdline.rst](https://github.com/python/cpython/blob/main/Doc/using/cmdline.rst)
- **dbldatagen**: values derived from `now()` / `current_timestamp()` break repeatability. Its docs recommend explicit `begin`/`end`/`interval` instead — [dbldatagen repeatable_data_generation.rst](https://github.com/databrickslabs/dbldatagen/blob/master/docs/source/repeatable_data_generation.rst)
- **JAX**: aims for reproducibility that does not depend on the backend and for semantics that stay the same across jit boundaries and devices, which is a stronger goal than NumPy's — [JAX PRNG design](https://github.com/jax-ml/jax/blob/main/docs/jep/263-prng.md)
- **tpchgen-rs**: uses integer arithmetic rather than floats, and tests byte-for-byte equality against reference output, for both single and multi-part generation — [ARCHITECTURE.md](https://github.com/datafusion-contrib/tpcgen-rs/blob/main/ARCHITECTURE.md); [README](https://github.com/datafusion-contrib/tpcgen-rs)

### Inferences
Concrete rules for a Misata "output compatibility" contract:
1. Pin the BitGenerator explicitly (`Philox`), never `default_rng`, because the default may change. Draw only `integers(…, dtype=uint64)` full-range or `random()`, which NEP 19 binds BitGenerators to keep stable. Implement Misata-owned transforms for normal, lognormal, Zipf, Poisson, choice-with-weights and so on, written as inverse-CDF on uniforms or as integer algorithms. Then a NumPy upgrade cannot change Misata output.
2. Don't depend on Python `hash()`, `set` or `dict`-of-set iteration order for anything that feeds values. To derive per-column seeds from names, use a stable hash such as `hashlib.blake2b(name.encode()).digest()[:16]` → SeedSequence entropy.
3. Use `np.sort(kind="stable")` / `argsort(kind="stable")` wherever ties are possible. pandas `sort_values` defaults to quicksort, which is not stable. This is from general knowledge, not verified against a cited source this session.
4. For floating-point reproducibility:
   - avoid transcendental-heavy float paths, since libm can differ by platform;
   - round generated money and decimals to integer cents early;
   - prefer integer timestamps (epoch seconds or ms);
   - avoid `multivariate_normal` and other LAPACK-backed sampling. Use Misata's own Cholesky on a fixed small matrix, or accept that results may differ by machine.
5. Stamp `misata_output_version` (and the RNG algorithm) into Parquet key-value metadata and the CLI manifest. Keep the old transforms reachable via `compat="0.9"`, similar to how NumPy keeps `RandomState` frozen. A golden-hash test suite should run in CI across Linux, macOS, Windows and ARM, comparing SHA-256 of canonical output per (schema, seed, version), as tpchgen does.
6. Faker-backed columns can't be part of the cross-version guarantee unless Faker is pinned to a patch version. Misata's own vocab and grammar text generators can be.

### Gaps
- I didn't find a documented "output compatibility mode" in dbldatagen beyond the repeatable-by-construction principle, and no per-version output guarantee.
- Platform-specific differences in NumPy's float transforms were not measured. Only the docs' caveat is cited.

## 5. Incremental / time-windowed generation and streaming roll-ups

### Takeaway
If each day (or time window) is its own block key, and entity state comes from deterministic functions rather than accumulated history, then new days can be appended without regenerating earlier ones. Roll-ups can be computed per block and merged, because counts, sums, min and max are associative.

### Cited Findings
- dbldatagen's guidance applies here: generate dates and timestamps from explicit `begin`, `end` and `interval` rather than `now()`, so that runs on later dates produce the same data — [dbldatagen repeatable_data_generation.rst](https://github.com/databrickslabs/dbldatagen/blob/master/docs/source/repeatable_data_generation.rst)
- tpchgen streams data with bounded memory per thread ("memory usage is a function of the number of threads"). It writes multi-part output whose bytes match a single-part run — [datafusion blog source](https://github.com/apache/datafusion-site/blob/main/content/blog/2025-04-10-fastest-tpch-generator.md); [tpcgen-rs README](https://github.com/datafusion-contrib/tpcgen-rs)
- Polars' streaming engine handles aggregations in batches, for larger-than-memory group-bys — [polars streaming.md](https://github.com/pola-rs/polars/blob/main/docs/source/user-guide/concepts/streaming.md)
- SeedSequence entropy can be a list of integers such as `[day_index, table_id, root_seed]`, with varying IDs first, which gives independent streams per day — [NumPy parallel.rst](https://github.com/numpy/numpy/blob/main/doc/source/reference/random/parallel.rst)

### Inferences
Suggested Misata design:
- **Time-partitioned facts**: `rng_key = (root_seed, table, column, day_index, block_within_day)`.
  - The row count for day d is drawn from that day's own RNG, for example a seasonality-modulated Poisson.
  - Row IDs come from `global_offset(d)`, which needs the prefix sum of counts before d. To keep appends O(1), either store a small manifest of per-day counts, or use IDs that encode the date, such as `(day_index << 32) | seq`, or a Feistel permutation of them.
- **Entities that change over time** (customers signing up): sign-up day is a deterministic function of the entity ID, so `customers active on day d` is computable without history. Facts on day d sample FKs only from entities whose signup day is ≤ d, using the inverse-CDF over a prefix of the parent space.
- **Slowly-changing attributes** (plan changes, churn): define them as a pure function of (entity_id, d) through a per-entity event schedule drawn from the entity's own key. Don't derive them from an accumulated simulation, which would need a full replay to append a day.
- **Roll-ups**: emit per-block partial aggregates (count, sum, sum of squares, min, max, HyperLogLog/approx sketches for distinct counts) next to each block. Merge them in a final reduce. A daily roll-up is then exactly the sum of that day's block partials, and it can be appended along with the new day.
- **Tests**: the property to check is that generate(days 0..N) followed by append(day N+1) is byte-identical to generate(days 0..N+1).

### Gaps
- I found no external library documentation that describes a "consistent append" feature for synthetic data generators. The recommendations above are design inferences from the cited primitives.
- I found no sources on streaming generation of distinct-count roll-ups for synthetic data specifically.
