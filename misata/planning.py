"""Planning layer for deterministic realism configuration."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np


CARDINALITY_PATTERNS: Dict[tuple[str, str], tuple[float, float]] = {
    ("user", "order"): (3.0, 8.0),
    ("customer", "order"): (3.0, 8.0),
    ("order", "orderitem"): (2.0, 5.0),
    ("order", "item"): (2.0, 5.0),
    ("company", "user"): (5.0, 25.0),
    ("user", "session"): (8.0, 30.0),
    ("user", "event"): (15.0, 80.0),
    ("subscription", "invoice"): (6.0, 24.0),
    ("patient", "appointment"): (2.0, 8.0),
    ("account", "transaction"): (20.0, 100.0),
    ("customer", "account"): (1.0, 2.5),
    ("employee", "timesheet"): (50.0, 200.0),
    ("student", "enrollment"): (3.0, 8.0),
    ("entity", "event"): (10.0, 50.0),
    ("entity", "activity"): (8.0, 30.0),
    ("entity", "item"): (2.0, 5.0),
}

REFERENCE_TABLE_PATTERNS = {
    "categor", "type", "status", "tag", "role", "permission",
    "department", "region", "currency", "language", "country",
    "brand", "color", "size", "material", "genre", "plan",
    "tier", "level", "priority", "state", "province",
}

ACTIVITY_TABLE_PATTERNS = {
    "event", "log", "activity", "session", "audit", "history",
    "click", "pageview", "impression", "metric", "telemetry",
}

LINE_ITEM_PATTERNS = {"item", "line", "detail", "entry", "position"}


@dataclass
class TablePlan:
    """Planned generation settings for a single table."""

    name: str
    row_count: int
    semantic_role: str
    text_strategies: Dict[str, str] = field(default_factory=dict)
    protected_columns: set[str] = field(default_factory=set)


@dataclass
class GenerationPlan:
    """Resolved deterministic generation plan."""

    tables: Dict[str, TablePlan]

    def row_count_for(self, table_name: str, fallback: int) -> int:
        table_plan = self.tables.get(table_name)
        return table_plan.row_count if table_plan else fallback

    def text_strategy_for(self, table_name: str, column_name: str) -> Optional[str]:
        table_plan = self.tables.get(table_name)
        if not table_plan:
            return None
        return table_plan.text_strategies.get(column_name)


class GenerationPlanner:
    """Computes deterministic realism plans from schema config."""

    def __init__(self, schema_config: Any, rng: Optional[np.random.Generator] = None):
        self.schema_config = schema_config
        self.rng = rng or np.random.default_rng(schema_config.seed or 42)

    def build(self) -> GenerationPlan:
        row_counts = self._resolve_row_counts()
        tables = {}

        for table in self.schema_config.tables:
            columns = self.schema_config.get_columns(table.name)
            semantic_role = self._classify_table(table.name)
            text_strategies = {
                column.name: self._classify_text_column(table.name, column)
                for column in columns
                if column.type == "text"
            }
            text_strategies = {
                column_name: strategy
                for column_name, strategy in text_strategies.items()
                if strategy is not None
            }
            tables[table.name] = TablePlan(
                name=table.name,
                row_count=row_counts.get(table.name, table.row_count),
                semantic_role=semantic_role,
                text_strategies=text_strategies,
            )

        return GenerationPlan(tables=tables)

    def _resolve_row_counts(self) -> Dict[str, int]:
        realism = getattr(self.schema_config, "realism", None)
        if realism is None:
            return {table.name: table.row_count for table in self.schema_config.tables}

        row_counts = {table.name: table.row_count for table in self.schema_config.tables}
        overrides = dict(realism.row_count_overrides)
        row_counts.update(overrides)

        if realism.row_planning == "off":
            return row_counts

        non_reference_tables = [table for table in self.schema_config.tables if not table.is_reference]
        existing_counts = [row_counts[table.name] for table in non_reference_tables]
        all_same = len(set(existing_counts)) <= 1 if existing_counts else True

        if realism.row_planning == "heuristic" and not all_same and not overrides:
            return row_counts

        base_rows = realism.row_planning_base_rows or (existing_counts[0] if existing_counts else 100)
        planned = self._compute_intelligent_row_counts(base_rows, row_counts, realism.relationship_multipliers)
        planned.update(overrides)
        return planned

    def _compute_intelligent_row_counts(
        self,
        base_rows: int,
        existing_counts: Dict[str, int],
        relationship_multipliers: Dict[str, float],
    ) -> Dict[str, int]:
        tables = {table.name: table for table in self.schema_config.tables}
        relationships = self.schema_config.relationships
        children_of: Dict[str, list[str]] = {name: [] for name in tables}
        parents_of: Dict[str, list[str]] = {name: [] for name in tables}

        for relationship in relationships:
            if relationship.parent_table in children_of:
                children_of[relationship.parent_table].append(relationship.child_table)
            if relationship.child_table in parents_of:
                parents_of[relationship.child_table].append(relationship.parent_table)

        row_counts = {}
        for name, table in tables.items():
            if table.is_reference or self._classify_table(name) == "reference":
                row_counts[name] = len(table.inline_data) if table.inline_data else min(existing_counts.get(name, table.row_count), 50)

        roots = [name for name, parents in parents_of.items() if not parents]
        for root in roots:
            row_counts.setdefault(root, existing_counts.get(root, base_rows) or base_rows)

        queue = list(roots)
        visited = set(queue)
        while queue:
            parent_name = queue.pop(0)
            parent_count = row_counts.get(parent_name, existing_counts.get(parent_name, base_rows))

            for child_name in children_of[parent_name]:
                if child_name in row_counts:
                    continue

                key = f"{parent_name}->{child_name}"
                if key in relationship_multipliers:
                    multiplier = relationship_multipliers[key]
                else:
                    parent_semantic = self._semantic_category(parent_name)
                    child_semantic = self._semantic_category(child_name)
                    low, high = CARDINALITY_PATTERNS.get(
                        (parent_semantic, child_semantic),
                        CARDINALITY_PATTERNS.get(("entity", self._classify_table(child_name).replace("reference", "entity")), (2.0, 5.0)),
                    )
                    multiplier = float(self.rng.uniform(low, high))

                if len(parents_of[child_name]) > 1:
                    multiplier /= len(parents_of[child_name])

                child_count = max(10, int(round(parent_count * multiplier)))
                if self._classify_table(child_name) == "activity":
                    child_count = min(child_count, base_rows * 100)

                row_counts[child_name] = child_count
                if child_name not in visited:
                    visited.add(child_name)
                    queue.append(child_name)

        for name, table in tables.items():
            row_counts.setdefault(name, existing_counts.get(name, table.row_count))

        return row_counts

    def _classify_table(self, name: str) -> str:
        lowered = name.lower()
        if any(pattern in lowered for pattern in REFERENCE_TABLE_PATTERNS):
            return "reference"
        if any(pattern in lowered for pattern in ACTIVITY_TABLE_PATTERNS):
            return "activity"
        if any(pattern in lowered for pattern in LINE_ITEM_PATTERNS):
            return "line_item"
        if len(re.split(r"[_\s]", lowered)) >= 2:
            return "transaction"
        return "entity"

    def _semantic_category(self, name: str) -> str:
        lowered = name.lower()
        concepts = [
            "user", "customer", "patient", "student", "employee", "member",
            "order", "booking", "appointment", "purchase", "subscription",
            "order_item", "item", "line_item", "product", "course", "exercise", "plan",
            "company", "organization", "department", "payment", "invoice", "transaction",
            "review", "rating", "comment", "feedback", "event", "session", "log",
            "activity", "usage", "account", "wallet", "doctor", "teacher", "instructor",
            "timesheet", "enrollment", "grade",
        ]
        for concept in concepts:
            if concept in lowered:
                return concept.replace("_", "")
        return "entity"

    def _classify_text_column(self, table_name: str, column: Any) -> Optional[str]:
        params = column.distribution_params
        name = column.name.lower()
        table = table_name.lower()

        if name in {"first_name"}:
            return "first_name"
        if name in {"last_name"}:
            return "last_name"
        if "email" in name:
            return "email"
        if "username" in name or name == "handle":
            return "username"
        if "company" in name or "organization" in name:
            return "company_name"
        if "product" in table or "item" in table:
            if name in {"name", "product_name", "title"}:
                return "product_name"
            if "description" in name or "summary" in name:
                return "product_description"
        if "job" in name or "role" in name or "title" in name or "position" in name:
            return "job_title"
        if "city" in name:
            return "city"
        if "country" in name:
            return "country"
        if "state" in name or "province" in name or "region" in name:
            return "state"
        if name == "name":
            return "person_name"
        if "slug" in name:
            return "slug_source"

        text_type = params.get("text_type")
        if text_type in {"name", "email", "company", "address", "phone", "url"}:
            mapping = {
                "name": "person_name",
                "email": "email",
                "company": "company_name",
                "address": "address",
                "phone": "phone_number",
                "url": "url",
            }
            return mapping[text_type]
        return None
