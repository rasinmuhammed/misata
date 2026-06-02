"""
SpecBench task suite.

Each Task carries:
  - story:          the natural-language / declarative specification (generator input)
  - oracle:         the analytical targets, computed INDEPENDENTLY of any generator
  - schema_tables:  generic schema description (for the Faker baseline & FIVR/TCV)
  - fks:            (parent_table, parent_key, child_table, child_key) edges
  - metric spec:    which column/time-column carry the outcome, and the period targets

Oracles are frozen in the task definition — the spec *is* the ground truth — so there
is no circularity: we never read targets back from a generator's output.

This module ships a small but real seed suite (extensible to the full 18x4 grid). The
seed suite is enough to produce the paper's E5 table and the Prop-5 curve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Task:
    task_id: str
    mode: str                                   # "spec" (cold-start) | "reference"
    story: str
    rows: int

    # outcome oracle (Family A)
    metric_table: str
    metric_col: str
    time_col: Optional[str] = None
    period_freq: str = "M"
    period_targets: Dict[str, float] = field(default_factory=dict)   # label -> sum
    rate_targets: Dict[str, float] = field(default_factory=dict)     # col==value -> p
    group_targets: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # integrity oracle (Family B)
    fks: List[Tuple[str, str, str, str]] = field(default_factory=list)
    temporal_order: List[Tuple[str, str, str]] = field(default_factory=list)  # (table, earlier, later)
    constraints: List[Dict[str, Any]] = field(default_factory=list)  # hard constraints (CSAT)

    # generic schema (for the Faker baseline)
    schema_tables: List[Dict[str, Any]] = field(default_factory=list)
    primary_table: str = ""

    # reference-mode only
    reference_tables: Optional[Dict[str, Any]] = None


def _saas_curve_task() -> Task:
    """SaaS MRR curve — the canonical Family-A conformance task.

    Oracle contains ONLY the anchors the specification explicitly declares
    ($50k January, $200k December). Interpolated months are the generator's choice,
    not declared targets, so measuring against them would be inventing ground truth.
    Period labels are month-of-year ('01'..'12'), matched year-agnostically, because
    the spec fixes the shape across "a year", not a calendar year.
    """
    targets = {"01": 50_000.0, "12": 200_000.0}
    story = (
        "SaaS company with 5k users - MRR $50k in January rising to $200k in December, "
        "Q3 dip in July, strong Q4"
    )
    return Task(
        task_id="saas_mrr_curve",
        mode="spec",
        story=story,
        rows=5000,
        metric_table="subscriptions",
        metric_col="mrr",
        time_col="start_date",
        period_freq="M",
        period_targets=targets,
        # Hard constraint: per-subscription MRR ceiling ($1000 plan cap). Misata respects
        # per-row bounds by construction; blind aggregate-rescale inflates the tail past
        # the cap because multiplying a period to hit its sum scales up the largest rows.
        constraints=[{"table": "subscriptions", "column": "mrr", "op": "<=", "value": 1000.0}],
        fks=[("users", "user_id", "subscriptions", "user_id")],
        primary_table="subscriptions",
        schema_tables=[
            {"name": "users", "pk": "user_id", "rows": 5000, "columns": [
                {"name": "country", "kind": "category", "choices": ["US", "UK", "DE", "IN"]},
                {"name": "signup_date", "kind": "date", "start": "2024-01-01", "span_days": 365},
            ]},
            {"name": "subscriptions", "pk": "subscription_id", "rows": 6000, "columns": [
                {"name": "user_id", "kind": "fk", "parent": "users", "parent_pk": "user_id"},
                {"name": "mrr", "kind": "metric", "scale": 150},
                {"name": "start_date", "kind": "date", "start": "2024-01-01", "span_days": 365},
            ]},
        ],
    )


def _ecommerce_fk_task() -> Task:
    """Ecommerce — Family-B integrity focus (multi-table FK + temporal order)."""
    story = "Ecommerce store with 2k customers and 8k orders across 2024"
    return Task(
        task_id="ecommerce_integrity",
        mode="spec",
        story=story,
        rows=2000,
        metric_table="orders",
        metric_col="amount",
        time_col="ordered_at",
        period_freq="M",
        period_targets={},                       # integrity task: no curve target
        fks=[("customers", "customer_id", "orders", "customer_id")],
        temporal_order=[("orders", "ordered_at", "shipped_at")],
        primary_table="orders",
        schema_tables=[
            {"name": "customers", "pk": "customer_id", "rows": 2000, "columns": [
                {"name": "country", "kind": "category", "choices": ["US", "UK", "DE"]},
            ]},
            {"name": "orders", "pk": "order_id", "rows": 8000, "columns": [
                {"name": "customer_id", "kind": "fk", "parent": "customers", "parent_pk": "customer_id"},
                {"name": "amount", "kind": "metric", "scale": 85},
                {"name": "ordered_at", "kind": "date", "start": "2024-01-01", "span_days": 365},
            ]},
        ],
    )


def _reference_mode_task() -> Task:
    """Reference-mode: a real source table IS supplied, so SDV competes on its turf.

    We synthesize a 'real' single table with a known monthly revenue curve, hand it to
    learned methods to train on, and give Misata only the SPEC derived from it
    (the two anchor months). We then measure conformance (AME) for everyone. SDV runs
    for real here; the expected story is SDV leads on fidelity context but scores poorly
    on AME because it imitates the cloud of points, not the declared target.
    """
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(7)
    # Build a real table whose Jan sum ~50k and Dec sum ~200k via row density.
    frames = []
    monthly = {1: 50_000.0, 6: 100_000.0, 12: 200_000.0}
    # fill all 12 months on a smooth ramp for a realistic 'real' dataset
    ramp = np.linspace(50_000, 200_000, 12)
    for i, total in enumerate(ramp, start=1):
        n = max(50, int(total / 150))
        vals = rng.lognormal(mean=np.log(150), sigma=0.5, size=n)
        vals *= total / vals.sum()            # make the month sum exact in the 'real' data
        dates = pd.to_datetime(f"2024-{i:02d}-01") + pd.to_timedelta(
            rng.integers(0, 27, size=n), unit="D")
        frames.append(pd.DataFrame({"amount": vals, "ordered_at": dates,
                                    "region": rng.choice(["N", "S", "E", "W"], size=n)}))
    real = pd.concat(frames, ignore_index=True)

    t = Task(
        task_id="revenue_reference_mode",
        mode="reference",
        # Ecommerce story so Misata parses a revenue curve onto orders.amount; the
        # supplied 'orders' reference table lets SDV train on real data of the same shape.
        story=("Ecommerce store with revenue $50k in January rising to $200k in December, "
               "2k orders"),
        rows=2000,
        metric_table="orders",
        metric_col="amount",
        time_col="ordered_at",
        period_freq="M",
        period_targets={"01": 50_000.0, "12": 200_000.0},
        primary_table="orders",
        schema_tables=[
            {"name": "orders", "pk": "order_id", "rows": len(real), "columns": [
                {"name": "amount", "kind": "metric", "scale": 150},
                {"name": "ordered_at", "kind": "date", "start": "2024-01-01", "span_days": 365},
                {"name": "region", "kind": "category", "choices": ["N", "S", "E", "W"]},
            ]},
        ],
        reference_tables={"orders": real},
    )
    return t


def seed_suite() -> List[Task]:
    """The minimal real suite needed for E5 + the Prop-5 curve."""
    return [_saas_curve_task(), _ecommerce_fk_task(), _reference_mode_task()]
