"""
LLM-powered schema generator using Groq Llama 3.3.

This module provides intelligent schema generation from natural language,
including:
- Reference tables with actual LLM-generated data (exercises, plans, meals)
- Transactional tables with foreign keys to reference tables
- Industry-realistic column configurations
"""

import json
import os
import re
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    import anthropic as _anthropic_sdk
except ImportError:
    _anthropic_sdk = None

from misata.curve_fitting import CurveFitter
from misata.feedback import FeedbackDatabase
from misata.schema import Column, OutcomeCurve, RateCurve, Relationship, ScenarioEvent, SchemaConfig, Table
from misata.research import DeepResearchAgent


# Load .env file if it exists
def _load_env():
    """Load environment variables from .env file."""
    env_paths = [
        Path.cwd() / ".env",
        Path.cwd().parent / ".env",  # apps/.env or api parent
        Path.cwd().parent.parent / ".env",  # Misata root from apps/api
        Path(__file__).parent.parent / ".env",  # packages/core/.env
        Path(__file__).parent.parent.parent / ".env",  # packages/.env
        Path(__file__).parent.parent.parent.parent / ".env",  # Misata root from packages/core/misata
        Path.home() / ".misata" / ".env",
    ]

    for env_path in env_paths:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        # Remove quotes if present
                        value = value.strip().strip("'\"")
                        os.environ.setdefault(key.strip(), value)
            break

_load_env()

# ---------------------------------------------------------------------------
# Numeric spread sanitizer — prompt rules don't bind a model, code does.
# An LLM that emits mean=50000 with a missing/degenerate std (or min==max)
# produces a visually constant money column (the annual_gmv=50000 field
# report). Deterministic post-processing repairs the spread.
# ---------------------------------------------------------------------------

_MONEY_COLUMN_RE = re.compile(
    r"(gmv|revenue|price|amount|value|spend|spent|cost|income|salary|wage|"
    r"budget|mrr|arr|fee|balance|total|payment|invoice|earning|profit)",
    re.IGNORECASE,
)


