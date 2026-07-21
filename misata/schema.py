"""
Pydantic models for Misata configuration.

These models define the blueprint for synthetic data generation,
including tables, columns, relationships, and scenario events.
"""

import warnings
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


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
    filters: Optional[Dict[str, Any]] = None  # e.g., {"status": "active"}


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
