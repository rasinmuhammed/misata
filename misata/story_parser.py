"""
Story parser for converting natural language descriptions to SchemaConfig.

This module provides rule-based pattern matching to extract:
- Business domain (SaaS, E-commerce, Pharma, etc.)
- Scale parameters (number of users, transactions, etc.)
- Temporal patterns (growth, churn, seasonality, crashes)
- Data relationships
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from misata.schema import Column, OutcomeCurve, RateCurve, Relationship, ScenarioEvent, SchemaConfig, Table


@dataclass
class DetectionReport:
    """Structured account of what the StoryParser understood from a story.

    Returned by :meth:`StoryParser.detection_report` after :meth:`StoryParser.parse`.
    Use this to show a confirmation/preview step before generating data — the
    no-code studio surfaces it as a "did we understand you correctly?" panel,
    and the CLI prints it before any rows are written.

    Attributes:
        domain: Detected domain code (e.g. "saas") or None if no domain matched.
        domain_confidence: ``"high"`` (multiple keywords matched in the same domain),
            ``"low"`` (single keyword), or ``"none"`` (no domain detected).
        matched_keywords: Keywords from the detected domain that appeared in the story.
        near_misses: ``{domain: [keywords]}`` for *other* domains whose keywords also
            appeared. Useful for ambiguous stories ("a fintech with crypto wallets"
            could match both fintech and crypto).
        scale_params: Parsed scale signals (``{"users": 5000, "orders": 10000, ...}``).
        temporal_events: Detected events (``[{type, value}, ...]``).
        locale: Auto-detected locale code (e.g. "de_DE") or None.
        table_preview: ``[{name, rows, columns}]`` for every table that will be generated.
        total_rows: Sum of all ``table_preview`` row counts.
        warnings: Human-readable warnings (fallback to generic, ambiguous domain, etc.).
    """

    domain: Optional[str] = None
    domain_confidence: str = "none"
    matched_keywords: List[str] = field(default_factory=list)
    near_misses: Dict[str, List[str]] = field(default_factory=dict)
    scale_params: Dict[str, int] = field(default_factory=dict)
    temporal_events: List[Dict[str, Any]] = field(default_factory=list)
    locale: Optional[str] = None
    table_preview: List[Dict[str, Any]] = field(default_factory=list)
    total_rows: int = 0
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """Render a concise multi-line summary suitable for CLI / notebook output."""
        lines: List[str] = []
        if self.domain:
            confidence_marker = {"high": "✓", "low": "?", "none": "✗"}.get(
                self.domain_confidence, "?"
            )
            kw_str = ", ".join(self.matched_keywords[:3])
            if len(self.matched_keywords) > 3:
                kw_str += f" (+{len(self.matched_keywords) - 3})"
            lines.append(
                f"{confidence_marker} Domain: {self.domain}  [{self.domain_confidence}]"
                + (f"  matched: {kw_str}" if kw_str else "")
            )
        else:
            lines.append("✗ Domain: not detected (using generic single-table fallback)")

        if self.near_misses:
            other = ", ".join(
                f"{d}({', '.join(kws[:2])})" for d, kws in self.near_misses.items()
            )
            lines.append(f"  Other matches considered: {other}")

        if self.locale:
            lines.append(f"✓ Locale: {self.locale}")

        if self.scale_params:
            scale_str = ", ".join(f"{k}={v:,}" for k, v in self.scale_params.items())
            lines.append(f"✓ Scale: {scale_str}")

        if self.temporal_events:
            lines.append(f"✓ Events: {len(self.temporal_events)} detected")

        if self.table_preview:
            lines.append("")
            lines.append(f"  Will generate {len(self.table_preview)} table(s), "
                         f"{self.total_rows:,} total rows:")
            col_w = max(len(t["name"]) for t in self.table_preview) + 2
            for t in self.table_preview:
                lines.append(
                    f"    {t['name']:<{col_w}} {t['rows']:>10,} rows  "
                    f"({t['columns']} columns)"
                )

        for w in self.warnings:
            lines.append(f"⚠ {w}")

        return "\n".join(lines)


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
        # fooddelivery before ecommerce — "orders" and "courier" appear in both; food signals win
        "fooddelivery": ["food delivery", "ubereats", "doordash", "grubhub", "restaurant delivery", "meal delivery", "takeout", "takeaway", "food app", "restaurants", "menu items"],
        "ecommerce": ["ecommerce", "e-commerce", "orders", "cart", "products", "shop", "store", "retail"],
        "pharma": ["pharma", "research", "timesheet", "clinical", "trials"],
        # crypto before fintech — both have "wallet"; crypto signals are more specific
        "crypto": ["crypto", "blockchain", "web3", "defi", "nft", "ethereum", "bitcoin", "solana", "smart contract", "dex", "dao", "crypto exchange", "token sale", "on-chain"],
        "fintech": ["fintech", "transactions", "payments", "wallet", "banking", "loans", "credit", "fraud"],
        "healthcare": ["healthcare", "health", "patients", "doctors", "hospital", "clinic", "appointments", "medical"],
        # social before marketplace — "platform" alone is too generic; social signals are distinct
        "social": ["social media", "instagram", "tiktok", "twitter", "feed", "followers", "likes", "influencer", "content creator", "creator economy", "reels", "social network"],
        # realestate before marketplace — both have "listings" and "agents" as keywords
        "realestate": ["real estate", "realty", "housing", "mortgage", "homes for sale", "property listing"],
        "marketplace": ["marketplace", "gig", "freelance", "sellers", "buyers", "listings"],
        "logistics": ["logistics", "shipping", "delivery", "fleet", "warehouse", "supply chain", "routes", "drivers"],
        "hr": ["hr", "human resources", "employees", "payroll", "workforce", "hiring", "headcount", "salaries", "onboarding"],
        "edtech": ["edtech", "e-learning", "lms", "courses", "students", "instructors", "lessons", "enrollments", "quizzes", "learning platform", "online learning"],
        "gaming": ["gaming", "game", "players", "leaderboard", "achievements", "quests", "guilds", "matches", "sessions", "levels", "esports", "rpg"],
        # crm before marketplace — "deals" and "contacts" are CRM-specific
        "crm": ["crm", "salesforce", "hubspot", "contacts", "deals", "pipeline", "leads", "opportunities", "sales pipeline", "account management"],
        "insurance": ["insurance", "policy", "claim", "premium", "coverage", "underwriting", "actuary", "insurer", "policyholder", "risk assessment"],
        "travel": ["travel", "hotel", "flights", "bookings", "airline", "airbnb", "booking.com", "expedia", "hospitality", "reservations", "trips", "itinerary", "tourism"],
        "streaming": ["streaming", "netflix", "spotify", "watch history", "content library", "subscribers", "watchlist", "episodes", "series", "vod", "ott", "media platform"],
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
        "slump": 0.72,
        "crash": 0.5,
        "decline": 0.75,
        "slow": 0.8,
        "low": 0.8,
        "flat": 1.0,
        "strong": 1.15,
        "push": 1.2,
        "high": 1.2,
        "peak": 1.25,
        "boom": 1.3,
        "spike": 1.3,
        "surge": 1.3,
    }

    # Maps quarter labels to their constituent calendar months.
    QUARTER_MONTHS: Dict[str, List[int]] = {
        "q1": [1, 2, 3],
        "q2": [4, 5, 6],
        "q3": [7, 8, 9],
        "q4": [10, 11, 12],
    }

    # Named seasonal/commercial events → (month, relative factor).
    # Multi-month events use None and are handled explicitly.
    NAMED_EVENT_MODIFIERS: Dict[str, Any] = {
        "new year": (1, 1.25),
        "valentine": (2, 1.2),
        "tax season": (4, 1.2),
        "back to school": (8, 1.2),
        "back-to-school": (8, 1.2),
        "black friday": (11, 1.55),
        "cyber monday": (11, 1.45),
        "cyber week": (11, 1.4),
        "christmas": (12, 1.4),
        "xmas": (12, 1.4),
        "holiday season": (12, 1.35),
        "festive season": (12, 1.3),
        "summer slump": None,   # handled below: months 7+8 → 0.75
        "summer lull": None,
        "slow summer": None,
    }

    # Word-form and Nx multipliers that indicate overall growth factor.
    WORD_MULTIPLIERS: Dict[str, float] = {
        "halved": 0.5,
        "doubled": 2.0,
        "tripled": 3.0,
        "quadrupled": 4.0,
        "10x": 10.0,
        "5x": 5.0,
        "3x": 3.0,
        "2x": 2.0,
    }

    def __init__(self):
        """Initialize the story parser."""
        self.detected_domain: Optional[str] = None
        self.scale_params: Dict[str, int] = {}
        self.temporal_events: List[Tuple[str, Any]] = []
        # Populated by parse() — exposed via detection_report()
        self._matched_keywords: List[str] = []
        self._near_misses: Dict[str, List[str]] = {}
        self._detection_warnings: List[str] = []
        self._last_schema: Optional[SchemaConfig] = None
        self.detected_locale: Optional[str] = None

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
        """Detect business domain from story text.

        Scoring (highest score wins; dict order is the tiebreaker):
          • +5  if the literal domain name appears in the story
                ("fintech" → fintech, "crypto" → crypto). This is the
                user's strongest explicit signal and beats any generic
                keyword hit.
          • +1  per matched keyword.

        Records every domain that matched into ``self._matched_keywords``
        (winning domain) and ``self._near_misses`` (every other domain
        with at least one keyword hit) for the DetectionReport.
        """
        story_lower = story.lower()
        all_matches: Dict[str, List[str]] = {}
        scores: Dict[str, int] = {}

        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            hits = [kw for kw in keywords if kw in story_lower]
            if not hits:
                continue
            score = len(hits)
            # Literal domain name (e.g. "fintech") is the strongest signal —
            # explicit user intent beats incidental keyword matches like
            # "churn" appearing in a fintech-but-mentions-subscriptions story.
            if domain in story_lower:
                score += 5
            all_matches[domain] = hits
            scores[domain] = score

        if not all_matches:
            self._matched_keywords = []
            self._near_misses = {}
            return None

        # Highest score wins; ties broken by DOMAIN_KEYWORDS order (precedence).
        domain_order = list(self.DOMAIN_KEYWORDS.keys())
        winner = max(
            all_matches,
            key=lambda d: (scores[d], -domain_order.index(d)),
        )
        self._matched_keywords = all_matches[winner]
        self._near_misses = {d: kws for d, kws in all_matches.items() if d != winner}
        return winner

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

        # Process month-then-value first, then value-then-month — so the more
        # explicit "$50k in Jan" form overwrites the looser "Jan 50k" form when
        # both match the same month.
        for match in list(month_then_value) + list(value_then_month):
            month_token = match.group("month").lower()
            month_number = self.MONTHS.get(month_token[:3], self.MONTHS.get(month_token))
            if month_number is None:
                continue
            raw_value = match.group("value").strip().lower()
            # Skip "January 2023" — when the value is a bare 4-digit number in
            # the year range, it's a calendar year, not a target value.
            cleaned = raw_value.replace("$", "").replace(",", "").strip()
            if (
                cleaned.isdigit()
                and len(cleaned) == 4
                and 1900 <= int(cleaned) <= 2100
            ):
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

    _MONTH_RE = (
        r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?"
        r"|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    )

    def _extract_qualitative_month_modifiers(self, story: str) -> Dict[int, float]:
        """Extract qualitative modifiers — months, quarters, and named events.

        Handles three pattern families:
        * ``"dip in September"`` / ``"peak in Q4"`` — explicit keyword + period
        * ``"Q3 slump"`` / ``"strong Q4"`` — qualifier before or after a quarter
        * Named events: ``"Black Friday"`` → Nov ×1.55, ``"summer slump"`` → Jul+Aug ×0.75
        """
        modifiers: Dict[int, float] = {}

        # ── month-level keyword modifiers ──────────────────────────────────
        for keyword, factor in self.QUALITATIVE_MONTH_FACTORS.items():
            # "dip in September", "peak in Dec"
            for match in re.finditer(
                rf"{keyword}\s+in\s+({self._MONTH_RE})", story, re.IGNORECASE
            ):
                month_token = match.group(1).lower()
                m = self.MONTHS.get(month_token[:3], self.MONTHS.get(month_token))
                if m is not None:
                    modifiers[m] = factor

        # ── quarter-level keyword modifiers ────────────────────────────────
        for keyword, factor in self.QUALITATIVE_MONTH_FACTORS.items():
            for pattern in (
                rf"{keyword}\s+in\s+(q[1-4])\b",   # "dip in Q3"
                rf"(q[1-4])\s+{keyword}\b",         # "Q3 dip"
                rf"\b(q[1-4])\s+(?:was\s+(?:a\s+)?)?{keyword}\b",  # "Q3 was a peak"
                rf"{keyword}(?:s)?\s+(?:in|during|through)\s+(q[1-4])\b",  # "peaks in Q4"
                rf"{keyword}\s+(q[1-4])\b",         # "strong Q4", "slow Q1"
            ):
                for match in re.finditer(pattern, story, re.IGNORECASE):
                    quarter = match.group(1).lower()
                    for m in self.QUARTER_MONTHS.get(quarter, []):
                        modifiers[m] = factor

        # ── named commercial / seasonal events ─────────────────────────────
        story_lower = story.lower()
        for event, effect in self.NAMED_EVENT_MODIFIERS.items():
            if event not in story_lower:
                continue
            if effect is None:
                # summer slump / slow summer → July + August
                modifiers[7] = min(modifiers.get(7, 1.0), 0.75)
                modifiers[8] = min(modifiers.get(8, 1.0), 0.75)
            else:
                month, factor = effect
                modifiers[month] = max(modifiers.get(month, 1.0), factor)

        return modifiers

    def _extract_multiplier_growth(self, story: str) -> Optional[float]:
        """Return the overall end-of-period multiplier implied by the story.

        Recognises:
        * Word forms: ``"doubled"``, ``"tripled"``, ``"halved"``
        * Nx notation: ``"10x growth"``, ``"5x increase"``, ``"2x"``, ``"3x jump"``
        * Percentage: ``"grew 300%"`` (300% = 4× starting value, i.e. 3× *increase*)

        Returns ``None`` when no multiplier pattern is detected.
        """
        story_lower = story.lower()

        # Word forms
        for word, factor in self.WORD_MULTIPLIERS.items():
            if re.search(rf"\b{re.escape(word)}\b", story_lower):
                return factor

        # Nx patterns (e.g. "10x growth", "3x increase", "5x in Q4")
        nx_match = re.search(
            r"\b(\d+(?:\.\d+)?)x\b(?:\s+(?:growth|increase|jump|surge|rise|gain))?",
            story_lower,
        )
        if nx_match:
            return float(nx_match.group(1))

        # "grew / increased / jumped N%" where N > 100 implies multiplicative factor
        pct_match = re.search(
            r"\b(?:grew|grown|increased?|jumped?|surged?)\s+(\d+(?:\.\d+)?)%",
            story_lower,
        )
        if pct_match:
            pct = float(pct_match.group(1))
            if pct > 100:
                return 1.0 + pct / 100.0  # 300% growth → 4× total

        return None

    def _extract_quarter_anchors(self, story: str) -> Dict[int, float]:
        """Extract quarter-level numeric anchors like ``"$100k in Q2"`` or ``"Q3: $150k"``.

        Expands each quarter anchor to its three constituent months, filling any
        gaps that ``_extract_target_month_points`` couldn't find.
        """
        anchors: Dict[int, float] = {}

        # "$50k in Q2", "Q1: $30k", "Q3 = $200k", "$100k for Q4"
        for pattern in (
            r"(?P<value>\$?\d[\d,]*(?:\.\d+)?\s*[kmb]?)\s+(?:in|for|by|at)\s+(?P<q>q[1-4])\b",
            r"\b(?P<q>q[1-4])\b\s*(?::|=|at|was|is|=)?\s*(?P<value>\$?\d[\d,]*(?:\.\d+)?\s*[kmb]?)",
        ):
            for match in re.finditer(pattern, story, re.IGNORECASE):
                quarter = match.group("q").lower()
                months = self.QUARTER_MONTHS.get(quarter, [])
                val = self._parse_numeric_value(match.group("value"))
                for m in months:
                    anchors.setdefault(m, val)

        return anchors

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
        "slump", "boom", "doubled", "tripled", "halved",
        "black friday", "christmas", "summer slump",
        "q1", "q2", "q3", "q4",
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
        # Extend the trigger set with multiplier + quarter + named event signals
        extended_signals = list(self.CURVE_SIGNAL_TOKENS) + list(self.WORD_MULTIPLIERS) + [
            "q1", "q2", "q3", "q4",
            "black friday", "christmas", "summer slump", "doubled", "tripled",
        ]
        if not any(token in story_lower for token in extended_signals):
            return None

        period_count = self._extract_period_count(story)
        anchors = self._extract_target_month_points(story, period_count)
        modifiers = self._extract_qualitative_month_modifiers(story)
        multiplier = self._extract_multiplier_growth(story)

        # Merge in quarter-level anchors (lower priority than explicit month anchors)
        for m, v in self._extract_quarter_anchors(story).items():
            anchors.setdefault(m, v)

        # Convert a multiplier into endpoint anchors so everything flows through
        # the same linear-interpolation path.
        if multiplier is not None:
            if not anchors:
                # No anchors at all: derive a baseline and create start→end anchors
                baseline = (avg_transaction_value or 1.0) * max(
                    self.scale_params.get(
                        "orders", self.scale_params.get("users", 1000)
                    ) / period_count,
                    1.0,
                )
                anchors = {1: baseline, period_count: baseline * multiplier}
            elif len(anchors) == 1:
                # One explicit anchor: use it as the pivot point.
                pivot_month, pivot_val = next(iter(sorted(anchors.items())))
                if pivot_month <= period_count // 2:
                    # Anchor is early → treat as start, derive end
                    anchors = {pivot_month: pivot_val, period_count: pivot_val * multiplier}
                else:
                    # Anchor is late → treat as end, back-derive start
                    anchors = {1: pivot_val / multiplier, pivot_month: pivot_val}
            # With >= 2 explicit anchors the user has been precise — honour those.
            multiplier = None  # absorbed

        # If we still have no anchors and no modifiers, nothing to shape
        if len(anchors) < 2 and not modifiers:
            return None

        months = np.arange(1, period_count + 1)

        if len(anchors) >= 2:
            x_known = np.array(sorted(anchors.keys()), dtype=float)
            y_known = np.array([anchors[int(m)] for m in x_known], dtype=float)
            interpolated = np.interp(months, x_known, y_known)
        elif len(anchors) == 1:
            # One anchor + qualitative modifiers: use the anchor as a flat baseline
            baseline_val = next(iter(anchors.values()))
            interpolated = np.full(period_count, baseline_val, dtype=float)
        else:
            # Pure qualitative: derive a flat baseline from avg_transaction_value
            baseline_val = (avg_transaction_value or 1.0) * max(
                self.scale_params.get("orders", self.scale_params.get("users", 1000)) / period_count,
                1.0,
            )
            interpolated = np.full(period_count, baseline_val, dtype=float)

        # Ensure interpolated is always a plain float64 ndarray.
        interpolated = np.asarray(interpolated, dtype=float)

        # Apply qualitative modifiers (dip, peak, spike, quarter patterns, named events)
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

    # ── Rate-noun → (candidate column names, true_value) ──────────────────
    # Each entry maps a natural-language rate noun to the boolean column names
    # that domain templates may produce, plus the value that represents the
    # positive class.  The simulator's _enforce_rate_curve picks the first
    # candidate column name that actually exists in the generated table.
    RATE_NOUN_MAP: Dict[str, Dict[str, Any]] = {
        "fraud":       {"columns": ["is_fraud", "is_fraudulent", "fraud"], "true_value": True},
        "fraudulent":  {"columns": ["is_fraudulent", "is_fraud"],          "true_value": True},
        "churn":       {"columns": ["is_churned", "churned"],               "true_value": True},
        "churned":     {"columns": ["is_churned", "churned"],               "true_value": True},
        "defect":      {"columns": ["is_defective", "defective"],           "true_value": True},
        "defective":   {"columns": ["is_defective", "defective"],           "true_value": True},
        "late":        {"columns": ["is_late", "late", "is_delayed"],       "true_value": True},
        "delayed":     {"columns": ["is_delayed", "is_late"],               "true_value": True},
        "default":     {"columns": ["is_defaulted", "defaulted"],           "true_value": True},
        "defaulted":   {"columns": ["is_defaulted", "defaulted"],           "true_value": True},
        "cancelled":   {"columns": ["is_cancelled", "cancelled", "status"], "true_value": True},
        "returned":    {"columns": ["is_returned", "returned"],              "true_value": True},
        "active":      {"columns": ["is_active", "active"],                 "true_value": True},
        "inactive":    {"columns": ["is_active", "active"],                 "true_value": False},
    }

    # Column names considered as the "time" axis, in priority order.
    _TIME_COLUMN_CANDIDATES = ["date", "created_at", "transaction_date", "order_date",
                                "event_date", "signup_date", "timestamp", "payment_date"]

    def _resolve_rate_time_column(self, schema: SchemaConfig, table_name: str) -> str:
        """Return the most plausible time column for a given table in the schema."""
        cols = {c.name for c in schema.get_columns(table_name)}
        for candidate in self._TIME_COLUMN_CANDIDATES:
            if candidate in cols:
                return candidate
        # Fallback: first date-typed column
        for col in schema.get_columns(table_name):
            if col.type == "date":
                return col.name
        return "date"

    def _extract_rate_curves(self, story: str, schema: SchemaConfig) -> List[RateCurve]:
        """Extract RateCurve constraints from natural-language stories.

        Recognises three pattern families:

        1. **Flat rate**: ``"2% fraud rate"`` → single anchor covering all periods.
        2. **Period-specific**: ``"3% fraud in Q1"`` → one anchor at month 2 (Q1 midpoint).
        3. **Rising / falling range**: ``"3% fraud in Q1 rising to 8% by Q4"`` →
           two anchor points with ``interpolate=True``.

        The method is deliberately conservative — it only emits a RateCurve when
        the rate noun maps to a known boolean column that exists (or will exist) in
        the schema, and the detected rate is in (0, 1).  Ambiguous or unparseable
        patterns are silently skipped.

        Args:
            story:  Raw user story text.
            schema: The SchemaConfig already built by the domain builder.

        Returns:
            List of ``RateCurve`` objects to attach to ``schema.rate_curves``.
        """
        story_lower = story.lower()
        curves: List[RateCurve] = []

        # Quarter → representative month index for anchor points.
        _Q_MID = {"q1": 2, "q2": 5, "q3": 8, "q4": 11}
        _Q_LAST = {"q1": 3, "q2": 6, "q3": 9, "q4": 12}

        _MONTH_RE = (
            r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?"
            r"|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?"
            r"|nov(?:ember)?|dec(?:ember)?"
        )
        _Q_RE = r"q[1-4]"
        _PERIOD_RE = rf"(?:{_MONTH_RE}|{_Q_RE})"

        def _period_to_month(tok: str) -> int:
            tok = tok.lower()
            if tok in _Q_MID:
                return _Q_MID[tok]
            if tok in _Q_LAST:
                return _Q_LAST[tok]
            return self.MONTHS.get(tok[:3], self.MONTHS.get(tok, 1))

        def _end_period_to_month(tok: str) -> int:
            """Use the LAST month of a quarter as the end anchor."""
            tok = tok.lower()
            if tok in _Q_LAST:
                return _Q_LAST[tok]
            return self.MONTHS.get(tok[:3], self.MONTHS.get(tok, 12))

        # Try each known rate noun in the story
        for noun, spec in self.RATE_NOUN_MAP.items():
            # Must appear in the story
            if not re.search(rf"\b{re.escape(noun)}\b", story_lower):
                continue

            # Find the target table and column in the schema
            target_table: Optional[str] = None
            target_col: Optional[str] = None
            for table in schema.tables:
                col_names = {c.name for c in schema.get_columns(table.name)}
                for cand in spec["columns"]:
                    if cand in col_names:
                        target_table = table.name
                        target_col = cand
                        break
                if target_col:
                    break

            if target_table is None or target_col is None:
                continue  # noun present but column not in schema — skip

            time_col = self._resolve_rate_time_column(schema, target_table)

            # ── Pattern 3: rising / falling range ─────────────────────────
            # "3% fraud in Q1 rising/climbing/growing/dropping to 8% by Q4"
            range_match = re.search(
                rf"(\d+(?:\.\d+)?)%\s*(?:[\w\s]{{0,12}})?{re.escape(noun)}[\w\s]{{0,30}}?"
                rf"(?:in|during|at)?\s*({_PERIOD_RE})\s*"
                rf"(?:rising|climbing|growing|increasing|falling|dropping|declining)\s*to\s*"
                rf"(\d+(?:\.\d+)?)%\s*(?:by|in|at)?\s*({_PERIOD_RE})",
                story_lower,
                re.IGNORECASE,
            )
            if not range_match:
                # Also try reversed noun-first form: "fraud rising from 3% in Q1 to 8% by Q4"
                range_match = re.search(
                    rf"{re.escape(noun)}[\w\s]{{0,20}}?"
                    rf"(?:from)?\s*(\d+(?:\.\d+)?)%\s*(?:in|at)?\s*({_PERIOD_RE})\s*"
                    rf"(?:to|through|until)\s*(\d+(?:\.\d+)?)%\s*(?:by|in|at)?\s*({_PERIOD_RE})",
                    story_lower,
                    re.IGNORECASE,
                )

            if range_match:
                r1 = float(range_match.group(1)) / 100.0
                p1 = _period_to_month(range_match.group(2))
                r2 = float(range_match.group(3)) / 100.0
                p2 = _end_period_to_month(range_match.group(4))
                if 0 < r1 <= 1 and 0 < r2 <= 1 and p1 != p2:
                    curves.append(RateCurve(
                        table=target_table,
                        column=target_col,
                        time_column=time_col,
                        true_value=spec["true_value"],
                        interpolate=True,
                        description=f"NL-extracted: {noun} {r1*100:.1f}%→{r2*100:.1f}%",
                        rate_points=[
                            {"period": str(p1), "rate": round(r1, 6)},
                            {"period": str(p2), "rate": round(r2, 6)},
                        ],
                    ))
                    continue  # Don't also add a flat anchor for the same noun

            # ── Pattern 2: single period anchor ───────────────────────────
            # "3% fraud in Q1" / "fraud rate of 5% in January"
            period_match = re.search(
                rf"(\d+(?:\.\d+)?)%\s*(?:[\w\s]{{0,12}})?{re.escape(noun)}[\w\s]{{0,20}}?"
                rf"(?:in|during|at|for)?\s*({_PERIOD_RE})",
                story_lower,
                re.IGNORECASE,
            )
            if not period_match:
                period_match = re.search(
                    rf"{re.escape(noun)}[\w\s]{{0,20}}?"
                    rf"(?:of|at|=)?\s*(\d+(?:\.\d+)?)%\s*(?:in|during|at)?\s*({_PERIOD_RE})",
                    story_lower,
                    re.IGNORECASE,
                )

            if period_match:
                r = float(period_match.group(1)) / 100.0
                p = _period_to_month(period_match.group(2))
                if 0 < r <= 1:
                    curves.append(RateCurve(
                        table=target_table,
                        column=target_col,
                        time_column=time_col,
                        true_value=spec["true_value"],
                        interpolate=False,
                        description=f"NL-extracted: {noun} {r*100:.1f}% at period {p}",
                        rate_points=[{"period": str(p), "rate": round(r, 6)}],
                    ))
                    continue

            # ── Pattern 1: flat rate — no period qualifier ─────────────────
            # "2% fraud rate" / "fraud rate of 2%" / "2% fraudulent transactions"
            flat_match = re.search(
                rf"(\d+(?:\.\d+)?)%\s*(?:[\w]{{0,15}}\s*){{0,3}}{re.escape(noun)}",
                story_lower,
                re.IGNORECASE,
            ) or re.search(
                rf"{re.escape(noun)}\s+(?:rate\s+)?(?:of\s+)?(\d+(?:\.\d+)?)%",
                story_lower,
                re.IGNORECASE,
            )
            if flat_match:
                r = float(flat_match.group(1)) / 100.0
                if 0 < r <= 1:
                    curves.append(RateCurve(
                        table=target_table,
                        column=target_col,
                        time_column=time_col,
                        true_value=spec["true_value"],
                        interpolate=False,
                        description=f"NL-extracted: flat {noun} rate {r*100:.1f}%",
                        rate_points=[{"period": "all", "rate": round(r, 6)}],
                    ))

        # Deduplicate: keep the most complex curve (most anchor points) per
        # (table, column) pair in case multiple patterns matched.
        seen: Dict[tuple, RateCurve] = {}
        for rc in curves:
            key = (rc.table, rc.column)
            existing = seen.get(key)
            if existing is None or len(rc.rate_points) > len(existing.rate_points):
                seen[key] = rc
        return list(seen.values())

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
        elif self.detected_domain == "social":
            schema = self._build_social_schema(story, default_rows)
        elif self.detected_domain == "realestate":
            schema = self._build_realestate_schema(story, default_rows)
        elif self.detected_domain == "fooddelivery":
            schema = self._build_fooddelivery_schema(story, default_rows)
        elif self.detected_domain == "edtech":
            schema = self._build_edtech_schema(story, default_rows)
        elif self.detected_domain == "gaming":
            schema = self._build_gaming_schema(story, default_rows)
        elif self.detected_domain == "crm":
            schema = self._build_crm_schema(story, default_rows)
        elif self.detected_domain == "crypto":
            schema = self._build_crypto_schema(story, default_rows)
        elif self.detected_domain == "insurance":
            schema = self._build_insurance_schema(story, default_rows)
        elif self.detected_domain == "travel":
            schema = self._build_travel_schema(story, default_rows)
        elif self.detected_domain == "streaming":
            schema = self._build_streaming_schema(story, default_rows)
        else:
            schema = self._build_generic_schema(story, default_rows)

        # Inject detected locale into realism config
        if self.detected_locale:
            if schema.realism is None:
                from misata.schema import RealismConfig
                object.__setattr__(schema, "realism", RealismConfig())
            object.__setattr__(schema.realism, "locale", self.detected_locale)

        # Build detection warnings (consumed by detection_report())
        self._detection_warnings = []
        if self.detected_domain is None:
            self._detection_warnings.append(
                "No domain detected. Falling back to a generic single-table schema. "
                "Add a domain keyword (e.g. 'saas', 'fintech', 'ecommerce') for a richer schema."
            )
        if self._near_misses:
            other_domains = ", ".join(self._near_misses.keys())
            self._detection_warnings.append(
                f"Story also matched: {other_domains}. The highest-scoring domain won; "
                "name the desired domain literally (e.g. 'fintech') if you want a different one."
            )

        # Gap A: extract RateCurve constraints from the story and attach them
        # to the schema.  This runs AFTER the domain builder so it can resolve
        # column names against the produced table definitions.
        detected_rate_curves = self._extract_rate_curves(story, schema)
        if detected_rate_curves:
            existing = list(getattr(schema, "rate_curves", []) or [])
            # Use model_copy to stay immutable; fall back to object.__setattr__
            try:
                schema = schema.model_copy(update={"rate_curves": existing + detected_rate_curves})
            except Exception:
                object.__setattr__(schema, "rate_curves", existing + detected_rate_curves)

        # Cache the produced schema so detection_report() can preview tables
        self._last_schema = schema
        return schema

    def detection_report(self) -> "DetectionReport":
        """Return a structured account of what was detected by the most recent ``parse()``.

        Call this *after* :meth:`parse` to preview detected domain, scale, locale,
        and the tables that will be generated — useful for confirmation flows in
        no-code UIs and for explaining ambiguous stories.

        Example::

            >>> parser = StoryParser()
            >>> parser.parse("A fintech with crypto wallets and 5k users")
            >>> print(parser.detection_report().summary())

        Returns:
            DetectionReport (dataclass) with domain, confidence, near misses,
            scale, events, locale, table preview, and warnings.
        """
        confidence = "none"
        if self.detected_domain:
            confidence = "high" if len(self._matched_keywords) >= 2 else "low"

        events = [
            {"type": ev_type, "value": value}
            for ev_type, value in self.temporal_events
        ]

        table_preview: List[Dict[str, Any]] = []
        total_rows = 0
        if self._last_schema is not None:
            for tbl in self._last_schema.tables:
                rows = tbl.row_count or 0
                total_rows += rows
                table_preview.append(
                    {
                        "name": tbl.name,
                        "rows": rows,
                        "columns": len(self._last_schema.get_columns(tbl.name)),
                    }
                )

        return DetectionReport(
            domain=self.detected_domain,
            domain_confidence=confidence,
            matched_keywords=list(self._matched_keywords),
            near_misses={d: list(kws) for d, kws in self._near_misses.items()},
            scale_params=dict(self.scale_params),
            temporal_events=events,
            locale=self.detected_locale,
            table_preview=table_preview,
            total_rows=total_rows,
            warnings=list(self._detection_warnings),
        )

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

        # Wire any declared churn RATE directly into the churned column's probability,
        # so "20% churn" actually yields ~20% churned (previously the rate was only used
        # in a description string while a date-condition event set ~55% churned).
        churn_rate = next((v for et, v in self.temporal_events if et == "churn"), None)
        if churn_rate is not None:
            for col in columns.get("users", []):
                if col.name == "churned":
                    col.distribution_params["probability"] = float(churn_rate)

        # Build scenario events from temporal patterns
        events = []
        for event_type, value in self.temporal_events:
            if event_type == "churn":
                # The proportion is now controlled by the churned column's probability
                # (set above). We keep a cascade so cancelled subscriptions track churn,
                # but condition it on the churned flag rather than an arbitrary date.
                events.append(
                    ScenarioEvent(
                        name="Churn_Cascade",
                        table="users",
                        column="churned",
                        condition="churned == True",
                        modifier_type="set",
                        modifier_value=True,
                        description=f"Churn rate of {value*100:.0f}%",
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
        num_products = max(50, num_customers // 5)
        num_orders = self.scale_params.get("orders", int(num_customers * 3))

        tables = [
            Table(name="customers", row_count=num_customers),
            Table(name="products",  row_count=num_products),
            Table(name="orders",    row_count=num_orders),
        ]

        columns = {
            "customers": [
                Column(name="customer_id", type="int", unique=True, distribution_params={"min": 1, "max": num_customers * 2}),
                Column(name="email", type="text", unique=True, distribution_params={"text_type": "email"}),
                Column(name="name", type="text", distribution_params={"text_type": "name"}),
                Column(name="signup_date", type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
                Column(name="country", type="categorical", distribution_params={
                    "choices": ["United States", "United Kingdom", "Canada", "Germany",
                                "France", "Australia", "India", "Brazil", "Netherlands",
                                "Sweden", "Spain", "Japan", "Singapore", "Mexico", "Italy"],
                    "probabilities": [0.32, 0.10, 0.07, 0.07, 0.06, 0.05, 0.07,
                                      0.04, 0.03, 0.03, 0.03, 0.04, 0.03, 0.03, 0.03],
                }),
            ],
            "products": [
                Column(name="product_id", type="int", unique=True, distribution_params={"min": 1, "max": num_products + 1}),
                Column(name="name", type="text", distribution_params={"text_type": "product_name"}),
                Column(name="category", type="categorical", distribution_params={
                    "choices": ["electronics", "clothing", "home & garden", "sports", "books", "beauty"],
                    "sampling": "zipf",
                }),
                Column(name="price", type="float", distribution_params={
                    "distribution": "lognormal", "mu": 4.2, "sigma": 1.2, "min": 0.99, "max": 2000.0, "decimals": 2,
                }),
                Column(name="stock_count", type="int", distribution_params={
                    "distribution": "lognormal", "mu": 4.0, "sigma": 1.0, "min": 0, "max": 5000, "decimals": 0,
                }),
                Column(name="rating", type="float", distribution_params={
                    "distribution": "beta", "a": 6.0, "b": 2.0, "min": 1.0, "max": 5.0, "decimals": 1,
                }),
            ],
            "orders": [
                Column(name="order_id",    type="int", unique=True, distribution_params={"min": 1, "max": num_orders * 2}),
                Column(name="customer_id", type="foreign_key"),
                Column(name="product_id",  type="foreign_key"),
                Column(name="quantity", type="int", distribution_params={
                    "distribution": "lognormal", "mu": 0.5, "sigma": 0.6, "min": 1, "max": 20, "decimals": 0,
                }),
                Column(name="order_date", type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
                Column(name="amount", type="float", distribution_params={"min": 1.0, "decimals": 2}),
                Column(name="status", type="categorical", distribution_params={
                    "choices": ["completed", "shipped", "pending", "returned", "cancelled"],
                    "probabilities": [0.72, 0.12, 0.08, 0.05, 0.03],
                }),
                Column(name="payment_method", type="categorical", distribution_params={
                    "choices": ["credit_card", "debit_card", "paypal", "apple_pay", "bank_transfer"],
                    "probabilities": [0.45, 0.25, 0.15, 0.10, 0.05],
                }),
            ],
        }

        relationships = [
            Relationship(parent_table="customers", child_table="orders", parent_key="customer_id", child_key="customer_id"),
            Relationship(parent_table="products",  child_table="orders", parent_key="product_id",  child_key="product_id"),
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
                Column(name="project_id", type="int", unique=True, distribution_params={"min": 1, "max": num_projects + 1}),
                Column(name="project_name", type="text", distribution_params={"text_type": "research_project_name"}),
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
                Column(name="entry_id", type="int", unique=True, distribution_params={"min": 1, "max": num_timesheets + 1}),
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
        if re.search(r"\b(cpf|aadhaar|ssn|national id|national_id|kyc)\b", story, re.IGNORECASE):
            columns["customers"].insert(
                4,
                Column(name="national_id", type="text", distribution_params={"text_type": "national_id"}),
            )
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
                Column(name="age", type="int", distribution_params={"distribution": "normal", "mean": 45, "std": 18, "min": 1, "max": 100}),
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
        num_sellers = self.scale_params.get("sellers", max(10, num_users // 5))
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
                Column(name="price", type="float", distribution_params={
                    "distribution": "lognormal", "mu": 4.5, "sigma": 1.5, "min": 0.99, "max": 50000, "decimals": 2,
                }),
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
                Column(name="amount", type="float", distribution_params={
                    "distribution": "lognormal", "mu": 4.5, "sigma": 1.2, "min": 0.99, "max": 50000, "decimals": 2,
                }),
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
                Column(name="estimated_hours", type="float", distribution_params={"distribution": "lognormal", "mu": 1.8, "sigma": 0.6, "min": 0.5, "max": 16.0, "decimals": 1}),
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
                Column(name="delivered_at", type="date", distribution_params={
                    "after_column": "shipped_at", "min_delta_days": 1, "max_delta_days": 21,
                    "null_if": {"column": "status", "values": ["pending", "in_transit", "failed", "returned"]},
                }),
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
                Column(name="email",          type="text", distribution_params={"text_type": "email"}),
                Column(name="date_of_birth", type="date", distribution_params={"start": "1960-01-01", "end": "2000-12-31"}),
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
                Column(name="hire_date", type="date", distribution_params={
                    "after_column": "date_of_birth", "min_delta_days": 6570, "max_delta_days": 18250,
                    "max_date": "today",
                }),
                Column(name="tenure_years", type="float", distribution_params={
                    "date_diff_to": "hire_date", "decimals": 1, "max": 40.0,
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
                    # Monthly pay: median ~$5k (ln(5000)≈8.5); sigma gives realistic spread
                    "distribution": "lognormal", "mu": 8.5, "sigma": 0.5, "min": 1200.0, "decimals": 2,
                }),
                Column(name="tax_withheld", type="float", distribution_params={
                    # ~22-32% effective tax rate
                    "distribution": "beta", "a": 3.0, "b": 7.0, "min": 0.18, "max": 0.40, "decimals": 4,
                }),
                Column(name="net_pay", type="float", distribution_params={
                    # Net = gross × (1 − tax_withheld); formula ensures row-level consistency
                    "formula": "gross_pay * (1 - tax_withheld)", "decimals": 2,
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
        num_transactions = max(1, int(num_properties * 0.6))  # ~60% of listings close

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
                Column(name="state", type="categorical", distribution_params={
                    "choices": ["California", "Texas", "Florida", "New York", "Illinois",
                                "Pennsylvania", "Ohio", "Georgia", "North Carolina", "Michigan",
                                "New Jersey", "Virginia", "Washington", "Arizona", "Colorado"],
                    "probabilities": [0.15, 0.12, 0.08, 0.08, 0.06, 0.06, 0.06, 0.06,
                                      0.05, 0.05, 0.05, 0.04, 0.04, 0.03, 0.07],
                }),
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

    def _build_social_schema(self, story: str, default_rows: int) -> SchemaConfig:
        """Build a social media / creator-economy schema.

        Tables: users, posts, follows, reactions, comments.
        Follower counts follow a power-law (Pareto) — a small number of
        accounts capture most of the reach, matching real platform data.
        """
        num_users    = self.scale_params.get("users", default_rows)
        # Posts: ~3-5 per active user; reactions: ~20 per post; comments: ~4 per post
        num_posts     = int(num_users * 4)
        num_follows   = int(num_users * 15)   # avg 15 follow edges per account
        num_reactions = int(num_posts * 20)
        num_comments  = int(num_posts * 4)

        tables = [
            Table(name="users",     row_count=num_users),
            Table(name="posts",     row_count=num_posts),
            Table(name="follows",   row_count=num_follows),
            Table(name="reactions", row_count=num_reactions),
            Table(name="comments",  row_count=num_comments),
        ]
        columns = {
            "users": [
                Column(name="user_id",    type="int",  unique=True, distribution_params={"min": 1, "max": num_users + 1}),
                Column(name="username",   type="text", distribution_params={"text_type": "username"}),
                Column(name="display_name", type="text", distribution_params={"text_type": "name"}),
                Column(name="email",      type="text", distribution_params={"text_type": "email"}),
                Column(name="bio",        type="text", distribution_params={"text_type": "bio"}),
                Column(name="account_type", type="categorical", distribution_params={
                    "choices": ["personal", "creator", "brand", "business"],
                    "probabilities": [0.70, 0.18, 0.07, 0.05],
                }),
                Column(name="follower_count", type="int", distribution_params={
                    # Power-law approximated with lognormal: median ~250, tail reaches millions
                    "distribution": "lognormal", "mu": 5.5, "sigma": 2.5, "min": 10, "max": 50_000_000, "decimals": 0,
                }),
                Column(name="following_count", type="int", distribution_params={
                    "distribution": "lognormal", "mu": 5.5, "sigma": 1.2, "min": 0, "max": 5000, "decimals": 0,
                }),
                Column(name="post_count", type="int", distribution_params={
                    "distribution": "lognormal", "mu": 3.5, "sigma": 1.5, "min": 0, "max": 50_000, "decimals": 0,
                }),
                Column(name="verified", type="boolean", distribution_params={"probability": 0.03}),
                Column(name="joined_date", type="date", distribution_params={"start": "2018-01-01", "end": "2024-12-31"}),
                Column(name="is_active", type="boolean", distribution_params={"probability": 0.78}),
            ],
            "posts": [
                Column(name="post_id",    type="int", unique=True, distribution_params={"min": 1, "max": num_posts + 1}),
                Column(name="user_id",    type="foreign_key"),
                Column(name="content_type", type="categorical", distribution_params={
                    "choices": ["photo", "video", "reel", "story", "text", "carousel"],
                    "probabilities": [0.35, 0.25, 0.18, 0.12, 0.06, 0.04],
                }),
                Column(name="caption",    type="text", distribution_params={"text_type": "caption"}),
                Column(name="like_count", type="int", distribution_params={
                    # Engagement follows a power-law relative to account size
                    "distribution": "lognormal", "mu": 3.8, "sigma": 2.0, "min": 0, "decimals": 0,
                }),
                Column(name="comment_count", type="int", distribution_params={
                    "distribution": "lognormal", "mu": 2.0, "sigma": 1.8, "min": 0, "decimals": 0,
                }),
                Column(name="share_count", type="int", distribution_params={
                    "distribution": "lognormal", "mu": 1.2, "sigma": 1.6, "min": 0, "decimals": 0,
                }),
                Column(name="view_count", type="int", distribution_params={
                    "distribution": "lognormal", "mu": 5.5, "sigma": 2.2, "min": 0, "decimals": 0,
                }),
                Column(name="engagement_rate", type="float", distribution_params={
                    # Real average engagement: 1-5% for most creators
                    "distribution": "beta", "a": 1.5, "b": 20.0, "min": 0.001, "max": 0.30, "decimals": 4,
                }),
                Column(name="hashtag_count", type="int", distribution_params={
                    "choices": [0, 1, 2, 3, 5, 8, 10, 15, 20, 30],
                    "probabilities": [0.10, 0.08, 0.10, 0.12, 0.15, 0.15, 0.12, 0.10, 0.05, 0.03],
                }),
                Column(name="posted_at",  type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
                Column(name="is_sponsored", type="boolean", distribution_params={"probability": 0.06}),
            ],
            "follows": [
                Column(name="follow_id",   type="int", unique=True, distribution_params={"min": 1, "max": num_follows + 1}),
                Column(name="follower_id", type="foreign_key"),
                Column(name="followee_id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": num_users + 1}),
                Column(name="followed_at", type="date", distribution_params={"start": "2018-01-01", "end": "2024-12-31"}),
                Column(name="is_mutual",   type="boolean", distribution_params={"probability": 0.42}),
            ],
            "reactions": [
                Column(name="reaction_id", type="int", unique=True, distribution_params={"min": 1, "max": num_reactions + 1}),
                Column(name="post_id",     type="foreign_key"),
                Column(name="user_id",     type="int", distribution_params={"distribution": "uniform", "min": 1, "max": num_users + 1}),
                Column(name="reaction_type", type="categorical", distribution_params={
                    "choices": ["like", "love", "haha", "wow", "sad", "angry"],
                    "probabilities": [0.65, 0.18, 0.07, 0.05, 0.03, 0.02],
                }),
                Column(name="reacted_at",  type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
            ],
            "comments": [
                Column(name="comment_id", type="int", unique=True, distribution_params={"min": 1, "max": num_comments + 1}),
                Column(name="post_id",    type="foreign_key"),
                Column(name="user_id",    type="int", distribution_params={"distribution": "uniform", "min": 1, "max": num_users + 1}),
                Column(name="body",       type="text", distribution_params={"text_type": "comment_body"}),
                Column(name="like_count", type="int", distribution_params={
                    "distribution": "lognormal", "mu": 1.0, "sigma": 1.5, "min": 0, "decimals": 0,
                }),
                Column(name="is_reply",   type="boolean", distribution_params={"probability": 0.35}),
                Column(name="parent_comment_id", type="int", distribution_params={"min": 1, "max": num_comments + 1}),
                Column(name="commented_at", type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
            ],
        }
        relationships = [
            Relationship(parent_table="users", child_table="posts",
                         parent_key="user_id", child_key="user_id"),
            Relationship(parent_table="users", child_table="follows",
                         parent_key="user_id", child_key="follower_id"),
            Relationship(parent_table="posts", child_table="reactions",
                         parent_key="post_id", child_key="post_id"),
            Relationship(parent_table="posts", child_table="comments",
                         parent_key="post_id", child_key="post_id"),
        ]
        return SchemaConfig(
            name="Social Media Dataset", description=f"Generated from story: {story}",
            domain="social", tables=tables, columns=columns,
            relationships=relationships, events=[],
        )

    def _build_fooddelivery_schema(self, story: str, default_rows: int) -> SchemaConfig:
        num_restaurants = max(20, self.scale_params.get("restaurants", max(50, default_rows // 20)))
        num_customers   = self.scale_params.get("users", default_rows)
        num_couriers    = max(10, num_restaurants // 2)
        num_orders      = self.scale_params.get("orders", default_rows)
        num_items       = int(num_orders * 2.5)

        tables = [
            Table(name="restaurants",  row_count=num_restaurants),
            Table(name="customers",    row_count=num_customers),
            Table(name="couriers",     row_count=num_couriers),
            Table(name="orders",       row_count=num_orders),
            Table(name="order_items",  row_count=num_items),
        ]
        columns = {
            "restaurants": [
                Column(name="restaurant_id", type="int", unique=True, distribution_params={"min": 1, "max": num_restaurants + 1}),
                Column(name="name",          type="text", distribution_params={"text_type": "restaurant_name"}),
                Column(name="cuisine_type",  type="categorical", distribution_params={
                    "choices": ["italian", "chinese", "indian", "mexican", "american", "japanese", "thai", "mediterranean", "korean", "pizza"],
                    "probabilities": [0.13, 0.12, 0.11, 0.10, 0.12, 0.10, 0.09, 0.08, 0.08, 0.07],
                }),
                Column(name="city",          type="text", distribution_params={"text_type": "city"}),
                Column(name="rating",        type="float", distribution_params={"distribution": "beta", "a": 6.0, "b": 2.0, "min": 1.0, "max": 5.0, "decimals": 1}),
                Column(name="delivery_fee",  type="float", distribution_params={"distribution": "lognormal", "mu": 1.5, "sigma": 0.5, "min": 0.99, "max": 9.99, "decimals": 2}),
                Column(name="min_order",     type="float", distribution_params={"distribution": "lognormal", "mu": 2.5, "sigma": 0.4, "min": 5.0, "max": 50.0, "decimals": 2}),
                Column(name="avg_prep_minutes", type="int", distribution_params={"distribution": "normal", "mean": 22, "std": 8, "min": 8, "max": 60}),
                Column(name="is_active",     type="boolean", distribution_params={"probability": 0.90}),
                Column(name="joined_date",   type="date", distribution_params={"start": "2019-01-01", "end": "2024-06-30"}),
            ],
            "customers": [
                Column(name="customer_id",   type="int", unique=True, distribution_params={"min": 1, "max": num_customers + 1}),
                Column(name="first_name",    type="text", distribution_params={"text_type": "first_name"}),
                Column(name="last_name",     type="text", distribution_params={"text_type": "last_name"}),
                Column(name="email",         type="text", distribution_params={"text_type": "email"}),
                Column(name="city",          type="text", distribution_params={"text_type": "city"}),
                Column(name="signup_date",   type="date", distribution_params={"start": "2020-01-01", "end": "2024-12-31"}),
                Column(name="total_orders",  type="int", distribution_params={"distribution": "lognormal", "mu": 2.5, "sigma": 1.2, "min": 1, "max": 500, "decimals": 0}),
                Column(name="is_premium",    type="boolean", distribution_params={"probability": 0.18}),
            ],
            "couriers": [
                Column(name="courier_id",    type="int", unique=True, distribution_params={"min": 1, "max": num_couriers + 1}),
                Column(name="first_name",    type="text", distribution_params={"text_type": "first_name"}),
                Column(name="last_name",     type="text", distribution_params={"text_type": "last_name"}),
                Column(name="vehicle_type",  type="categorical", distribution_params={
                    "choices": ["bicycle", "scooter", "motorcycle", "car"],
                    "probabilities": [0.25, 0.35, 0.25, 0.15],
                }),
                Column(name="rating",        type="float", distribution_params={"distribution": "beta", "a": 7.0, "b": 1.5, "min": 1.0, "max": 5.0, "decimals": 2}),
                Column(name="total_deliveries", type="int", distribution_params={"distribution": "lognormal", "mu": 5.5, "sigma": 1.5, "min": 1, "max": 10000, "decimals": 0}),
                Column(name="status",        type="categorical", distribution_params={
                    "choices": ["available", "on_delivery", "offline"],
                    "probabilities": [0.40, 0.45, 0.15],
                }),
                Column(name="joined_date",   type="date", distribution_params={"start": "2020-01-01", "end": "2024-12-31"}),
            ],
            "orders": [
                Column(name="order_id",      type="int", unique=True, distribution_params={"min": 1, "max": num_orders + 1}),
                Column(name="customer_id",   type="foreign_key"),
                Column(name="restaurant_id", type="foreign_key"),
                Column(name="courier_id",    type="foreign_key"),
                Column(name="status",        type="categorical", distribution_params={
                    "choices": ["delivered", "in_transit", "preparing", "cancelled", "refunded"],
                    "probabilities": [0.72, 0.12, 0.08, 0.05, 0.03],
                }),
                Column(name="subtotal",      type="float", distribution_params={"distribution": "lognormal", "mu": 3.2, "sigma": 0.7, "min": 5.0, "max": 300.0, "decimals": 2}),
                Column(name="delivery_fee",  type="float", distribution_params={"distribution": "lognormal", "mu": 1.5, "sigma": 0.5, "min": 0.99, "max": 9.99, "decimals": 2}),
                Column(name="tip_amount",    type="float", distribution_params={"distribution": "lognormal", "mu": 1.2, "sigma": 0.8, "min": 0.0, "max": 30.0, "decimals": 2}),
                Column(name="payment_method", type="categorical", distribution_params={
                    "choices": ["credit_card", "debit_card", "paypal", "apple_pay", "google_pay", "cash"],
                    "probabilities": [0.38, 0.25, 0.14, 0.10, 0.09, 0.04],
                }),
                Column(name="placed_at",     type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
                Column(name="delivered_at",  type="date", distribution_params={
                    "after_column": "placed_at", "min_delta_days": 0, "max_delta_days": 1,
                    "null_if": {"column": "status", "values": ["cancelled", "refunded"]},
                }),
                Column(name="delivery_minutes", type="int", distribution_params={"distribution": "normal", "mean": 38, "std": 12, "min": 15, "max": 120}),
                Column(name="customer_rating", type="float", distribution_params={"distribution": "beta", "a": 5.0, "b": 1.5, "min": 1.0, "max": 5.0, "decimals": 1}),
            ],
            "order_items": [
                Column(name="item_id",       type="int", unique=True, distribution_params={"min": 1, "max": num_items + 1}),
                Column(name="order_id",      type="foreign_key"),
                Column(name="item_name",     type="text", distribution_params={"text_type": "menu_item"}),
                Column(name="category",      type="categorical", distribution_params={
                    "choices": ["main", "side", "drink", "dessert", "starter", "combo"],
                    "probabilities": [0.40, 0.20, 0.18, 0.10, 0.07, 0.05],
                }),
                Column(name="quantity",      type="int", distribution_params={"distribution": "lognormal", "mu": 0.4, "sigma": 0.6, "min": 1, "max": 10, "decimals": 0}),
                Column(name="unit_price",    type="float", distribution_params={"distribution": "lognormal", "mu": 2.3, "sigma": 0.6, "min": 1.5, "max": 60.0, "decimals": 2}),
                Column(name="special_instructions", type="boolean", distribution_params={"probability": 0.15}),
            ],
        }
        relationships = [
            Relationship(parent_table="customers",   child_table="orders",      parent_key="customer_id",   child_key="customer_id"),
            Relationship(parent_table="restaurants", child_table="orders",      parent_key="restaurant_id", child_key="restaurant_id"),
            Relationship(parent_table="couriers",    child_table="orders",      parent_key="courier_id",    child_key="courier_id"),
            Relationship(parent_table="orders",      child_table="order_items", parent_key="order_id",      child_key="order_id"),
        ]
        return SchemaConfig(
            name="Food Delivery Dataset", description=f"Generated from story: {story}",
            domain="fooddelivery", tables=tables, columns=columns,
            relationships=relationships, events=[],
        )

    def _build_edtech_schema(self, story: str, default_rows: int) -> SchemaConfig:
        num_instructors = max(10, self.scale_params.get("instructors", max(20, default_rows // 30)))
        num_courses     = max(20, self.scale_params.get("courses", max(50, default_rows // 10)))
        num_students    = self.scale_params.get("users", default_rows)
        num_enrollments = self.scale_params.get("orders", int(num_students * 2.5))
        num_attempts    = int(num_enrollments * 3)

        tables = [
            Table(name="instructors",  row_count=num_instructors),
            Table(name="courses",      row_count=num_courses),
            Table(name="students",     row_count=num_students),
            Table(name="enrollments",  row_count=num_enrollments),
            Table(name="quiz_attempts", row_count=num_attempts),
        ]
        columns = {
            "instructors": [
                Column(name="instructor_id", type="int", unique=True, distribution_params={"min": 1, "max": num_instructors + 1}),
                Column(name="first_name",    type="text", distribution_params={"text_type": "first_name"}),
                Column(name="last_name",     type="text", distribution_params={"text_type": "last_name"}),
                Column(name="email",         type="text", distribution_params={"text_type": "email"}),
                Column(name="expertise",     type="categorical", distribution_params={
                    "choices": ["programming", "data_science", "design", "business", "marketing", "photography", "music", "language", "finance", "health"],
                    "probabilities": [0.22, 0.18, 0.12, 0.11, 0.10, 0.07, 0.07, 0.06, 0.05, 0.02],
                }),
                Column(name="rating",        type="float", distribution_params={"distribution": "beta", "a": 7.0, "b": 2.0, "min": 1.0, "max": 5.0, "decimals": 2}),
                Column(name="total_courses",  type="int", distribution_params={"distribution": "lognormal", "mu": 1.8, "sigma": 0.9, "min": 1, "max": 50, "decimals": 0}),
                Column(name="joined_date",    type="date", distribution_params={"start": "2018-01-01", "end": "2023-12-31"}),
            ],
            "courses": [
                Column(name="course_id",    type="int", unique=True, distribution_params={"min": 1, "max": num_courses + 1}),
                Column(name="instructor_id", type="foreign_key"),
                Column(name="title",         type="text", distribution_params={"text_type": "product_name"}),
                Column(name="category",      type="categorical", distribution_params={
                    "choices": ["programming", "data_science", "design", "business", "marketing", "photography", "music", "language", "finance", "health"],
                    "probabilities": [0.22, 0.18, 0.12, 0.11, 0.10, 0.07, 0.07, 0.06, 0.05, 0.02],
                }),
                Column(name="level",         type="categorical", distribution_params={
                    "choices": ["beginner", "intermediate", "advanced", "all_levels"],
                    "probabilities": [0.35, 0.38, 0.18, 0.09],
                }),
                Column(name="price",         type="float", distribution_params={"distribution": "lognormal", "mu": 3.5, "sigma": 0.7, "min": 0.0, "max": 199.99, "decimals": 2}),
                Column(name="duration_hours", type="float", distribution_params={"distribution": "lognormal", "mu": 2.8, "sigma": 0.8, "min": 0.5, "max": 80.0, "decimals": 1}),
                Column(name="num_lessons",    type="int", distribution_params={"distribution": "lognormal", "mu": 2.5, "sigma": 0.7, "min": 3, "max": 200, "decimals": 0}),
                Column(name="rating",         type="float", distribution_params={"distribution": "beta", "a": 6.0, "b": 2.0, "min": 1.0, "max": 5.0, "decimals": 2}),
                Column(name="enrolled_count", type="int", distribution_params={"distribution": "lognormal", "mu": 6.5, "sigma": 2.0, "min": 0, "max": 500_000, "decimals": 0}),
                Column(name="is_free",        type="boolean", distribution_params={"probability": 0.12}),
                Column(name="published_at",   type="date", distribution_params={"start": "2019-01-01", "end": "2024-12-31"}),
            ],
            "students": [
                Column(name="student_id",    type="int", unique=True, distribution_params={"min": 1, "max": num_students + 1}),
                Column(name="first_name",    type="text", distribution_params={"text_type": "first_name"}),
                Column(name="last_name",     type="text", distribution_params={"text_type": "last_name"}),
                Column(name="email",         type="text", distribution_params={"text_type": "email"}),
                Column(name="country",       type="text", distribution_params={"text_type": "country"}),
                Column(name="signup_date",   type="date", distribution_params={"start": "2019-01-01", "end": "2024-12-31"}),
                Column(name="is_premium",    type="boolean", distribution_params={"probability": 0.22}),
                Column(name="total_courses_enrolled", type="int", distribution_params={"distribution": "lognormal", "mu": 1.5, "sigma": 1.2, "min": 1, "max": 200, "decimals": 0}),
            ],
            "enrollments": [
                Column(name="enrollment_id", type="int", unique=True, distribution_params={"min": 1, "max": num_enrollments + 1}),
                Column(name="student_id",    type="foreign_key"),
                Column(name="course_id",     type="foreign_key"),
                Column(name="enrolled_at",   type="date", distribution_params={"start": "2020-01-01", "end": "2024-12-31"}),
                Column(name="status",        type="categorical", distribution_params={
                    "choices": ["active", "completed", "dropped", "paused"],
                    "probabilities": [0.38, 0.42, 0.12, 0.08],
                }),
                Column(name="progress_pct",  type="float", distribution_params={"distribution": "beta", "a": 1.5, "b": 1.2, "min": 0.0, "max": 100.0, "decimals": 1}),
                Column(name="completed_at",  type="date", distribution_params={
                    "after_column": "enrolled_at", "min_delta_days": 7, "max_delta_days": 365,
                    "null_if": {"column": "status", "values": ["active", "dropped", "paused"]},
                }),
                Column(name="certificate_issued", type="boolean", distribution_params={"probability": 0.38}),
                Column(name="rating_given",  type="float", distribution_params={
                    "distribution": "beta", "a": 5.0, "b": 1.5, "min": 1.0, "max": 5.0, "decimals": 1,
                    "null_if": {"column": "status", "values": ["active", "dropped", "paused"]},
                }),
            ],
            "quiz_attempts": [
                Column(name="attempt_id",    type="int", unique=True, distribution_params={"min": 1, "max": num_attempts + 1}),
                Column(name="enrollment_id", type="foreign_key"),
                Column(name="quiz_number",   type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 10}),
                Column(name="score_pct",     type="float", distribution_params={"distribution": "beta", "a": 4.0, "b": 2.0, "min": 0.0, "max": 100.0, "decimals": 1}),
                Column(name="passed",        type="boolean", distribution_params={"probability": 0.72}),
                Column(name="time_taken_minutes", type="int", distribution_params={"distribution": "normal", "mean": 18, "std": 8, "min": 2, "max": 90}),
                Column(name="attempted_at",  type="date", distribution_params={"start": "2020-01-01", "end": "2024-12-31"}),
            ],
        }
        relationships = [
            Relationship(parent_table="instructors", child_table="courses",      parent_key="instructor_id", child_key="instructor_id"),
            Relationship(parent_table="students",    child_table="enrollments",  parent_key="student_id",    child_key="student_id"),
            Relationship(parent_table="courses",     child_table="enrollments",  parent_key="course_id",     child_key="course_id"),
            Relationship(parent_table="enrollments", child_table="quiz_attempts", parent_key="enrollment_id", child_key="enrollment_id"),
        ]
        return SchemaConfig(
            name="EdTech Dataset", description=f"Generated from story: {story}",
            domain="edtech", tables=tables, columns=columns,
            relationships=relationships, events=[],
        )

    def _build_gaming_schema(self, story: str, default_rows: int) -> SchemaConfig:
        num_players   = self.scale_params.get("users", default_rows)
        num_matches   = self.scale_params.get("orders", int(num_players * 5))
        num_sessions  = int(num_players * 8)
        num_achievements = int(num_players * 4)

        tables = [
            Table(name="players",      row_count=num_players),
            Table(name="matches",      row_count=num_matches),
            Table(name="sessions",     row_count=num_sessions),
            Table(name="achievements", row_count=num_achievements),
        ]
        columns = {
            "players": [
                Column(name="player_id",    type="int", unique=True, distribution_params={"min": 1, "max": num_players + 1}),
                Column(name="username",     type="text", distribution_params={"text_type": "username"}),
                Column(name="email",        type="text", distribution_params={"text_type": "email"}),
                Column(name="country",      type="text", distribution_params={"text_type": "country"}),
                Column(name="level",        type="int", distribution_params={"distribution": "lognormal", "mu": 3.2, "sigma": 1.1, "min": 1, "max": 100, "decimals": 0}),
                Column(name="rank",         type="categorical", distribution_params={
                    "choices": ["bronze", "silver", "gold", "platinum", "diamond", "master", "grandmaster"],
                    "probabilities": [0.30, 0.25, 0.20, 0.12, 0.07, 0.04, 0.02],
                }),
                Column(name="total_matches",   type="int", distribution_params={"distribution": "lognormal", "mu": 5.5, "sigma": 1.5, "min": 1, "max": 50000, "decimals": 0}),
                Column(name="win_rate",        type="float", distribution_params={"distribution": "beta", "a": 5.0, "b": 5.0, "min": 0.0, "max": 1.0, "decimals": 3}),
                Column(name="total_hours_played", type="float", distribution_params={"distribution": "lognormal", "mu": 5.8, "sigma": 1.6, "min": 0.5, "max": 10000.0, "decimals": 1}),
                Column(name="account_type",    type="categorical", distribution_params={
                    "choices": ["free", "premium", "vip"],
                    "probabilities": [0.60, 0.30, 0.10],
                }),
                Column(name="is_banned",       type="boolean", distribution_params={"probability": 0.02}),
                Column(name="registered_at",   type="date", distribution_params={"start": "2018-01-01", "end": "2024-12-31"}),
            ],
            "matches": [
                Column(name="match_id",     type="int", unique=True, distribution_params={"min": 1, "max": num_matches + 1}),
                Column(name="player_id",    type="foreign_key"),
                Column(name="game_mode",    type="categorical", distribution_params={
                    "choices": ["ranked", "casual", "tournament", "co-op", "custom"],
                    "probabilities": [0.38, 0.32, 0.12, 0.12, 0.06],
                }),
                Column(name="result",       type="categorical", distribution_params={
                    "choices": ["win", "loss", "draw", "abandoned"],
                    "probabilities": [0.46, 0.46, 0.05, 0.03],
                }),
                Column(name="duration_minutes", type="int", distribution_params={"distribution": "normal", "mean": 28, "std": 12, "min": 3, "max": 120}),
                Column(name="kills",        type="int", distribution_params={"distribution": "lognormal", "mu": 2.0, "sigma": 0.9, "min": 0, "max": 50, "decimals": 0}),
                Column(name="deaths",       type="int", distribution_params={"distribution": "lognormal", "mu": 1.8, "sigma": 0.9, "min": 0, "max": 40, "decimals": 0}),
                Column(name="assists",      type="int", distribution_params={"distribution": "lognormal", "mu": 1.5, "sigma": 1.0, "min": 0, "max": 30, "decimals": 0}),
                Column(name="score",        type="int", distribution_params={"distribution": "lognormal", "mu": 8.0, "sigma": 1.2, "min": 0, "max": 50000, "decimals": 0}),
                Column(name="xp_earned",    type="int", distribution_params={"distribution": "lognormal", "mu": 5.5, "sigma": 0.8, "min": 10, "max": 5000, "decimals": 0}),
                Column(name="played_at",    type="date", distribution_params={"start": "2021-01-01", "end": "2024-12-31"}),
            ],
            "sessions": [
                Column(name="session_id",   type="int", unique=True, distribution_params={"min": 1, "max": num_sessions + 1}),
                Column(name="player_id",    type="foreign_key"),
                Column(name="started_at",   type="date", distribution_params={"start": "2021-01-01", "end": "2024-12-31"}),
                Column(name="duration_minutes", type="int", distribution_params={"distribution": "lognormal", "mu": 4.2, "sigma": 1.0, "min": 1, "max": 600, "decimals": 0}),
                Column(name="device",       type="categorical", distribution_params={
                    "choices": ["pc", "console", "mobile", "cloud"],
                    "probabilities": [0.52, 0.28, 0.15, 0.05],
                }),
                Column(name="region",       type="categorical", distribution_params={
                    "choices": ["NA", "EU", "APAC", "LATAM", "ME"],
                    "probabilities": [0.35, 0.28, 0.22, 0.10, 0.05],
                }),
            ],
            "achievements": [
                Column(name="achievement_id", type="int", unique=True, distribution_params={"min": 1, "max": num_achievements + 1}),
                Column(name="player_id",    type="foreign_key"),
                Column(name="achievement_name", type="categorical", distribution_params={
                    "choices": [
                        "First Blood", "Hat Trick", "Unstoppable", "Sharpshooter",
                        "Team Player", "Speed Demon", "Survivor", "Legend",
                        "Top Fragger", "Flawless Victory", "Weekend Warrior", "Veteran",
                    ],
                    "probabilities": [0.15, 0.12, 0.10, 0.10, 0.09, 0.09, 0.09, 0.07, 0.07, 0.05, 0.04, 0.03],
                }),
                Column(name="rarity",       type="categorical", distribution_params={
                    "choices": ["common", "rare", "epic", "legendary"],
                    "probabilities": [0.55, 0.28, 0.12, 0.05],
                }),
                Column(name="xp_reward",    type="int", distribution_params={"distribution": "lognormal", "mu": 4.5, "sigma": 1.2, "min": 10, "max": 5000, "decimals": 0}),
                Column(name="unlocked_at",  type="date", distribution_params={"start": "2021-01-01", "end": "2024-12-31"}),
            ],
        }
        relationships = [
            Relationship(parent_table="players", child_table="matches",      parent_key="player_id", child_key="player_id"),
            Relationship(parent_table="players", child_table="sessions",     parent_key="player_id", child_key="player_id"),
            Relationship(parent_table="players", child_table="achievements", parent_key="player_id", child_key="player_id"),
        ]
        return SchemaConfig(
            name="Gaming Dataset", description=f"Generated from story: {story}",
            domain="gaming", tables=tables, columns=columns,
            relationships=relationships, events=[],
        )

    def _build_crm_schema(self, story: str, default_rows: int) -> SchemaConfig:
        num_companies  = max(20, self.scale_params.get("companies", max(50, default_rows // 10)))
        num_contacts   = self.scale_params.get("users", default_rows)
        num_deals      = self.scale_params.get("orders", int(num_contacts * 1.5))
        num_activities = int(num_deals * 4)

        tables = [
            Table(name="companies",  row_count=num_companies),
            Table(name="contacts",   row_count=num_contacts),
            Table(name="deals",      row_count=num_deals),
            Table(name="activities", row_count=num_activities),
        ]
        columns = {
            "companies": [
                Column(name="company_id",   type="int", unique=True, distribution_params={"min": 1, "max": num_companies + 1}),
                Column(name="name",         type="text", distribution_params={"text_type": "company"}),
                Column(name="industry",     type="categorical", distribution_params={
                    "choices": ["technology", "finance", "healthcare", "retail", "manufacturing", "media", "education", "real_estate", "consulting", "other"],
                    "probabilities": [0.22, 0.14, 0.12, 0.11, 0.10, 0.08, 0.08, 0.07, 0.06, 0.02],
                }),
                Column(name="size",         type="categorical", distribution_params={
                    "choices": ["1-10", "11-50", "51-200", "201-500", "501-1000", "1000+"],
                    "probabilities": [0.25, 0.28, 0.22, 0.13, 0.07, 0.05],
                }),
                Column(name="country",      type="text", distribution_params={"text_type": "country"}),
                Column(name="website",      type="text", distribution_params={"text_type": "url"}),
                Column(name="annual_revenue", type="float", distribution_params={
                    "distribution": "lognormal", "mu": 13.5, "sigma": 2.0, "min": 50000, "decimals": 0,
                }),
                Column(name="created_at",   type="date", distribution_params={"start": "2018-01-01", "end": "2024-12-31"}),
            ],
            "contacts": [
                Column(name="contact_id",   type="int", unique=True, distribution_params={"min": 1, "max": num_contacts + 1}),
                Column(name="company_id",   type="foreign_key"),
                Column(name="first_name",   type="text", distribution_params={"text_type": "first_name"}),
                Column(name="last_name",    type="text", distribution_params={"text_type": "last_name"}),
                Column(name="email",        type="text", distribution_params={"text_type": "email"}),
                Column(name="job_title",    type="text", distribution_params={"text_type": "job"}),
                Column(name="phone",        type="text", distribution_params={"text_type": "phone"}),
                Column(name="lead_source",  type="categorical", distribution_params={
                    "choices": ["organic_search", "paid_search", "referral", "social", "email", "event", "direct", "partner"],
                    "probabilities": [0.22, 0.18, 0.16, 0.14, 0.12, 0.08, 0.06, 0.04],
                }),
                Column(name="lifecycle_stage", type="categorical", distribution_params={
                    "choices": ["subscriber", "lead", "mql", "sql", "opportunity", "customer", "evangelist"],
                    "probabilities": [0.20, 0.22, 0.18, 0.14, 0.10, 0.12, 0.04],
                }),
                Column(name="created_at",   type="date", distribution_params={"start": "2019-01-01", "end": "2024-12-31"}),
                Column(name="last_activity_at", type="date", distribution_params={"start": "2023-01-01", "end": "2024-12-31"}),
            ],
            "deals": [
                Column(name="deal_id",      type="int", unique=True, distribution_params={"min": 1, "max": num_deals + 1}),
                Column(name="contact_id",   type="foreign_key"),
                Column(name="company_id",   type="foreign_key"),
                Column(name="name",         type="text", distribution_params={"text_type": "company"}),
                Column(name="stage",        type="categorical", distribution_params={
                    "choices": ["prospecting", "qualification", "proposal", "negotiation", "closed_won", "closed_lost"],
                    "probabilities": [0.22, 0.18, 0.15, 0.12, 0.20, 0.13],
                }),
                Column(name="amount",       type="float", distribution_params={
                    "distribution": "lognormal", "mu": 9.5, "sigma": 1.8, "min": 500, "decimals": 0,
                }),
                Column(name="probability",  type="float", distribution_params={
                    "distribution": "beta", "a": 2.0, "b": 2.0, "min": 0.0, "max": 1.0, "decimals": 2,
                }),
                Column(name="close_date",   type="date", distribution_params={"start": "2023-01-01", "end": "2025-12-31"}),
                Column(name="created_at",   type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
                Column(name="owner",        type="text", distribution_params={"text_type": "name"}),
            ],
            "activities": [
                Column(name="activity_id",  type="int", unique=True, distribution_params={"min": 1, "max": num_activities + 1}),
                Column(name="deal_id",      type="foreign_key"),
                Column(name="type",         type="categorical", distribution_params={
                    "choices": ["call", "email", "meeting", "demo", "proposal_sent", "follow_up", "note"],
                    "probabilities": [0.22, 0.28, 0.16, 0.12, 0.08, 0.10, 0.04],
                }),
                Column(name="outcome",      type="categorical", distribution_params={
                    "choices": ["positive", "neutral", "negative", "no_response"],
                    "probabilities": [0.38, 0.30, 0.12, 0.20],
                }),
                Column(name="duration_minutes", type="int", distribution_params={
                    "distribution": "lognormal", "mu": 3.0, "sigma": 0.8, "min": 5, "max": 180, "decimals": 0,
                }),
                Column(name="notes",        type="text", distribution_params={"text_type": "support_ticket"}),
                Column(name="occurred_at",  type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
            ],
        }
        relationships = [
            Relationship(parent_table="companies", child_table="contacts",   parent_key="company_id", child_key="company_id"),
            Relationship(parent_table="contacts",  child_table="deals",      parent_key="contact_id", child_key="contact_id"),
            Relationship(parent_table="companies", child_table="deals",      parent_key="company_id", child_key="company_id"),
            Relationship(parent_table="deals",     child_table="activities", parent_key="deal_id",    child_key="deal_id"),
        ]
        return SchemaConfig(
            name="CRM Dataset", description=f"Generated from story: {story}",
            domain="crm", tables=tables, columns=columns,
            relationships=relationships, events=[],
        )

    def _build_crypto_schema(self, story: str, default_rows: int) -> SchemaConfig:
        num_wallets   = self.scale_params.get("users", default_rows)
        num_tokens    = max(10, self.scale_params.get("tokens", 20))
        num_txns      = self.scale_params.get("orders", int(num_wallets * 8))
        num_prices    = int(num_tokens * 365)

        tables = [
            Table(name="wallets",     row_count=num_wallets),
            Table(name="tokens",      row_count=num_tokens),
            Table(name="transactions", row_count=num_txns),
            Table(name="token_prices", row_count=num_prices),
        ]
        columns = {
            "wallets": [
                Column(name="wallet_id",    type="int", unique=True, distribution_params={"min": 1, "max": num_wallets + 1}),
                Column(name="address",      type="text", distribution_params={"text_type": "username"}),
                Column(name="chain",        type="categorical", distribution_params={
                    "choices": ["ethereum", "solana", "polygon", "bnb_chain", "avalanche", "arbitrum", "optimism"],
                    "probabilities": [0.35, 0.20, 0.15, 0.12, 0.08, 0.06, 0.04],
                }),
                Column(name="wallet_type",  type="categorical", distribution_params={
                    "choices": ["eoa", "multisig", "smart_contract", "exchange"],
                    "probabilities": [0.65, 0.15, 0.12, 0.08],
                }),
                Column(name="eth_balance",  type="float", distribution_params={
                    "distribution": "lognormal", "mu": 0.5, "sigma": 2.5, "min": 0.0, "max": 50000.0, "decimals": 6,
                }),
                Column(name="usd_balance",  type="float", distribution_params={
                    "distribution": "lognormal", "mu": 7.0, "sigma": 2.5, "min": 0.0, "max": 10_000_000.0, "decimals": 2,
                }),
                Column(name="is_defi_active", type="boolean", distribution_params={"probability": 0.38}),
                Column(name="created_at",   type="date", distribution_params={"start": "2018-01-01", "end": "2024-12-31"}),
            ],
            "tokens": [
                Column(name="token_id",     type="int", unique=True, distribution_params={"min": 1, "max": num_tokens + 1}),
                Column(name="symbol",       type="categorical", distribution_params={
                    "choices": ["ETH", "BTC", "SOL", "USDC", "USDT", "BNB", "MATIC", "AVAX", "ARB", "OP",
                                "LINK", "UNI", "AAVE", "CRV", "SNX", "MKR", "COMP", "YFI", "SUSHI", "BAL"],
                }),
                Column(name="name",         type="categorical", distribution_params={
                    "choices": ["Ethereum", "Bitcoin", "Solana", "USD Coin", "Tether", "BNB", "Polygon", "Avalanche",
                                "Arbitrum", "Optimism", "Chainlink", "Uniswap", "Aave", "Curve", "Synthetix",
                                "Maker", "Compound", "yearn.finance", "SushiSwap", "Balancer"],
                }),
                Column(name="category",     type="categorical", distribution_params={
                    "choices": ["layer1", "layer2", "stablecoin", "defi", "governance"],
                    "probabilities": [0.25, 0.20, 0.15, 0.25, 0.15],
                }),
                Column(name="market_cap",   type="float", distribution_params={
                    "distribution": "lognormal", "mu": 20.0, "sigma": 3.0, "min": 1_000_000.0, "decimals": 0,
                }),
                Column(name="listed_at",    type="date", distribution_params={"start": "2015-01-01", "end": "2023-12-31"}),
            ],
            "transactions": [
                Column(name="txn_id",       type="int", unique=True, distribution_params={"min": 1, "max": num_txns + 1}),
                Column(name="from_wallet",  type="foreign_key"),
                Column(name="token_id",     type="foreign_key"),
                Column(name="txn_type",     type="categorical", distribution_params={
                    "choices": ["transfer", "swap", "stake", "unstake", "bridge", "mint", "burn", "claim"],
                    "probabilities": [0.35, 0.28, 0.12, 0.08, 0.07, 0.04, 0.04, 0.02],
                }),
                Column(name="amount",       type="float", distribution_params={
                    "distribution": "lognormal", "mu": 4.0, "sigma": 2.5, "min": 0.000001, "decimals": 6,
                }),
                Column(name="usd_value",    type="float", distribution_params={
                    "distribution": "lognormal", "mu": 6.5, "sigma": 2.8, "min": 0.01, "decimals": 2,
                }),
                Column(name="gas_fee_usd",  type="float", distribution_params={
                    "distribution": "lognormal", "mu": 1.5, "sigma": 1.2, "min": 0.001, "max": 500.0, "decimals": 4,
                }),
                Column(name="status",       type="categorical", distribution_params={
                    "choices": ["confirmed", "pending", "failed"],
                    "probabilities": [0.92, 0.05, 0.03],
                }),
                Column(name="block_number", type="int", distribution_params={
                    "distribution": "uniform", "min": 17_000_000, "max": 21_000_000,
                }),
                Column(name="txn_at",       type="date", distribution_params={"start": "2021-01-01", "end": "2024-12-31"}),
            ],
            "token_prices": [
                Column(name="price_id",     type="int", unique=True, distribution_params={"min": 1, "max": num_prices + 1}),
                Column(name="token_id",     type="foreign_key"),
                Column(name="price_usd",    type="float", distribution_params={
                    "distribution": "lognormal", "mu": 4.0, "sigma": 3.5, "min": 0.000001, "decimals": 6,
                }),
                Column(name="volume_24h",   type="float", distribution_params={
                    "distribution": "lognormal", "mu": 18.0, "sigma": 2.5, "min": 0.0, "decimals": 0,
                }),
                Column(name="market_cap",   type="float", distribution_params={
                    "distribution": "lognormal", "mu": 20.0, "sigma": 3.0, "min": 0.0, "decimals": 0,
                }),
                Column(name="pct_change_24h", type="float", distribution_params={
                    "distribution": "normal", "mean": 0.0, "std": 5.0, "min": -50.0, "max": 100.0, "decimals": 2,
                }),
                Column(name="recorded_at",  type="date", distribution_params={"start": "2021-01-01", "end": "2024-12-31"}),
            ],
        }
        relationships = [
            Relationship(parent_table="wallets", child_table="transactions", parent_key="wallet_id", child_key="from_wallet"),
            Relationship(parent_table="tokens",  child_table="transactions", parent_key="token_id",  child_key="token_id"),
            Relationship(parent_table="tokens",  child_table="token_prices", parent_key="token_id",  child_key="token_id"),
        ]
        return SchemaConfig(
            name="Crypto/Web3 Dataset", description=f"Generated from story: {story}",
            domain="crypto", tables=tables, columns=columns,
            relationships=relationships, events=[],
        )

    def _build_insurance_schema(self, story: str, default_rows: int) -> SchemaConfig:
        num_customers = self.scale_params.get("users", default_rows)
        num_policies  = max(1, int(num_customers * 1.3))
        num_claims    = max(1, int(num_policies * 0.18))
        num_payments  = max(1, int(num_policies * 12))

        tables = [
            Table(name="customers", row_count=num_customers),
            Table(name="policies",  row_count=num_policies),
            Table(name="claims",    row_count=num_claims),
            Table(name="payments",  row_count=num_payments),
        ]
        columns = {
            "customers": [
                Column(name="customer_id",   type="int", unique=True, distribution_params={"min": 1, "max": num_customers + 1}),
                Column(name="first_name",    type="text", distribution_params={"text_type": "first_name"}),
                Column(name="last_name",     type="text", distribution_params={"text_type": "last_name"}),
                Column(name="email",         type="text", distribution_params={"text_type": "email"}),
                Column(name="date_of_birth", type="date", distribution_params={"start": "1950-01-01", "end": "2000-12-31"}),
                Column(name="gender",        type="categorical", distribution_params={
                    "choices": ["male", "female", "non_binary", "prefer_not_to_say"],
                    "probabilities": [0.48, 0.48, 0.02, 0.02],
                }),
                Column(name="credit_score",  type="int", distribution_params={
                    "distribution": "normal", "mean": 680, "std": 80, "min": 300, "max": 850,
                }),
                Column(name="state",         type="categorical", distribution_params={
                    "choices": ["CA", "TX", "FL", "NY", "PA", "IL", "OH", "GA", "NC", "MI",
                                "NJ", "VA", "WA", "AZ", "MA", "TN", "IN", "MO", "MD", "WI"],
                    "probabilities": [0.12, 0.10, 0.08, 0.08, 0.05, 0.05, 0.04, 0.04, 0.04, 0.04,
                                      0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.03, 0.03, 0.02],
                }),
                Column(name="customer_since", type="date", distribution_params={
                    "after_column": "date_of_birth", "min_delta_days": 6570, "max_delta_days": 27375,
                }),
            ],
            "policies": [
                Column(name="policy_id",     type="int", unique=True, distribution_params={"min": 1, "max": num_policies + 1}),
                Column(name="customer_id",   type="foreign_key"),
                Column(name="policy_type",   type="categorical", distribution_params={
                    "choices": ["auto", "home", "life", "health", "renters", "umbrella", "business"],
                    "probabilities": [0.32, 0.25, 0.18, 0.12, 0.07, 0.04, 0.02],
                }),
                Column(name="status",        type="categorical", distribution_params={
                    "choices": ["active", "expired", "cancelled", "pending", "suspended"],
                    "probabilities": [0.65, 0.18, 0.09, 0.05, 0.03],
                }),
                Column(name="premium_monthly", type="float", distribution_params={
                    "distribution": "lognormal", "mu": 5.2, "sigma": 0.8, "min": 20.0, "max": 2000.0, "decimals": 2,
                }),
                Column(name="coverage_amount", type="float", distribution_params={
                    "distribution": "lognormal", "mu": 12.5, "sigma": 1.5, "min": 10_000.0, "decimals": 0,
                }),
                Column(name="deductible",    type="categorical", distribution_params={
                    "choices": [250, 500, 1000, 2000, 2500, 5000],
                    "probabilities": [0.08, 0.30, 0.35, 0.14, 0.08, 0.05],
                }),
                Column(name="risk_score",    type="float", distribution_params={
                    "distribution": "beta", "a": 2.0, "b": 5.0, "min": 0.0, "max": 1.0, "decimals": 4,
                }),
                Column(name="start_date",    type="date", distribution_params={"start": "2015-01-01", "end": "2024-12-31"}),
                Column(name="end_date",      type="date", distribution_params={
                    "after_column": "start_date", "min_delta_days": 365, "max_delta_days": 1825,
                }),
            ],
            "claims": [
                Column(name="claim_id",      type="int", unique=True, distribution_params={"min": 1, "max": num_claims + 1}),
                Column(name="policy_id",     type="foreign_key"),
                Column(name="claim_type",    type="categorical", distribution_params={
                    "choices": ["collision", "theft", "water_damage", "fire", "medical", "liability", "natural_disaster", "other"],
                    "probabilities": [0.28, 0.12, 0.18, 0.08, 0.14, 0.10, 0.06, 0.04],
                }),
                Column(name="status",        type="categorical", distribution_params={
                    "choices": ["approved", "under_review", "denied", "settled", "withdrawn"],
                    "probabilities": [0.52, 0.18, 0.12, 0.14, 0.04],
                }),
                Column(name="amount_claimed", type="float", distribution_params={
                    "distribution": "lognormal", "mu": 8.5, "sigma": 1.8, "min": 100.0, "decimals": 2,
                }),
                Column(name="amount_paid",   type="float", distribution_params={
                    "distribution": "lognormal", "mu": 8.2, "sigma": 1.8, "min": 0.0, "decimals": 2,
                    "null_if": {"column": "status", "values": ["under_review", "denied", "withdrawn"]},
                }),
                Column(name="is_fraudulent", type="boolean", distribution_params={"probability": 0.04}),
                Column(name="filed_at",      type="date", distribution_params={"start": "2018-01-01", "end": "2024-12-31"}),
                Column(name="resolved_at",   type="date", distribution_params={
                    "after_column": "filed_at", "min_delta_days": 7, "max_delta_days": 180,
                    "null_if": {"column": "status", "values": ["under_review", "withdrawn"]},
                }),
            ],
            "payments": [
                Column(name="payment_id",    type="int", unique=True, distribution_params={"min": 1, "max": num_payments + 1}),
                Column(name="policy_id",     type="foreign_key"),
                Column(name="amount",        type="float", distribution_params={
                    "distribution": "lognormal", "mu": 5.2, "sigma": 0.8, "min": 20.0, "max": 2000.0, "decimals": 2,
                }),
                Column(name="method",        type="categorical", distribution_params={
                    "choices": ["ach", "credit_card", "check", "wire"],
                    "probabilities": [0.52, 0.30, 0.12, 0.06],
                }),
                Column(name="status",        type="categorical", distribution_params={
                    "choices": ["paid", "failed", "pending", "refunded"],
                    "probabilities": [0.88, 0.06, 0.04, 0.02],
                }),
                Column(name="paid_at",       type="date", distribution_params={"start": "2015-01-01", "end": "2024-12-31"}),
            ],
        }
        relationships = [
            Relationship(parent_table="customers", child_table="policies",  parent_key="customer_id", child_key="customer_id"),
            Relationship(parent_table="policies",  child_table="claims",    parent_key="policy_id",   child_key="policy_id"),
            Relationship(parent_table="policies",  child_table="payments",  parent_key="policy_id",   child_key="policy_id"),
        ]
        return SchemaConfig(
            name="Insurance Dataset", description=f"Generated from story: {story}",
            domain="insurance", tables=tables, columns=columns,
            relationships=relationships, events=[],
        )

    def _build_travel_schema(self, story: str, default_rows: int) -> SchemaConfig:
        num_users     = self.scale_params.get("users", default_rows)
        num_hotels    = max(50, num_users // 20)
        num_flights   = max(200, num_users // 5)
        num_bookings  = max(1, int(num_users * 2.5))
        num_reviews   = max(1, int(num_bookings * 0.45))

        tables = [
            Table(name="users",    row_count=num_users),
            Table(name="hotels",   row_count=num_hotels),
            Table(name="flights",  row_count=num_flights),
            Table(name="bookings", row_count=num_bookings),
            Table(name="reviews",  row_count=num_reviews),
        ]
        columns = {
            "users": [
                Column(name="user_id",       type="int",  unique=True, distribution_params={"min": 1, "max": num_users + 1}),
                Column(name="first_name",    type="text", distribution_params={"text_type": "first_name"}),
                Column(name="last_name",     type="text", distribution_params={"text_type": "last_name"}),
                Column(name="email",         type="text", distribution_params={"text_type": "email"}),
                Column(name="phone",         type="text", distribution_params={"text_type": "phone_number"}),
                Column(name="country",       type="categorical", distribution_params={
                    "choices": ["US", "GB", "DE", "FR", "IN", "AU", "CA", "JP", "BR", "SG", "AE", "NL"],
                    "probabilities": [0.28, 0.10, 0.08, 0.07, 0.08, 0.06, 0.07, 0.05, 0.05, 0.04, 0.04, 0.08],
                }),
                Column(name="loyalty_tier",  type="categorical", distribution_params={
                    "choices": ["bronze", "silver", "gold", "platinum"],
                    "probabilities": [0.55, 0.28, 0.12, 0.05],
                }),
                Column(name="points_balance", type="int", distribution_params={
                    "distribution": "lognormal", "mu": 7.5, "sigma": 1.5, "min": 0, "decimals": 0,
                }),
                Column(name="signup_at",     type="date", distribution_params={"start": "2016-01-01", "end": "2024-12-31"}),
            ],
            "hotels": [
                Column(name="hotel_id",        type="int",  unique=True, distribution_params={"min": 1, "max": num_hotels + 1}),
                Column(name="name",            type="text", distribution_params={"text_type": "company_name"}),
                Column(name="city",            type="text", distribution_params={"text_type": "city"}),
                Column(name="country",         type="categorical", distribution_params={
                    "choices": ["US", "FR", "ES", "IT", "TH", "JP", "AE", "GB", "MX", "GR", "TR", "ID"],
                    "sampling": "zipf",
                }),
                Column(name="star_rating",     type="categorical", distribution_params={
                    "choices": [1, 2, 3, 4, 5],
                    "probabilities": [0.03, 0.07, 0.25, 0.40, 0.25],
                }),
                Column(name="price_per_night", type="float", distribution_params={
                    "distribution": "lognormal", "mu": 4.8, "sigma": 0.9, "min": 30.0, "decimals": 2,
                }),
                Column(name="review_score",    type="float", distribution_params={
                    "distribution": "beta", "a": 8.0, "b": 2.0, "min": 1.0, "max": 10.0, "decimals": 1,
                }),
                Column(name="total_rooms",     type="int", distribution_params={
                    "distribution": "lognormal", "mu": 4.5, "sigma": 0.8, "min": 10, "decimals": 0,
                }),
            ],
            "flights": [
                Column(name="flight_id",       type="int",  unique=True, distribution_params={"min": 1, "max": num_flights + 1}),
                Column(name="origin",          type="categorical", distribution_params={
                    "choices": ["JFK", "LAX", "LHR", "CDG", "DXB", "SIN", "HND", "SYD", "ORD", "FRA", "AMS", "BOM"],
                    "sampling": "zipf",
                }),
                Column(name="destination",     type="categorical", distribution_params={
                    "choices": ["JFK", "LAX", "LHR", "CDG", "DXB", "SIN", "HND", "SYD", "ORD", "FRA", "AMS", "BOM"],
                    "sampling": "uniform",
                }),
                Column(name="airline",         type="categorical", distribution_params={
                    "choices": ["Delta", "United", "American", "British Airways", "Lufthansa", "Emirates", "Singapore Airlines", "Qantas", "Air France", "KLM"],
                    "sampling": "zipf",
                }),
                Column(name="cabin",           type="categorical", distribution_params={
                    "choices": ["economy", "premium_economy", "business", "first"],
                    "probabilities": [0.72, 0.14, 0.11, 0.03],
                }),
                Column(name="price",           type="float", distribution_params={
                    "distribution": "lognormal", "mu": 5.8, "sigma": 0.9, "min": 49.0, "decimals": 2,
                }),
                Column(name="duration_minutes", type="int", distribution_params={
                    "distribution": "lognormal", "mu": 5.0, "sigma": 0.7, "min": 60, "max": 900, "decimals": 0,
                }),
                Column(name="departure_at",    type="date", distribution_params={"start": "2023-01-01", "end": "2025-12-31"}),
                Column(name="seats_total",     type="int", distribution_params={
                    "choices": [150, 180, 220, 300, 350, 400], "probabilities": [0.15, 0.20, 0.25, 0.20, 0.12, 0.08],
                }),
                Column(name="seats_booked",    type="int", distribution_params={
                    "distribution": "normal", "mean": 170, "std": 50, "min": 10, "max": 400, "decimals": 0,
                }),
            ],
            "bookings": [
                Column(name="booking_id",      type="int",  unique=True, distribution_params={"min": 1, "max": num_bookings + 1}),
                Column(name="user_id",         type="foreign_key"),
                Column(name="booking_type",    type="categorical", distribution_params={
                    "choices": ["hotel", "flight", "package"],
                    "probabilities": [0.42, 0.38, 0.20],
                }),
                Column(name="status",          type="categorical", distribution_params={
                    "choices": ["confirmed", "pending", "cancelled", "completed", "refunded"],
                    "probabilities": [0.55, 0.10, 0.15, 0.18, 0.02],
                }),
                Column(name="total_price",     type="float", distribution_params={
                    "distribution": "lognormal", "mu": 6.2, "sigma": 1.0, "min": 49.0, "decimals": 2,
                }),
                Column(name="currency",        type="categorical", distribution_params={
                    "choices": ["USD", "EUR", "GBP", "AUD", "SGD", "JPY", "INR"],
                    "probabilities": [0.40, 0.25, 0.12, 0.08, 0.05, 0.05, 0.05],
                }),
                Column(name="num_travelers",   type="int", distribution_params={
                    "choices": [1, 2, 3, 4, 5, 6], "probabilities": [0.35, 0.38, 0.12, 0.08, 0.04, 0.03],
                }),
                Column(name="booked_at",       type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
                Column(name="travel_date",     type="date", distribution_params={
                    "after_column": "booked_at", "min_delta_days": 1, "max_delta_days": 365,
                }),
                Column(name="cancellation_reason", type="categorical", distribution_params={
                    "choices": ["change_of_plans", "better_price", "emergency", "weather", "airline_issue", None],
                    "probabilities": [0.30, 0.20, 0.15, 0.15, 0.10, 0.10],
                    "null_if": {"column": "status", "values": ["confirmed", "pending", "completed"]},
                }),
            ],
            "reviews": [
                Column(name="review_id",       type="int",  unique=True, distribution_params={"min": 1, "max": num_reviews + 1}),
                Column(name="booking_id",      type="foreign_key"),
                Column(name="rating",          type="int", distribution_params={
                    "choices": [1, 2, 3, 4, 5], "probabilities": [0.04, 0.06, 0.13, 0.35, 0.42],
                }),
                Column(name="title",           type="text", distribution_params={"text_type": "short_review_title"}),
                Column(name="body",            type="text", distribution_params={"text_type": "review"}),
                Column(name="helpful_votes",   type="int", distribution_params={
                    "distribution": "lognormal", "mu": 1.5, "sigma": 1.2, "min": 0, "decimals": 0,
                }),
                Column(name="posted_at",       type="date", distribution_params={"start": "2022-01-01", "end": "2024-12-31"}),
            ],
        }
        relationships = [
            Relationship(parent_table="users",    child_table="bookings", parent_key="user_id",    child_key="user_id"),
            Relationship(parent_table="bookings", child_table="reviews",  parent_key="booking_id", child_key="booking_id"),
        ]
        return SchemaConfig(
            name="Travel Dataset", description=f"Generated from story: {story}",
            domain="travel", tables=tables, columns=columns,
            relationships=relationships, events=[],
        )

    def _build_streaming_schema(self, story: str, default_rows: int) -> SchemaConfig:
        num_subscribers  = self.scale_params.get("users", default_rows)
        num_content      = max(500, num_subscribers // 10)
        num_history      = int(num_subscribers * 15)
        num_ratings      = int(num_subscribers * 4)

        tables = [
            Table(name="subscribers",  row_count=num_subscribers),
            Table(name="content",      row_count=num_content),
            Table(name="watch_history", row_count=num_history),
            Table(name="ratings",      row_count=num_ratings),
        ]
        columns = {
            "subscribers": [
                Column(name="subscriber_id",  type="int",  unique=True, distribution_params={"min": 1, "max": num_subscribers + 1}),
                Column(name="first_name",     type="text", distribution_params={"text_type": "first_name"}),
                Column(name="last_name",      type="text", distribution_params={"text_type": "last_name"}),
                Column(name="email",          type="text", distribution_params={"text_type": "email"}),
                Column(name="plan",           type="categorical", distribution_params={
                    "choices": ["basic", "standard", "premium", "family"],
                    "probabilities": [0.22, 0.38, 0.30, 0.10],
                }),
                Column(name="country",        type="categorical", distribution_params={
                    "choices": ["US", "GB", "DE", "IN", "BR", "CA", "FR", "AU", "MX", "JP", "ES", "KR"],
                    "probabilities": [0.30, 0.08, 0.07, 0.08, 0.07, 0.06, 0.06, 0.05, 0.05, 0.04, 0.04, 0.10],
                }),
                Column(name="signup_at",      type="date", distribution_params={"start": "2018-01-01", "end": "2024-12-31"}),
                Column(name="last_active_at", type="date", distribution_params={
                    "after_column": "signup_at", "min_delta_days": 0, "max_delta_days": 730,
                }),
                Column(name="is_churned",     type="boolean", distribution_params={"probability": 0.18}),
                Column(name="churned_at",     type="date", distribution_params={
                    "after_column": "signup_at", "min_delta_days": 30, "max_delta_days": 1825,
                    "null_if": {"column": "is_churned", "values": [False]},
                }),
            ],
            "content": [
                Column(name="content_id",     type="int",  unique=True, distribution_params={"min": 1, "max": num_content + 1}),
                Column(name="title",          type="text", distribution_params={"text_type": "product_name"}),
                Column(name="type",           type="categorical", distribution_params={
                    "choices": ["movie", "series", "documentary", "short", "special"],
                    "probabilities": [0.40, 0.35, 0.12, 0.08, 0.05],
                }),
                Column(name="genre",          type="categorical", distribution_params={
                    "choices": ["drama", "comedy", "thriller", "action", "romance", "sci-fi", "horror", "documentary", "animation", "crime"],
                    "probabilities": [0.20, 0.16, 0.14, 0.13, 0.10, 0.09, 0.07, 0.05, 0.04, 0.02],
                }),
                Column(name="language",       type="categorical", distribution_params={
                    "choices": ["en", "es", "fr", "de", "hi", "pt", "ko", "ja", "zh", "ar"],
                    "probabilities": [0.45, 0.12, 0.08, 0.07, 0.06, 0.06, 0.05, 0.04, 0.04, 0.03],
                }),
                Column(name="release_year",   type="int", distribution_params={
                    "distribution": "normal", "mean": 2018, "std": 6, "min": 1990, "max": 2024, "decimals": 0,
                }),
                Column(name="duration_minutes", type="int", distribution_params={
                    "distribution": "lognormal", "mu": 4.5, "sigma": 0.6, "min": 5, "max": 240, "decimals": 0,
                }),
                Column(name="rating_mpaa",    type="categorical", distribution_params={
                    "choices": ["G", "PG", "PG-13", "R", "NC-17", "TV-MA", "TV-14"],
                    "probabilities": [0.05, 0.12, 0.28, 0.30, 0.02, 0.15, 0.08],
                }),
                Column(name="imdb_score",     type="float", distribution_params={
                    "distribution": "beta", "a": 5.0, "b": 2.0, "min": 1.0, "max": 10.0, "decimals": 1,
                }),
                Column(name="added_at",       type="date", distribution_params={"start": "2018-01-01", "end": "2024-12-31"}),
            ],
            "watch_history": [
                Column(name="history_id",     type="int",  unique=True, distribution_params={"min": 1, "max": num_history + 1}),
                Column(name="subscriber_id",  type="foreign_key"),
                Column(name="content_id",     type="foreign_key"),
                Column(name="started_at",     type="date", distribution_params={"start": "2019-01-01", "end": "2024-12-31"}),
                Column(name="watch_duration_minutes", type="int", distribution_params={
                    "distribution": "lognormal", "mu": 3.8, "sigma": 0.9, "min": 1, "decimals": 0,
                }),
                Column(name="completed",      type="boolean", distribution_params={"probability": 0.62}),
                Column(name="device",         type="categorical", distribution_params={
                    "choices": ["smart_tv", "mobile", "desktop", "tablet", "console"],
                    "probabilities": [0.38, 0.28, 0.18, 0.10, 0.06],
                }),
            ],
            "ratings": [
                Column(name="rating_id",      type="int",  unique=True, distribution_params={"min": 1, "max": num_ratings + 1}),
                Column(name="subscriber_id",  type="foreign_key"),
                Column(name="content_id",     type="foreign_key"),
                Column(name="stars",          type="int", distribution_params={
                    "choices": [1, 2, 3, 4, 5], "probabilities": [0.05, 0.08, 0.16, 0.36, 0.35],
                }),
                Column(name="rated_at",       type="date", distribution_params={"start": "2019-01-01", "end": "2024-12-31"}),
            ],
        }
        relationships = [
            Relationship(parent_table="subscribers",  child_table="watch_history", parent_key="subscriber_id", child_key="subscriber_id"),
            Relationship(parent_table="content",      child_table="watch_history", parent_key="content_id",    child_key="content_id"),
            Relationship(parent_table="subscribers",  child_table="ratings",       parent_key="subscriber_id", child_key="subscriber_id"),
            Relationship(parent_table="content",      child_table="ratings",       parent_key="content_id",    child_key="content_id"),
        ]
        return SchemaConfig(
            name="Streaming Dataset", description=f"Generated from story: {story}",
            domain="streaming", tables=tables, columns=columns,
            relationships=relationships, events=[],
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
