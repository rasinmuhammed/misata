"""
Pydantic models for Misata configuration.

These models define the blueprint for synthetic data generation,
including tables, columns, relationships, and scenario events.
"""

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
    distribution_params: Dict[str, Any] = Field(default_factory=dict)
    nullable: bool = False
    unique: bool = False

    @field_validator("distribution_params")
    @classmethod
    def validate_params(cls, v: Dict[str, Any], info: Any) -> Dict[str, Any]:
        """Validate distribution parameters based on column type."""
        col_type = info.data.get("type")

        if col_type == "categorical" and "choices" not in v:
            raise ValueError("Categorical columns must have 'choices' in distribution_params")

        if col_type == "date":
            if "relative_to" not in v:
                # Provide sensible defaults if start/end not specified
                if "start" not in v:
                    from datetime import datetime, timedelta
                    v["start"] = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
                if "end" not in v:
                    from datetime import datetime
                    v["end"] = datetime.now().strftime("%Y-%m-%d")

        if col_type in ["int", "float"]:
            if "distribution" not in v:
                v["distribution"] = "normal"  # Default to normal distribution

        return v


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
    constraints: List["Constraint"] = Field(default_factory=list)



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
    type: Literal["max_per_group", "min_per_group", "sum_limit", "unique_combination"]
    group_by: List[str] = Field(default_factory=list)
    column: Optional[str] = None  # Not needed for unique_combination
    value: Optional[float] = None  # The limit value
    action: Literal["cap", "redistribute", "drop", "error"] = "cap"


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
        seed: Random seed for reproducibility
    """

    name: str
    description: Optional[str] = None
    tables: List[Table]
    columns: Dict[str, List[Column]]
    relationships: List[Relationship] = Field(default_factory=list)
    events: List[ScenarioEvent] = Field(default_factory=list)
    seed: Optional[int] = None

    @field_validator("columns")
    @classmethod
    def validate_columns(cls, v: Dict[str, List[Column]], info: Any) -> Dict[str, List[Column]]:
        """Ensure all tables have column definitions."""
        tables = info.data.get("tables", [])
        table_names = {t.name for t in tables}

        for table_name in table_names:
            if table_name not in v:
                raise ValueError(f"Table '{table_name}' has no column definitions")

        return v

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
