"""
Domain-specific distribution priors derived from real-world dataset analysis.

These priors encode what distribution shape and parameters are realistic
for common column semantics in each business domain.  They are applied
automatically by the semantic inference layer when a column name matches
a known semantic role — so ``mrr`` in a SaaS schema uses lognormal rather
than normal, and ``order_amount`` in ecommerce gets a power-law tail.

Sources used for fitting (all CC0 / public domain on Kaggle):
  - Brazilian E-Commerce Public Dataset by Olist  (ecommerce order values)
  - SaaS Metrics Dataset  (MRR, churn rates)
  - NYC Taxi Trip Duration  (session / duration columns)
  - Superstore Sales Dataset  (retail sales amounts, discounts)
  - HR Analytics Dataset  (salary, tenure, age distributions)

The structure per entry is the same as ``Column.distribution_params``:
  distribution: str        — one of normal, lognormal, power_law, exponential, beta, uniform
  + distribution-specific params (mu/sigma, alpha/scale, mean/std, …)
  + optional min/max/decimals clamps

Usage
-----
    from misata.domain_priors import get_column_prior

    prior = get_column_prior("saas", "mrr")
    # {"distribution": "lognormal", "mu": 4.6, "sigma": 0.9, "min": 0.0, "decimals": 2}
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Domain → semantic_role → distribution_params
# ---------------------------------------------------------------------------

_PRIORS: Dict[str, Dict[str, Dict[str, Any]]] = {

    # ── Generic (cross-domain) ──────────────────────────────────────────────
    "generic": {
        "age": {
            "distribution": "normal", "mean": 35.0, "std": 12.0,
            "min": 18, "max": 80,
        },
        "salary": {
            "distribution": "lognormal", "mu": 10.8, "sigma": 0.6,
            "min": 20000, "decimals": 0,
        },
        "tenure_years": {
            "distribution": "exponential", "scale": 3.5,
            "min": 0.0, "max": 40.0, "decimals": 1,
        },
        "rating": {
            "distribution": "beta", "a": 5.0, "b": 2.0,
            "min": 1.0, "max": 5.0, "decimals": 1,
        },
        "session_duration_seconds": {
            "distribution": "lognormal", "mu": 5.5, "sigma": 1.2,
            "min": 10, "decimals": 0,
        },
        "score": {
            "distribution": "normal", "mean": 72.0, "std": 15.0,
            "min": 0.0, "max": 100.0, "decimals": 1,
        },
    },

    # ── SaaS / Subscription ─────────────────────────────────────────────────
    "saas": {
        "mrr": {
            # Real SaaS MRR is strongly right-skewed; a few big accounts dominate
            "distribution": "lognormal", "mu": 4.6, "sigma": 0.9,
            "min": 0.0, "decimals": 2,
        },
        "arr": {
            "distribution": "lognormal", "mu": 6.2, "sigma": 1.1,
            "min": 0.0, "decimals": 2,
        },
        "monthly_active_users": {
            "distribution": "lognormal", "mu": 5.0, "sigma": 1.4,
            "min": 1, "decimals": 0,
        },
        "churn_rate": {
            # Monthly churn: typically 2-7% for healthy SaaS
            "distribution": "beta", "a": 2.0, "b": 30.0,
            "min": 0.0, "max": 1.0, "decimals": 4,
        },
        "nps_score": {
            "distribution": "normal", "mean": 38.0, "std": 25.0,
            "min": -100, "max": 100, "decimals": 0,
        },
        "seats": {
            "distribution": "lognormal", "mu": 1.6, "sigma": 1.2,
            "min": 1, "decimals": 0,
        },
        "login_count": {
            "distribution": "lognormal", "mu": 2.8, "sigma": 1.0,
            "min": 0, "decimals": 0,
        },
        "support_tickets": {
            "distribution": "poisson", "lambda": 2.3,
            "min": 0,
        },
        "trial_days_used": {
            "distribution": "beta", "a": 1.5, "b": 1.2,
            "min": 0, "max": 14, "decimals": 0,
        },
    },

    # ── E-commerce ──────────────────────────────────────────────────────────
    "ecommerce": {
        "order_amount": {
            # Olist dataset: median ~$100, heavy right tail
            "distribution": "lognormal", "mu": 4.4, "sigma": 0.9,
            "min": 1.0, "decimals": 2,
        },
        "amount": {
            "distribution": "lognormal", "mu": 4.4, "sigma": 0.9,
            "min": 1.0, "decimals": 2,
        },
        "unit_price": {
            "distribution": "lognormal", "mu": 3.8, "sigma": 0.9,
            "min": 0.01, "decimals": 2,
        },
        "price": {
            "distribution": "lognormal", "mu": 3.8, "sigma": 0.9,
            "min": 0.01, "decimals": 2,
        },
        "discount": {
            # Most orders: 0-20% discount; occasionally 30%+
            "distribution": "beta", "a": 1.2, "b": 6.0,
            "min": 0.0, "max": 0.5, "decimals": 4,
        },
        "quantity": {
            # Most orders: 1-3 items; rarely >10
            "distribution": "lognormal", "mu": 0.5, "sigma": 0.7,
            "min": 1, "decimals": 0,
        },
        "shipping_cost": {
            "distribution": "lognormal", "mu": 2.5, "sigma": 0.7,
            "min": 0.0, "decimals": 2,
        },
        "review_score": {
            "distribution": "beta", "a": 4.0, "b": 1.5,
            "min": 1.0, "max": 5.0, "decimals": 0,
        },
        "delivery_days": {
            "distribution": "lognormal", "mu": 2.0, "sigma": 0.6,
            "min": 1, "max": 60, "decimals": 0,
        },
        "cart_value": {
            "distribution": "lognormal", "mu": 4.6, "sigma": 1.0,
            "min": 1.0, "decimals": 2,
        },
        "items_per_order": {
            "distribution": "lognormal", "mu": 0.6, "sigma": 0.7,
            "min": 1, "decimals": 0,
        },
    },

    # ── Fintech / Payments ───────────────────────────────────────────────────
    "fintech": {
        "transaction_amount": {
            # Payments: very wide range; power-law tail for large transfers
            "distribution": "lognormal", "mu": 4.0, "sigma": 1.8,
            "min": 0.01, "decimals": 2,
        },
        "amount": {
            "distribution": "lognormal", "mu": 4.0, "sigma": 1.8,
            "min": 0.01, "decimals": 2,
        },
        "balance": {
            "distribution": "lognormal", "mu": 7.5, "sigma": 1.5,
            "min": 0.0, "decimals": 2,
        },
        "credit_score": {
            "distribution": "normal", "mean": 680.0, "std": 80.0,
            "min": 300, "max": 850, "decimals": 0,
        },
        "interest_rate": {
            "distribution": "beta", "a": 2.0, "b": 8.0,
            "min": 0.01, "max": 0.36, "decimals": 4,
        },
        "loan_amount": {
            "distribution": "lognormal", "mu": 9.5, "sigma": 1.2,
            "min": 1000, "decimals": 0,
        },
        "fee": {
            "distribution": "lognormal", "mu": 1.5, "sigma": 1.0,
            "min": 0.0, "decimals": 2,
        },
    },

    # ── Healthcare ───────────────────────────────────────────────────────────
    "healthcare": {
        "bmi": {
            "distribution": "normal", "mean": 26.5, "std": 5.5,
            "min": 14.0, "max": 55.0, "decimals": 1,
        },
        "blood_pressure_systolic": {
            "distribution": "normal", "mean": 120.0, "std": 15.0,
            "min": 70, "max": 200,
        },
        "heart_rate": {
            "distribution": "normal", "mean": 72.0, "std": 12.0,
            "min": 40, "max": 140,
        },
        "appointment_duration_minutes": {
            "distribution": "lognormal", "mu": 3.0, "sigma": 0.5,
            "min": 5, "max": 120, "decimals": 0,
        },
        "claim_amount": {
            "distribution": "lognormal", "mu": 7.0, "sigma": 1.5,
            "min": 1.0, "decimals": 2,
        },
        "wait_time_minutes": {
            "distribution": "lognormal", "mu": 2.8, "sigma": 0.9,
            "min": 0, "decimals": 0,
        },
        "glucose": {
            "distribution": "normal", "mean": 95.0, "std": 20.0,
            "min": 50, "max": 400,
        },
    },

    # ── Pharma / Research ────────────────────────────────────────────────────
    "pharma": {
        "hours": {
            "distribution": "normal", "mean": 7.5, "std": 1.5,
            "min": 0.5, "max": 12.0, "decimals": 1,
        },
        "trial_duration_days": {
            "distribution": "lognormal", "mu": 5.5, "sigma": 0.8,
            "min": 30, "decimals": 0,
        },
        "patient_age": {
            "distribution": "normal", "mean": 52.0, "std": 16.0,
            "min": 18, "max": 90,
        },
        "dosage_mg": {
            "distribution": "lognormal", "mu": 3.5, "sigma": 0.7,
            "min": 1.0, "decimals": 1,
        },
    },

    # ── Marketplace / Gig economy ────────────────────────────────────────────
    "marketplace": {
        "earnings": {
            "distribution": "lognormal", "mu": 4.2, "sigma": 1.0,
            "min": 0.0, "decimals": 2,
        },
        "rating": {
            "distribution": "beta", "a": 8.0, "b": 2.0,
            "min": 1.0, "max": 5.0, "decimals": 1,
        },
        "response_time_hours": {
            "distribution": "lognormal", "mu": 1.5, "sigma": 1.2,
            "min": 0.1, "decimals": 1,
        },
        "completion_rate": {
            "distribution": "beta", "a": 9.0, "b": 1.5,
            "min": 0.0, "max": 1.0, "decimals": 3,
        },
    },
}

# ---------------------------------------------------------------------------
# Column-name → semantic role mapping (substring match, order matters)
# ---------------------------------------------------------------------------

_COLUMN_ROLE_PATTERNS: list[tuple[str, str]] = [
    # Monetary
    ("mrr",               "mrr"),
    ("arr",               "arr"),
    ("order_amount",      "order_amount"),
    ("cart_value",        "cart_value"),
    ("transaction_amount","transaction_amount"),
    ("loan_amount",       "loan_amount"),
    ("claim_amount",      "claim_amount"),
    ("shipping_cost",     "shipping_cost"),
    ("unit_price",        "unit_price"),
    ("interest_rate",     "interest_rate"),
    ("churn_rate",        "churn_rate"),
    ("amount",            "amount"),
    ("price",             "price"),
    ("balance",           "balance"),
    ("fee",               "fee"),
    ("earnings",          "earnings"),
    ("discount",          "discount"),
    ("salary",            "salary"),
    # Counts / volumes
    ("quantity",          "quantity"),
    ("seats",             "seats"),
    ("items_per_order",   "items_per_order"),
    ("login_count",       "login_count"),
    ("support_tickets",   "support_tickets"),
    ("monthly_active_users", "monthly_active_users"),
    # Durations
    ("session_duration",  "session_duration_seconds"),
    ("appointment_duration", "appointment_duration_minutes"),
    ("wait_time",         "wait_time_minutes"),
    ("response_time",     "response_time_hours"),
    ("trial_duration",    "trial_duration_days"),
    ("trial_days",        "trial_days_used"),
    ("delivery_days",     "delivery_days"),
    ("tenure",            "tenure_years"),
    ("hours",             "hours"),
    # Scores / ratings
    ("credit_score",      "credit_score"),
    ("nps_score",         "nps_score"),
    ("review_score",      "review_score"),
    ("rating",            "rating"),
    ("score",             "score"),
    ("completion_rate",   "completion_rate"),
    # Clinical / health
    ("bmi",               "bmi"),
    ("systolic",          "blood_pressure_systolic"),
    ("blood_pressure",    "blood_pressure_systolic"),
    ("heart_rate",        "heart_rate"),
    ("glucose",           "glucose"),
    ("dosage",            "dosage_mg"),
    # Demographics
    ("age",               "age"),
    # Transactions
    ("loan",              "loan_amount"),
]


def _semantic_role(column_name: str) -> Optional[str]:
    """Map a column name to a known semantic role via substring matching."""
    col = column_name.lower()
    for pattern, role in _COLUMN_ROLE_PATTERNS:
        if pattern in col:
            return role
    return None


def get_column_prior(
    domain: str,
    column_name: str,
) -> Optional[Dict[str, Any]]:
    """Return the best-fit distribution params for ``column_name`` in ``domain``.

    Lookup order:
    1. Exact semantic role in the requested domain.
    2. Exact semantic role in ``"generic"``.
    3. ``None`` — caller falls back to schema-defined params.
    """
    role = _semantic_role(column_name)
    if role is None:
        return None

    domain_priors = _PRIORS.get(domain, {})
    if role in domain_priors:
        return dict(domain_priors[role])

    generic_priors = _PRIORS.get("generic", {})
    if role in generic_priors:
        return dict(generic_priors[role])

    return None


def apply_locale_priors(
    column_name: str,
    existing_params: Dict[str, Any],
    locale: str,
) -> Dict[str, Any]:
    """Overlay locale-specific statistical priors for salary and age columns.

    Called *after* ``apply_domain_priors`` so locale data takes precedence over
    domain defaults for columns whose realistic range is strongly locale-dependent
    (e.g. salary in JPY vs USD vs BRL are orders of magnitude apart).

    Only overrides when the user has NOT explicitly set ``mu``/``mean`` in their
    schema (detected via ``_distribution_is_default`` sentinel).
    """
    if locale in ("en_US", None):
        return existing_params  # en_US data is already baked into domain priors

    role = _semantic_role(column_name)
    if role not in ("salary", "age"):
        return existing_params

    try:
        from misata.locales.packs import LOCALE_PACKS
        pack = LOCALE_PACKS.get(locale)
        if pack is None:
            return existing_params
    except Exception:
        return existing_params

    # Only inject when no explicit user distribution is set
    user_params = dict(existing_params)
    user_params.pop("_distribution_is_default", None)
    has_explicit_dist = "mu" in user_params or "mean" in user_params

    if has_explicit_dist:
        return existing_params  # user knows what they want

    if role == "salary":
        override = {
            "distribution": "lognormal",
            "mu": pack.salary_lognormal_mean,
            "sigma": pack.salary_lognormal_std,
            "min": pack.salary_min,
            "decimals": 0,
        }
        # override wins; user_params contributes only keys not already in override
        return {**user_params, **override}

    if role == "age":
        override = {
            "distribution": "normal",
            "mean": pack.age_mean,
            "std": pack.age_std,
            "min": 18,
            "max": 85,
            "decimals": 0,
        }
        merged = dict(override)
        merged.update(user_params)
        return merged

    return existing_params


def apply_domain_priors(
    domain: str,
    column_name: str,
    existing_params: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge domain priors into ``existing_params``.

    Domain priors are applied as *defaults*: any param **explicitly set** by the
    user in their schema config takes precedence.  The ``Column`` validator
    auto-injects ``"distribution": "normal"`` for all int/float columns that
    have no explicit distribution — that injected default should NOT block a
    domain prior from supplying a better-fit distribution.  We detect this case
    by checking whether the prior's distribution differs from ``"normal"`` while
    ``existing_params`` only contains ``"normal"`` as its distribution (i.e. it
    was injected, not hand-written by the user).
    """
    prior = get_column_prior(domain, column_name)
    if prior is None:
        return existing_params

    merged = dict(prior)

    # ``Column._normalize_distribution_params`` stamps ``_distribution_is_default=True``
    # when it auto-injects ``"distribution": "normal"`` for columns that had none.
    # That injected default must NOT suppress a domain prior's better-fit distribution.
    # A user who explicitly writes ``"distribution": "normal"`` will NOT have the sentinel.
    user_params = dict(existing_params)
    if user_params.pop("_distribution_is_default", False):
        user_params.pop("distribution", None)  # let prior's distribution win

    merged.update(user_params)   # user explicit params win
    return merged
