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
        r"(\d+[KkMm]?)\s*employees": "users",
        r"(\d+[KkMm]?)\s*patients": "users",
        r"(\d+[KkMm]?)\s*members": "users",
        r"(\d+[KkMm]?)\s*transactions": "transactions",
        r"(\d+[KkMm]?)\s*orders": "orders",
        r"(\d+[KkMm]?)\s*projects": "projects",
        r"(\d+[KkMm]?)\s*properties": "properties",
        r"(\d+[KkMm]?)\s*listings": "properties",
        r"(\d+[KkMm]?)\s*agents": "agents",
        r"(\d+[KkMm]?)\s*drivers": "drivers",
        r"(\d+[KkMm]?)\s*sellers": "sellers",
        r"(\d+[KkMm]?)\s*doctors": "doctors",
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
        "ecommerce": ["ecommerce", "e-commerce", "orders", "cart", "products", "shop", "store", "retail"],
        "pharma": ["pharma", "research", "timesheet", "clinical", "trials"],
        "fintech": ["fintech", "transactions", "payments", "wallet", "banking", "loans", "credit", "fraud"],
        "healthcare": ["healthcare", "health", "patients", "doctors", "hospital", "clinic", "appointments", "medical"],
        # realestate before marketplace — both have "listings" and "agents" as keywords
        "realestate": ["real estate", "realty", "housing", "mortgage", "homes for sale", "property listing"],
        "marketplace": ["marketplace", "gig", "freelance", "platform", "sellers", "buyers", "listings"],
        "logistics": ["logistics", "shipping", "delivery", "fleet", "warehouse", "supply chain", "routes", "drivers"],
        "hr": ["hr", "human resources", "employees", "payroll", "workforce", "hiring", "headcount", "salaries", "onboarding"],
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

    # Trigger tokens that signal a monetary/metric curve is requested
    CURVE_SIGNAL_TOKENS = [
        "revenue", "sales", "mrr", "arr", "gmv", "amount",
        "orders", "bookings", "transactions", "volume", "churn",
        "growth", "peak", "dip", "spike", "surge", "drop", "decline",
    ]

    def _build_absolute_monthly_curve(
        self,
        story: str,
        *,
        table: str,
        column: str,
        time_column: str,
        avg_transaction_value: Optional[float],
    ) -> Optional[OutcomeCurve]:
        """Create an exact monthly outcome curve from story anchors.

        Works with:
        - Fully numeric:  "revenue from $50k in Jan to $200k in Dec"
        - Mixed:          "$50k in Jan, peak in November"
        - Qualitative:    "sales peak in November, dip in March"
        """
        story_lower = story.lower()
        if not any(token in story_lower for token in self.CURVE_SIGNAL_TOKENS):
            return None

        period_count = self._extract_period_count(story)
        anchors = self._extract_target_month_points(story, period_count)
        modifiers = self._extract_qualitative_month_modifiers(story)

        # If we have no numeric anchors but do have qualitative modifiers,
        # synthesise a flat baseline from avg_transaction_value so the
        # modifiers have something meaningful to shape.
        if len(anchors) < 2 and not modifiers:
            return None

        months = np.arange(1, period_count + 1)

        if len(anchors) >= 2:
            x_known = np.array(sorted(anchors.keys()), dtype=float)
            y_known = np.array([anchors[int(m)] for m in x_known], dtype=float)
            interpolated = np.interp(months, x_known, y_known)
        elif len(anchors) == 1:
            # One anchor + qualitative modifiers: use the anchor as the baseline
            baseline = next(iter(anchors.values()))
            interpolated = np.full(period_count, baseline, dtype=float)
        else:
            # Pure qualitative: derive a flat baseline from avg_transaction_value.
            # We pick a round number that feels representative for the domain.
            baseline = (avg_transaction_value or 1.0) * max(
                self.scale_params.get("orders", self.scale_params.get("users", 1000)) / period_count,
                1.0,
            )
            interpolated = np.full(period_count, baseline, dtype=float)

        # Apply qualitative modifiers (dip, peak, spike, …)
        for month_number, factor in modifiers.items():
            if 1 <= month_number <= period_count:
                interpolated[month_number - 1] *= factor

        # Re-pin explicit numeric anchors so they are exact
        for month_number, exact_value in anchors.items():
            if 1 <= month_number <= period_count:
                interpolated[month_number - 1] = exact_value

        curve_points = [
            {"month": int(m), "target_value": round(max(float(v), 0.0), 2)}
            for m, v in zip(months, interpolated)
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

        # Detect locale from story text
        try:
            from misata.locales.detector import detect_locale_from_story
            self.detected_locale = detect_locale_from_story(story)
        except Exception:
            self.detected_locale = None

        # Build schema based on detected domain
        if self.detected_domain == "saas":
            schema = self._build_saas_schema(story, default_rows)
        elif self.detected_domain == "ecommerce":
            schema = self._build_ecommerce_schema(story, default_rows)
        elif self.detected_domain == "pharma":
            schema = self._build_pharma_schema(story, default_rows)
        elif self.detected_domain == "fintech":
            schema = self._build_fintech_schema(story, default_rows)
        elif self.detected_domain == "healthcare":
            schema = self._build_healthcare_schema(story, default_rows)
        elif self.detected_domain == "marketplace":
            schema = self._build_marketplace_schema(story, default_rows)
        elif self.detected_domain == "logistics":
            schema = self._build_logistics_schema(story, default_rows)
        elif self.detected_domain == "hr":
            schema = self._build_hr_schema(story, default_rows)
        elif self.detected_domain == "realestate":
            schema = self._build_realestate_schema(story, default_rows)
        else:
            schema = self._build_generic_schema(story, default_rows)

        # Inject detected locale into realism config
        if self.detected_locale:
            if schema.realism is None:
                from misata.schema import RealismConfig
                object.__setattr__(schema, "realism", RealismConfig())
            object.__setattr__(schema.realism, "locale", self.detected_locale)

        return schema

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
                Column(name="user_id", type="int", unique=True, distribution_params={"min": 1, "max": num_users * 2}),
                Column(name="email", type="text", distribution_params={"text_type": "email"}),
                Column(name="name", type="text", distribution_params={"text_type": "name"}),
                Column(
                    name="signup_date",
                    type="date",
                    distribution_params={"start": "2022-01-01", "end": "2024-12-31"},
                ),
                Column(
                    name="country",
                    type="categorical",
                    distribution_params={
                        "choices": ["United States", "United Kingdom", "Canada", "Germany",
                                    "France", "Australia", "India", "Brazil", "Netherlands",
                                    "Sweden", "Spain", "Japan", "Singapore", "Mexico", "Italy"],
                        "probabilities": [0.32, 0.10, 0.07, 0.07, 0.06, 0.05, 0.07,
                                          0.04, 0.03, 0.03, 0.03, 0.04, 0.03, 0.03, 0.03],
                    },
                ),
                Column(name="churned", type="boolean", distribution_params={"probability": 0.15}),
            ],
            "subscriptions": [
                Column(
                    name="subscription_id",
                    type="int",
                    unique=True,
                    distribution_params={"min": 1, "max": num_subscriptions * 2},
                ),
                Column(name="user_id", type="foreign_key", distribution_params={}),
                Column(
                    name="plan",
                    type="categorical",
                    distribution_params={
                        # Real SaaS freemium: large free tier, tapers up to enterprise
                        "choices": ["free", "starter", "pro", "enterprise"],
                        "probabilities": [0.40, 0.30, 0.25, 0.05],
                    },
                ),
                Column(
                    name="start_date",
                    type="date",
                    distribution_params={"start": "2022-01-01", "end": "2024-12-31"},
                ),
                Column(
                    name="mrr",
                    type="float",
                    # Conditional on plan tier — free=$0, paid tiers follow lognormal
                    # matching real SaaS pricing benchmarks (Starter~$49, Pro~$149, Enterprise~$665)
                    distribution_params={
                        "depends_on": "plan",
                        "mapping": {
                            "free":       {"value": 0.0},
                            "starter":    {"distribution": "lognormal", "mu": 3.9, "sigma": 0.25, "min": 9.0,  "decimals": 2},
                            "pro":        {"distribution": "lognormal", "mu": 5.0, "sigma": 0.30, "min": 49.0, "decimals": 2},
                            "enterprise": {"distribution": "lognormal", "mu": 6.5, "sigma": 0.50, "min": 200.0,"decimals": 2},
                        },
                        "default": {"distribution": "lognormal", "mu": 4.6, "sigma": 0.9},
                        "min": 0.0,
                        "decimals": 2,
                    },
                ),
                Column(
                    name="status",
                    type="categorical",
                    distribution_params={
                        # ~15% churned users → ~15% cancelled; add paused for realism
                        "choices": ["active", "cancelled", "paused", "trialing"],
                        "probabilities": [0.68, 0.18, 0.08, 0.06],
                    },
                ),
                Column(
                    name="billing_cycle",
                    type="categorical",
                    distribution_params={
                        # Annual contracts dominate in healthy SaaS (lower churn)
                        "choices": ["monthly", "annual"],
                        "probabilities": [0.35, 0.65],
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
                events.append(
                    ScenarioEvent(
                        name="High_Churn_Period",
                        table="users",
                        column="churned",
                        condition="signup_date < '2023-06-01'",
                        modifier_type="set",
                        modifier_value=True,
                        description=f"Churn rate of {value*100:.0f}%",
                        # Cascade: mark matching subscriptions as cancelled
                        propagate_to={"subscriptions": {"status": "cancelled"}},
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
            domain="saas",
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
                Column(name="customer_id", type="int", unique=True, distribution_params={"min": 1, "max": num_customers * 2}),
                Column(name="email", type="text", unique=True, distribution_params={"text_type": "email"}),
                Column(name="name", type="text", distribution_params={"text_type": "name"}),
                Column(
                    name="signup_date",
                    type="date",
                    distribution_params={"start": "2022-01-01", "end": "2024-12-31"},
                ),
                Column(
                    name="country",
                    type="categorical",
                    distribution_params={
                        "choices": ["United States", "United Kingdom", "Canada", "Germany",
                                    "France", "Australia", "India", "Brazil", "Netherlands",
                                    "Sweden", "Spain", "Japan", "Singapore", "Mexico", "Italy"],
                        "probabilities": [0.32, 0.10, 0.07, 0.07, 0.06, 0.05, 0.07,
                                          0.04, 0.03, 0.03, 0.03, 0.04, 0.03, 0.03, 0.03],
                    },
                ),
            ],
            "orders": [
                Column(name="order_id", type="int", unique=True, distribution_params={"min": 1, "max": num_orders * 2}),
                Column(name="customer_id", type="foreign_key", distribution_params={}),
                Column(
                    name="order_date",
                    type="date",
                    distribution_params={"start": "2022-01-01", "end": "2024-12-31"},
                ),
                Column(
                    name="amount",
                    type="float",
                    # Domain prior: lognormal (mu=4.4, sigma=0.9) → median ~$81, mean ~$120
                    distribution_params={"min": 1.0, "decimals": 2},
                ),
                Column(
                    name="category",
                    type="categorical",
                    distribution_params={
                        # Zipf — electronics dominates, beauty trails off
                        "choices": ["electronics", "clothing", "home & garden", "sports", "books", "beauty"],
                        "sampling": "zipf",
                    },
                ),
                Column(
                    name="status",
                    type="categorical",
                    distribution_params={
                        # Real return/cancel rates: ~8% returned, ~4% cancelled
                        "choices": ["completed", "shipped", "pending", "returned", "cancelled"],
                        "probabilities": [0.72, 0.12, 0.08, 0.05, 0.03],
                    },
                ),
                Column(
                    name="payment_method",
                    type="categorical",
                    distribution_params={
                        "choices": ["credit_card", "debit_card", "paypal", "apple_pay", "bank_transfer"],
                        "probabilities": [0.45, 0.25, 0.15, 0.10, 0.05],
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
            domain="ecommerce",
            tables=tables,
            columns=columns,
            relationships=relationships,
            events=[],
            outcome_curves=[outcome_curve] if outcome_curve else [],
        )

    def _build_pharma_schema(self, story: str, default_rows: int) -> SchemaConfig:
        """Build a Pharma services-specific schema."""
        num_projects = self.scale_params.get("projects", max(1, default_rows // 100))
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
            domain="pharma",
            tables=tables,
            columns=columns,
            relationships=relationships,
            events=[],
            outcome_curves=[outcome_curve] if outcome_curve else [],
        )

    def _build_fintech_schema(self, story: str, default_rows: int) -> SchemaConfig:
        num_customers = self.scale_params.get("users", default_rows)
        num_transactions = self.scale_params.get("transactions", int(num_customers * 10))
        num_accounts = int(num_customers * 1.3)

        tables = [
            Table(name="customers", row_count=num_customers),
            Table(name="accounts", row_count=num_accounts),
            Table(name="transactions", row_count=num_transactions),
        ]
        columns = {
            "customers": [
                Column(name="customer_id", type="int", unique=True, distribution_params={"min": 1, "max": num_customers + 1}),
                Column(name="first_name", type="text", distribution_params={"text_type": "first_name"}),
                Column(name="last_name", type="text", distribution_params={"text_type": "last_name"}),
                Column(name="email", type="text", distribution_params={"text_type": "email"}),
                Column(name="credit_score", type="int", distribution_params={"distribution": "normal", "mean": 680, "std": 80, "min": 300, "max": 850}),
                Column(name="country", type="text", distribution_params={"text_type": "country"}),
                Column(name="created_at", type="date", distribution_params={"start": "2020-01-01", "end": "2024-12-31"}),
            ],
            "accounts": [
                Column(name="account_id", type="int", unique=True, distribution_params={"min": 1, "max": num_accounts + 1}),
                Column(name="customer_id", type="foreign_key"),
                Column(name="account_type", type="categorical", distribution_params={
                    "choices": ["checking", "savings", "investment", "credit"],
                    "sampling": "zipf",
                }),
                Column(name="balance", type="float", distribution_params={"min": 0.0, "decimals": 2}),
                Column(name="status", type="categorical", distribution_params={
                    "choices": ["active", "frozen", "closed"],
                    "probabilities": [0.85, 0.08, 0.07],
                }),
                Column(name="opened_at", type="date", distribution_params={"start": "2020-01-01", "end": "2024-12-31"}),
            ],
            "transactions": [
                Column(name="transaction_id", type="int", unique=True, distribution_params={"min": 1, "max": num_transactions + 1}),
                Column(name="account_id", type="foreign_key"),
                Column(name="amount", type="float", distribution_params={"min": 0.01, "decimals": 2}),
                Column(name="transaction_type", type="categorical", distribution_params={
                    "choices": ["purchase", "transfer", "withdrawal", "deposit", "refund"],
                    "sampling": "zipf",
                }),
                Column(name="status", type="categorical", distribution_params={
                    "choices": ["completed", "pending", "failed", "reversed"],
                    "probabilities": [0.88, 0.06, 0.04, 0.02],
                }),
                Column(name="transaction_date", type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
                Column(name="is_fraud", type="boolean", distribution_params={"probability": 0.02}),
            ],
        }
        relationships = [
            Relationship(parent_table="customers", child_table="accounts", parent_key="customer_id", child_key="customer_id"),
            Relationship(parent_table="accounts", child_table="transactions", parent_key="account_id", child_key="account_id"),
        ]
        outcome_curve = self._build_absolute_monthly_curve(
            story, table="transactions", column="amount", time_column="transaction_date", avg_transaction_value=250.0,
        )
        return SchemaConfig(
            name="Fintech Dataset", description=f"Generated from story: {story}",
            domain="fintech", tables=tables, columns=columns,
            relationships=relationships, events=[],
            outcome_curves=[outcome_curve] if outcome_curve else [],
        )

    def _build_healthcare_schema(self, story: str, default_rows: int) -> SchemaConfig:
        num_patients = self.scale_params.get("users", default_rows)
        # 1 doctor per ~20 patients; cap to avoid absurd doctor counts
        num_doctors = self.scale_params.get("doctors", min(max(10, num_patients // 20), 500))
        num_appointments = int(num_patients * 3)

        tables = [
            Table(name="doctors", row_count=num_doctors),
            Table(name="patients", row_count=num_patients),
            Table(name="appointments", row_count=num_appointments),
        ]
        columns = {
            "doctors": [
                Column(name="doctor_id", type="int", unique=True, distribution_params={"min": 1, "max": num_doctors + 1}),
                Column(name="first_name", type="text", distribution_params={"text_type": "first_name"}),
                Column(name="last_name", type="text", distribution_params={"text_type": "last_name"}),
                Column(name="specialty", type="categorical", distribution_params={
                    "choices": ["General Practice", "Cardiology", "Neurology", "Pediatrics", "Oncology", "Orthopedics", "Dermatology", "Psychiatry"],
                    "sampling": "zipf",
                }),
                Column(name="years_experience", type="int", distribution_params={"distribution": "normal", "mean": 12, "std": 7, "min": 1, "max": 40}),
            ],
            "patients": [
                Column(name="patient_id", type="int", unique=True, distribution_params={"min": 1, "max": num_patients + 1}),
                Column(name="first_name", type="text", distribution_params={"text_type": "first_name"}),
                Column(name="last_name", type="text", distribution_params={"text_type": "last_name"}),
                Column(name="age", type="int", distribution_params={"distribution": "normal", "mean": 45, "std": 18, "min": 0, "max": 100}),
                Column(name="gender", type="categorical", distribution_params={"choices": ["Male", "Female", "Non-binary"], "probabilities": [0.49, 0.49, 0.02]}),
                Column(name="blood_type", type="categorical", distribution_params={
                    "choices": ["O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"],
                    "probabilities": [0.38, 0.34, 0.09, 0.03, 0.07, 0.06, 0.02, 0.01],
                }),
                Column(name="registered_at", type="date", distribution_params={"start": "2018-01-01", "end": "2024-12-31"}),
            ],
            "appointments": [
                Column(name="appointment_id", type="int", unique=True, distribution_params={"min": 1, "max": num_appointments + 1}),
                Column(name="patient_id", type="foreign_key"),
                Column(name="doctor_id", type="foreign_key"),
                Column(name="appointment_date", type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
                Column(name="status", type="categorical", distribution_params={
                    "choices": ["completed", "scheduled", "cancelled", "no_show"],
                    "probabilities": [0.70, 0.15, 0.10, 0.05],
                }),
                Column(name="duration_minutes", type="int", distribution_params={"distribution": "normal", "mean": 25, "std": 10, "min": 5, "max": 90}),
                Column(name="type", type="categorical", distribution_params={
                    "choices": ["in-person", "telehealth", "follow-up", "emergency"],
                    "probabilities": [0.55, 0.25, 0.15, 0.05],
                }),
            ],
        }
        relationships = [
            Relationship(parent_table="patients", child_table="appointments", parent_key="patient_id", child_key="patient_id"),
            Relationship(parent_table="doctors", child_table="appointments", parent_key="doctor_id", child_key="doctor_id"),
        ]
        outcome_curve = self._build_absolute_monthly_curve(
            story, table="appointments", column="duration_minutes", time_column="appointment_date", avg_transaction_value=25.0,
        )
        return SchemaConfig(
            name="Healthcare Dataset", description=f"Generated from story: {story}",
            domain="healthcare", tables=tables, columns=columns,
            relationships=relationships, events=[],
            outcome_curves=[outcome_curve] if outcome_curve else [],
        )

    def _build_marketplace_schema(self, story: str, default_rows: int) -> SchemaConfig:
        num_users = self.scale_params.get("users", default_rows)
        num_sellers = max(10, num_users // 5)
        num_listings = int(num_sellers * 8)
        num_orders = int(num_users * 4)

        tables = [
            Table(name="sellers", row_count=num_sellers),
            Table(name="buyers", row_count=num_users),
            Table(name="listings", row_count=num_listings),
            Table(name="orders", row_count=num_orders),
        ]
        columns = {
            "sellers": [
                Column(name="seller_id", type="int", unique=True, distribution_params={"min": 1, "max": num_sellers + 1}),
                Column(name="name", type="text", distribution_params={"text_type": "name"}),
                Column(name="rating", type="float", distribution_params={"distribution": "beta", "a": 8.0, "b": 2.0, "min": 1.0, "max": 5.0, "decimals": 1}),
                Column(name="total_sales", type="int", distribution_params={"distribution": "lognormal", "mu": 3.5, "sigma": 1.2, "min": 0}),
                Column(name="joined_at", type="date", distribution_params={"start": "2019-01-01", "end": "2024-12-31"}),
                Column(name="verified", type="boolean", distribution_params={"probability": 0.65}),
            ],
            "buyers": [
                Column(name="buyer_id", type="int", unique=True, distribution_params={"min": 1, "max": num_users + 1}),
                Column(name="name", type="text", distribution_params={"text_type": "name"}),
                Column(name="email", type="text", distribution_params={"text_type": "email"}),
                Column(name="joined_at", type="date", distribution_params={"start": "2020-01-01", "end": "2024-12-31"}),
                Column(name="country", type="text", distribution_params={"text_type": "country"}),
            ],
            "listings": [
                Column(name="listing_id", type="int", unique=True, distribution_params={"min": 1, "max": num_listings + 1}),
                Column(name="seller_id", type="foreign_key"),
                Column(name="title", type="text", distribution_params={"text_type": "product_name"}),
                Column(name="category", type="categorical", distribution_params={
                    "choices": ["electronics", "clothing", "home", "sports", "books", "beauty"],
                    "sampling": "zipf",
                }),
                Column(name="price", type="float", distribution_params={"min": 1.0, "decimals": 2}),
                Column(name="status", type="categorical", distribution_params={
                    "choices": ["active", "sold", "paused", "removed"],
                    "probabilities": [0.60, 0.25, 0.10, 0.05],
                }),
                Column(name="created_at", type="date", distribution_params={"start": "2021-01-01", "end": "2024-12-31"}),
            ],
            "orders": [
                Column(name="order_id", type="int", unique=True, distribution_params={"min": 1, "max": num_orders + 1}),
                Column(name="buyer_id", type="foreign_key"),
                Column(name="listing_id", type="foreign_key"),
                Column(name="amount", type="float", distribution_params={"min": 1.0, "decimals": 2}),
                Column(name="status", type="categorical", distribution_params={
                    "choices": ["completed", "shipped", "pending", "refunded", "cancelled"],
                    "probabilities": [0.65, 0.15, 0.10, 0.06, 0.04],
                }),
                Column(name="ordered_at", type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
            ],
        }
        relationships = [
            Relationship(parent_table="sellers", child_table="listings", parent_key="seller_id", child_key="seller_id"),
            Relationship(parent_table="buyers", child_table="orders", parent_key="buyer_id", child_key="buyer_id"),
            Relationship(parent_table="listings", child_table="orders", parent_key="listing_id", child_key="listing_id"),
        ]
        outcome_curve = self._build_absolute_monthly_curve(
            story, table="orders", column="amount", time_column="ordered_at", avg_transaction_value=85.0,
        )
        return SchemaConfig(
            name="Marketplace Dataset", description=f"Generated from story: {story}",
            domain="marketplace", tables=tables, columns=columns,
            relationships=relationships, events=[],
            outcome_curves=[outcome_curve] if outcome_curve else [],
        )

    def _build_logistics_schema(self, story: str, default_rows: int) -> SchemaConfig:
        num_drivers = max(10, self.scale_params.get("users", default_rows // 50))
        num_vehicles = int(num_drivers * 1.2)
        num_shipments = self.scale_params.get("orders", default_rows)
        num_routes = max(5, num_drivers * 3)

        tables = [
            Table(name="drivers", row_count=num_drivers),
            Table(name="vehicles", row_count=num_vehicles),
            Table(name="routes", row_count=num_routes),
            Table(name="shipments", row_count=num_shipments),
        ]
        columns = {
            "drivers": [
                Column(name="driver_id", type="int", unique=True, distribution_params={"min": 1, "max": num_drivers + 1}),
                Column(name="first_name", type="text", distribution_params={"text_type": "first_name"}),
                Column(name="last_name", type="text", distribution_params={"text_type": "last_name"}),
                Column(name="license_class", type="categorical", distribution_params={
                    "choices": ["A", "B", "C", "CDL"],
                    "probabilities": [0.15, 0.45, 0.30, 0.10],
                }),
                Column(name="years_experience", type="int", distribution_params={"distribution": "lognormal", "mu": 2.0, "sigma": 0.8, "min": 0, "max": 40}),
                Column(name="status", type="categorical", distribution_params={
                    "choices": ["active", "on_leave", "inactive"],
                    "probabilities": [0.80, 0.12, 0.08],
                }),
            ],
            "vehicles": [
                Column(name="vehicle_id", type="int", unique=True, distribution_params={"min": 1, "max": num_vehicles + 1}),
                Column(name="driver_id", type="foreign_key"),
                Column(name="vehicle_type", type="categorical", distribution_params={
                    "choices": ["van", "truck", "semi", "motorcycle", "cargo_bike"],
                    "sampling": "zipf",
                }),
                Column(name="capacity_kg", type="float", distribution_params={"distribution": "lognormal", "mu": 6.5, "sigma": 1.0, "min": 10, "decimals": 0}),
                Column(name="year", type="int", distribution_params={"distribution": "normal", "mean": 2019, "std": 3, "min": 2010, "max": 2024}),
                Column(name="status", type="categorical", distribution_params={
                    "choices": ["available", "in_use", "maintenance"],
                    "probabilities": [0.50, 0.40, 0.10],
                }),
            ],
            "routes": [
                Column(name="route_id", type="int", unique=True, distribution_params={"min": 1, "max": num_routes + 1}),
                Column(name="origin_city", type="text", distribution_params={"text_type": "city"}),
                Column(name="destination_city", type="text", distribution_params={"text_type": "city"}),
                Column(name="distance_km", type="float", distribution_params={"distribution": "lognormal", "mu": 5.0, "sigma": 1.0, "min": 5, "decimals": 1}),
                Column(name="estimated_hours", type="float", distribution_params={"distribution": "lognormal", "mu": 2.5, "sigma": 0.7, "min": 0.5, "decimals": 1}),
            ],
            "shipments": [
                Column(name="shipment_id", type="int", unique=True, distribution_params={"min": 1, "max": num_shipments + 1}),
                Column(name="driver_id", type="foreign_key"),
                Column(name="route_id", type="foreign_key"),
                Column(name="weight_kg", type="float", distribution_params={"distribution": "lognormal", "mu": 3.0, "sigma": 1.0, "min": 0.1, "decimals": 1}),
                Column(name="status", type="categorical", distribution_params={
                    "choices": ["delivered", "in_transit", "pending", "failed", "returned"],
                    "probabilities": [0.70, 0.15, 0.08, 0.04, 0.03],
                }),
                Column(name="shipped_at", type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
                Column(name="delivered_at", type="date", distribution_params={"start": "2022-01-01", "end": "2025-06-30"}),
                Column(name="cost", type="float", distribution_params={"distribution": "lognormal", "mu": 3.5, "sigma": 0.8, "min": 5.0, "decimals": 2}),
            ],
        }
        relationships = [
            Relationship(parent_table="drivers", child_table="vehicles", parent_key="driver_id", child_key="driver_id"),
            Relationship(parent_table="drivers", child_table="shipments", parent_key="driver_id", child_key="driver_id"),
            Relationship(parent_table="routes", child_table="shipments", parent_key="route_id", child_key="route_id"),
        ]
        outcome_curve = self._build_absolute_monthly_curve(
            story, table="shipments", column="cost", time_column="shipped_at", avg_transaction_value=45.0,
        )
        return SchemaConfig(
            name="Logistics Dataset", description=f"Generated from story: {story}",
            domain="logistics", tables=tables, columns=columns,
            relationships=relationships, events=[],
            outcome_curves=[outcome_curve] if outcome_curve else [],
        )

    def _build_hr_schema(self, story: str, default_rows: int) -> SchemaConfig:
        """Build an HR / workforce schema."""
        num_employees   = self.scale_params.get("users", default_rows)
        # Real companies have 5-20 departments regardless of headcount
        num_departments = min(max(5, num_employees // 50), 20)
        num_payroll     = int(num_employees * 12)  # ~12 pay periods per employee

        tables = [
            Table(name="departments", row_count=num_departments),
            Table(name="employees",   row_count=num_employees),
            Table(name="payroll",     row_count=num_payroll),
        ]
        columns = {
            "departments": [
                Column(name="department_id", type="int", unique=True, distribution_params={"min": 1, "max": num_departments + 1}),
                Column(name="name", type="categorical", distribution_params={
                    "choices": ["Engineering", "Product", "Design", "Sales", "Marketing", "HR", "Finance", "Operations", "Legal", "Support"],
                    "sampling": "zipf",
                }),
                Column(name="headcount_budget", type="int", distribution_params={
                    "distribution": "lognormal", "mu": 2.8, "sigma": 0.8, "min": 2, "decimals": 0,
                }),
                Column(name="location", type="categorical", distribution_params={
                    "choices": ["Remote", "New York", "San Francisco", "Austin", "London", "Berlin", "Singapore"],
                    "probabilities": [0.35, 0.18, 0.15, 0.10, 0.10, 0.07, 0.05],
                }),
            ],
            "employees": [
                Column(name="employee_id", type="int", unique=True, distribution_params={"min": 1, "max": num_employees + 1}),
                Column(name="first_name", type="text", distribution_params={"text_type": "first_name"}),
                Column(name="last_name",  type="text", distribution_params={"text_type": "last_name"}),
                Column(name="email",      type="text", distribution_params={"text_type": "email"}),
                Column(name="department_id", type="foreign_key"),
                Column(name="role", type="categorical", distribution_params={
                    "choices": ["Individual Contributor", "Senior IC", "Staff", "Manager", "Director", "VP", "C-Level"],
                    "probabilities": [0.35, 0.25, 0.15, 0.13, 0.07, 0.04, 0.01],
                }),
                Column(name="salary", type="float", distribution_params={
                    # Conditional on seniority — role drives salary tier
                    "depends_on": "role",
                    "mapping": {
                        "Individual Contributor": {"distribution": "lognormal", "mu": 11.0, "sigma": 0.25, "min": 45000,  "decimals": 0},
                        "Senior IC":              {"distribution": "lognormal", "mu": 11.4, "sigma": 0.20, "min": 90000,  "decimals": 0},
                        "Staff":                  {"distribution": "lognormal", "mu": 11.7, "sigma": 0.20, "min": 130000, "decimals": 0},
                        "Manager":                {"distribution": "lognormal", "mu": 11.6, "sigma": 0.25, "min": 100000, "decimals": 0},
                        "Director":               {"distribution": "lognormal", "mu": 11.9, "sigma": 0.25, "min": 140000, "decimals": 0},
                        "VP":                     {"distribution": "lognormal", "mu": 12.2, "sigma": 0.30, "min": 200000, "decimals": 0},
                        "C-Level":                {"distribution": "lognormal", "mu": 12.7, "sigma": 0.40, "min": 300000, "decimals": 0},
                    },
                    "default": {"distribution": "lognormal", "mu": 11.2, "sigma": 0.30},
                    "decimals": 0,
                }),
                Column(name="hire_date", type="date", distribution_params={"start": "2018-01-01", "end": "2024-12-31"}),
                Column(name="tenure_years", type="float", distribution_params={
                    "distribution": "exponential", "scale": 3.2, "min": 0.0, "max": 20.0, "decimals": 1,
                }),
                Column(name="status", type="categorical", distribution_params={
                    "choices": ["active", "on_leave", "terminated"],
                    "probabilities": [0.88, 0.05, 0.07],
                }),
                Column(name="performance_score", type="float", distribution_params={
                    # Real performance distributions: most cluster around 3, few at extremes
                    "distribution": "beta", "a": 5.0, "b": 2.0, "min": 1.0, "max": 5.0, "decimals": 1,
                }),
            ],
            "payroll": [
                Column(name="payroll_id",  type="int", unique=True, distribution_params={"min": 1, "max": num_payroll + 1}),
                Column(name="employee_id", type="foreign_key"),
                Column(name="period_start", type="date", distribution_params={"start": "2023-01-01", "end": "2024-12-01"}),
                Column(name="gross_pay", type="float", distribution_params={
                    # Domain prior will apply salary-like lognormal
                    "distribution": "lognormal", "mu": 9.8, "sigma": 0.5, "min": 1500.0, "decimals": 2,
                }),
                Column(name="tax_withheld", type="float", distribution_params={
                    # ~22-32% effective tax rate
                    "distribution": "beta", "a": 3.0, "b": 7.0, "min": 0.18, "max": 0.40, "decimals": 4,
                }),
                Column(name="net_pay", type="float", distribution_params={
                    "distribution": "lognormal", "mu": 9.5, "sigma": 0.5, "min": 1000.0, "decimals": 2,
                }),
                Column(name="pay_type", type="categorical", distribution_params={
                    "choices": ["regular", "overtime", "bonus", "commission"],
                    "probabilities": [0.78, 0.10, 0.08, 0.04],
                }),
            ],
        }
        relationships = [
            Relationship(parent_table="departments", child_table="employees",
                         parent_key="department_id", child_key="department_id"),
            Relationship(parent_table="employees", child_table="payroll",
                         parent_key="employee_id", child_key="employee_id"),
        ]
        outcome_curve = self._build_absolute_monthly_curve(
            story, table="payroll", column="gross_pay", time_column="period_start", avg_transaction_value=6000.0,
        )
        return SchemaConfig(
            name="HR Dataset", description=f"Generated from story: {story}",
            domain="hr", tables=tables, columns=columns,
            relationships=relationships, events=[],
            outcome_curves=[outcome_curve] if outcome_curve else [],
        )

    def _build_realestate_schema(self, story: str, default_rows: int) -> SchemaConfig:
        """Build a real estate schema: agents, properties, transactions."""
        num_properties   = self.scale_params.get("properties", self.scale_params.get("users", default_rows))
        # Each agent handles ~15-25 listings; cap agents at a sensible number
        num_agents       = self.scale_params.get("agents", min(max(10, num_properties // 20), 500))
        num_transactions = int(num_properties * 0.6)  # ~60% of listings close

        tables = [
            Table(name="agents",       row_count=num_agents),
            Table(name="properties",   row_count=num_properties),
            Table(name="transactions", row_count=num_transactions),
        ]
        columns = {
            "agents": [
                Column(name="agent_id",         type="int",  unique=True, distribution_params={"min": 1, "max": num_agents + 1}),
                Column(name="first_name",        type="text", distribution_params={"text_type": "first_name"}),
                Column(name="last_name",         type="text", distribution_params={"text_type": "last_name"}),
                Column(name="email",             type="text", distribution_params={"text_type": "email"}),
                Column(name="years_experience",  type="int",  distribution_params={
                    "distribution": "lognormal", "mu": 1.8, "sigma": 0.9, "min": 1, "max": 40, "decimals": 0,
                }),
                Column(name="rating",            type="float", distribution_params={
                    # Agents who survive are rated high — right-skewed toward 5
                    "distribution": "beta", "a": 8.0, "b": 2.0, "min": 1.0, "max": 5.0, "decimals": 1,
                }),
                Column(name="total_sales",       type="int", distribution_params={
                    "distribution": "lognormal", "mu": 3.2, "sigma": 1.1, "min": 0, "decimals": 0,
                }),
                Column(name="agency", type="categorical", distribution_params={
                    "choices": ["Coldwell Banker", "RE/MAX", "Keller Williams", "Century 21", "eXp Realty", "Independent"],
                    "probabilities": [0.20, 0.18, 0.17, 0.15, 0.12, 0.18],
                }),
            ],
            "properties": [
                Column(name="property_id",  type="int",  unique=True, distribution_params={"min": 1, "max": num_properties + 1}),
                Column(name="agent_id",     type="foreign_key"),
                Column(name="property_type", type="categorical", distribution_params={
                    "choices": ["single_family", "condo", "townhouse", "multi_family", "land"],
                    "probabilities": [0.52, 0.25, 0.13, 0.07, 0.03],
                }),
                Column(name="bedrooms", type="int", distribution_params={
                    "choices": [1, 2, 3, 4, 5, 6],
                    "probabilities": [0.08, 0.22, 0.38, 0.22, 0.07, 0.03],
                }),
                Column(name="bathrooms", type="float", distribution_params={
                    "choices": [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
                    "probabilities": [0.10, 0.12, 0.35, 0.18, 0.15, 0.06, 0.04],
                }),
                Column(name="sqft", type="int", distribution_params={
                    # Real US home size: median ~1900 sqft, right-skewed
                    "distribution": "lognormal", "mu": 7.6, "sigma": 0.4, "min": 400, "decimals": 0,
                }),
                Column(name="list_price", type="float", distribution_params={
                    # US median home ~$410k, heavy right tail
                    "distribution": "lognormal", "mu": 12.9, "sigma": 0.7, "min": 50000, "decimals": 0,
                }),
                Column(name="city", type="text", distribution_params={"text_type": "city"}),
                Column(name="state", type="text", distribution_params={"text_type": "state"}),
                Column(name="listed_date", type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
                Column(name="status", type="categorical", distribution_params={
                    "choices": ["active", "pending", "sold", "withdrawn", "expired"],
                    "probabilities": [0.25, 0.12, 0.48, 0.09, 0.06],
                }),
            ],
            "transactions": [
                Column(name="transaction_id", type="int", unique=True, distribution_params={"min": 1, "max": num_transactions + 1}),
                Column(name="property_id",    type="foreign_key"),
                Column(name="sale_price",     type="float", distribution_params={
                    # Sale price slightly below/above list price — lognormal, median ~$400k
                    "distribution": "lognormal", "mu": 12.9, "sigma": 0.65, "min": 50000, "decimals": 0,
                }),
                Column(name="days_on_market", type="int", distribution_params={
                    # Real US DOM: median ~23 days, right-skewed
                    "distribution": "lognormal", "mu": 3.1, "sigma": 0.9, "min": 1, "max": 500, "decimals": 0,
                }),
                Column(name="close_date", type="date", distribution_params={"start": "2022-02-01", "end": "2025-01-31"}),
                Column(name="commission_pct", type="float", distribution_params={
                    # Typical agent commission: 2.5-3% per side
                    "distribution": "beta", "a": 5.0, "b": 3.0, "min": 0.02, "max": 0.04, "decimals": 4,
                }),
                Column(name="financing_type", type="categorical", distribution_params={
                    "choices": ["conventional", "FHA", "VA", "cash", "jumbo"],
                    "probabilities": [0.48, 0.18, 0.12, 0.15, 0.07],
                }),
            ],
        }
        relationships = [
            Relationship(parent_table="agents",     child_table="properties",   parent_key="agent_id",    child_key="agent_id"),
            Relationship(parent_table="properties", child_table="transactions", parent_key="property_id", child_key="property_id"),
        ]
        outcome_curve = self._build_absolute_monthly_curve(
            story, table="transactions", column="sale_price", time_column="close_date", avg_transaction_value=420000.0,
        )
        return SchemaConfig(
            name="Real Estate Dataset", description=f"Generated from story: {story}",
            domain="realestate", tables=tables, columns=columns,
            relationships=relationships, events=[],
            outcome_curves=[outcome_curve] if outcome_curve else [],
        )

    def _build_generic_schema(self, story: str, default_rows: int) -> SchemaConfig:
        """Build a generic schema when domain is not detected.

        Emits a warning so users know the parser fell back to a single generic
        table instead of a rich domain-specific schema.  They should either
        use more explicit keywords (e.g. "SaaS", "ecommerce") or switch to the
        LLM parser for open-ended stories.
        """
        import warnings
        warnings.warn(
            "StoryParser could not detect a domain from the story. "
            "Falling back to a single generic table. "
            "Add a domain keyword (saas, ecommerce, fintech, healthcare, marketplace, logistics) "
            "for a richer schema, or use LLMSchemaGenerator for open-ended stories.",
            UserWarning,
            stacklevel=3,
        )
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
