"""
Story parser for converting natural language descriptions to SchemaConfig.

This module provides rule-based pattern matching to extract:
- Business domain (SaaS, E-commerce, Pharma, etc.)
- Scale parameters (number of users, transactions, etc.)
- Temporal patterns (growth, churn, seasonality, crashes)
- Data relationships
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from misata.schema import Column, OutcomeCurve, Relationship, ScenarioEvent, SchemaConfig, Table


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

    MONTHS = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }

    QUALITATIVE_MONTH_FACTORS = {
        "dip": 0.7,
        "drop": 0.7,
        "decline": 0.75,
        "low": 0.8,
        "peak": 1.25,
        "spike": 1.3,
        "surge": 1.3,
        "high": 1.2,
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

    def _parse_numeric_value(self, raw_value: str) -> float:
        """Parse currency-like values such as $50k, 150,000, or 1.5M."""
        cleaned = raw_value.strip().lower().replace(",", "")
        cleaned = cleaned.replace("$", "").replace("usd", "").strip()

        multiplier = 1.0
        if cleaned.endswith("k"):
            multiplier = 1_000.0
            cleaned = cleaned[:-1]
        elif cleaned.endswith("m"):
            multiplier = 1_000_000.0
            cleaned = cleaned[:-1]
        elif cleaned.endswith("b"):
            multiplier = 1_000_000_000.0
            cleaned = cleaned[:-1]

        return float(cleaned) * multiplier

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

    def _extract_period_count(self, story: str) -> int:
        """Infer how many monthly buckets the user is asking for."""
        match = re.search(r"over\s+(\d+)\s+months?", story, re.IGNORECASE)
        if match:
            return max(2, int(match.group(1)))

        if re.search(r"\b(jan|january)\b", story, re.IGNORECASE) and re.search(r"\b(dec|december)\b", story, re.IGNORECASE):
            return 12

        return 12

    def _extract_target_month_points(self, story: str, period_count: int) -> Dict[int, float]:
        """Extract explicit numeric control points such as 50k in Jan."""
        anchors: Dict[int, float] = {}

        value_then_month = re.finditer(
            r"(?P<value>\$?\d[\d,]*(?:\.\d+)?\s*[kmb]?)\s+(?:in|for|by|at)\s+(?P<month>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)",
            story,
            re.IGNORECASE,
        )
        month_then_value = re.finditer(
            r"(?P<month>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s*(?:at|=|:)?\s*(?P<value>\$?\d[\d,]*(?:\.\d+)?\s*[kmb]?)",
            story,
            re.IGNORECASE,
        )

        for match in list(value_then_month) + list(month_then_value):
            month_token = match.group("month").lower()
            month_number = self.MONTHS.get(month_token[:3], self.MONTHS.get(month_token))
            if month_number is None:
                continue
            anchors[month_number] = self._parse_numeric_value(match.group("value"))

        range_match = re.search(
            r"from\s+(?P<start>\$?\d[\d,]*(?:\.\d+)?\s*[kmb]?)\s+to\s+(?P<end>\$?\d[\d,]*(?:\.\d+)?\s*[kmb]?)(?:\s+over\s+(?P<months>\d+)\s+months?)?",
            story,
            re.IGNORECASE,
        )
        if range_match and len(anchors) < 2:
            anchors.setdefault(1, self._parse_numeric_value(range_match.group("start")))
            final_period = int(range_match.group("months") or period_count)
            anchors.setdefault(final_period, self._parse_numeric_value(range_match.group("end")))

        return anchors

    def _extract_qualitative_month_modifiers(self, story: str) -> Dict[int, float]:
        """Extract qualitative modifiers like dip in September or peak in December."""
        modifiers: Dict[int, float] = {}

        for keyword, factor in self.QUALITATIVE_MONTH_FACTORS.items():
            for match in re.finditer(
                rf"{keyword}\s+in\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)",
                story,
                re.IGNORECASE,
            ):
                month_token = match.group(1).lower()
                month_number = self.MONTHS.get(month_token[:3], self.MONTHS.get(month_token))
                if month_number is not None:
                    modifiers[month_number] = factor

        return modifiers

    def _extract_reference_year(self, story: str) -> int:
        """Choose a year for generated monthly targets."""
        match = re.search(r"\b(20\d{2})\b", story)
        if match:
            return int(match.group(1))
        return datetime.now().year

    def _extract_intra_period_pattern(self, story: str) -> str:
        """Detect sub-bucket patterns like weekday_heavy or end_heavy."""
        story_lower = story.lower()
        if re.search(r"\bslow\s+(on\s+)?weekends?\b", story_lower):
            return "weekday_heavy"
        if re.search(r"\bslow\s+(on\s+)?weekdays?\b", story_lower):
            return "weekend_heavy"
        if re.search(r"\bweekdays?\b", story_lower):
            return "weekday_heavy"
        if re.search(r"\bweekends?\b", story_lower):
            return "weekend_heavy"
        if re.search(r"\b(end\s+of|late\b)", story_lower):
            return "end_heavy"
        if re.search(r"\b(start\s+of|beginning\s+of|early\b)", story_lower):
            return "start_heavy"
        return "uniform"

    def _build_absolute_monthly_curve(
        self,
        story: str,
        *,
        table: str,
        column: str,
        time_column: str,
        avg_transaction_value: Optional[float],
    ) -> Optional[OutcomeCurve]:
        """Create an exact monthly outcome curve from story anchors."""
        story_lower = story.lower()
        if not any(token in story_lower for token in ["revenue", "sales", "mrr", "arr", "gmv", "amount"]):
            return None

        period_count = self._extract_period_count(story)
        anchors = self._extract_target_month_points(story, period_count)
        if len(anchors) < 2:
            return None

        months = np.arange(1, period_count + 1)
        x_known = np.array(sorted(anchors.keys()), dtype=float)
        y_known = np.array([anchors[int(month)] for month in x_known], dtype=float)
        interpolated = np.interp(months, x_known, y_known)

        modifiers = self._extract_qualitative_month_modifiers(story)
        for month_number, factor in modifiers.items():
            if 1 <= month_number <= period_count:
                interpolated[month_number - 1] *= factor

        for month_number, exact_value in anchors.items():
            if 1 <= month_number <= period_count:
                interpolated[month_number - 1] = exact_value

        curve_points = [
            {"month": int(month_number), "target_value": round(max(float(value), 0.0), 2)}
            for month_number, value in zip(months, interpolated)
        ]

        year = self._extract_reference_year(story)
        intra_pattern = self._extract_intra_period_pattern(story)
        return OutcomeCurve(
            table=table,
            column=column,
            time_column=time_column,
            time_unit="month",
            pattern_type="growth",
            value_mode="absolute",
            intra_period_pattern=intra_pattern,
            description=story,
            avg_transaction_value=avg_transaction_value,
            start_date=f"{year}-01-01",
            curve_points=curve_points,
        )

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

        outcome_curve = self._build_absolute_monthly_curve(
            story,
            table="subscriptions",
            column="mrr",
            time_column="start_date",
            avg_transaction_value=150.0,
        )

        return SchemaConfig(
            name="SaaS Dataset",
            description=f"Generated from story: {story}",
            tables=tables,
            columns=columns,
            relationships=relationships,
            events=events,
            outcome_curves=[outcome_curve] if outcome_curve else [],
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

        outcome_curve = self._build_absolute_monthly_curve(
            story,
            table="orders",
            column="amount",
            time_column="order_date",
            avg_transaction_value=75.0,
        )

        return SchemaConfig(
            name="E-commerce Dataset",
            description=f"Generated from story: {story}",
            tables=tables,
            columns=columns,
            relationships=relationships,
            events=[],
            outcome_curves=[outcome_curve] if outcome_curve else [],
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

        outcome_curve = self._build_absolute_monthly_curve(
            story,
            table="timesheets",
            column="hours",
            time_column="date",
            avg_transaction_value=7.5,
        )

        return SchemaConfig(
            name="Pharma Services Dataset",
            description=f"Generated from story: {story}",
            tables=tables,
            columns=columns,
            relationships=relationships,
            events=[],
            outcome_curves=[outcome_curve] if outcome_curve else [],
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

        outcome_curve = self._build_absolute_monthly_curve(
            story,
            table="main_table",
            column="value",
            time_column="date",
            avg_transaction_value=100.0,
        )

        return SchemaConfig(
            name="Generic Dataset",
            description=f"Generated from story: {story}",
            tables=tables,
            columns=columns,
            relationships=[],
            events=[],
            outcome_curves=[outcome_curve] if outcome_curve else [],
        )
