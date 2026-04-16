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
    row_count: int = Field(default=100, gt=0)
    description: Optional[str] = None
    is_reference: bool = False
    inline_data: Optional[List[Dict[str, Any]]] = None
    columns: List[str] = Field(default_factory=list)
    constraints: List["Constraint"] = Field(default_factory=list)
    workflow_preset: Optional[str] = None
    workflow_config: Optional[Dict[str, Any]] = None



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
    noise_config: Optional[NoiseConfig] = None
    realism: Optional[RealismConfig] = None
    seed: Optional[int] = None

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