def _sanitize_numeric_spread(
    col_name: str, col_type: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    """Repair degenerate spreads on LLM-authored money columns.

    Applies only to money-named numeric columns (safe scope):
      - ``min == max``      → widen to ±25% around the value
      - ``std`` missing     → 25% of ``mean``
      - ``std``/mean < 0.1% → 25% of ``mean`` (an effectively constant spec
        no real dataset exhibits; year-like tight-but-real stds stay)
    """
    if col_type not in ("int", "float") or not isinstance(params, dict):
        return params
    if not _MONEY_COLUMN_RE.search(col_name or ""):
        return params
    if params.get("distribution") == "categorical" or "choices" in params:
        return params
    out = dict(params)

    lo, hi = out.get("min"), out.get("max")
    if (
        isinstance(lo, (int, float)) and isinstance(hi, (int, float))
        and lo == hi and lo != 0
    ):
        center = float(lo)
        out["min"] = round(center * 0.75, 2)
        out["max"] = round(center * 1.25, 2)
        warnings.warn(
            f"Column '{col_name}': LLM declared min == max == {center:g}; "
            f"widened to ±25% so the column is not constant."
        )

    mean = out.get("mean")
    if isinstance(mean, (int, float)) and mean != 0:
        std = out.get("std")
        degenerate = (
            std is None
            or (isinstance(std, (int, float)) and abs(float(std)) < abs(float(mean)) * 0.001)
        )
        if degenerate:
            out["std"] = round(abs(float(mean)) * 0.25, 4)
            if std is not None:
                warnings.warn(
                    f"Column '{col_name}': std {std:g} is <0.1% of mean "
                    f"{mean:g} (effectively constant); raised to 25% of mean."
                )
    return out


# ---------------------------------------------------------------------------
# Domain vocabulary — deterministic post-processing enforces these values
# instead of relying on the LLM to remember the right words.
# ---------------------------------------------------------------------------

_DOMAIN_SIGNALS: List[tuple] = [
    ("real_estate", [
        "listing", "listings", "properties", "property", "homes", "home",
        "apartment", "apartments", "condo", "condos", "house", "houses",
        "realt", "mortgage", "mls", "sqft", "square_foot", "square_footage",
    ]),
    ("ecommerce", [
        "order", "orders", "product", "products", "cart", "checkout",
        "purchase", "purchases", "inventory", "shop", "sku", "catalog",
    ]),
    ("healthcare", [
        "patient", "patients", "doctor", "doctors", "hospital", "clinic",
        "diagnosis", "diagnoses", "prescription", "appointment", "procedure",
    ]),
    ("finance", [
        "account", "accounts", "transaction", "transactions", "loan", "loans",
        "bank", "payment", "payments", "credit", "debit", "ledger", "portfolio",
    ]),
    ("hr", [
        "employee", "employees", "department", "departments", "salary", "payroll",
        "hire", "performance", "headcount", "workforce",
    ]),
    ("saas", [
        "subscription", "subscriptions", "tenant", "tenants", "mrr", "arr",
        "churn", "billing", "workspace", "feature",
    ]),
    ("logistics", [
        "shipment", "shipments", "delivery", "deliveries", "warehouse",
        "freight", "carrier", "route", "tracking",
    ]),
    ("education", [
        "student", "students", "course", "courses", "grade", "grades",
        "enrollment", "teacher", "lesson", "exam",
    ]),
]

_DOMAIN_VOCAB: Dict[str, Dict[str, List]] = {
    "real_estate": {
        "property_type": ["Single Family Home", "Condo", "Townhouse", "Multi-Family", "Apartment", "Studio", "Loft"],
        "listing_status": ["Active", "Pending", "Sold", "Off Market", "Expired"],
        "status": ["Active", "Pending", "Sold", "Off Market", "Expired"],
        "city": ["San Francisco", "Los Angeles", "New York", "Chicago", "Miami", "Austin", "Seattle", "Denver", "Boston", "Phoenix"],
        "state": ["CA", "NY", "TX", "FL", "WA", "CO", "IL", "AZ", "GA", "NC"],
        "neighborhood_type": ["Urban", "Suburban", "Rural", "Downtown", "Waterfront", "Historic District"],
        "heating_type": ["Central Air", "Electric", "Natural Gas", "Radiant Heat", "Heat Pump", "Baseboard"],
        "cooling_type": ["Central AC", "Window Units", "Mini-Split", "Evaporative Cooler", "None"],
        "parking": ["Attached Garage", "Detached Garage", "Street Parking", "Driveway", "Carport", "None"],
        "parking_type": ["Attached Garage", "Detached Garage", "Street Parking", "Driveway", "Carport", "None"],
        "condition": ["Excellent", "Good", "Fair", "Needs Work", "New Construction"],
        "property_style": ["Ranch", "Colonial", "Victorian", "Contemporary", "Craftsman", "Tudor", "Cape Cod"],
        "amenity_type": ["Pool", "Gym", "Garden", "Elevator", "Rooftop Terrace", "Concierge", "Doorman"],
        "view_type": ["City View", "Ocean View", "Mountain View", "Garden View", "No View"],
        "listing_type": ["For Sale", "For Rent", "For Lease"],
    },
    "ecommerce": {
        "category": ["Electronics", "Clothing & Apparel", "Home & Garden", "Sports & Outdoors", "Books", "Toys & Games", "Food & Grocery", "Beauty & Health"],
        "order_status": ["Processing", "Awaiting Shipment", "Shipped", "Out for Delivery", "Delivered", "Returned", "Cancelled"],
        "status": ["Processing", "Awaiting Shipment", "Shipped", "Delivered", "Returned", "Cancelled"],
        "shipping_method": ["Standard", "Express", "Overnight", "Free Shipping", "In-Store Pickup"],
        "payment_method": ["Credit Card", "Debit Card", "PayPal", "Apple Pay", "Google Pay", "Bank Transfer"],
        "return_reason": ["Defective Product", "Wrong Item Sent", "Changed Mind", "Better Price Found", "Arrived Too Late"],
        "product_condition": ["New", "Like New", "Good", "Acceptable", "Refurbished"],
    },
    "healthcare": {
        "blood_type": ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"],
        "department": ["Cardiology", "Oncology", "Neurology", "Pediatrics", "Emergency", "Orthopedics", "Radiology", "Surgery"],
        "appointment_status": ["Scheduled", "Completed", "Cancelled", "No Show", "Rescheduled"],
        "status": ["Scheduled", "Completed", "Cancelled", "No Show", "Rescheduled"],
        "visit_type": ["Initial Consultation", "Follow-up", "Annual Checkup", "Emergency", "Procedure"],
        "insurance_type": ["Private", "Medicare", "Medicaid", "Self-Pay", "Workers Compensation"],
    },
    "finance": {
        "account_type": ["Checking", "Savings", "Credit", "Investment", "Mortgage", "Business"],
        "transaction_type": ["Debit", "Credit", "Transfer", "Deposit", "Withdrawal", "Payment"],
        "status": ["Completed", "Pending", "Failed", "Reversed", "Processing"],
        "transaction_status": ["Completed", "Pending", "Failed", "Reversed", "Processing"],
        "loan_status": ["Current", "Late", "Delinquent", "Default", "Paid Off"],
        "credit_rating": ["AAA", "AA", "A", "BBB", "BB", "B", "CCC"],
        "payment_method": ["ACH Transfer", "Wire Transfer", "Check", "Credit Card", "Debit Card"],
    },
    "hr": {
        "department": ["Engineering", "Sales", "Marketing", "Finance", "Human Resources", "Operations", "Product", "Legal", "Customer Support"],
        "employment_type": ["Full-time", "Part-time", "Contract", "Intern", "Temporary"],
        "status": ["Active", "On Leave", "Terminated", "Resigned", "Retired"],
        "employment_status": ["Active", "On Leave", "Terminated", "Resigned", "Retired"],
        "performance_rating": ["Exceptional", "Exceeds Expectations", "Meets Expectations", "Below Expectations", "Unsatisfactory"],
        "education_level": ["High School", "Associate Degree", "Bachelor's Degree", "Master's Degree", "PhD"],
    },
    "saas": {
        "plan_type": ["Free", "Starter", "Pro", "Business", "Enterprise"],
        "plan": ["Free", "Starter", "Pro", "Business", "Enterprise"],
        "status": ["Active", "Trial", "Past Due", "Cancelled", "Paused"],
        "subscription_status": ["Active", "Trial", "Past Due", "Cancelled", "Paused"],
        "billing_cycle": ["Monthly", "Annual", "Quarterly"],
        "churn_reason": ["Too Expensive", "Missing Features", "Found Alternative", "Business Closed", "No Longer Needed"],
    },
    "logistics": {
        "status": ["Received", "Processing", "In Transit", "Out for Delivery", "Delivered", "Returned"],
        "shipment_status": ["Received", "Processing", "In Transit", "Out for Delivery", "Delivered", "Returned"],
        "carrier": ["FedEx", "UPS", "DHL", "USPS", "Amazon Logistics"],
        "service_level": ["Standard Ground", "2-Day Air", "Next Day Air", "International Economy", "International Express"],
    },
    "education": {
        "department": ["Computer Science", "Mathematics", "Physics", "English", "History", "Biology", "Chemistry", "Business", "Arts"],
        "letter_grade": ["A", "A-", "B+", "B", "B-", "C+", "C", "D", "F"],
        "enrollment_status": ["Enrolled", "Withdrawn", "Graduated", "On Leave", "Suspended"],
        "status": ["Enrolled", "Withdrawn", "Graduated", "On Leave", "Suspended"],
        "course_type": ["Lecture", "Lab", "Seminar", "Online", "Hybrid"],
    },
}

_COL_VOCAB: Dict[str, List] = {
    "gender": ["Male", "Female", "Non-binary", "Prefer not to say"],
    "sex": ["Male", "Female"],
    "country": ["United States", "United Kingdom", "Canada", "Germany", "France", "Australia", "Japan", "India", "Brazil"],
    "currency": ["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "INR"],
    "day_of_week": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "quarter": ["Q1", "Q2", "Q3", "Q4"],
    "season": ["Spring", "Summer", "Fall", "Winter"],
    "priority": ["Low", "Medium", "High", "Critical"],
    "severity": ["Low", "Medium", "High", "Critical"],
    "size": ["XS", "S", "M", "L", "XL", "XXL"],
    "language": ["English", "Spanish", "French", "German", "Chinese", "Japanese", "Portuguese", "Arabic"],
    "continent": ["North America", "South America", "Europe", "Asia", "Africa", "Australia", "Antarctica"],
    "color": ["Red", "Blue", "Green", "Yellow", "Black", "White", "Gray", "Orange", "Purple", "Brown"],
}

_BLACKLISTED_VALUES: frozenset = frozenset({
    "premium", "enterprise", "professional", "essential", "team", "ultimate",
    "scale", "starter", "growth", "core", "max", "ultra", "pro", "lite",
    "default", "general", "advanced", "basic", "standard", "primary",
    "secondary", "custom", "plus", "business",
    "type_a", "type_b", "type_c", "type_d",
    "category_a", "category_b", "category_c",
    "value_1", "value_2", "value_3",
    "option_1", "option_2", "option_3",
})


SYSTEM_PROMPT = """You are Misata, an expert synthetic data architect. Your job is to generate REALISTIC database schemas based ONLY on the user's story. 

## CRITICAL: DO NOT USE DEFAULT EXAMPLES
- Generate tables that are SPECIFIC to the user's domain.
- If user says "pet store", create tables like "pets", "pet_categories", "pet_sales".
- If user says "music streaming", create tables like "songs", "artists", "streams".
- NEVER default to fitness/exercise/workout tables UNLESS the user explicitly asks for them.

## TABLE TYPES

### 1. REFERENCE TABLES (is_reference: true)
Small lookup / dimension tables (3-20 rows) with ACTUAL DATA you generate.
- ANY table of plans, tiers, statuses, types, categories, roles, stages, or
  similar labels MUST be is_reference: true with `inline_data` — NEVER a
  code-generated table. Its label column (name/status/type) is real data you
  write, not something the engine should invent (or it becomes person names).
- MUST have an "id" column (integer, sequential from 1)
- Put the REAL values in inline_data, using the user's story when it names them.
  e.g. plans the user described as "Starter, Pro, Enterprise":
  `"inline_data": [{"id":1,"name":"Starter","monthly_price":49},{"id":2,"name":"Pro","monthly_price":199},{"id":3,"name":"Enterprise","monthly_price":499}]`
  e.g. an invoice_status table: `[{"id":1,"status":"Pending"},{"id":2,"status":"Paid"},{"id":3,"status":"Overdue"}]`
- DOMAIN-SPECIFIC VALUES ONLY. Use real-world vocabulary for each domain.
  SaaS tier words ("Premium", "Standard", "Advanced", "Basic", "Core", "Pro")
  MUST NOT appear as values for non-SaaS categories (cities, property types,
  heating types, parking, etc.). Use the COMPLETE EXAMPLE at the end of this
  prompt as a reference for correct real-estate vocabulary.
- EXACT USER VALUES: When the user's story explicitly names the values for a
  category (e.g., "Free, Pro, Enterprise plans"), use EXACTLY those values —
  do not add, rename, or remove any. Only invent values when the user did NOT
  specify them.
- HUMAN-READABLE STRINGS in inline_data and choices: for display columns (type,
  status, method, category, reason, tier, plan, channel, industry, department)
  always use Title Case or Sentence case strings ("Credit Card", "In Progress",
  "Off Market") — NEVER snake_case ("credit_card", "in_progress", "off_market").
  Snake_case is for column NAMES only, not values.
- For free-text columns on transactional tables, set a `text_type` when obvious
  (email, name, company, url for domains, phone, address, city, country).

### 2. TRANSACTIONAL TABLES (is_reference: false)
Large tables generated by code using foreign keys.
- Use row_count to specify size
- Use foreign_key type to reference parent tables
- CRITICAL: Every column ending in `_id` that references another table MUST have
  `"type": "foreign_key"`. NEVER use `"type": "text"` or `"type": "int"` for FK
  columns (city_id, property_type_id, agent_id, status_id, etc.).

## OUTPUT FORMAT

{
  "name": "Dataset Name based on user's domain",
  "description": "Description of the domain",
  "seed": 42,
  "tables": [
    {
      "name": "domain_specific_reference_table",
      "is_reference": true,
      "inline_data": [
        {"id": 1, "name": "Value A", "price": 10.00},
        {"id": 2, "name": "Value B", "price": 20.00}
      ]
    },
    {
      "name": "domain_specific_transactional_table",
      "row_count": 10000,
      "is_reference": false
    }
  ],
  "columns": {
    "domain_specific_transactional_table": [
      {"name": "id", "type": "int", "distribution_params": {"distribution": "uniform", "min": 1, "max": 10000}, "unique": true},
      {"name": "ref_id", "type": "foreign_key", "distribution_params": {}},
      {"name": "amount", "type": "float", "distribution_params": {"distribution": "normal", "mean": 50, "std": 20}},
      {"name": "date", "type": "date", "distribution_params": {"start": "2024-01-01", "end": "2025-12-31"}}
    ]
  },
  "relationships": [
    {"parent_table": "domain_specific_reference_table", "child_table": "domain_specific_transactional_table", "parent_key": "id", "child_key": "ref_id"}
  ],
  "outcome_curves": [],
  "rate_curves": [],
  "events": []
}

## SMART DEFAULTS FOR COLUMNS

Age: int, normal, mean: 35, std: 12, min: 18, max: 80
Price/Amount: float, exponential, scale: 50, min: 0.01, decimals: 2
Rating (1-5): int, categorical, choices: [1,2,3,4,5], probabilities: [0.05, 0.08, 0.15, 0.32, 0.40]
Bedrooms: int, categorical, choices: [1,2,3,4,5,6], probabilities: [0.05,0.20,0.35,0.25,0.10,0.05]
Bathrooms: float, categorical, choices: [1.0,1.5,2.0,2.5,3.0,3.5], probabilities: [0.10,0.20,0.35,0.20,0.10,0.05]
Quantity: int, poisson, lambda: 3, min: 1
Duration (min): int, normal, mean: 45, std: 20, min: 5
Boolean: boolean, probability: 0.5-0.9 depending on context
Date: date, start/end based on user's time context

## CORRELATED COLUMNS (use `depends_on`)
When the prompt states that a column depends on ANOTHER column (such as plan type affecting MRR amount), you MUST emit `depends_on`.
If it crosses a foreign key, use dot notation:
`"distribution_params": {"depends_on": "tenant_id.plan_type_id", "mapping": {"Enterprise": {"mean": 5000, "std": 500}, "Startup": {"mean": 100, "std": 20}}}`

## QUANTITATIVE PATTERNS — PICK THE RIGHT TOOL (decision tree)

A common mistake is to force EVERY quantitative statement into an outcome_curve.
Do NOT. There are FIVE distinct tools. Choose by what the user is describing:

⚠️  DISAMBIGUATION — "X [rises/falls] WITH another column" vs "X rises OVER TIME":
- "price rises WITH square footage" → two columns moving together → Tool 5 (correlation, r > 0)
- "price falls WITH distance from city center" → inverse column relationship → Tool 5 (correlation, r < 0)
- "revenue rises FROM January TO December" → one value changing over time → Tool 1 (outcome_curve)
The phrase "X [rises/falls/increases/decreases] with [column name]" is ALWAYS Tool 5 — NEVER an outcome_curve.
"with" followed by another column = cross-column relationship, no time involved.

1. A MAGNITUDE of a numeric column changing OVER TIME (revenue, sales, volume,
   amount) -> `outcome_curves`.  ("revenue peaks in December")
2. A RATE / PROPORTION / PERCENTAGE of a boolean or categorical outcome changing
   OVER TIME (churn rate, fraud rate, conversion rate, default rate, return rate)
   -> `rate_curves`.  ("churn rises from 2% to 9% over the year")
3. A STATIC split / mix / share with NO time component (a fixed breakdown)
   -> categorical `choices` + `probabilities` on the column. NOT a curve.
   ("70% resolved, 20% pending, 10% escalated")
4. A DISTRIBUTION SHAPE (power-law, long-tail, bimodal, "a few get most, most get
   little", heavily skewed) -> set `distribution` in distribution_params on the
   column (e.g. "zipf", "lognormal", "pareto"). NOT a curve.
   ("a few creators get millions of views, most get very few")
5. TWO NUMERIC COLUMNS that move together or in opposition ("price rises with
   square footage", "default rate falls as credit score rises") -> `correlations`
   on the table. NEVER an outcome_curve — there is no time component here.

CRITICAL placement rule: a curve's `column` MUST be a real measure column
(amount, revenue, count, price, a boolean flag, …). NEVER attach a curve to an
`id`, primary-key, or foreign-key column. If there is no suitable measure column,
do NOT emit a curve.

Only emit a curve when the user ACTUALLY describes a time trend or rate change.
Do NOT invent seasonal/growth curves for prompts that don't mention them.

### Tool 1 — outcome_curves (magnitude over time)
If the user provides EXPLICIT numeric targets by period, output exact target curves:
- "50k in Jan, 80k in Feb, 120k in Mar" -> `value_mode: "absolute"` with `target_value`
- "revenue rises from 50k in Jan to 200k in Dec" -> concrete monthly target_value points
- qualitative words like "dip in September" -> a lower target_value for September
- sub-period patterns ("busy on weekdays", "spikes at month end") -> set
  `intra_period_pattern` to "weekday_heavy" | "weekend_heavy" | "start_heavy" | "end_heavy".

Keywords: "peak"/"spike"/"surge" -> high; "dip"/"drop" -> low;
"growth"/"upward trend" -> pattern_type "growth"; "seasonal" -> pattern_type "seasonal".

"outcome_curves": [
  {
    "table": "sales", "column": "amount", "time_column": "sale_date",
    "time_unit": "month", "pattern_type": "seasonal", "value_mode": "absolute",
    "intra_period_pattern": "weekday_heavy",
    "description": "High in December, low in February",
    "curve_points": [
      {"month": 1, "target_value": 50000},
      {"month": 9, "target_value": 90000},
      {"month": 12, "target_value": 200000}
    ]
  }
]

### Tool 2 — rate_curves (a rate/proportion over time)
Use this ONLY when a percentage CHANGES ACROSS TIME ("rises from 2% in Jan to 9%
by Dec", "fraud climbs over the year"). It needs ≥2 rate_points at DIFFERENT
periods. If the percentages do not change over time, this is NOT a rate_curve —
use Tool 3 instead.
`column` is the boolean/categorical column; `true_value` is the positive class.
Each rate_point is `{"period": "<YYYY-MM>" or month index, "rate": <0..1>}`.

"rate_curves": [
  {
    "table": "subscriptions", "column": "churned", "time_column": "churn_date",
    "time_unit": "month", "true_value": true, "interpolate": true,
    "description": "Monthly churn rises from 2% in Jan to 9% by Dec",
    "rate_points": [
      {"period": 1, "rate": 0.02},
      {"period": 12, "rate": 0.09}
    ]
  }
]

### Tool 3 — static proportions (no time) -> probabilities
A breakdown whose percentages sum across CATEGORIES at a single point in time
(NO "over the year", NO "rises to", NO month/period) is a static split. It is
NOT a rate_curve and NOT an outcome_curve — put it directly on the column as
`choices` + `probabilities`. Example — "70% resolved, 20% pending, 10% escalated":
{"name": "status", "type": "categorical",
 "distribution_params": {"choices": ["resolved","pending","escalated"],
                          "probabilities": [0.70, 0.20, 0.10]}}
Litmus test: if the numbers add up to 100% across categories, it's Tool 3
(probabilities). If a single percentage moves between two times, it's Tool 2
(rate_curve).

### Tool 4 — distribution shape -> distribution_params
"a few creators get millions of views, most get very few" is NOT a curve. It is a
heavy-tailed distribution on the view-count column:
{"name": "view_count", "type": "int",
 "distribution_params": {"distribution": "zipf", "a": 2.0, "min": 0}}
Use "lognormal" or "pareto" for income/wealth/file-size style long tails.

### Conditional / dependent rates -> depends_on (see CORRELATED COLUMNS above)
"approval depends on policy type: auto 80%, health 60%" is a CONDITIONAL rate, not
a curve. Put it on the boolean column with `depends_on`:
{"name": "approved", "type": "boolean",
 "distribution_params": {"depends_on": "policy_type_id",
                          "mapping": {"auto": 0.80, "health": 0.60}}}

### Correlations between two numeric columns -> table `correlations`
"default rate increases as credit score decreases" — when BOTH are numeric and you
want them statistically linked, declare a correlation on the TABLE (negative r for
inverse relationships):
"tables": [{"name": "loans", "row_count": 8000,
            "correlations": [{"col_a": "credit_score", "col_b": "default_probability", "r": -0.6}]}]
If one side is a boolean outcome conditioned on the other, prefer `depends_on` instead.

Real-estate example: "price rises with square footage AND falls with distance from city center":
"tables": [{"name": "listings", "row_count": 10000,
            "correlations": [
              {"col_a": "price", "col_b": "square_footage", "r": 0.75},
              {"col_a": "price", "col_b": "distance_from_city_center_miles", "r": -0.65}
            ]}]
This has NO time component — emit ZERO outcome_curves or rate_curves for it.

## NOISE CONFIGURATION
If the user mentions wanting messy, dirty, or imperfect data, include a `noise_config` object exactly like this:
"noise_config": {
  "mode": "analytics_safe",
  "null_rate": 0.05,
  "typo_rate": 0.02
}

## DATE RANGE RULES
- "Last 2 years" -> start: 2024-01-01, end: 2025-12-31
- "Past year" -> start: 2025-01-01, end: 2025-12-31
- "Historical data" -> start: 2020-01-01, end: 2025-12-31
- No mention -> Default to current year (2025)

## COMPLETE WORKED EXAMPLE

Story: "A real-estate dataset of 10,000 listings where price rises with square footage and falls with distance from the city center."

```json
{
  "name": "Real Estate Listings",
  "seed": 42,
  "tables": [
    {"name":"property_types","is_reference":true,"row_count":7,
     "inline_data":[
       {"id":1,"name":"Single Family Home"},{"id":2,"name":"Condo"},
       {"id":3,"name":"Townhouse"},{"id":4,"name":"Multi-Family"},
       {"id":5,"name":"Apartment"},{"id":6,"name":"Studio"},{"id":7,"name":"Loft"}
     ]},
    {"name":"listing_statuses","is_reference":true,"row_count":5,
     "inline_data":[
       {"id":1,"status":"Active"},{"id":2,"status":"Pending"},{"id":3,"status":"Sold"},
       {"id":4,"status":"Off Market"},{"id":5,"status":"Expired"}
     ]},
    {"name":"listings","is_reference":false,"row_count":10000,
     "correlations":[
       {"col_a":"price","col_b":"square_footage","r":0.75},
       {"col_a":"price","col_b":"distance_from_city_center_miles","r":-0.65}
     ]}
  ],
  "columns":{
    "listings":[
      {"name":"id","type":"int","distribution_params":{"distribution":"uniform","min":1,"max":10000},"unique":true},
      {"name":"property_type_id","type":"foreign_key","distribution_params":{}},
      {"name":"status_id","type":"foreign_key","distribution_params":{}},
      {"name":"price","type":"float","distribution_params":{"distribution":"lognormal","mean":12.5,"std":0.6,"min":80000,"decimals":0}},
      {"name":"square_footage","type":"int","distribution_params":{"distribution":"normal","mean":1800,"std":600,"min":400,"max":8000}},
      {"name":"bedrooms","type":"int","distribution_params":{"distribution":"categorical","choices":[1,2,3,4,5,6],"probabilities":[0.05,0.20,0.35,0.25,0.10,0.05]}},
      {"name":"bathrooms","type":"float","distribution_params":{"distribution":"categorical","choices":[1.0,1.5,2.0,2.5,3.0],"probabilities":[0.15,0.25,0.35,0.20,0.05]}},
      {"name":"distance_from_city_center_miles","type":"float","distribution_params":{"distribution":"exponential","scale":8.0,"min":0.1,"decimals":1}},
      {"name":"year_built","type":"int","distribution_params":{"distribution":"normal","mean":1985,"std":25,"min":1900,"max":2024}},
      {"name":"listing_date","type":"date","distribution_params":{"start":"2023-01-01","end":"2025-12-31"}},
      {"name":"city","type":"text","distribution_params":{"text_type":"city"}},
      {"name":"address","type":"text","distribution_params":{"text_type":"address"}}
    ]
  },
  "relationships":[
    {"parent_table":"property_types","child_table":"listings","parent_key":"id","child_key":"property_type_id"},
    {"parent_table":"listing_statuses","child_table":"listings","parent_key":"id","child_key":"status_id"}
  ],
  "outcome_curves":[],
  "rate_curves":[],
  "events":[]
}
```

Key points this example demonstrates:
- Reference table inline_data uses REAL values ("Single Family Home", "Active") — NEVER "Premium/Standard/Basic"
- "price rises WITH square_footage" → `correlations` on the table (r=+0.75), NOT outcome_curves
- "price falls WITH distance" → `correlations` (r=-0.65), NOT outcome_curves
- outcome_curves=[] because the story has NO time trend
- Every *_id column → `"type":"foreign_key"`, never text or int

Generate schemas ONLY based on the user's story. Be creative and domain-specific."""



GRAPH_REVERSE_PROMPT = """You are Misata, an expert at reverse-engineering data patterns.
Given a description of a desired chart or graph pattern, generate a schema that will
produce data matching that EXACT pattern when plotted.

Follow the same two-tier table structure:
- Reference tables with inline_data for lookup values
- Transactional tables with foreign keys for mass data

The user will describe a chart they want. Your job is to generate data that,
when plotted, produces that exact chart."""


ENRICH_SCHEMA_PROMPT = """You are Misata, an expert synthetic data architect. You receive a BARE database schema (table names, column names, types, relationships) and your job is to ENRICH it with realistic, mathematically intelligent data generation parameters.

## YOUR GOAL
Analyze the schema structure, infer the domain, and return enriched column definitions that will produce **realistic, correlated** synthetic data — not random noise.

## WHAT YOU MUST RETURN

For each column, return enriched `distribution_params` following these rules:

### 1. STATISTICAL DISTRIBUTIONS (pick the RIGHT one)
- Prices/amounts → `{"distribution": "exponential", "scale": 50, "min": 0.01, "decimals": 2}`
- Ratings (1-5) → `{"distribution": "categorical", "choices": [1,2,3,4,5], "probabilities": [0.05, 0.08, 0.15, 0.32, 0.40]}`
- Counts/quantities → `{"distribution": "poisson", "lambda": 3, "min": 1}`
- Ages → `{"distribution": "normal", "mean": 35, "std": 12, "min": 18, "max": 80}`
- Percentages → `{"distribution": "uniform", "min": 0, "max": 100, "decimals": 1}`
- Durations → `{"distribution": "normal", "mean": 45, "std": 20, "min": 5}`

### 2. CORRELATED COLUMNS (use `depends_on`)
When columns are logically related to other columns (even via foreign keys!), use conditional distributions:
- Salary depends on job_title: `{"depends_on": "job_title", "mapping": {"Intern": {"mean": 40000, "std": 5000}, "CTO": {"mean": 200000, "std": 30000}}}`
- State depends on country: `{"depends_on": "country", "mapping": {"USA": ["CA", "TX", "NY"], "UK": ["England", "Scotland"]}}`
- Churn depends on plan: `{"depends_on": "plan_type_id", "mapping": {"Free": 0.3, "Pro": 0.1, "Enterprise": 0.05}}`
- Cross-Table FK Dependency (CRITICAL): If 'amount' depends on the tenant's plan type, use dot notation:
  `{"depends_on": "tenant_id.plan_type_id", "mapping": {"Enterprise": {"mean": 5000, "std": 500}, "Startup": {"mean": 100, "std": 20}}}`

### 3. TEXT TYPE INFERENCE (from column name)
- email, user_email → `{"text_type": "email"}`
- name, full_name, first_name, last_name → `{"text_type": "name"}`
- company, company_name, organization → `{"text_type": "company"}`
- phone, phone_number → `{"text_type": "phone"}`
- address, street → `{"text_type": "address"}`
- url, website, link → `{"text_type": "url"}`
- description, notes, comment → `{"text_type": "sentence"}`

### 4. CATEGORICAL COLUMNS (infer from domain)
- status columns → choices SPECIFIC to the entity, never a generic trio:
  listing status → `["active", "pending", "sold", "under_offer", "withdrawn", "expired"]`,
  order status → `["pending", "confirmed", "shipped", "delivered", "cancelled", "returned"]`,
  invoice status → `["draft", "sent", "paid", "overdue", "disputed"]`
- priority → `{"choices": ["low", "medium", "high", "critical"], "probabilities": [0.2, 0.4, 0.3, 0.1]}`
- type/category → domain-specific choices with realistic probabilities
  (property types → House/Apartment/Condo/Townhouse/Villa — NOT tier words like Premium/Basic)

### 5. REFERENCE TABLES (small lookup tables)
If a table looks like a lookup (few expected rows, referenced by others via FK), convert it:
- Set `is_reference: true`
- Generate `inline_data` with realistic rows (5-20 rows)
- Include an `id` column with sequential integers
- Label values must be domain-appropriate for the table's noun and ALL DISTINCT
  (a `property_types` table lists House/Apartment/Condo…, never Premium/Basic;
  a 5-row statuses table needs 5 different statuses)

### 5b. MONETARY SCALE (sanity-check every money column)
Amounts must match the business context, and when a plan/tier/category exists
they MUST use `depends_on` + `mapping` rather than one global distribution:
- SaaS invoice/MRR → plan-priced: Free = 0, Pro ≈ 29–99/mo, Enterprise ≈ 500–5000/mo
  → `{"depends_on": "plan_tier_id", "mapping": {"Free": 0, "Pro": {"mean": 49, "std": 15}, "Enterprise": {"mean": 1500, "std": 600}}}`
- Real-estate listing price → 50k–5M; coffee/food order → 3–80; salary → locale-scaled
- NEVER give a mean without a std for money: std should be roughly 20–40% of the mean

### 6. BUSINESS RULE CONSTRAINTS
Infer constraints from column names:
- hours/duration in timesheets → `{"name": "max_daily_hours", "type": "max_per_group", "group_by": ["employee_id", "date"], "column": "hours", "value": 8, "action": "cap"}`

## CRITICAL RULES
- Skip `foreign_key` columns entirely — return them unchanged
- Skip `id` columns that are primary keys — return them unchanged  
- Dates: provide appropriate `start` and `end` based on the inferred domain
- Every `int` and `float` column MUST have a `distribution` key in distribution_params
- Every `categorical` column MUST have `choices` and `probabilities`
- Every `text` column MUST have `text_type`
- Every `date` column MUST have `start` and `end`
- Be SPECIFIC to the domain you infer from the schema

## OUTPUT FORMAT

Return valid JSON with this structure:
{
  "inferred_domain": "Brief description of the domain",
  "columns": {
    "table_name": [
      {"name": "col_name", "type": "col_type", "distribution_params": {...}, "nullable": false, "unique": false}
    ]
  },
  "reference_tables": [
    {
      "name": "table_name",
      "inline_data": [{"id": 1, "name": "Value A"}, ...]
    }
  ],
  "constraints": {
    "table_name": [
      {"name": "rule_name", "type": "max_per_group", "group_by": [...], "column": "col", "value": 8, "action": "cap"}
    ]
  }
}"""


class LLMSchemaGenerator:
    """
    Generate realistic schemas from natural language using LLMs.

    Supports multiple providers:
    - groq: Groq Cloud (Llama 3.3) - Fast, free tier
    - openai: OpenAI (GPT-4o) - Best quality
    - ollama: Local Ollama - Free, private

    This is the "brain" of Misata - what makes it genuinely AI-powered.
    """

    # Provider configurations
    PROVIDERS = {
        "groq": {
            "base_url": None,  # Uses default
            "env_key": "GROQ_API_KEY",
            "default_model": "qwen/qwen3-32b",
            "protocol": "openai",
        },
        "openai": {
            "base_url": None,
            "env_key": "OPENAI_API_KEY",
            "default_model": "gpt-4o-mini",
            "protocol": "openai",
        },
        "ollama": {
            "base_url": "http://localhost:11434/v1",
            "env_key": None,  # No key needed for local
            "default_model": "llama3",
            "protocol": "openai",
        },
        "anthropic": {
            "base_url": None,
            "env_key": "ANTHROPIC_API_KEY",
            "default_model": "claude-haiku-4-5-20251001",
            "protocol": "anthropic",
        },
        "bedrock": {
            # AWS Bedrock — Claude via the Converse API. Simplest auth: a Bedrock
            # API key in AWS_BEARER_TOKEN_BEDROCK (no IAM access keys needed);
            # the standard AWS chain (IAM keys / role) also works. Region from
            # AWS_REGION, model from BEDROCK_MODEL_ID (or default).
            # Sonnet 4.5 is the quality default for schema generation; set
            # BEDROCK_MODEL_ID to a Haiku id for a cheaper/faster path, or to a
            # region inference-profile id (us./eu./global.) if your account
            # requires it.
            "base_url": None,
            "env_key": None,
            "default_model": "anthropic.claude-sonnet-4-5-20250929-v1:0",
            "protocol": "bedrock",
        },
        "gemini": {
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "env_key": "GEMINI_API_KEY",
            "default_model": "gemini-2.0-flash",
            "protocol": "openai",  # Gemini exposes an OpenAI-compatible endpoint
        },
    }

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        enable_feedback: bool = False,
        feedback_db_path: Optional[str] = None,
        feedback_min_occurrences: int = 3,
    ):
        """
        Initialize the LLM generator.

        Args:
            provider: LLM provider ("groq", "openai", "ollama").
                      Defaults to MISATA_PROVIDER env var or "groq".
            api_key: API key. If not provided, reads from provider's env var.
            model: Model name. If not provided, uses provider default.
            base_url: Custom API base URL (for Ollama or compatible APIs).
        """
        # Determine provider
        self.provider = provider or os.environ.get("MISATA_PROVIDER", "groq").lower()
        self.enable_feedback = enable_feedback
        self.feedback_db_path = feedback_db_path
        self.feedback_min_occurrences = feedback_min_occurrences
        self._feedback_db: Optional[FeedbackDatabase] = None

        if self.provider not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {self.provider}. Use: {list(self.PROVIDERS.keys())}")

        config = self.PROVIDERS[self.provider]
        self._protocol = config["protocol"]

        # Get API key
        self.api_key = api_key
        if not self.api_key and config["env_key"]:
            self.api_key = os.environ.get(config["env_key"])

        if not self.api_key and self.provider not in ("ollama", "bedrock"):
            env_key = config["env_key"]
            raise ValueError(
                f"{self.provider.title()} API key required. "
                f"Set {env_key} environment variable or pass api_key parameter."
            )

        # Set model. Bedrock model ids vary by what's enabled in the account/
        # region, so an env override is honoured before the default.
        self.model = model or config["default_model"]
        if self.provider == "bedrock":
            self.model = model or os.environ.get("BEDROCK_MODEL_ID") or config["default_model"]

        # Set base URL
        self.base_url = base_url or config["base_url"]

        # Initialize client
        if self.provider == "groq":
            if Groq is None:
                raise ImportError(
                    "groq package required for the Groq provider. "
                    "Install with: pip install groq"
                )
            self.client = Groq(api_key=self.api_key)

        elif self.provider == "anthropic":
            if _anthropic_sdk is None:
                raise ImportError(
                    "anthropic package required. Install with: pip install anthropic"
                )
            self.client = _anthropic_sdk.Anthropic(api_key=self.api_key)

        elif self.provider == "bedrock":
            # Prefer a Bedrock bearer token (AWS_BEARER_TOKEN_BEDROCK env var or
            # api_key param) for direct HTTP — no boto3 or IAM credentials needed.
            # Falls back to boto3 with the standard AWS credential chain if no
            # bearer token is available.
            bearer = self.api_key or os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
            self._bedrock_region = (
                self.base_url
                or os.environ.get("AWS_REGION")
                or os.environ.get("AWS_DEFAULT_REGION")
                or "us-east-1"
            )
            if bearer:
                self._bedrock_bearer = bearer
                self.client = None
            else:
                self._bedrock_bearer = None
                try:
                    import boto3
                except ImportError:
                    raise ImportError(
                        "boto3 required for the Bedrock provider when no bearer token is set. "
                        "Install with: pip install 'misata[bedrock]', or set AWS_BEARER_TOKEN_BEDROCK."
                    )
                self.client = boto3.client("bedrock-runtime", region_name=self._bedrock_region)

        else:
            # OpenAI, Ollama, and Gemini all use the OpenAI-compatible interface
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError(
                    f"openai package required for {self.provider}. "
                    "Install with: pip install openai"
                )

            client_kwargs: Dict[str, str] = {}
            if self.api_key:
                client_kwargs["api_key"] = self.api_key
            if self.base_url:
                client_kwargs["base_url"] = self.base_url

            # Ollama doesn't need a real API key
            if self.provider == "ollama":
                client_kwargs["api_key"] = "ollama"

            self.client = OpenAI(**client_kwargs)

    def _get_feedback_db(self) -> Optional[FeedbackDatabase]:
        """Lazily initialize the feedback database when feedback is enabled."""
        if not self.enable_feedback:
            return None
        if self._feedback_db is None:
            self._feedback_db = FeedbackDatabase(self.feedback_db_path)
        return self._feedback_db

    def _infer_feedback_industry(
        self,
        text: str = "",
        table_names: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Infer a broad industry scope for feedback rules."""
        corpus = text.lower()
        if table_names:
            corpus = f"{corpus} {' '.join(table_names).lower()}"

        domain_keywords = {
            "saas": ["saas", "subscription", "billing", "mrr", "arr", "tenant"],
            "ecommerce": ["ecommerce", "order", "cart", "product", "shipping", "inventory"],
            "finance": ["finance", "payment", "account", "transaction", "bank"],
            "healthcare": ["health", "clinical", "patient", "diagnosis", "pharma", "procedure"],
            "education": ["student", "course", "lesson", "enrollment", "grade"],
        }

        for industry, keywords in domain_keywords.items():
            if any(keyword in corpus for keyword in keywords):
                return industry
        return None

    def _build_feedback_prompt(
        self,
        *,
        story: Optional[str] = None,
        schema: Optional[SchemaConfig] = None,
        prompt: Optional[str] = None,
    ) -> str:
        """Build an optional scoped feedback suffix for LLM prompts."""
        feedback_db = self._get_feedback_db()
        if feedback_db is None:
            return ""

        table_names = [table.name for table in schema.tables] if schema else None
        industry = self._infer_feedback_industry(
            text=" ".join(part for part in [story or "", prompt or ""] if part),
            table_names=table_names,
        )
        enhancement = feedback_db.generate_prompt_enhancement(
            min_occurrences=self.feedback_min_occurrences,
            industry=industry,
            table_names=table_names,
        )
        if not enhancement:
            return ""
        return f"\n\nLEARNED FEEDBACK RULES:\n{enhancement}"

    def generate_from_story(
        self,
        story: str,
        use_research: bool = False,
        default_rows: int = 10000,
        temperature: float = 0.3,
    ) -> SchemaConfig:
        """
        Generate a realistic schema from a natural language story.

        Args:
            story: Natural language description of the data needs
            default_rows: Default row count if not specified in story
            temperature: LLM temperature (lower = more consistent)

        Returns:
            SchemaConfig ready for data generation
        """
        research_context = ""
        if use_research:
            domain = "SaaS"
            story_lower = story.lower()
            if "fitness" in story_lower:
                domain = "Fitness App"
            elif "ecommerce" in story_lower or "shop" in story_lower:
                domain = "Ecommerce"
            elif "finance" in story_lower:
                domain = "Fintech"

            try:
                agent = DeepResearchAgent(use_mock=True)
                entities = agent.search_entities(domain, "Competitors", limit=5)
                names = [entity["name"] for entity in entities if entity.get("name")]
                if names:
                    research_context = (
                        "\n\nREAL WORLD CONTEXT (INJECTED):\n"
                        f"Research found these top players in {domain}: {', '.join(names)}.\n"
                        "Use these names as examples in the 'inline_data' for reference tables if relevant."
                    )
            except Exception as exc:
                warnings.warn(f"Research agent unavailable: {exc}")

        user_prompt = f"""Generate a complete synthetic data schema in JSON format for:

{story}
{research_context}

CRITICAL INSTRUCTIONS:
1. Generate tables SPECIFIC to the domain described above. DO NOT use generic fitness/exercise examples.
2. Create REFERENCE TABLES (is_reference: true) with inline_data for any lookup/configuration data relevant to THIS domain.
3. Create TRANSACTIONAL TABLES (is_reference: false) with row_count for high-volume data like users, transactions, events, etc.
4. Use foreign_key to link transactional tables to reference tables.
5. Default row count for transactional tables: {default_rows}
6. For quantitative patterns, pick the RIGHT tool (see the decision tree in the system prompt):
   a MAGNITUDE over time -> outcome_curves; a RATE/PROPORTION of a bool/categorical over time -> rate_curves;
   a STATIC split ("70/20/10") -> categorical probabilities; a SHAPE ("a few get most") -> a heavy-tailed distribution;
   a CONDITIONAL rate ("approval depends on type") -> depends_on; two correlated numeric columns -> table correlations.
7. If the story gives explicit numeric targets by month/period, use exact `target_value` outcome_curves with `value_mode: "absolute"`.
8. Never attach a curve to an id/primary-key/foreign-key column, and do NOT invent curves the story didn't describe.
9. If the user mentions sub-period trends ("slow weekends"), set `intra_period_pattern` ("weekday_heavy", "weekend_heavy", "start_heavy", "end_heavy").
10. If the user mentions a time range (e.g., "last 2 years"), set date column start/end accordingly.

Output valid JSON. Be creative and domain-specific - DO NOT copy the system prompt examples."""
        user_prompt += self._build_feedback_prompt(story=story)


        raw = self._call_api(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=6000,
            temperature=temperature,
        )
        schema_dict = self._parse_json_response(raw)
        return self._parse_schema(schema_dict)

    def generate_from_graph(
        self,
        graph_description: str,
        temperature: float = 0.2,
    ) -> SchemaConfig:
        """
        REVERSE ENGINEERING: Generate schema that produces desired graph patterns.
        """
        user_prompt = f"""Generate a JSON schema that will produce this chart pattern:

{graph_description}

Include reference tables with inline_data for lookup values and transactional tables for mass data. Output valid JSON."""


        raw = self._call_api(
            messages=[
                {"role": "system", "content": GRAPH_REVERSE_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=6000,
            temperature=temperature,
        )
        schema_dict = self._parse_json_response(raw)
        return self._parse_schema(schema_dict)

    # ------------------------------------------------------------------
    # Resilience helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(text: str) -> str:
        """Strip markdown code fences and return the innermost JSON string."""
        # Remove ```json ... ``` or ``` ... ``` wrappers
        text = text.strip()
        fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
        if fenced:
            return fenced.group(1).strip()
        # Some models wrap with a single backtick or add trailing prose
        # Try to find the first '{' and last '}' as the JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]
        return text

    def _call_api(self, messages: List[Dict], max_tokens: int = 6000, temperature: float = 0.3, max_retries: int = 3) -> str:
        """
        Call the LLM API with retry logic for transient failures.

        Supports OpenAI-compatible (groq, openai, ollama, gemini) and native
        Anthropic protocols.  Returns raw response text; never raises on parse
        errors — callers handle that.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                protocol = getattr(self, "_protocol", "openai")
                if protocol == "anthropic":
                    content = self._call_anthropic(messages, max_tokens, temperature)
                elif protocol == "bedrock":
                    content = self._call_bedrock(messages, max_tokens, temperature)
                else:
                    content = self._call_openai_compatible(messages, max_tokens, temperature)
                if not content:
                    raise ValueError("LLM returned an empty response.")
                return content
            except Exception as exc:
                last_exc = exc
                exc_str = str(exc).lower()
                if any(s in exc_str for s in ("rate_limit", "429", "timeout", "502", "503", "504", "connection", "overloaded", "throttl")):
                    wait = 2 ** attempt
                    warnings.warn(f"LLM API transient error (attempt {attempt + 1}/{max_retries}): {exc}. Retrying in {wait}s.")
                    time.sleep(wait)
                    continue
                break
        raise RuntimeError(
            f"LLM API call failed after {max_retries} attempts. Last error: {last_exc}"
        ) from last_exc

    def _call_openai_compatible(self, messages: List[Dict], max_tokens: int, temperature: float) -> str:
        """Call any OpenAI-compatible endpoint.

        Newer OpenAI models (the gpt-5 family and the o-series reasoning models) reject the
        legacy ``max_tokens`` parameter and only accept the model-default temperature, using
        ``max_completion_tokens`` instead. Older models (gpt-4o, and Groq/Together-hosted
        Llama) take ``max_tokens`` and a custom temperature. We try the legacy form first to
        preserve existing behavior, and on the specific 400 that names the unsupported
        parameter we retry with the modern form. This keeps one code path working across both
        generations without hard-coding model names.
        """
        base: Dict = dict(model=self.model, messages=messages)
        # Gemini's OpenAI-compat layer doesn't support response_format yet
        if self.provider not in ("gemini", "ollama"):
            base["response_format"] = {"type": "json_object"}

        try:
            response = self.client.chat.completions.create(
                **base, temperature=temperature, max_tokens=max_tokens)
        except Exception as exc:
            msg = str(exc).lower()
            modern = ("max_completion_tokens" in msg or "max_tokens" in msg
                      or "unsupported parameter" in msg or "temperature" in msg)
            if not modern:
                raise
            # Modern models: use max_completion_tokens and drop the custom temperature.
            # Optionally cap reasoning effort (set on the instance) so a simple extraction
            # task stays fast and cheap instead of paying for deep reasoning it does not need.
            extra: Dict = {}
            effort = getattr(self, "reasoning_effort", None)
            if effort:
                extra["reasoning_effort"] = effort
            response = self.client.chat.completions.create(
                **base, max_completion_tokens=max_tokens, **extra)
        return response.choices[0].message.content

    def _call_anthropic(self, messages: List[Dict], max_tokens: int, temperature: float) -> str:
        """Call Anthropic's Messages API (native SDK, different wire format)."""
        # Anthropic separates the system prompt from user/assistant turns
        system_text = ""
        turns = []
        for msg in messages:
            if msg["role"] == "system":
                system_text = msg["content"]
            else:
                turns.append({"role": msg["role"], "content": msg["content"]})

        # Ask the model to respond with JSON explicitly since Anthropic has no
        # response_format parameter like OpenAI does.
        if turns and not turns[-1]["content"].strip().endswith("JSON"):
            turns[-1] = {
                "role": turns[-1]["role"],
                "content": turns[-1]["content"] + "\n\nRespond with valid JSON only.",
            }

        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_text,
            messages=turns,
        )
        return response.content[0].text

    def _call_bedrock(self, messages: List[Dict], max_tokens: int, temperature: float) -> str:
        """Call AWS Bedrock via the Converse API (provider-agnostic message format).

        Converse separates the system prompt and uses a content-block message
        shape. Bedrock has no JSON-mode flag, so — like the Anthropic path — we
        nudge the model to emit JSON only.

        Auth: prefers a bearer token (AWS_BEARER_TOKEN_BEDROCK / api_key) via
        direct HTTPS — no boto3 or IAM credentials needed. Falls back to boto3
        when no bearer token is set.
        """
        import json as _json

        system_text = ""
        turns: List[Dict] = []
        for msg in messages:
            if msg["role"] == "system":
                system_text = msg["content"]
            else:
                turns.append({"role": msg["role"], "content": [{"text": msg["content"]}]})

        if turns and not turns[-1]["content"][0]["text"].strip().endswith("JSON"):
            turns[-1]["content"][0]["text"] += "\n\nRespond with valid JSON only."

        payload: Dict[str, Any] = {
            "messages": turns,
            "inferenceConfig": {"maxTokens": min(max_tokens, 4096), "temperature": temperature},
        }
        if system_text:
            system_blocks: List[Dict[str, Any]] = [{"text": system_text}]
            if len(system_text) >= 16000:
                system_blocks.append({"cachePoint": {"type": "default"}})
            payload["system"] = system_blocks

        if getattr(self, "_bedrock_bearer", None):
            import requests as _req
            endpoint = (
                f"https://bedrock-runtime.{self._bedrock_region}.amazonaws.com"
                f"/model/{self.model}/converse"
            )
            resp = _req.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {self._bedrock_bearer}",
                    "Content-Type": "application/json",
                },
                data=_json.dumps(payload),
                timeout=60,
            )
            if not resp.ok:
                raise RuntimeError(f"Bedrock bearer error: {resp.status_code} {resp.text}")
            data = resp.json()
            return data["output"]["message"]["content"][0]["text"]

        # boto3 path (IAM credentials)
        kwargs: Dict[str, Any] = {"modelId": self.model, **payload}
        response = self.client.converse(**kwargs)
        return response["output"]["message"]["content"][0]["text"]

    def _parse_json_response(self, raw: str) -> Dict:
        """
        Parse the raw LLM text into a dict.

        Tries direct parse first, then strips markdown fences, then falls
        back to extracting the first JSON object in the text.
        Raises `ValueError` with a human-readable message on complete failure.
        """
        for attempt_text in (raw, self._extract_json(raw)):
            try:
                return json.loads(attempt_text)
            except json.JSONDecodeError:
                pass
        raise ValueError(
            "Could not parse LLM response as JSON. "
            f"Raw response (first 500 chars): {raw[:500]!r}"
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_time_unit(unit, allow_quarter: bool = False) -> str:
        """Map an LLM time_unit onto the schema's allowed units.

        OutcomeCurve allows {day, week, month}; RateCurve additionally allows
        "quarter" — pass ``allow_quarter=True`` for the latter.
        """
        u = str(unit or "month").lower().strip()
        quarter_target = "quarter" if allow_quarter else "month"
        mapping = {
            "daily": "day", "hour": "day", "hourly": "day",
            "weekly": "week", "biweekly": "week", "fortnight": "week",
            "monthly": "month",
            "quarter": quarter_target, "quarterly": quarter_target,
            "year": "month", "yearly": "month", "annual": "month", "annually": "month",
        }
        u = mapping.get(u, u)
        allowed = ("day", "week", "month", "quarter") if allow_quarter else ("day", "week", "month")
        return u if u in allowed else "month"

    def _normalize_distribution_params(self, col_type: str, params: Dict) -> Dict:
        """Normalize LLM output variations in distribution_params."""
        normalized = params.copy()

        # Normalize date column parameters
        if col_type == "date":
            if "start_date" in normalized and "start" not in normalized:
                normalized["start"] = normalized.pop("start_date")
            if "end_date" in normalized and "end" not in normalized:
                normalized["end"] = normalized.pop("end_date")
            if "start" not in normalized:
                normalized["start"] = "2023-01-01"
            if "end" not in normalized:
                normalized["end"] = "2024-12-31"

        # Normalize categorical parameters
        if col_type == "categorical":
            if "options" in normalized and "choices" not in normalized:
                normalized["choices"] = normalized.pop("options")
            if "choices" not in normalized:
                normalized["choices"] = ["A", "B", "C"]

        # Coerce/repair probabilities. The LLM sometimes emits string numbers
        # ("0.5"), mixes ints and strings, gives the wrong count, or values that
        # don't sum to 1 — any of which crashes validation's sum(). Make it
        # bullet-proof: keep a clean float list that matches `choices` and sums
        # to 1, else drop it so the engine falls back to a uniform distribution.
        if "probabilities" in normalized:
            probs = normalized.get("probabilities")
            choices = normalized.get("choices")
            cleaned = None
            if isinstance(probs, (list, tuple)):
                try:
                    cleaned = [float(p) for p in probs]
                except (TypeError, ValueError):
                    cleaned = None
            if cleaned is not None and any(p < 0 for p in cleaned):
                cleaned = None
            if cleaned is not None and isinstance(choices, (list, tuple)) and len(cleaned) != len(choices):
                cleaned = None  # length mismatch — let the engine use uniform
            if cleaned is not None:
                total = sum(cleaned)
                if total > 0:
                    normalized["probabilities"] = [p / total for p in cleaned]
                else:
                    normalized.pop("probabilities", None)
            else:
                normalized.pop("probabilities", None)

        # Numeric distribution parameter sanity — the simulator crashes on
        # impossible values (negative std, inverted min/max, non-positive scale).
        # Fix them deterministically so generation always succeeds.
        if "std" in normalized:
            try:
                std_val = float(normalized["std"])
                normalized["std"] = max(abs(std_val), 1e-6)
            except (TypeError, ValueError):
                normalized.pop("std", None)

        if "min" in normalized and "max" in normalized:
            try:
                mn, mx = float(normalized["min"]), float(normalized["max"])
                if mn > mx:
                    normalized["min"], normalized["max"] = mx, mn
            except (TypeError, ValueError):
                pass

        if "scale" in normalized:
            try:
                if float(normalized["scale"]) <= 0:
                    normalized["scale"] = 1.0
            except (TypeError, ValueError):
                normalized.pop("scale", None)

        if "lambda" in normalized:
            try:
                if float(normalized["lambda"]) <= 0:
                    normalized["lambda"] = 1.0
            except (TypeError, ValueError):
                normalized.pop("lambda", None)

        if "a" in normalized and normalized.get("distribution") in ("zipf", "pareto", "powerlaw"):
            try:
                if float(normalized["a"]) <= 1:
                    normalized["a"] = 1.1
            except (TypeError, ValueError):
                normalized.pop("a", None)

        # Curve Fitting for 'control_points'
        if "control_points" in normalized:
            try:
                points = normalized.pop("control_points")
                dist_type = normalized.get("distribution", "normal")
                fitter = CurveFitter()
                fitted_params = fitter.fit_distribution(points, dist_type)
                normalized.update(fitted_params)
            except Exception as exc:
                warnings.warn(f"Curve fitting failed for control_points: {exc}")

        return normalized

    def _parse_schema(self, schema_dict: Dict) -> SchemaConfig:
        """Parse LLM output into validated SchemaConfig."""

        # Parse tables
        tables = []
        for t in schema_dict.get("tables", []):
            if not isinstance(t, dict):
                continue
            table_name_raw = t.get("name")
            if not table_name_raw:
                warnings.warn(f"Skipping table with missing 'name': {t!r}")
                continue
            is_ref = t.get("is_reference", False)
            inline = t.get("inline_data", None)
            row_count = t.get("row_count", len(inline) if inline else 100)

            # Pairwise numeric correlations ("default rate rises as credit score
            # falls"). Keep only well-formed {col_a, col_b, r} entries so a
            # malformed correlation never aborts the build.
            raw_corr = t.get("correlations") or []
            correlations = [
                {"col_a": c["col_a"], "col_b": c["col_b"], "r": float(c["r"])}
                for c in raw_corr
                if isinstance(c, dict) and {"col_a", "col_b", "r"} <= c.keys()
            ] if isinstance(raw_corr, list) else []

            tables.append(Table(
                name=table_name_raw,
                row_count=row_count,
                description=t.get("description"),
                is_reference=is_ref,
                inline_data=inline,
                correlations=correlations,
            ))

        # Parse columns (only for transactional tables, reference tables use inline_data)
        columns = {}
        for table_name, cols in schema_dict.get("columns", {}).items():
            if not isinstance(cols, list):
                continue
            columns[table_name] = []
            for c in cols:
                if not isinstance(c, dict):
                    continue
                if not c.get("name"):
                    continue
                col_type = c.get("type", "text")
                
                # Normalize LLM type variations to valid schema types
                type_mapping = {
                    "string": "text",
                    "str": "text",
                    "varchar": "text",
                    "char": "text",
                    "integer": "int",
                    "number": "float",
                    "decimal": "float",
                    "double": "float",
                    "timestamp": "datetime",
                    "bool": "boolean",
                    "enum": "categorical",
                    "category": "categorical",
                    "fk": "foreign_key",
                }
                col_type = type_mapping.get(col_type.lower(), col_type)

                # Models sometimes put a SEMANTIC text type in the `type` field
                # (e.g. `type: "email"`), which isn't a valid Column type and used
                # to crash the whole parse with a ValidationError. Coerce it to a
                # `text` column and carry the intent through as `text_type`.
                _SEMANTIC_TEXT_TYPES = {
                    "email", "url", "uri", "phone", "name", "full_name", "address",
                    "company", "city", "country", "username", "uuid", "ipv4", "ip",
                    "first_name", "last_name", "job", "domain",
                }
                raw_params = dict(c.get("distribution_params", {}) or {})
                if col_type.lower() in _SEMANTIC_TEXT_TYPES:
                    raw_params.setdefault("text_type", col_type.lower())
                    col_type = "text"

                # Final safety net: any still-unrecognized type becomes text rather
                # than aborting generation.
                _VALID_TYPES = {
                    "int", "float", "date", "time", "datetime",
                    "categorical", "foreign_key", "text", "boolean",
                }
                if col_type not in _VALID_TYPES:
                    warnings.warn(
                        f"Unknown column type {col_type!r} on {table_name}.{c['name']} — coercing to text"
                    )
                    col_type = "text"

                # Coerce known small-integer columns from categorical/enum to int.
                # Models often emit bedrooms/bathrooms as enum or categorical; they
                # must be int so they render and export as numbers, not labels.
                _INT_FORCE_NAMES = {
                    "bedrooms", "num_bedrooms", "bedroom_count", "beds",
                    "bathrooms", "num_bathrooms", "bathroom_count", "baths",
                    "half_baths", "full_baths",
                    "floors", "stories", "num_floors", "num_stories",
                    "rooms", "num_rooms", "room_count",
                }
                if col_type == "categorical" and c.get("name", "").lower() in _INT_FORCE_NAMES:
                    col_type = "int"
                    if not raw_params.get("distribution"):
                        col_lc = c.get("name", "").lower()
                        if "bath" in col_lc:
                            raw_params = {
                                "distribution": "categorical",
                                "choices": [1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
                                "probabilities": [0.10, 0.20, 0.35, 0.20, 0.10, 0.05],
                            }
                        else:
                            raw_params = {
                                "distribution": "categorical",
                                "choices": [1, 2, 3, 4, 5, 6],
                                "probabilities": [0.05, 0.20, 0.35, 0.25, 0.10, 0.05],
                            }

                normalized_params = self._normalize_distribution_params(col_type, raw_params)
                normalized_params = _sanitize_numeric_spread(
                    c.get("name", ""), col_type, normalized_params
                )

                columns[table_name].append(Column(
                    name=c["name"],
                    type=col_type,
                    distribution_params=normalized_params,
                    nullable=c.get("nullable", False),
                    unique=c.get("unique", False)
                ))

        # For reference tables without columns, create columns from inline_data
        for table in tables:
            if table.is_reference and table.inline_data and table.name not in columns:
                # Infer columns from first row of inline_data
                first_row = table.inline_data[0]
                columns[table.name] = []
                for col_name, value in first_row.items():
                    if isinstance(value, int):
                        col_type = "int"
                    elif isinstance(value, float):
                        col_type = "float"
                    else:
                        col_type = "text"
                    columns[table.name].append(Column(
                        name=col_name,
                        type=col_type,
                        distribution_params={}
                    ))

        # Parse relationships
        relationships = []
        for r in schema_dict.get("relationships", []):
            if not isinstance(r, dict):
                continue
            required = ("parent_table", "child_table", "parent_key", "child_key")
            if not all(r.get(k) for k in required):
                warnings.warn(f"Skipping malformed relationship: {r!r}")
                continue
            relationships.append(Relationship(
                parent_table=r["parent_table"],
                child_table=r["child_table"],
                parent_key=r["parent_key"],
                child_key=r["child_key"],
                temporal_constraint=r.get("temporal_constraint", False)
            ))

        # Parse events
        events = []
        for e in schema_dict.get("events", []):
            if not all(key in e for key in ["name", "table", "column", "condition", "modifier_type", "modifier_value"]):
                continue
            events.append(ScenarioEvent(
                name=e["name"],
                table=e["table"],
                column=e["column"],
                condition=e["condition"],
                modifier_type=e["modifier_type"],
                modifier_value=e["modifier_value"],
                description=e.get("description")
            ))

        # Parse outcome curves (temporal patterns from natural language). The LLM
        # sometimes emits a time_unit the schema doesn't allow ("quarter") or an
        # otherwise-malformed curve; normalize what we can and skip (don't crash
        # the whole generation) what we can't.
        # A measure column is a valid curve target; an id / primary-key /
        # foreign-key column is not. Models routinely attach a curve to a key
        # column when they can't find a real measure (e.g. a curve on
        # "video_views.id"). Such a curve is meaningless, so we drop it.
        def _is_measure_column(table_name: str, col_name: str) -> bool:
            for col in columns.get(table_name, []):
                if col.name == col_name:
                    if col.type in ("foreign_key", "uuid"):
                        return False
                    if getattr(col, "primary_key", False) or col.unique:
                        return False
                    low = col_name.lower()
                    if low == "id" or low.endswith("_id") or low.endswith("_uuid"):
                        return False
                    return True
            # Column not found in the table — be permissive (time_column repair
            # below may still fix it); the engine skips truly-invalid curves.
            return True

        outcome_curves = []
        for c in schema_dict.get("outcome_curves", []):
            if not isinstance(c, dict) or not all(key in c for key in ["table", "column"]):
                continue
            if not _is_measure_column(c["table"], c["column"]):
                warnings.warn(
                    f"Dropping outcome_curve on non-measure column "
                    f"{c.get('table')}.{c.get('column')} (id/key columns can't carry a curve)"
                )
                continue
            try:
                outcome_curves.append(OutcomeCurve(
                    table=c["table"],
                    column=c["column"],
                    time_column=c.get("time_column", "date"),
                    time_unit=self._normalize_time_unit(c.get("time_unit")),
                    pattern_type=c.get("pattern_type", "seasonal"),
                    value_mode=c.get("value_mode", "auto"),
                    intra_period_pattern=c.get("intra_period_pattern", "uniform"),
                    description=c.get("description"),
                    avg_transaction_value=c.get("avg_transaction_value"),
                    min_transactions_per_period=c.get("min_transactions_per_period", 1),
                    max_transactions_per_period=c.get("max_transactions_per_period", 10000),
                    concentration=c.get("concentration", 2.0),
                    start_date=c.get("start_date"),
                    curve_points=c.get("curve_points", [])
                ))
            except Exception as exc:  # malformed curve — keep the schema, drop the curve
                warnings.warn(f"Skipping malformed outcome_curve for {c.get('table')}.{c.get('column')}: {exc}")

        # Repair common LLM quirks in an outcome curve's time_column so a well-formed curve
        # is not discarded over a malformed pointer. Two patterns recur across models: a
        # dotted path ("order_items.order_id.order_date") and a non-date column (an integer
        # "month" index). We resolve to the leaf name, then to a real date or datetime column
        # in the curve's table, and coerce the referenced column to a date type only when the
        # table offers no date column to point at. Curves that already reference a date column
        # are left untouched.
        for oc in outcome_curves:
            col_objs = columns.get(oc.table, [])
            types = {col.name: col.type for col in col_objs}
            tc = oc.time_column or "date"
            if "." in tc:
                tc = tc.split(".")[-1]
            date_cols = [n for n, ty in types.items() if ty in ("date", "datetime")]
            if tc in types and types[tc] in ("date", "datetime"):
                oc.time_column = tc
            elif date_cols:
                oc.time_column = date_cols[0]
            elif tc in types:
                for col in col_objs:
                    if col.name == tc:
                        col.type = "date"
                oc.time_column = tc
            else:
                oc.time_column = tc

        # Parse rate curves (a rate/proportion of a boolean or categorical column
        # over time — orthogonal to outcome_curves, which scale a numeric
        # magnitude). Same resilience: normalize what we can, skip what we can't.
        rate_curves = []
        for c in schema_dict.get("rate_curves", []):
            if not isinstance(c, dict) or not all(key in c for key in ["table", "column"]):
                continue
            # A rate curve legitimately targets a boolean/categorical column, but
            # never an id / primary-key / foreign-key column (e.g. a model that
            # attaches the churn rate to "status_id"). _is_measure_column allows
            # bool/categorical and rejects key columns — exactly what we want.
            if not _is_measure_column(c["table"], c["column"]):
                warnings.warn(
                    f"Dropping rate_curve on non-measure column "
                    f"{c.get('table')}.{c.get('column')} (id/key columns can't carry a rate)"
                )
                continue
            try:
                rate_curves.append(RateCurve(
                    table=c["table"],
                    column=c["column"],
                    time_column=c.get("time_column", "date"),
                    time_unit=self._normalize_time_unit(
                        c.get("time_unit"), allow_quarter=True
                    ),
                    true_value=c.get("true_value", True),
                    interpolate=c.get("interpolate", True),
                    description=c.get("description"),
                    rate_points=c.get("rate_points", c.get("curve_points", [])),
                ))
            except Exception as exc:  # malformed — keep the schema, drop the curve
                warnings.warn(f"Skipping malformed rate_curve for {c.get('table')}.{c.get('column')}: {exc}")

        # Repair a rate curve's time_column the same way as outcome curves: resolve
        # a dotted/leaf pointer to a real date column, or coerce one if absent.
        for rc in rate_curves:
            col_objs = columns.get(rc.table, [])
            types = {col.name: col.type for col in col_objs}
            tc = (rc.time_column or "date").split(".")[-1]
            date_cols = [n for n, ty in types.items() if ty in ("date", "datetime")]
            if tc in types and types[tc] in ("date", "datetime"):
                rc.time_column = tc
            elif date_cols:
                rc.time_column = date_cols[0]
            elif tc in types:
                for col in col_objs:
                    if col.name == tc:
                        col.type = "date"
                rc.time_column = tc
            else:
                rc.time_column = tc

        # Repair the single most common LLM mistake: a foreign_key column with no
        # matching Relationship (e.g. sellers.tier_id but no relationship to
        # `tiers`). Left alone it raises SchemaValidationError and crashes the
        # whole generation. We infer the parent from the column name; if no parent
        # table exists we demote the orphan FK to a plain int so it still passes.
        self._repair_foreign_keys(tables, columns, relationships)

        # Detect and break circular FK chains before they reach the simulator.
        # The simulator raises ValueError on cycles; better to remove one edge
        # here with a clear warning than to crash generation silently. Passing
        # columns lets it demote the orphaned FK column left by the dropped edge.
        self._break_circular_relationships(tables, relationships, columns)

        # Ensure every reference table has usable inline_data. The LLM sometimes
        # marks a table as is_reference without emitting data rows; auto-generate
        # from domain vocabulary or demote to a transactional table.
        col_names_for_domain = [c.name for cols in columns.values() for c in cols]
        domain_for_repair = self._detect_domain([t.name for t in tables], col_names_for_domain)
        self._repair_reference_inline_data(tables, columns, domain_for_repair)

        schema = SchemaConfig(
            name=schema_dict.get("name", "Generated Dataset"),
            description=schema_dict.get("description"),
            tables=tables,
            columns=columns,
            relationships=relationships,
            events=events,
            outcome_curves=outcome_curves,
            rate_curves=rate_curves,
            noise_config=schema_dict.get("noise_config"),
            seed=schema_dict.get("seed", 42)
        )
        self._enforce_vocabulary(schema)
        return schema

    @staticmethod
    def _detect_domain(table_names: List[str], col_names: List[str]) -> Optional[str]:
        """Infer the dataset domain from table and column names using word-boundary matching."""
        corpus = " ".join(table_names + col_names).lower()
        scores: Dict[str, int] = {}
        for domain, signals in _DOMAIN_SIGNALS:
            score = sum(
                1 for s in signals
                if re.search(r"\b" + re.escape(s) + r"\b", corpus)
            )
            if score > 0:
                scores[domain] = score
        return max(scores, key=lambda k: scores[k]) if scores else None

    @staticmethod
    def _enforce_vocabulary(schema: SchemaConfig) -> None:
        """Replace LLM-hallucinated categorical values with domain-validated vocabulary.

        Only activates when the current choices contain blacklisted words (SaaS tier
        labels used in non-SaaS contexts). Leaves good LLM-generated values untouched.
        """
        table_names = [t.name for t in schema.tables]
        col_names_all = [c.name for cols in schema.columns.values() for c in cols]
        domain = LLMSchemaGenerator._detect_domain(table_names, col_names_all)
        domain_vocab: Dict[str, List] = _DOMAIN_VOCAB.get(domain, {}) if domain else {}

        for _tname, cols in schema.columns.items():
            for col in cols:
                if col.type != "categorical":
                    continue
                params = col.distribution_params or {}
                choices = params.get("choices", [])
                if not isinstance(choices, list) or not choices:
                    continue

                choices_lower = {str(c).lower().strip() for c in choices}
                if not (choices_lower & _BLACKLISTED_VALUES):
                    continue  # choices look fine — do not override

                col_key = re.sub(r"(_id|_name|_code|_type|_label|_value)$", "", col.name.lower())

                replacement: Optional[List] = None
                for vocab_key, values in _COL_VOCAB.items():
                    if vocab_key in col_key or col_key in vocab_key:
                        replacement = values
                        break

                if replacement is None and domain_vocab:
                    for vocab_key, values in domain_vocab.items():
                        if vocab_key in col_key or col_key in vocab_key:
                            replacement = values
                            break

                if replacement:
                    new_params = dict(params)
                    new_params["choices"] = replacement
                    new_params.pop("probabilities", None)
                    col.distribution_params = new_params

        # Enforce vocabulary in reference table inline_data rows.
        # The LLM sometimes emits blacklisted values directly in the lookup rows.
        for table in schema.tables:
            if not table.is_reference or not table.inline_data:
                continue
            tname_key = re.sub(r"s$", "", table.name.lower())
            for vocab_key, values in domain_vocab.items():
                if vocab_key not in tname_key and tname_key not in vocab_key:
                    continue
                # Found a vocabulary match for this reference table — check each row
                # for a non-id label column and replace any blacklisted values.
                for row in table.inline_data:
                    if not isinstance(row, dict):
                        continue
                    for col_name, cell_val in row.items():
                        if col_name == "id":
                            continue
                        if isinstance(cell_val, str) and cell_val.lower().strip() in _BLACKLISTED_VALUES:
                            # Replace with a value from the vocabulary (cycle through)
                            idx = (row.get("id", 1) - 1) % len(values)
                            row[col_name] = values[idx]
                break

    @staticmethod
    def _repair_foreign_keys(tables, columns, relationships) -> None:
        """Ensure every foreign_key column has a Relationship, or is demoted to int.

        Three passes:
        1. Auto-detect *_id columns typed as text/int that match a known parent table
           by name → promote to foreign_key and add the missing Relationship.
        2. Promote child_key columns already declared in a Relationship but wrongly
           typed as text/int → foreign_key.
        3. Handle foreign_key typed columns that still lack a Relationship → create
           one or demote to int if no parent can be found.
        """
        table_names = [t.name for t in tables]
        existing = {(r.child_table, r.child_key) for r in relationships}

        def find_parent(base: str, child_table: str):
            b = base.lower()
            bsing = b[:-1] if b.endswith("s") else b
            best, best_score = None, 0
            for tn in table_names:
                t = tn.lower()
                tsing = t[:-1] if t.endswith("s") else t
                leaf = t.split("_")[-1]
                leafsing = leaf[:-1] if leaf.endswith("s") else leaf
                if t == b or t == b + "s" or t == b + "es" or tsing == bsing:
                    score = 3
                elif leaf == b or leafsing == bsing:
                    score = 2
                elif t.endswith("_" + b) or t.endswith("_" + b + "s"):
                    score = 1
                else:
                    continue
                # prefer a different table over a self-match, then shorter names
                if score > best_score or (score == best_score and best and tn != child_table and best == child_table):
                    best, best_score = tn, score
            return best

        # Pass 1: auto-detect *_id columns typed as text/int that have no Relationship.
        # The LLM frequently emits city_id/property_type_id as "text"; we match by name
        # and promote them so the simulator can resolve FK values correctly.
        for tname, cols in columns.items():
            for col in cols:
                name_lc = col.name.lower()
                if col.type == "foreign_key":
                    continue
                if col.unique:
                    continue
                if name_lc == "id" or not name_lc.endswith("_id"):
                    continue
                if (tname, col.name) in existing:
                    continue
                base = re.sub(r"(_id)$", "", name_lc) or name_lc
                parent = find_parent(base, tname)
                if parent:
                    col.type = "foreign_key"
                    col.distribution_params = {}
                    relationships.append(Relationship(
                        parent_table=parent, parent_key="id",
                        child_table=tname, child_key=col.name,
                    ))
                    existing.add((tname, col.name))

        # Pass 2: promote child_key columns in declared Relationships typed as text/int.
        for rel in relationships:
            for col in columns.get(rel.child_table, []):
                if col.name == rel.child_key and col.type != "foreign_key":
                    col.type = "foreign_key"
                    col.distribution_params = {}

        # Pass 3: foreign_key columns still missing a Relationship → create one or demote.
        for tname, cols in columns.items():
            for col in cols:
                if col.type != "foreign_key" or (tname, col.name) in existing:
                    continue
                base = re.sub(r"(_id|_fk|_key|_ref|id)$", "", col.name.lower()) or col.name.lower()
                parent = find_parent(base, tname)
                if parent:
                    relationships.append(Relationship(
                        parent_table=parent, parent_key="id",
                        child_table=tname, child_key=col.name,
                    ))
                    existing.add((tname, col.name))
                else:
                    # No parent table to point at — demote to a plain int so the
                    # schema validates instead of crashing on an orphan FK.
                    col.type = "int"
                    params = dict(col.distribution_params or {})
                    params.setdefault("distribution", "uniform")
                    params.setdefault("min", 1)
                    params.setdefault("max", 1000)
                    col.distribution_params = params

    @staticmethod
    def _break_circular_relationships(
        tables: List[Table],
        relationships: List[Relationship],
        columns: Optional[Dict[str, List]] = None,
    ) -> None:
        """Detect and break multi-table cycles in FK relationships.

        The simulator raises ValueError on cross-table cycles (a→b→a). We remove
        the last edge that closes each cycle and warn. Self-referential FKs
        (employee.manager_id → employee) are NOT cycles here — the simulator
        handles them explicitly — so they are excluded from detection and never
        dropped. When an edge is dropped, the now-orphaned FK column is demoted
        to a plain int so it doesn't fail validation. Modifies `relationships`
        (and `columns`, if given) in-place.
        """
        from collections import deque as _deque

        def _demote_orphan(child_table: str, child_key: str) -> None:
            """Turn a now-parentless FK column into a plain int."""
            if columns is None:
                return
            for col in columns.get(child_table, []):
                if col.name == child_key and col.type == "foreign_key":
                    col.type = "int"
                    params = dict(col.distribution_params or {})
                    params.setdefault("distribution", "uniform")
                    params.setdefault("min", 1)
                    params.setdefault("max", 1000)
                    col.distribution_params = params

        table_names = {t.name for t in tables}
        while True:
            # Build parent→children adjacency, excluding self-referential edges.
            fwd: Dict[str, set] = {n: set() for n in table_names}
            in_deg: Dict[str, int] = {n: 0 for n in table_names}
            for rel in relationships:
                if rel.parent_table == rel.child_table:
                    continue  # self-referential — legitimate, skip
                if rel.parent_table not in table_names or rel.child_table not in table_names:
                    continue
                if rel.child_table not in fwd[rel.parent_table]:
                    fwd[rel.parent_table].add(rel.child_table)
                    in_deg[rel.child_table] += 1

            # Kahn's algorithm — any node left unvisited is in a cycle.
            q = _deque(n for n, d in in_deg.items() if d == 0)
            visited = set()
            while q:
                n = q.popleft()
                visited.add(n)
                for child in fwd[n]:
                    in_deg[child] -= 1
                    if in_deg[child] == 0:
                        q.append(child)

            cycle_members = table_names - visited
            if not cycle_members:
                break  # no cross-table cycle remains

            # Remove the last non-self-referential relationship inside the cycle.
            for i in range(len(relationships) - 1, -1, -1):
                rel = relationships[i]
                if rel.parent_table == rel.child_table:
                    continue  # never drop a self-referential FK
                if rel.child_table in cycle_members and rel.parent_table in cycle_members:
                    warnings.warn(
                        f"Circular FK detected — dropping relationship "
                        f"{rel.parent_table}.{rel.parent_key} → "
                        f"{rel.child_table}.{rel.child_key} to break the cycle."
                    )
                    relationships.pop(i)
                    _demote_orphan(rel.child_table, rel.child_key)
                    break
            else:
                break  # safety: nothing removable, exit to avoid infinite loop

    @staticmethod
    def _repair_reference_inline_data(
        tables: List[Table],
        columns: Dict[str, List],
        domain: Optional[str],
    ) -> None:
        """Ensure every reference table has usable inline_data.

        Three sub-cases:
        1. inline_data rows are missing the `id` column → add sequential ids.
        2. inline_data is None/empty and we can find domain vocab for the
           table → auto-generate rows from _DOMAIN_VOCAB.
        3. inline_data is None/empty and no vocab match → convert to a regular
           transactional table (is_reference=False) with a warning so the
           simulator doesn't produce empty DataFrames.
        """
        domain_vocab: Dict[str, List] = _DOMAIN_VOCAB.get(domain, {}) if domain else {}

        for table in tables:
            if not table.is_reference:
                continue

            rows = table.inline_data

            # Case 1: rows exist but id column is missing → inject it
            if rows and isinstance(rows[0], dict) and "id" not in rows[0]:
                for i, row in enumerate(rows, 1):
                    row.setdefault("id", i)
                continue

            # Cases 2 & 3: no inline_data at all
            if rows:
                continue

            # Try to generate from domain vocabulary
            tname_key = re.sub(r"s$", "", table.name.lower())  # strip trailing 's'
            matched_values: Optional[List] = None
            for vocab_key, values in domain_vocab.items():
                if vocab_key in tname_key or tname_key in vocab_key:
                    matched_values = values
                    break

            if matched_values:
                # Infer the non-id label column name from existing columns or table name
                cols = columns.get(table.name, [])
                label_col = next(
                    (c.name for c in cols if c.name not in ("id",) and c.type in ("text", "categorical")),
                    "name",
                )
                table.inline_data = [
                    {"id": i + 1, label_col: v} for i, v in enumerate(matched_values)
                ]
                table.row_count = len(matched_values)
            else:
                # No vocab — demote to transactional so simulator generates it normally
                warnings.warn(
                    f"Reference table '{table.name}' has no inline_data and no "
                    f"matching vocabulary — converting to a regular table."
                )
                table.is_reference = False

    def enrich_schema(
        self,
        schema: SchemaConfig,
        prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> SchemaConfig:
        """
        Enrich a bare schema with LLM-inferred realistic distribution parameters.

        Takes a schema from introspection (SQLAlchemy, DB URL) that has only
        table/column structure and enriches it with:
        - Proper statistical distributions per column
        - Correlated column mappings (depends_on)
        - Reference table inline_data
        - Business rule constraints
        - Text type inference

        Args:
            schema: Bare SchemaConfig from introspection
            prompt: Optional user hint (e.g., "e-commerce with high churn")
            temperature: LLM temperature (lower = more consistent)

        Returns:
            Enriched SchemaConfig ready for realistic data generation
        """
        # Serialize schema to compact representation for the LLM
        schema_summary = self._serialize_schema_for_llm(schema)

        user_prompt = f"""Analyze this database schema and return enriched column definitions with realistic distribution parameters.

SCHEMA:
{json.dumps(schema_summary, indent=2)}

{f'DOMAIN HINT: {prompt}' if prompt else ''}

Return valid JSON with enriched columns, reference_tables, and constraints. Be domain-specific based on the table/column names you see."""
        user_prompt += self._build_feedback_prompt(schema=schema, prompt=prompt)

        raw = self._call_api(
            messages=[
                {"role": "system", "content": ENRICH_SCHEMA_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=8000,
            temperature=temperature,
        )
        enrichment = self._parse_json_response(raw)
        return self._apply_enrichment(schema, enrichment)

    def _serialize_schema_for_llm(self, schema: SchemaConfig) -> Dict:
        """Serialize a SchemaConfig to a compact JSON for the LLM."""
        tables = []
        for t in schema.tables:
            tables.append({
                "name": t.name,
                "row_count": t.row_count,
                "is_reference": t.is_reference,
            })

        columns = {}
        for table_name, cols in schema.columns.items():
            columns[table_name] = []
            for c in cols:
                columns[table_name].append({
                    "name": c.name,
                    "type": c.type,
                    "nullable": c.nullable,
                    "unique": c.unique,
                })

        relationships = []
        for r in schema.relationships:
            relationships.append({
                "parent_table": r.parent_table,
                "child_table": r.child_table,
                "parent_key": r.parent_key,
                "child_key": r.child_key,
            })

        return {
            "tables": tables,
            "columns": columns,
            "relationships": relationships,
        }

    def _apply_enrichment(self, schema: SchemaConfig, enrichment: Dict) -> SchemaConfig:
        """
        Merge LLM enrichment back into the original SchemaConfig.

        Updates distribution_params, converts reference tables, adds constraints.
        Preserves all existing structure (table names, relationships, FK columns).
        """
        import copy
        enriched = copy.deepcopy(schema)

        # Type mapping for LLM output normalization
        type_mapping = {
            "string": "text", "str": "text", "varchar": "text", "char": "text",
            "integer": "int", "number": "float", "decimal": "float", "double": "float",
            "timestamp": "datetime", "bool": "boolean",
            "enum": "categorical", "category": "categorical", "fk": "foreign_key",
        }

        # 1. Update column distribution_params
        enriched_columns = enrichment.get("columns", {})
        for table_name, cols in enriched_columns.items():
            if table_name not in enriched.columns:
                continue

            # Build lookup of existing columns
            existing_cols = {c.name: c for c in enriched.columns[table_name]}

            for enriched_col_data in cols:
                col_name = enriched_col_data.get("name")
                if not col_name or col_name not in existing_cols:
                    continue

                existing_col = existing_cols[col_name]

                # Skip FK columns — they're handled by the simulator
                if existing_col.type == "foreign_key":
                    continue

                # Skip primary key id columns
                if col_name == "id" and existing_col.unique:
                    continue

                # Update distribution_params
                new_params = enriched_col_data.get("distribution_params", {})
                if new_params:
                    normalized = self._normalize_distribution_params(
                        existing_col.type, new_params
                    )
                    existing_col.distribution_params = normalized

                # Update type if LLM suggests a better one (e.g., text → categorical)
                new_type = enriched_col_data.get("type", existing_col.type)
                new_type = type_mapping.get(new_type.lower(), new_type)
                # Only allow safe type transitions
                safe_transitions = {
                    ("text", "categorical"),
                    ("int", "categorical"),
                    ("text", "boolean"),
                    ("int", "boolean"),
                }
                if new_type != existing_col.type:
                    if (existing_col.type, new_type) in safe_transitions:
                        existing_col.type = new_type

        # 2. Convert reference tables with inline_data
        ref_tables = enrichment.get("reference_tables", [])
        for ref in ref_tables:
            ref_name = ref.get("name")
            inline_data = ref.get("inline_data")
            if not ref_name or not inline_data:
                continue

            # Find the matching table
            for table in enriched.tables:
                if table.name == ref_name:
                    table.is_reference = True
                    table.inline_data = inline_data
                    table.row_count = len(inline_data)

                    # Update columns from inline_data if needed
                    if ref_name in enriched.columns:
                        first_row = inline_data[0]
                        new_cols = []
                        for col_name_key, value in first_row.items():
                            if isinstance(value, int):
                                col_type = "int"
                            elif isinstance(value, float):
                                col_type = "float"
                            elif isinstance(value, bool):
                                col_type = "boolean"
                            else:
                                col_type = "text"
                            new_cols.append(Column(
                                name=col_name_key,
                                type=col_type,
                                distribution_params={}
                            ))
                        enriched.columns[ref_name] = new_cols
                    break

        # 3. Add business rule constraints
        constraints_map = enrichment.get("constraints", {})
        for table_name, constraints_list in constraints_map.items():
            for table in enriched.tables:
                if table.name == table_name:
                    from misata.schema import Constraint
                    for c in constraints_list:
                        try:
                            constraint = Constraint(
                                name=c.get("name", "unnamed"),
                                type=c.get("type", "max_per_group"),
                                group_by=c.get("group_by", []),
                                column=c.get("column"),
                                value=c.get("value"),
                                action=c.get("action", "cap"),
                            )
                            table.constraints.append(constraint)
                        except Exception as exc:
                            warnings.warn(f"Skipping invalid constraint for table '{table_name}': {exc}")
                    break

        return enriched


# Convenience functions
def generate_schema(story: str, api_key: Optional[str] = None, use_research: bool = False) -> SchemaConfig:
    """Quick helper to generate schema from story."""
    generator = LLMSchemaGenerator(api_key=api_key)
    return generator.generate_from_story(story, use_research=use_research)


def generate_from_chart(description: str, api_key: Optional[str] = None) -> SchemaConfig:
    """Quick helper to reverse-engineer schema from chart description."""
    generator = LLMSchemaGenerator(api_key=api_key)
    return generator.generate_from_graph(description)
