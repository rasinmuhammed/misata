"""
Story parser for converting natural language descriptions to SchemaConfig.

This module provides rule-based pattern matching to extract:
- Business domain (SaaS, E-commerce, Pharma, etc.)
- Scale parameters (number of users, transactions, etc.)
- Temporal patterns (growth, churn, seasonality, crashes)
- Data relationships
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from misata.schema import Column, Relationship, ScenarioEvent, SchemaConfig, Table


class StoryParser:
    """
    Parses natural language stories into SchemaConfig objects.

    Uses regex patterns and template matching for MVP version.
    Future: Can be enhanced with LLM integration.
    """

    # Pattern definitions
    SCALE_PATTERNS = {
        r"(\d+[KkMm]?)\s*users": "users",
        r"(\d+[KkMm]?)\s*customers": "users",
        r"(\d+[KkMm]?)\s*transactions": "transactions",
        r"(\d+[KkMm]?)\s*orders": "orders",
        r"(\d+[KkMm]?)\s*projects": "projects",
    }

    TEMPORAL_PATTERNS = {
        r"(\d+)%\s*growth": ("growth", "rate"),
        r"(\d+)%\s*churn": ("churn", "rate"),
        r"crash\s*in\s*([QqJjFfMmAaSsOoNnDd]+\s*\d{4})": ("crash", "date"),
        r"seasonality": ("seasonality", None),
        r"seasonal": ("seasonality", None),
    }

    DOMAIN_KEYWORDS = {
        "saas": ["saas", "subscription", "mrr", "arr", "churn"],
        "ecommerce": ["ecommerce", "e-commerce", "orders", "cart", "products"],
        "pharma": ["pharma", "research", "timesheet", "clinical", "trials"],
        "fintech": ["fintech", "transactions", "payments", "wallet"],
    }

    def __init__(self):
        """Initialize the story parser."""
        self.detected_domain: Optional[str] = None
        self.scale_params: Dict[str, int] = {}
        self.temporal_events: List[Tuple[str, Any]] = []

    def _parse_number(self, num_str: str) -> int:
        """Parse number strings like '50K', '1.5M' to integers."""
        num_str = num_str.strip().upper()

        if num_str.endswith('K'):
            return int(float(num_str[:-1]) * 1000)
        elif num_str.endswith('M'):
            return int(float(num_str[:-1]) * 1_000_000)
        else:
            return int(num_str)

    def _detect_domain(self, story: str) -> Optional[str]:
        """Detect business domain from story text."""
        story_lower = story.lower()

        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            for keyword in keywords:
                if keyword in story_lower:
                    return domain

        return None

    def _extract_scale(self, story: str) -> Dict[str, int]:
        """Extract scale parameters (number of records) from story."""
        scale_params = {}

        for pattern, entity_type in self.SCALE_PATTERNS.items():
            match = re.search(pattern, story, re.IGNORECASE)
            if match:
                num_str = match.group(1)
                scale_params[entity_type] = self._parse_number(num_str)

        return scale_params

    def _extract_temporal_events(self, story: str) -> List[Tuple[str, Any]]:
        """Extract temporal patterns (growth, churn, crashes, etc.)."""
        events = []

        for pattern, (event_type, param_type) in self.TEMPORAL_PATTERNS.items():
            matches = re.finditer(pattern, story, re.IGNORECASE)
            for match in matches:
                if param_type == "rate":
                    value = int(match.group(1))
                    events.append((event_type, value / 100))  # Convert percentage
                elif param_type == "date":
                    date_str = match.group(1)
                    events.append((event_type, date_str))
                else:
                    events.append((event_type, None))

        return events

    def parse(self, story: str, default_rows: int = 10000) -> SchemaConfig:
        """
        Parse a natural language story into a SchemaConfig.

        Args:
            story: Natural language description of the data to generate
            default_rows: Default number of rows if not specified in story

        Returns:
            SchemaConfig object ready for data generation

        Example:
            >>> parser = StoryParser()
            >>> config = parser.parse(
            ...     "A SaaS company with 50K users, 20% churn in Q3 2023"
            ... )
        """
        # Extract information from story
        self.detected_domain = self._detect_domain(story)
        self.scale_params = self._extract_scale(story)
        self.temporal_events = self._extract_temporal_events(story)

        # Build schema based on detected domain
        if self.detected_domain == "saas":
            return self._build_saas_schema(story, default_rows)
        elif self.detected_domain == "ecommerce":
            return self._build_ecommerce_schema(story, default_rows)
        elif self.detected_domain == "pharma":
            return self._build_pharma_schema(story, default_rows)
        else:
            # Generic schema
            return self._build_generic_schema(story, default_rows)

    def _build_saas_schema(self, story: str, default_rows: int) -> SchemaConfig:
        """Build a SaaS-specific schema."""
        num_users = self.scale_params.get("users", default_rows)
        num_subscriptions = int(num_users * 1.2)  # Some users have multiple subs

        # Define tables
        tables = [
            Table(name="users", row_count=num_users, description="User accounts"),
            Table(
                name="subscriptions",
                row_count=num_subscriptions,
                description="User subscriptions",
            ),
        ]

        # Define columns
        columns = {
            "users": [
                Column(name="user_id", type="int", distribution_params={"min": 1, "max": num_users}),
                Column(name="email", type="text", distribution_params={"text_type": "email"}),
                Column(name="name", type="text", distribution_params={"text_type": "name"}),
                Column(
                    name="signup_date",
                    type="date",
                    distribution_params={"start": "2022-01-01", "end": "2024-12-31"},
                ),
                Column(
                    name="plan",
                    type="categorical",
                    distribution_params={
                        "choices": ["free", "starter", "pro", "enterprise"],
                        "probabilities": [0.4, 0.3, 0.25, 0.05],
                    },
                ),
                Column(name="churned", type="boolean", distribution_params={"probability": 0.15}),
            ],
            "subscriptions": [
                Column(
                    name="subscription_id",
                    type="int",
                    distribution_params={"min": 1, "max": num_subscriptions},
                ),
                Column(name="user_id", type="foreign_key", distribution_params={}),
                Column(
                    name="start_date",
                    type="date",
                    distribution_params={"start": "2022-01-01", "end": "2024-12-31"},
                ),
                Column(
                    name="mrr",
                    type="float",
                    distribution_params={
                        "distribution": "normal",
                        "mean": 150.0,
                        "std": 50.0,
                        "min": 0.0,
                        "decimals": 2,
                    },
                ),
                Column(
                    name="status",
                    type="categorical",
                    distribution_params={
                        "choices": ["active", "cancelled", "paused"],
                        "probabilities": [0.7, 0.2, 0.1],
                    },
                ),
            ],
        }

        # Define relationships
        relationships = [
            Relationship(
                parent_table="users",
                child_table="subscriptions",
                parent_key="user_id",
                child_key="user_id",
            ),
        ]

        # Build scenario events from temporal patterns
        events = []
        for event_type, value in self.temporal_events:
            if event_type == "churn":
                # Parse the churn date from story (e.g., "Q3 2023")
                # For simplicity, use a fixed date
                events.append(
                    ScenarioEvent(
                        name="High_Churn_Period",
                        table="users",
                        column="churned",
                        condition="signup_date < '2023-06-01'",
                        modifier_type="set",
                        modifier_value=True,
                        description=f"Churn rate of {value*100:.0f}%",
                    )
                )
            elif event_type == "growth":
                events.append(
                    ScenarioEvent(
                        name="MRR_Growth",
                        table="subscriptions",
                        column="mrr",
                        condition="start_date > '2023-06-01'",
                        modifier_type="multiply",
                        modifier_value=1 + value,
                        description=f"Growth rate of {value*100:.0f}%",
                    )
                )

        return SchemaConfig(
            name="SaaS Dataset",
            description=f"Generated from story: {story}",
            tables=tables,
            columns=columns,
            relationships=relationships,
            events=events,
        )

    def _build_ecommerce_schema(self, story: str, default_rows: int) -> SchemaConfig:
        """Build an E-commerce-specific schema."""
        num_customers = self.scale_params.get("users", default_rows)
        num_orders = self.scale_params.get("orders", int(num_customers * 3))

        tables = [
            Table(name="customers", row_count=num_customers),
            Table(name="orders", row_count=num_orders),
        ]

        columns = {
            "customers": [
                Column(name="customer_id", type="int", distribution_params={"min": 1, "max": num_customers}),
                Column(name="email", type="text", distribution_params={"text_type": "email"}),
                Column(name="name", type="text", distribution_params={"text_type": "name"}),
                Column(
                    name="signup_date",
                    type="date",
                    distribution_params={"start": "2022-01-01", "end": "2024-12-31"},
                ),
            ],
            "orders": [
                Column(name="order_id", type="int", distribution_params={"min": 1, "max": num_orders}),
                Column(name="customer_id", type="foreign_key", distribution_params={}),
                Column(
                    name="order_date",
                    type="date",
                    distribution_params={"start": "2022-01-01", "end": "2024-12-31"},
                ),
                Column(
                    name="amount",
                    type="float",
                    distribution_params={
                        "distribution": "normal",
                        "mean": 75.0,
                        "std": 30.0,
                        "min": 10.0,
                        "decimals": 2,
                    },
                ),
            ],
        }

        relationships = [
            Relationship(
                parent_table="customers",
                child_table="orders",
                parent_key="customer_id",
                child_key="customer_id",
            ),
        ]

        return SchemaConfig(
            name="E-commerce Dataset",
            description=f"Generated from story: {story}",
            tables=tables,
            columns=columns,
            relationships=relationships,
            events=[],
        )

    def _build_pharma_schema(self, story: str, default_rows: int) -> SchemaConfig:
        """Build a Pharma services-specific schema."""
        num_projects = self.scale_params.get("projects", default_rows // 100)
        num_timesheets = default_rows

        tables = [
            Table(name="research_projects", row_count=num_projects),
            Table(name="timesheets", row_count=num_timesheets),
        ]

        columns = {
            "research_projects": [
                Column(name="project_id", type="int", distribution_params={"min": 1, "max": num_projects}),
                Column(name="project_name", type="text", distribution_params={"text_type": "company"}),
                Column(
                    name="start_date",
                    type="date",
                    distribution_params={"start": "2022-01-01", "end": "2024-01-01"},
                ),
                Column(
                    name="status",
                    type="categorical",
                    distribution_params={
                        "choices": ["planning", "active", "completed", "on-hold"],
                        "probabilities": [0.1, 0.5, 0.3, 0.1],
                    },
                ),
            ],
            "timesheets": [
                Column(name="entry_id", type="int", distribution_params={"min": 1, "max": num_timesheets}),
                Column(name="project_id", type="foreign_key", distribution_params={}),
                Column(name="employee_name", type="text", distribution_params={"text_type": "name"}),
                Column(
                    name="date",
                    type="date",
                    distribution_params={"start": "2022-01-01", "end": "2024-12-31"},
                ),
                Column(
                    name="hours",
                    type="float",
                    distribution_params={
                        "distribution": "normal",
                        "mean": 7.5,
                        "std": 1.5,
                        "min": 0.5,
                        "max": 12.0,
                        "decimals": 1,
                    },
                ),
            ],
        }

        relationships = [
            Relationship(
                parent_table="research_projects",
                child_table="timesheets",
                parent_key="project_id",
                child_key="project_id",
            ),
        ]

        return SchemaConfig(
            name="Pharma Services Dataset",
            description=f"Generated from story: {story}",
            tables=tables,
            columns=columns,
            relationships=relationships,
            events=[],
        )

    def _build_generic_schema(self, story: str, default_rows: int) -> SchemaConfig:
        """Build a generic schema when domain is not detected."""
        tables = [
            Table(name="main_table", row_count=default_rows),
        ]

        columns = {
            "main_table": [
                Column(name="id", type="int", distribution_params={"min": 1, "max": default_rows}),
                Column(name="name", type="text", distribution_params={"text_type": "name"}),
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
                    name="date",
                    type="date",
                    distribution_params={"start": "2022-01-01", "end": "2024-12-31"},
                ),
            ],
        }

        return SchemaConfig(
            name="Generic Dataset",
            description=f"Generated from story: {story}",
            tables=tables,
            columns=columns,
            relationships=[],
            events=[],
        )
