"""
Pydantic models for Misata configuration.

These models define the blueprint for synthetic data generation,
including tables, columns, relationships, and scenario events.
"""

import warnings
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class Column(BaseModel):
    """
    Defines a single column in a table.

    Attributes:
        name: Column name
        type: Data type (int, float, date, categorical, foreign_key, text)
        distribution_params: Parameters for data generation (mean, std, choices, etc.)
        nullable: Whether the column can contain NULL values
        unique: Whether values must be unique
    """

    name: str
    type: Literal["int", "float", "date", "time", "datetime", "categorical", "foreign_key", "text", "boolean"]
    distribution_params: Dict[str, Any] = Field(default_factory=dict, validate_default=True)
    nullable: bool = False
    unique: bool = False
    description: Optional[str] = None  # Human-readable context; used by LLM enrichment

    @staticmethod
    def _normalize_distribution_params(
        col_type: Optional[str],
        params: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Normalize common missing params so schema parsing stays forgiving."""
        normalized = dict(params or {})

        if col_type == "categorical":
            choices = normalized.get("choices")
            if not choices:
                warnings.warn(
                    "Categorical column missing 'choices'; using ['Unknown'] as a safe fallback.",
                    UserWarning,
                    stacklevel=3,
                )
                normalized["choices"] = ["Unknown"]
                normalized.setdefault("probabilities", [1.0])

        if col_type == "date" and "relative_to" not in normalized:
            # Fixed defaults guarantee reproducible generation regardless of run date.
            normalized.setdefault("start", "2020-01-01")
            normalized.setdefault("end", "2024-12-31")

        if col_type in ["int", "float"] and "distribution" not in normalized:
            normalized["distribution"] = "normal"
            normalized["_distribution_is_default"] = True  # sentinel: not user-set

        return normalized

    @field_validator("distribution_params", mode="before")
    @classmethod
    def validate_params(cls, v: Any, info: Any) -> Dict[str, Any]:
        """Validate distribution parameters based on column type."""
        col_type = info.data.get("type")
        return cls._normalize_distribution_params(col_type, v or {})

    def validate_generation_ready(self) -> None:
        """Raise if the column still lacks required information for generation."""
        if self.type == "categorical" and not self.distribution_params.get("choices"):
            raise ValueError(
                f"Column '{self.name}' is categorical but has no choices configured"
            )


class Table(BaseModel):
    """
    Defines a table to be generated.

    Tables can be either:
    - Reference tables: Small lookup tables with LLM-generated actual data (exercises, plans)
    - Transactional tables: Mass-generated tables using foreign keys to reference tables

    Attributes:
        name: Table name
        row_count: Number of rows to generate (ignored if inline_data is provided)
        description: Optional description of the table's purpose
        is_reference: If True, this is a lookup/reference table
        inline_data: Actual data rows for reference tables (list of dicts)
    """

    name: str
    # ge=0: 0 is a valid (empty) table; only negative counts are rejected.
    row_count: int = Field(default=100, ge=0)
    description: Optional[str] = None
    is_reference: bool = False
    inline_data: Optional[List[Dict[str, Any]]] = None
    columns: List[str] = Field(default_factory=list)
    constraints: List["Constraint"] = Field(default_factory=list)
    workflow_preset: Optional[str] = None
    workflow_config: Optional[Dict[str, Any]] = None
    # Set when this table lives in another schema and is owned by something
    # else: Supabase's `auth.users` is the motivating case. Such a table is
    # read so its children can reference real rows, and never written to.
    external_schema: Optional[str] = None
    correlations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Pairwise Pearson correlations to enforce between numeric columns after generation. "
            "Each entry: {col_a: str, col_b: str, r: float}  where r ∈ [-1, 1]."
        ),
    )
    state_machine: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Markov state machine that assigns a terminal status to every row. "
            "Keys: state_column, initial_state, transitions (dict of state → {next_state: prob})."
        ),
    )
    scd2: Optional["SCD2Config"] = Field(
        default=None,
        description=(
            "Slowly-changing-dimension (type 2) declaration: per entity, "
            "valid_from/valid_to tile without gaps or overlaps and exactly "
            "one version is current."
        ),
    )
    cluster_effect: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Hierarchical random intercepts (ICC) applied to child table columns. "
            "Keys: affects_table (str), affects_columns (dict of col_name → {icc: float, sd_between: float})."
        ),
    )


class Relationship(BaseModel):
    """
    Defines a parent-child relationship between tables.

    Ensures referential integrity by constraining child foreign keys
    to existing parent primary keys.

    Attributes:
        parent_table: Name of the parent table
        child_table: Name of the child table
        parent_key: Column name in parent table (usually primary key)
        child_key: Column name in child table (foreign key)
        temporal_constraint: If True, child events must occur after parent events
    """

    parent_table: str
    child_table: str
    parent_key: str
    child_key: str
    temporal_constraint: bool = False
    filters: Optional[Dict[str, Any]] = None  # e.g., {"status": "active"} — a
    # list value means membership: {"status": ["shipped", "completed"]}
    # Temporal eligibility: a child may only reference a parent that already
    # existed. An order line cannot contain a product created after the order
    # was placed, which is the Gauntlet's longest-standing known-red.
    # `parent_time` is the parent's creation timestamp. The child's effective
    # time is `child_time`, read from the child itself, or from
    # `child_time_table` when the moment that matters belongs to another parent
    # (an order line inherits its order's date, not one of its own).
    parent_time: Optional[str] = None
    child_time: Optional[str] = None
    child_time_table: Optional[str] = None
    # Partition isolation: the key must resolve to a parent that agrees with the
    # child on every one of these columns. Multi-tenancy is the usual reason
    # (`partition_by=["tenant_id"]`), and it is the same idea as the `partition
    # by` a window function needs: a value that crosses the boundary is not
    # merely unrealistic, it is a leak. Named after the SQL clause on purpose,
    # because the bug this prevents is the one a missing `partition by` causes.
    # The columns must exist on BOTH tables, and the child's copy must be
    # generated before this key, which column order already guarantees.
    partition_by: List[str] = Field(default_factory=list)
    min_children: int = 0  # every (eligible) parent gets at least this many
    # child rows. An order with zero line items does not exist in real data;
    # min_children=1 on orders→order_items guarantees coverage. Only honoured
    # when the child row_count can actually cover the parents; the shortfall
    # warns rather than silently inventing extra rows.


class Constraint(BaseModel):
    """
    Defines a business rule constraint to enforce during generation.

    Constraints are applied after generating a batch to ensure data
    adheres to real-world business rules.

    Attributes:
        name: Descriptive name of the constraint
        type: Type of constraint (max_per_group, min_per_group, unique_combination, sum_limit)
        group_by: List of columns to group by (e.g., ["employee_id", "date"])
        column: The column to constrain
        value: The constraint value (e.g., 8 for max 8 hours)
        action: What to do when constraint is violated (cap, redistribute, error)

    Examples:
        # Max 8 hours per employee per day
        Constraint(
            name="max_daily_hours",
            type="max_per_group",
            group_by=["employee_id", "date"],
            column="hours",
            value=8,
            action="cap"
        )

        # Each employee-project-date combination must be unique
        Constraint(
            name="unique_timesheet_entry",
            type="unique_combination",
            group_by=["employee_id", "project_id", "date"],
            action="drop"
        )
    """

    name: str
    type: Literal[
        "max_per_group",
        "min_per_group",
        "sum_limit",
        "unique_combination",
        "inequality",     # col_a OP col_b  (e.g. price > cost)
        "col_range",      # low_col <= col <= high_col
        "balanced_ledger",  # per group: sum(debit) == sum(credit), exactly
        "when_then",      # if when_column OP when_value then a rule on then_column
        "lte_parent",     # child column <= a column on its FK parent, row by row
        "sum_lte_parent",  # per parent: sum of child column <= parent column
    ]
    group_by: List[str] = Field(default_factory=list)
    column: Optional[str] = None
    value: Optional[float] = None
    action: Literal["cap", "redistribute", "drop", "error"] = "cap"
    # inequality fields
    column_a: Optional[str] = None
    operator: Optional[Literal[">", ">=", "<", "<="]] = None
    column_b: Optional[str] = None
    # col_range fields
    low_column: Optional[str] = None
    high_column: Optional[str] = None
    # balanced_ledger fields: double-entry accounting invariant. Each group
    # (a journal entry) is forced to sum(debit_column) == sum(credit_column)
    # exactly. Lines are first made one-sided (a ledger line is a debit OR a
    # credit, never both), then each side is scaled to a shared per-entry
    # total and the rounding residual is absorbed by the largest line so the
    # equality holds to the cent.
    debit_column: Optional[str] = None
    credit_column: Optional[str] = None
    decimals: int = 2
    # when_then fields: a status gates its dependent columns. The single most
    # common realism failure in relational data — an "active" subscription with
    # a cancellation date, an "open" ticket with a resolved_at — is a violated
    # implication nobody declared. Declaring it:
    #   Constraint(type="when_then", when_column="status", when_op="in",
    #              when_value=["active", "past_due"],
    #              then_column="cancelled_at", then="null")
    # `then` semantics: "null" forces then_column to NULL where the condition
    # holds; "not_null" fills missing values there (from then_value when given,
    # else by sampling the column's own non-null values so the fill matches the
    # column's real distribution); "set" writes then_value outright.
    when_column: Optional[str] = None
    when_op: Literal["==", "!=", "in", "not_in", ">", ">=", "<", "<="] = "=="
    when_value: Optional[Any] = None
    then_column: Optional[str] = None
    then: Optional[Literal["null", "not_null", "set"]] = None
    then_value: Optional[Any] = None
    # lte_parent / sum_lte_parent fields: declared on the CHILD table. The fk
    # is resolved from the declared relationship between the two tables.
    #   returns.refund_amount <= its order's total_amount:
    #     Constraint(type="lte_parent", column="refund_amount",
    #                parent_table="orders", parent_column="total_amount")
    #   payments for one order never exceed the order's total:
    #     Constraint(type="sum_lte_parent", column="amount",
    #                parent_table="orders", parent_column="total_amount")
    # Enforced with action="cap": lte_parent clamps each row; sum_lte_parent
    # rescales a parent's child rows proportionally when their sum overshoots.
    parent_table: Optional[str] = None
    parent_column: Optional[str] = None


class ScenarioEvent(BaseModel):
    """
    Defines a time-based or conditional modifier to apply to data.

    This is the "story" layer - events that force data to follow
    specific patterns (growth, crashes, seasonality, etc.).

    Attributes:
        name: Descriptive name of the event
        table: Table to apply the event to
        column: Column to modify
        condition: Python expression evaluated on the DataFrame (e.g., "date > '2023-11-01'")
        modifier_type: Type of modification (multiply, add, set, function)
        modifier_value: Value or function to apply
        description: Optional description of what this event represents

    Examples:
        # Revenue crash
        ScenarioEvent(
            name="Q3_Revenue_Crash",
            table="sales",
            column="revenue",
            condition="date >= '2023-07-01' and date < '2023-10-01'",
            modifier_type="multiply",
            modifier_value=0.5
        )

        # Set all churned users
        ScenarioEvent(
            name="Churn_Flag",
            table="users",
            column="churned",
            condition="signup_date < '2023-06-01'",
            modifier_type="set",
            modifier_value=True
        )
    """

    name: str
    table: str
    column: str
    condition: str
    modifier_type: Literal["multiply", "add", "set", "function"]
    modifier_value: Union[int, float, str, bool]
    description: Optional[str] = None
    # Cascade: propagate the affected parent-row IDs into child tables.
    # Each entry maps child_table -> {column: value} to apply on matched children.
    # Example: propagate_to={"subscriptions": {"status": "cancelled"}}
    propagate_to: Optional[Dict[str, Dict[str, Any]]] = None


class OutcomeCurve(BaseModel):
    """
    Defines a temporal/seasonal pattern for a numeric column.
    
    This is extracted from natural language descriptions like:
    "Revenue with a dip in September and peak in December"
    
    Attributes:
        table: Table containing the column to constrain
        column: Numeric column to apply the curve to
        time_column: Date/time column for grouping
        pattern_type: Type of pattern (seasonal, growth, decline, etc.)
        description: Human-readable description of the pattern
        time_unit: Bucket size for the constraint
        value_mode: Whether points are relative multipliers or exact targets
        avg_transaction_value: Optional average amount used to derive row counts
        curve_points: Relative or exact per-period values
    """
    table: str
    column: str
    time_column: str = "date"
    time_unit: Literal["day", "week", "month"] = "month"
    pattern_type: str = "seasonal"
    intra_period_pattern: Literal["uniform", "weekday_heavy", "weekend_heavy", "start_heavy", "end_heavy"] = "uniform"
    value_mode: Literal["auto", "relative", "absolute"] = "auto"
    description: Optional[str] = None
    avg_transaction_value: Optional[float] = None
    min_transactions_per_period: int = 1
    max_transactions_per_period: int = 10000
    concentration: float = 2.0
    start_date: Optional[str] = None
    curve_points: List[Dict[str, Any]] = Field(default_factory=list)


class RateCurve(BaseModel):
    """Declares an exact rate target for a boolean or categorical column per period.

    This covers the rate-conformance (RCE) axis from the SpecBench paper —
    orthogonal to the aggregate (AME) axis captured by ``OutcomeCurve``.

    Example — exactly 3% fraud in Q1 rising to 5% by Q4::

        RateCurve(
            table="transactions",
            column="is_fraud",
            time_column="transaction_date",
            time_unit="month",
            rate_points=[
                {"period": "2024-01", "rate": 0.03},
                {"period": "2024-06", "rate": 0.04},
                {"period": "2024-12", "rate": 0.05},
            ],
        )

    Attributes:
        table:        Table containing the column to constrain.
        column:       Boolean or categorical column to set the rate on.
        time_column:  Date/time column used to bucket rows into periods.
        time_unit:    Granularity of each period bucket.
        true_value:   The value counted as the "positive" class (default ``True``).
        interpolate:  When True, rates between declared anchor points are
                      linearly interpolated. When False, only declared periods
                      are constrained and the rest are left at their generated
                      distribution.
        description:  Human-readable description of what this rate curve models.
        rate_points:  List of ``{"period": "YYYY-MM", "rate": 0.03}`` dicts.
                      ``period`` accepts ``"YYYY-MM"`` (month), ``"YYYY-Qn"``
                      (quarter), or an integer month index.
    """

    table: str
    column: str
    time_column: str = "date"
    time_unit: Literal["day", "week", "month", "quarter"] = "month"
    true_value: Any = True
    interpolate: bool = True
    description: Optional[str] = None
    rate_points: List[Dict[str, Any]] = Field(default_factory=list)


class CohortRetention(BaseModel):
    """Declare a retention curve, and have the cohort table actually show it.

    "Of the customers who signed up in month M, 55% place an order in M+1 and
    40% in M+2" is the most-quoted invariant in SaaS and ecommerce analytics,
    and until now it was inexpressible here: you could control how many events
    existed and what they summed to, but not *which* entities produced them
    over time. So the cohort query every analyst runs first returned a shape
    nobody chose.

    Declaring it makes the cohort table exact. For every cohort period and
    every declared offset k, exactly ``round(fraction × cohort_size)`` distinct
    entities have at least one event in period ``cohort + k``.

    This governs the event table's entity key and its timestamp, because those
    are what a retention query reads. Every other column is left alone.

    Example, a cohort that halves then flattens::

        CohortRetention(
            table="orders", event_time="order_date", cohort_key="customer_id",
            cohort_table="customers", cohort_time="signup_date",
            unit="month",
            curve={0: 1.0, 1: 0.55, 2: 0.40, 3: 0.34},
        )

    Attributes:
        table:        Event table whose rows are the activity.
        event_time:   Timestamp column on the event table.
        cohort_key:   Entity key present on both tables.
        cohort_table: Entity table that defines cohort membership.
        cohort_time:  Timestamp on the entity table that assigns its cohort.
        unit:         Period granularity for both cohort and offset.
        curve:        Offset (0 = the cohort's own period) to fraction of the
                      cohort active in that period. Offset 0 is normally 1.0.
                      Fractions must each be between 0 and 1.
    """

    table: str
    event_time: str
    cohort_key: str
    cohort_table: str
    cohort_time: str
    unit: Literal["day", "week", "month"] = "month"
    curve: Dict[int, float]
    description: Optional[str] = None

    @field_validator("curve")
    @classmethod
    def _fractions_in_range(cls, v: Dict[int, float]) -> Dict[int, float]:
        if not v:
            raise ValueError("CohortRetention.curve needs at least one offset")
        for k, frac in v.items():
            if int(k) < 0:
                raise ValueError(f"retention offset {k} cannot be negative")
            if not 0.0 <= float(frac) <= 1.0:
                raise ValueError(
                    f"retention fraction for offset {k} is {frac}; a share of a "
                    f"cohort must be between 0 and 1"
                )
        return v


class Missingness(BaseModel):
    """Declare *why* values are missing, not just how often.

    Real data is missing for a reason. Income is absent more often for younger
    users; a satisfaction score is absent when nobody replied. That is MNAR
    (missing not at random), and it is what breaks models and pipelines in
    production. A flat ``null_rate`` produces MCAR, which is the one pattern
    real data almost never has.

    Declaring the mechanism makes the pattern exact: of the rows matching the
    condition, exactly ``rate`` are null; of the rest, exactly ``else_rate``.
    Counts use largest-remainder rounding, so a declared 40% is 40% of rows
    rather than 40% in expectation.

    Example, income missing far more often for the youngest band::

        Missingness(
            table="customers", column="income", rate=0.40, else_rate=0.05,
            when_column="age_band", when_op="in", when_value=["18-24"],
        )

    Omit the condition for a plain unconditional rate.

    Attributes:
        table, column: What goes missing.
        rate:          Fraction of matching rows set to NULL.
        else_rate:     Fraction of non-matching rows set to NULL.
        when_column, when_op, when_value: The condition selecting rows. When
                       ``when_column`` is omitted, ``rate`` applies to the whole
                       column and ``else_rate`` is ignored.
    """

    table: str
    column: str
    rate: float = Field(ge=0.0, le=1.0)
    else_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    when_column: Optional[str] = None
    when_op: Literal["==", "!=", "in", "not_in", ">", ">=", "<", "<="] = "=="
    when_value: Optional[Any] = None
    description: Optional[str] = None


class LateArrival(BaseModel):
    """Declare that some events land after the fact.

    Every incremental model and every watermark assumes events arrive roughly
    in order, and production quietly violates it: a mobile client syncs three
    days later, a webhook retries, a batch job backfills. No generator produces
    that, so the code path that handles it is never exercised until it fails on
    real data.

    Declaring it gives an ingest timestamp that is always at or after the event
    timestamp, where exactly ``late_fraction`` of rows arrive in a *later*
    period than the event, with delays bounded by ``max_delay_days``.

    Example, 5% of events landing up to three days late::

        LateArrival(
            table="events", event_time="occurred_at",
            ingest_time="ingested_at",
            late_fraction=0.05, max_delay_days=3,
        )

    Attributes:
        table:          Event table.
        event_time:     When it happened. Never modified.
        ingest_time:    When it was recorded. Written by this declaration.
        late_fraction:  Fraction of rows whose ingest lands a full day or more
                        after the event.
        max_delay_days: Upper bound on the delay for those rows.
        on_time_max_minutes: Upper bound on the delay for everything else, so
                        punctual rows still are not simultaneous.
    """

    table: str
    event_time: str
    ingest_time: str
    late_fraction: float = Field(default=0.05, ge=0.0, le=1.0)
    max_delay_days: int = Field(default=3, ge=1)
    on_time_max_minutes: int = Field(default=120, ge=1)
    description: Optional[str] = None


class GroupShares(BaseModel):
    """Declare exact shares of a measure across the values of a categorical
    column: "Electronics is 40% of revenue, Home 25%".

    Paired with an :class:`OutcomeCurve` on the same table and measure, the
    shares hold exactly within every declared period (the period target is
    split by the shares, so the group totals are fully declared, not
    measured). Without a curve, the shares hold exactly over the table's
    total.

    Attributes:
        table:        Fact table carrying the measure.
        measure:      Numeric column whose total is split.
        group_column: Categorical column defining the groups. Its values are
                      overwritten so the declared shares hold.
        shares:       Mapping of group label to fraction. Must sum to ~1;
                      a small deviation is normalised with a warning.
    """

    table: str
    measure: str
    group_column: str
    shares: Dict[str, float]
    description: Optional[str] = None


class LifecycleState(BaseModel):
    """One state an entity can occupy, and the column that records entering it.

    Attributes:
        name:      The value that appears in the lifecycle's ``state_column``.
        timestamp: Optional column recording when the entity entered this
                   state. When given, the column is NOT NULL for entities whose
                   path reached this state and NULL for every entity that did
                   not. Omit for states you do not timestamp.
        terminal:  True when no transition leaves this state.
    """

    name: str
    timestamp: Optional[str] = None
    terminal: bool = False


class Lifecycle(BaseModel):
    """Declare the state machine an entity moves through, and prove it held.

    A status column plus a scatter of per-state timestamps is the most common
    shape in real operational data, and the most commonly wrong: an "active"
    subscription carrying a cancellation date, a "cancelled" order with a
    delivery time, a "shipped" row whose ship date precedes its order date.
    Those are all the same defect — a row whose columns describe a history
    that could not have happened.

    Declaring the machine makes the whole class impossible. For a row in state
    S, the engine derives the path from ``initial`` to S and guarantees:

    1. ``state_column`` only ever holds a declared state name.
    2. Every state on the path has its timestamp populated, in path order.
    3. Every state off the path has its timestamp NULL.
    4. The whole chain postdates ``start_column`` when one is given.

    This subsumes hand-written ``when_then`` rules and status gating: instead
    of enumerating "if cancelled then cancelled_at is not null" for every pair,
    you declare the machine once and every implication follows from it.

    Example, an order that ships then completes, or is cancelled outright::

        Lifecycle(
            name="order_lifecycle",
            table="orders",
            state_column="status",
            start_column="order_date",
            initial="placed",
            states=[
                LifecycleState(name="placed",    timestamp="placed_at"),
                LifecycleState(name="shipped",   timestamp="shipped_at"),
                LifecycleState(name="completed", timestamp="completed_at", terminal=True),
                LifecycleState(name="cancelled", timestamp="cancelled_at", terminal=True),
            ],
            transitions=[
                ("placed", "shipped"),
                ("shipped", "completed"),
                ("placed", "cancelled"),
            ],
            weights={"placed": 0.10, "shipped": 0.15,
                     "completed": 0.60, "cancelled": 0.15},
        )

    Attributes:
        name:         Identifier used in warnings and audit findings.
        table:        Table whose rows are the entities.
        state_column: Column holding the entity's current state.
        states:       Every reachable state. Names must be unique.
        transitions:  Legal (from_state, to_state) pairs.
        initial:      The state every entity starts in.
        weights:      Optional share of rows to place in each state. Normalised
                      with a warning if the values do not sum to 1. States
                      omitted get zero rows. Defaults to uniform over states
                      that are reachable.
        start_column: Optional existing timestamp the whole chain must postdate
                      (an order's ``order_date``, a customer's ``signup_date``).
        max_days_per_step: Upper bound on the gap between consecutive state
                      timestamps, so a shipped-to-completed hop stays plausible.
    """

    name: str
    table: str
    state_column: str
    states: List[LifecycleState]
    transitions: List[Tuple[str, str]] = Field(default_factory=list)
    initial: Optional[str] = None
    weights: Optional[Dict[str, float]] = None
    start_column: Optional[str] = None
    max_days_per_step: int = 30
    description: Optional[str] = None

    @field_validator("states")
    @classmethod
    def _unique_state_names(cls, v: List["LifecycleState"]) -> List["LifecycleState"]:
        names = [s.name for s in v]
        if len(names) != len(set(names)):
            raise ValueError("Lifecycle state names must be unique")
        if not names:
            raise ValueError("Lifecycle needs at least one state")
        return v

    def state_names(self) -> List[str]:
        return [s.name for s in self.states]

    def timestamp_of(self, state: str) -> Optional[str]:
        for s in self.states:
            if s.name == state:
                return s.timestamp
        return None

    def timestamp_columns(self) -> List[str]:
        return [s.timestamp for s in self.states if s.timestamp]

    def path_to(self, target: str) -> Optional[List[str]]:
        """Shortest legal path from ``initial`` to ``target``.

        Returns None when the target is unreachable, which the caller reports
        rather than silently generating an impossible row. Breadth-first, so
        the path chosen is the shortest one; a state reachable two ways gets
        the direct route.
        """
        start = self.initial or (self.states[0].name if self.states else None)
        if start is None:
            return None
        if target == start:
            return [start]
        adjacency: Dict[str, List[str]] = {}
        for a, b in self.transitions:
            adjacency.setdefault(a, []).append(b)
        queue: List[List[str]] = [[start]]
        seen = {start}
        while queue:
            path = queue.pop(0)
            for nxt in adjacency.get(path[-1], []):
                if nxt in seen:
                    continue
                if nxt == target:
                    return path + [nxt]
                seen.add(nxt)
                queue.append(path + [nxt])
        return None


class EventLog(BaseModel):
    """An entity's state implies exactly which events its log contains.

    ``lifecycles`` made a status column trustworthy: a row in state S carries
    the timestamps of every state on the path to S, and nulls elsewhere. In an
    event-sourced system the same fact lives in a child table instead, and
    nothing tied the two together. The Warren suite measured the result: 602
    done tasks with no completion event, 332 open tasks that had somehow been
    completed, and 667 completion events that happened before work started.

    This is the same guarantee, projected onto the log. For each entity, the
    lifecycle already knows the ordered path its state implies. ``state_events``
    names the event type that records arriving at each state, and afterwards:

    * every state on the entity's path with a mapped event type has exactly one
      such event,
    * no event names a state the entity never reached,
    * those events ascend in path order, and agree with the entity's own
      timestamps where the lifecycle wrote them.

    Rows left over after the required events are filler, drawn only from event
    types that are legal for that entity. Costs: the whole event table is
    rewritten, so it needs at least one row per required event, and refuses
    with the arithmetic when it does not have them.
    """

    name: str
    table: str                      # the event table
    entity_table: str               # whose lifecycle the log explains
    entity_key: str                 # FK on the event table
    event_type_column: str
    event_time_column: str
    # state name -> the event type that records entering it
    state_events: Dict[str, str]
    # event types that may appear any number of times, in any order, as long as
    # the entity actually reached the state they belong to
    filler_events: List[str] = Field(default_factory=list)


class SensorResponse(BaseModel):
    """How one measurement responds as a unit accumulates damage.

    Damage runs 0 at commissioning to 1 at failure. `baseline` is the healthy
    reading and `at_failure` the reading the instant before it fails; what
    happens between them is the `shape`.

    Attributes:
        column: The measurement column.
        baseline: Reading at damage 0.
        at_failure: Reading at damage 1.
        shape: "linear" tracks damage directly. "exponential" stays flat and
            then climbs late, which is what a vibration RMS does as a spall
            opens up. "sqrt" moves early and then flattens.
        noise: Standard deviation of the measurement noise on top.
        decimals: Rounding, so a column reads like an instrument rather than
            like a float.
    """

    column: str
    baseline: float
    at_failure: float
    shape: Literal["linear", "exponential", "sqrt"] = "linear"
    noise: float = 0.0
    decimals: int = 3
    # Some measurements physically cannot fall. Accumulated tool wear is the
    # obvious one: material does not come back. Measurement noise alone made
    # wear decrease on a third of consecutive readings, which is the exact
    # criticism levelled at AI4I, so a cumulative quantity has to say it is one.
    monotonic: bool = False


class FailureMode(BaseModel):
    """A named way a unit fails, and what it does to the measurements.

    A mode that only labels the last row is decorative: a heat-dissipation
    failure that runs no hotter than a power failure tells a reader nothing and
    tells a model less. `accentuates` scales how far a named measurement travels
    for units failing this way, so the mode has a signature you can actually
    diagnose.

    Attributes:
        weight: Relative share of units failing this way.
        accentuates: column name -> multiplier on that column's damage response.
            1.0 leaves it alone; 2.0 sends it twice as far by failure.
    """

    weight: float = 1.0
    accentuates: Dict[str, float] = Field(default_factory=dict)


class Degradation(BaseModel):
    """Declare that units wear out, and when.

    Every other primitive here draws each row independently, which is correct
    for orders and payments and wrong for equipment: a machine has a history.
    Its wear accumulates, its measurements drift, and it eventually fails. A
    dataset without that has nothing to predict, which is the standing
    criticism of the public predictive-maintenance datasets, where tool wear is
    as likely to fall as to rise between consecutive readings.

    The declaration is the **failure time**. Each unit draws a life from
    `life_mean`/`life_std`, damage accumulates toward it, and the sensors follow
    the damage. Remaining useful life is therefore exact by construction rather
    than annotated afterwards, which is the property that makes the label worth
    training on.

    One row per (unit, cycle) is generated, replacing the table's row_count:
    the number of rows is the sum of the drawn lives, because a unit that lives
    300 cycles has 300 readings.

    Attributes:
        table: Table receiving one row per unit per cycle.
        unit_column / cycle_column: Identity and the cycle index within a unit.
        units: How many units in the fleet.
        life_mean / life_std / life_min / life_max: The life distribution.
            Unit-to-unit spread is what makes remaining life learnable rather
            than a constant.
        damage_exponent: Damage is (cycle/life) ** exponent. Above 1 the last
            stretch degrades fastest, which is how wear behaves.
        rul_column / damage_column: Where the exact labels are written.
        failure_column: 1 on a unit's final cycle, 0 elsewhere.
        failure_mode_column / failure_modes: Optional named modes with weights.
        responses: Measurements that follow the damage.
    """

    table: str
    unit_column: str = "unit_id"
    cycle_column: str = "cycle"
    units: int = 100
    life_mean: float = 220.0
    life_std: float = 45.0
    life_min: int = 20
    life_max: int = 1000
    damage_exponent: float = 1.3
    rul_column: str = "rul_cycles"
    damage_column: Optional[str] = "damage"
    failure_column: str = "machine_failure"
    failure_mode_column: Optional[str] = None
    # Either {"name": weight} or {"name": {"weight": w, "accentuates": {...}}}.
    # The plain form stays valid; the second gives the mode a signature.
    failure_modes: Dict[str, Union[float, FailureMode]] = Field(default_factory=dict)
    # Units are not identical. Each draws its own multiplier per response, so
    # the fleet is a population rather than one machine repeated: without it
    # every sensor is the same deterministic function of damage and they come
    # out near-collinear, which makes the data far easier than any real fleet.
    unit_variation: float = 0.10
    responses: List[SensorResponse] = Field(default_factory=list)
    description: Optional[str] = None


class StockFlowIdentity(BaseModel):
    """Declare an inventory table whose stock ledger reconciles to the unit.

    One row per (SKU, period). Two identities hold on every row and every
    consecutive pair, by construction:

        closing = opening + received - shipped        (within the row)
        opening of period t+1 = closing of period t   (across the chain)

    Shipments never exceed available stock, so no level ever goes negative.
    The trajectories themselves are generated, not declared, so evalpacks
    ship no questions from this identity (their answers would be measured,
    which the answer-key-first construction forbids); the story audit
    recomputes both identities instead.

    Attributes:
        table: Inventory movements table (one row per SKU per period).
        sku_column: Column identifying the SKU.
        period_column: Column carrying the period label.
        open_column / received_column / shipped_column / close_column:
            The four quantity columns of the ledger.
        periods: Ordered period labels (e.g. ["2025-01", ..., "2025-06"]).
        starting_min / starting_max: Range for each SKU's initial stock.
    """

    table: str
    sku_column: str = "sku"
    period_column: str = "period"
    open_column: str = "opening_stock"
    received_column: str = "received"
    shipped_column: str = "shipped"
    close_column: str = "closing_stock"
    periods: List[str]
    starting_min: int = 50
    starting_max: int = 500
    description: Optional[str] = None


class SCD2Config(BaseModel):
    """Declare a table as a slowly-changing-dimension (type 2) history.

    Every entity's versions tile time without gaps or overlaps: each row's
    ``valid_to`` equals the next version's ``valid_from``, exactly one row per
    entity is current, and the last version is open-ended (or closes at the
    window end). Data warehouses live on this shape; generated naively it is
    always wrong.

    Attributes:
        entity_column: Column identifying the entity whose history this is.
        valid_from: Timestamp column opening each version.
        valid_to: Timestamp column closing each version (empty on the open
            last version when ``open_ended``).
        current_flag: Optional boolean column, true only on the last version.
        avg_versions: Average versions per entity (the table's rows are
            distributed over ``row_count / avg_versions`` entities).
        start: History window start (defaults to the valid_from column's
            declared start, else 2020-01-01).
        end: History window end (defaults to the valid_from column's declared
            end, else 2024-12-31).
        open_ended: Last version's valid_to stays empty when true; closes at
            the window end when false.
    """

    entity_column: str
    valid_from: str = "valid_from"
    valid_to: str = "valid_to"
    current_flag: Optional[str] = None
    avg_versions: float = 3.0
    start: Optional[str] = None
    end: Optional[str] = None
    open_ended: bool = True


class WaterfallIdentity(BaseModel):
    """Declare a movements table whose rows reconcile to per-period balances.

    "MRR starts at 100k, ends January at 112k, February at 118k" becomes rows
    of new/expansion/contraction/churn whose signed sum per period equals the
    period's declared delta exactly, so the running balance recomputed from
    the raw rows hits every declared ending value.

    Attributes:
        table: Movements table the identity applies to.
        period_column: Column carrying the period label (e.g. "2025-01").
        type_column: Column carrying the movement type.
        amount_column: Numeric column carrying the (positive) movement amount.
        starting_value: Balance before the first declared period.
        points: Ordered per-period declarations:
            ``[{"period": "2025-01", "ending_value": 112000.0}, ...]``.
        inflow_shares: How gross inflow splits across inflow types.
        outflow_shares: How gross outflow splits across outflow types.
        outflow_rate: Gross outflow per period as a fraction of the previous
            balance (real books always churn something, even in a growth
            month). Raised automatically when a declared decline needs more.
    """

    table: str
    period_column: str = "period"
    type_column: str = "movement_type"
    amount_column: str = "amount"
    starting_value: float
    points: List[Dict[str, Any]]
    inflow_shares: Dict[str, float] = Field(
        default_factory=lambda: {"new": 0.65, "expansion": 0.35})
    outflow_shares: Dict[str, float] = Field(
        default_factory=lambda: {"churn": 0.7, "contraction": 0.3})
    outflow_rate: float = 0.03
    # Segment scoping: one movements table can carry several waterfalls, one
    # per segment value ("each tenant has its own declared MRR trajectory").
    # All specs sharing a table must use the same segment_column with
    # distinct segment_values; the pass writes the segment column too.
    segment_column: Optional[str] = None
    segment_value: Optional[str] = None
    description: Optional[str] = None


class NoiseConfig(BaseModel):
    """
    Configuration for optional realism noise injection.

    Modes:
    - off: disable all noise
    - ml_training: allow broad imperfections for ML robustness
    - analytics_safe: only mutate non-protected columns and never duplicate rows
    - custom: user-directed noise with optional protected columns
    """

    mode: Literal["off", "ml_training", "analytics_safe", "custom"] = "custom"
    null_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    outlier_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    typo_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    duplicate_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    null_columns: Optional[List[str]] = None
    outlier_columns: Optional[List[str]] = None
    typo_columns: Optional[List[str]] = None
    protected_columns: List[str] = Field(default_factory=list)
    exact_duplicates: bool = True


class TimeGrid(BaseModel):
    """A timestamp column lands on a declared grid, in declared hours.

    Misata has shaped timestamps by name-guess since early on: a column called
    ``appointment_time`` was snapped to quarter hours inside business hours
    because that is what appointments do. The guess is usually right and it is
    the single biggest tell that separates plausible timestamps from
    ``2022-08-29 06:36:12.995319155``. But a guess is not a guarantee: it was
    never declarable, never overridable, and never checked.

    ``TimeGrid`` is the declared form. The inference stays as a default; this
    is what you write when the grid matters and you want it proven. Only the
    time of day is touched, never the date, so no causal ordering between
    tables can be disturbed by asking for tidier clocks.

    Attributes:
        minute_grid: every value falls on a multiple of this many minutes.
        seconds: ``"zero"`` for a clean grid, ``"uniform"`` to keep seconds.
        hours: inclusive-exclusive local hour window, e.g. ``(9, 17)``.
    """

    table: str
    column: str
    minute_grid: int = Field(default=15, ge=1, le=1440)
    seconds: Literal["zero", "uniform"] = "zero"
    hours: Optional[Tuple[int, int]] = None

    @field_validator("hours")
    @classmethod
    def validate_hours(cls, v: Optional[Tuple[int, int]]) -> Optional[Tuple[int, int]]:
        if v is None:
            return v
        lo, hi = int(v[0]), int(v[1])
        if not (0 <= lo < hi <= 24):
            raise ValueError(
                f"hours must be a window 0 <= start < end <= 24, got ({lo}, {hi})")
        return (lo, hi)


class Duplicates(BaseModel):
    """Exactly this many rows are duplicates of another row.

    Deduplication is the most-written and least-tested logic in any pipeline,
    and it cannot be tested against data with no duplicates in it. The old
    ``noise_config.duplicate_rate`` sprayed copies at a probability and told you
    nothing afterwards, so a test written against it could not assert a number.

    The declared form is a count. Rows are not appended, they are overwritten:
    ``keys`` stay distinct and the row count never moves, which is what a real
    re-ingest looks like — the same record arriving twice under two surrogate
    keys. After generation, ``len(table) - len(table[subset].drop_duplicates())``
    equals exactly what you declared.

    Costs: duplicates are real rows, so any aggregate over ``table`` counts them.
    Declare this on a table that no roll-up or curve reconciles against, or
    expect those totals to include the copies, because they genuinely do.
    """

    table: str
    count: Optional[int] = None
    fraction: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    subset: Optional[List[str]] = None   # columns compared; default: all but keys
    keys: List[str] = Field(default_factory=list)  # stay distinct (surrogate PKs)

    @model_validator(mode="after")
    def validate_one_of(self) -> "Duplicates":
        # A field validator on `fraction` never fires when the field is simply
        # absent, which is exactly the case this needs to catch.
        if self.count is None and self.fraction is None:
            raise ValueError("Duplicates needs either 'count' or 'fraction'")
        return self


class Outliers(BaseModel):
    """Exactly this many rows are outliers, at a declared distance.

    ``noise_config.outlier_rate`` sprayed extreme values at a probability and
    told you nothing afterwards, so a test written against it could assert
    nothing. An anomaly detector evaluated on that data has no answer key.

    The declared form is a count and a distance, both measured with median and
    MAD rather than mean and standard deviation. That matters: outliers inflate
    the standard deviation they are measured against, so a mean-based threshold
    moves as you add them and the guarantee stops being checkable. Median and
    MAD do not move, so ``coherence_audit`` recomputes the same number from the
    emitted rows that the generator used to write them.
    """

    table: str
    column: str
    count: Optional[int] = None
    fraction: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    sigma: float = Field(default=6.0, gt=0.0)   # robust deviations from median
    direction: Literal["both", "high", "low"] = "both"

    @model_validator(mode="after")
    def validate_one_of(self) -> "Outliers":
        if self.count is None and self.fraction is None:
            raise ValueError("Outliers needs either 'count' or 'fraction'")
        return self


class Typos(BaseModel):
    """Exactly this many values are corrupted versions of a legal value.

    Fuzzy matching, deduplication and validation logic all need dirty input to
    be tested, and all of it is untestable against data whose every value is
    clean. ``noise_config.typo_rate`` produced dirt at a probability; this
    produces a known number of it.

    Restricted to columns with a declared ``choices`` set, because that is what
    makes the result verifiable: afterwards, exactly ``count`` values are NOT
    members of the declared vocabulary, and the audit checks precisely that. A
    typo in a free-text column is unfalsifiable, so the declaration refuses it
    rather than pretending.
    """

    table: str
    column: str
    count: Optional[int] = None
    fraction: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_one_of(self) -> "Typos":
        if self.count is None and self.fraction is None:
            raise ValueError("Typos needs either 'count' or 'fraction'")
        return self


class Bitemporal(BaseModel):
    """A fact with two independent time axes: when it was true, and when we knew.

    ``scd2`` tiles ONE axis. Bitemporal data has two, and they are genuinely
    independent: a correction recorded today can change what was true last
    March, without destroying the record of what we believed in between. That is
    the whole point of the shape, and "as of last Tuesday, what did we think the
    position was?" is the query it exists to answer.

    After generation, per entity:

    * exactly one row is current in system time (``superseded_at`` is null), and
      that row leaves valid time open,
    * system time tiles: every ``superseded_at`` equals the ``recorded_at`` of
      the version that replaced it, with no gap and no overlap,
    * an as-of query at any instant returns exactly one row per entity,
    * ``valid_to > valid_from`` and ``superseded_at > recorded_at`` everywhere.
    """

    name: str
    table: str
    entity_columns: List[str]
    valid_from: str
    valid_to: str
    recorded_at: str
    superseded_at: str
    avg_versions: float = Field(default=3.0, ge=1.0)


class DagEdges(BaseModel):
    """An edge table that is a directed acyclic graph.

    The forest rule added in 0.9.2 keeps a self-referential *column* acyclic. It
    says nothing about a join table, where the same guarantee needs a different
    construction: edges are drawn between nodes ordered by a topological rank, so
    an edge always points from lower rank to higher and a cycle cannot close.

    Guarantees no self-edges, no duplicate pairs, and no cycle at any depth.
    """

    name: str
    table: str
    node_table: str
    node_key: str
    from_column: str
    to_column: str


class TransitiveClosure(BaseModel):
    """A closure table that actually equals the closure of its edges.

    Warehouses materialise reachability so queries do not need a recursive CTE.
    Generated naively the closure and the edges are two unrelated random tables,
    and every question asked through the closure gets a different answer from the
    same question asked through the edges. Nothing row-level catches that.

    Afterwards the table contains exactly the reachable pairs of ``edge_table``,
    each once, with ``depth_column`` equal to the true shortest path length.
    Costs: the row count is whatever the closure actually is, so the declared
    ``row_count`` is advisory and the table is resized to fit the graph.
    """

    name: str
    table: str
    edge_table: str
    edge_from: str
    edge_to: str
    ancestor_column: str
    descendant_column: str
    depth_column: Optional[str] = None


class RealismConfig(BaseModel):
    """
    Configuration for advanced realism features.

    All options are explicit and opt-in to preserve deterministic defaults.
    """

    row_planning: Literal["off", "heuristic", "custom"] = "off"
    row_planning_base_rows: Optional[int] = Field(default=None, gt=0)
    row_count_overrides: Dict[str, int] = Field(default_factory=dict)
    relationship_multipliers: Dict[str, float] = Field(default_factory=dict)
    coherence: Literal["off", "standard", "strict"] = "off"
    workflow_mode: Literal["off", "preset", "custom"] = "off"
    reports: List[Literal["privacy", "fidelity", "data_card"]] = Field(default_factory=list)
    text_mode: Literal["default", "realistic_catalog"] = "default"
    domain_hint: Optional[str] = None
    locale: Optional[str] = None
    era: Optional[str] = None
    asset_store_dir: Optional[str] = None
    # Path to a shareable capsule JSON (see misata.capsules). Its
    # vocabularies override built-in pools for matching semantic names.
    capsule_file: Optional[str] = None

    @field_validator("row_count_overrides")
    @classmethod
    def validate_row_count_overrides(cls, v: Dict[str, int]) -> Dict[str, int]:
        """Row count overrides must stay positive."""
        for table_name, row_count in v.items():
            if row_count <= 0:
                raise ValueError(f"Row count override for '{table_name}' must be > 0")
        return v

    @field_validator("relationship_multipliers")
    @classmethod
    def validate_relationship_multipliers(cls, v: Dict[str, float]) -> Dict[str, float]:
        """Relationship multipliers must stay positive."""
        for relationship, multiplier in v.items():
            if multiplier <= 0:
                raise ValueError(f"Relationship multiplier for '{relationship}' must be > 0")
        return v


class SchemaConfig(BaseModel):
    """
    Complete configuration for synthetic data generation.

    This is the root configuration object that defines all tables,
    columns, relationships, and scenario events.

    Attributes:
        name: Name of the dataset/scenario
        description: Description of what this data represents
        tables: List of tables to generate
        columns: Mapping of table names to their column definitions
        relationships: List of inter-table relationships
        events: List of scenario events to apply
        outcome_curves: List of temporal patterns for constrained generation
        noise_config: Optional noise injection rules
        realism: Optional advanced realism planning and reporting rules
        seed: Random seed for reproducibility
    """

    name: str
    description: Optional[str] = None
    domain: Optional[str] = None  # e.g. "saas", "ecommerce", "fintech" — drives domain priors
    tables: List[Table]
    columns: Dict[str, List[Column]]
    relationships: List[Relationship] = Field(default_factory=list)
    events: List[ScenarioEvent] = Field(default_factory=list)
    outcome_curves: List[OutcomeCurve] = Field(default_factory=list)
    rate_curves: List[RateCurve] = Field(default_factory=list)
    group_shares: List[GroupShares] = Field(default_factory=list)
    waterfalls: List[WaterfallIdentity] = Field(default_factory=list)
    stock_flows: List[StockFlowIdentity] = Field(default_factory=list)
    degradations: List[Degradation] = Field(default_factory=list)
    lifecycles: List[Lifecycle] = Field(default_factory=list)
    retention: List[CohortRetention] = Field(default_factory=list)
    missingness: List[Missingness] = Field(default_factory=list)
    late_arrivals: List[LateArrival] = Field(default_factory=list)
    time_grids: List[TimeGrid] = Field(default_factory=list)
    duplicates: List[Duplicates] = Field(default_factory=list)
    event_logs: List[EventLog] = Field(default_factory=list)
    outliers: List[Outliers] = Field(default_factory=list)
    typos: List[Typos] = Field(default_factory=list)
    bitemporal: List[Bitemporal] = Field(default_factory=list)
    dag_edges: List[DagEdges] = Field(default_factory=list)
    closures: List[TransitiveClosure] = Field(default_factory=list)
    generation_mode: Literal["legacy", "anchored"] = Field(
        default="anchored",
        description=(
            "\"anchored\" (default) derives an independent RNG stream per "
            "column and per pass, so schema edits change only what they touch "
            "(adding a column leaves every other column byte-identical). "
            "\"legacy\" is the old sequential stream; bytes differ between "
            "modes for the same seed."
        ),
    )
    noise_config: Optional[NoiseConfig] = None
    realism: Optional[RealismConfig] = None
    seed: Optional[int] = None
    vocabularies: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description=(
            "Mini-capsule: column-name → list of real domain values, spent once "
            "at schema design time (typically by the LLM for niche domains). "
            "Merged into the generation capsule so open-ended text columns draw "
            "from real vocabulary instead of structural filler."
        ),
    )

    @field_validator("columns")
    @classmethod
    def validate_columns(cls, v: Dict[str, List[Column]], info: Any) -> Dict[str, List[Column]]:
        """Ensure all tables have column definitions, inferring reference-table columns when needed."""
        tables = info.data.get("tables", [])
        normalized = dict(v)

        for table in tables:
            if table.name in normalized and normalized[table.name]:
                continue

            if table.is_reference and table.inline_data:
                first_row = table.inline_data[0]
                inferred_columns = []
                for column_name, value in first_row.items():
                    if isinstance(value, bool):
                        column_type = "boolean"
                    elif isinstance(value, int):
                        column_type = "int"
                    elif isinstance(value, float):
                        column_type = "float"
                    else:
                        column_type = "text"
                    inferred_columns.append(
                        Column(
                            name=column_name,
                            type=column_type,
                            distribution_params={},
                        )
                    )
                normalized[table.name] = inferred_columns
                continue

            raise ValueError(f"Table '{table.name}' has no column definitions")

        return normalized

    @field_validator("relationships")
    @classmethod
    def validate_relationships(cls, v: List[Relationship], info: Any) -> List[Relationship]:
        """Ensure relationship references exist."""
        tables = info.data.get("tables", [])
        table_names = {t.name for t in tables}

        for rel in v:
            if rel.parent_table not in table_names:
                raise ValueError(f"Parent table '{rel.parent_table}' not found in schema")
            if rel.child_table not in table_names:
                raise ValueError(f"Child table '{rel.child_table}' not found in schema")

        return v

    def get_table(self, name: str) -> Optional[Table]:
        """Get a table by name."""
        for table in self.tables:
            if table.name == name:
                return table
        return None

    def get_columns(self, table_name: str) -> List[Column]:
        """Get columns for a specific table."""
        return self.columns.get(table_name, [])

    def summary(self) -> str:
        """Return a concise human-readable overview of this schema.

        Useful for quick inspection in notebooks and REPLs::

            >>> schema = parser.parse("A SaaS with 5k users")
            >>> print(schema.summary())
        """
        lines = [
            f"Schema: {self.name}",
            f"Domain: {self.domain or 'unspecified'}",
            f"Tables: {len(self.tables)}",
        ]
        total_rows = sum(t.row_count or 0 for t in self.tables)
        lines.append(f"Total rows: {total_rows:,}")
        lines.append("")

        col_w = max((len(t.name) for t in self.tables), default=5) + 2
        lines.append(f"  {'Table':<{col_w}} {'Rows':>8}  Columns")
        lines.append(f"  {'-' * col_w} {'-' * 8}  -------")
        for table in self.tables:
            cols = self.get_columns(table.name)
            col_names = ", ".join(c.name for c in cols[:5])
            if len(cols) > 5:
                col_names += f" … (+{len(cols) - 5} more)"
            rows_str = f"{table.row_count:,}" if table.row_count else "ref"
            lines.append(f"  {table.name:<{col_w}} {rows_str:>8}  {col_names}")

        if self.relationships:
            lines.append("")
            lines.append(f"  Relationships ({len(self.relationships)}):")
            for r in self.relationships:
                lines.append(f"    {r.parent_table}.{r.parent_key} → {r.child_table}.{r.child_key}")

        if self.outcome_curves:
            lines.append("")
            lines.append(f"  Outcome curves ({len(self.outcome_curves)}):")
            for c in self.outcome_curves:
                lines.append(f"    {c.table}.{c.column} over {c.time_column}")

        return "\n".join(lines)
