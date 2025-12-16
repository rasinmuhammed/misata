"""
Performance benchmark test for Misata.

Tests the ability to generate 1M+ rows efficiently.
"""

import time
from misata import DataSimulator, SchemaConfig, Table, Column


def benchmark_large_dataset():
    """Benchmark generating 1M rows."""
    print("=" * 70)
    print("Misata Performance Benchmark: 1M Rows")
    print("=" * 70)
    print()
    
    # Simple schema for pure performance testing
    config = SchemaConfig(
        name="Performance Test",
        description="1M row dataset for benchmarking",
        seed=42,
        tables=[
            Table(name="events", row_count=1_000_000),
        ],
        columns={
            "events": [
                Column(
                    name="event_id",
                    type="int",
                    distribution_params={"min": 1, "max": 1_000_000},
                ),
                Column(
                    name="timestamp",
                    type="date",
                    distribution_params={"start": "2023-01-01", "end": "2024-12-31"},
                ),
                Column(
                    name="value",
                    type="float",
                    distribution_params={
                        "distribution": "normal",
                        "mean": 100.0,
                        "std": 20.0,
                        "decimals": 2,
                    },
                ),
                Column(
                    name="category",
                    type="categorical",
                    distribution_params={
                        "choices": ["A", "B", "C", "D", "E"],
                        "probabilities": [0.3, 0.25, 0.2, 0.15, 0.1],
                    },
                ),
                Column(
                    name="active",
                    type="boolean",
                    distribution_params={"probability": 0.7},
                ),
            ],
        },
    )
    
    print(f"Generating {config.tables[0].row_count:,} rows...")
    print(f"Columns: {len(config.columns['events'])}")
    print()
    
    # Initialize
    simulator = DataSimulator(config)
    
    # Measure generation time
    start = time.time()
    data = simulator.generate_all()
    elapsed = time.time() - start
    
    # Results
    df = data["events"]
    total_rows = len(df)
    rows_per_sec = total_rows / elapsed if elapsed > 0 else 0
    memory_mb = df.memory_usage(deep=True).sum() / (1024 ** 2)
    
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"Total rows:        {total_rows:,}")
    print(f"Generation time:   {elapsed:.2f} seconds")
    print(f"Rows per second:   {rows_per_sec:,.0f}")
    print(f"Memory usage:      {memory_mb:.2f} MB")
    print()
    
    # Performance assessment
    if elapsed < 60:
        print("✓ PASSED: Generated 1M rows in under 60 seconds!")
        if rows_per_sec > 50000:
            print("  🚀 EXCELLENT: >50K rows/second")
        elif rows_per_sec > 20000:
            print("  ✓ GOOD: >20K rows/second")
        else:
            print("  ⚠ ACCEPTABLE: But room for optimization")
    else:
        print("⚠ SLOW: Took more than 60 seconds")
        print("  Consider further optimization")
    
    print()
    print("Sample data:")
    print(df.head())


if __name__ == "__main__":
    benchmark_large_dataset()
