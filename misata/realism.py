"""
Realism rules for post-generation data adjustment.

These rules enforce cross-column mathematical and logical consistency
that the column-level generator cannot express. This is what separates
a realism engine from a random Faker.

Rules are applied conservatively — only when relevant columns exist.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional, Set

import numpy as np
import pandas as pd

from misata.domain_capsule import DomainCapsule
from misata.vocab_seeds import (
    CITIES_BY_COUNTRY,
    FIRST_NAMES,
    JOB_TITLES as _JOB_TITLES_BY_DOMAIN,
    LAST_NAMES,
    PRODUCT_BY_CATEGORY,
    STATES_BY_COUNTRY,
)


INACTIVE_STATUSES = {"inactive", "cancelled", "canceled", "ended", "expired", "churned"}
ACTIVE_STATUSES = {"active", "trialing", "trial", "enabled"}
DELIVERED_STATUSES = {"delivered", "completed", "fulfilled"}

# Geography — now sourced from the rich seed pools
COUNTRY_STATES = STATES_BY_COUNTRY
COUNTRY_CITIES = CITIES_BY_COUNTRY

COMPANY_PREFIXES = [
    "North", "Blue", "Peak", "Cedar", "Summit", "Atlas", "Bright", "Modern",
    "Vertex", "True", "Prime", "Nova", "Apex", "Ever", "Silver", "Quantum",
]
COMPANY_ROOTS = [
    "Labs", "Systems", "Works", "Health", "Retail", "Logic", "Cloud", "Supply",
    "Dynamics", "Analytics", "Commerce", "Bio", "Capital", "Foods", "Networks", "Studio",
]
COMPANY_SUFFIXES = ["Inc", "Group", "Co", "Partners", "Holdings", "Solutions", "Collective"]

JOB_TITLES = _JOB_TITLES_BY_DOMAIN["generic"]

COUNTRIES = list(CITIES_BY_COUNTRY.keys())

# Product name pools — now sourced from the rich seed pools
PRODUCT_NAME_POOLS = PRODUCT_BY_CATEGORY

PRODUCT_DESCRIPTION_TEMPLATES = [
    "Designed for everyday use with reliable performance and clean design.",
    "Built for teams that want quality, durability, and fast setup.",
    "A customer favorite for comfort, performance, and long-term value.",
    "Combines premium materials with practical features for daily use.",
]


class RealisticTextGenerator:
    """Catalog-backed text generation for semantic text columns."""

    def __init__(
        self,
        rng: Optional[np.random.Generator] = None,
        capsule: Optional[DomainCapsule] = None,
        locale: Optional[str] = None,
    ):
        self.rng = rng or np.random.default_rng(42)
        self.capsule = capsule
        self.locale = locale or "en_US"
        self._faker = None  # lazy

    def _get_faker(self):
        if self._faker is None:
            try:
                from misata.locales.registry import LocaleRegistry
                self._faker = LocaleRegistry.global_instance().get_faker(self.locale)
            except Exception:
                try:
                    from faker import Faker
                    self._faker = Faker(self.locale)
                except Exception:
                    self._faker = None
        return self._faker

    def generate(
        self,
        column_name: str,
        table_name: str,
        size: int,
        semantic_type: Optional[str] = None,
        table_data: Optional[pd.DataFrame] = None,
    ) -> np.ndarray:
        semantic = semantic_type or self._infer_semantic(column_name, table_name)

        # When a non-default locale is active, prefer Faker for person/address data
        # so names, cities, and phones match the target locale.
        # Exception: if the domain capsule already has vocabulary loaded for this
        # semantic type (e.g. from a Kaggle asset store), the capsule takes priority.
        _has_capsule_vocab = lambda key: bool(self._vocabulary(key, []))  # noqa: E731
        faker = self._get_faker() if self.locale != "en_US" else None

        if semantic == "first_name":
            if faker and not _has_capsule_vocab("first_name"):
                return np.array([faker.first_name() for _ in range(size)])
            return self.rng.choice(self._vocabulary("first_name", FIRST_NAMES), size=size)
        if semantic == "last_name":
            if faker and not _has_capsule_vocab("last_name"):
                return np.array([faker.last_name() for _ in range(size)])
            return self.rng.choice(self._vocabulary("last_name", LAST_NAMES), size=size)
        if semantic == "person_name":
            if faker and not _has_capsule_vocab("first_name"):
                return np.array([faker.name() for _ in range(size)])
            first = self.rng.choice(self._vocabulary("first_name", FIRST_NAMES), size=size)
            last = self.rng.choice(self._vocabulary("last_name", LAST_NAMES), size=size)
            return np.array([f"{f} {l}" for f, l in zip(first, last)])
        if semantic == "email":
            if faker and not _has_capsule_vocab("first_name"):
                return np.array([faker.email() for _ in range(size)])
            first = self.rng.choice(self._vocabulary("first_name", FIRST_NAMES), size=size)
            last = self.rng.choice(self._vocabulary("last_name", LAST_NAMES), size=size)
            separators = self.rng.choice([".", "_", ""], size=size, p=[0.5, 0.2, 0.3])
            domains = self.rng.choice(
                ["gmail.com", "outlook.com", "yahoo.com", "icloud.com", "protonmail.com"],
                size=size,
            )
            return np.array(
                [
                    f"{re.sub(r'[^a-z]', '', f.lower())}{sep}{re.sub(r'[^a-z]', '', l.lower())}@{domain}"
                    for f, sep, l, domain in zip(first, separators, last, domains)
                ]
            )
        if semantic == "company_name":
            if faker:
                try:
                    from misata.locales.registry import LocaleRegistry
                    pack = LocaleRegistry.global_instance().get_pack(self.locale)
                    suffix = pack.company_suffixes
                    return np.array([f"{faker.company().split()[0]} {np.random.choice(suffix)}" for _ in range(size)])
                except Exception:
                    return np.array([faker.company() for _ in range(size)])
            company_names = self._vocabulary("company_name", [])
            if company_names:
                return self.rng.choice(company_names, size=size)
            return np.array(
                [
                    f"{self.rng.choice(COMPANY_PREFIXES)} {self.rng.choice(COMPANY_ROOTS)} {self.rng.choice(COMPANY_SUFFIXES)}"
                    for _ in range(size)
                ]
            )
        if semantic == "job_title":
            if faker:
                try:
                    return np.array([faker.job() for _ in range(size)])
                except Exception:
                    pass
            return self.rng.choice(self._vocabulary("job_title", JOB_TITLES), size=size)
        if semantic == "country":
            if faker:
                try:
                    return np.array([faker.country() for _ in range(size)])
                except Exception:
                    pass
            return self.rng.choice(self._vocabulary("country", COUNTRIES), size=size)
        if semantic == "state":
            if faker:
                try:
                    return np.array([faker.city() for _ in range(size)])  # state/prefecture via city for non-US
                except Exception:
                    pass
            countries = self._series_from_table(table_data, "country", size)
            states = self._vocabulary("state", [])
            if states:
                return self.rng.choice(states, size=size)
            return np.array([
                self.rng.choice(COUNTRY_STATES.get(country, COUNTRY_STATES["United States"]))
                for country in countries
            ])
        if semantic == "city":
            # Use locale pack top_cities list when available (real, population-ranked)
            try:
                from misata.locales.registry import LocaleRegistry
                pack = LocaleRegistry.global_instance().get_pack(self.locale)
                if pack.top_cities:
                    return self.rng.choice(pack.top_cities, size=size)
            except Exception:
                pass
            if faker:
                try:
                    return np.array([faker.city() for _ in range(size)])
                except Exception:
                    pass
            countries = self._series_from_table(table_data, "country", size)
            cities = self._vocabulary("city", [])
            if cities:
                return self.rng.choice(cities, size=size)
            return np.array([
                self.rng.choice(COUNTRY_CITIES.get(country, COUNTRY_CITIES["United States"]))
                for country in countries
            ])
        if semantic == "username":
            first = self.rng.choice(self._vocabulary("first_name", FIRST_NAMES), size=size)
            last = self.rng.choice(self._vocabulary("last_name", LAST_NAMES), size=size)
            return np.array([
                f"{re.sub(r'[^a-z]', '', f.lower())}{re.sub(r'[^a-z]', '', l.lower())}{int(self.rng.integers(1, 999)):03d}"
                for f, l in zip(first, last)
            ])
        if semantic == "address":
            numbers = self.rng.integers(10, 9999, size=size)
            streets = self.rng.choice(["Main", "Oak", "Maple", "Cedar", "Sunset", "Lake"], size=size)
            suffixes = self.rng.choice(["St", "Ave", "Blvd", "Ln", "Rd"], size=size)
            return np.array([f"{n} {street} {suffix}" for n, street, suffix in zip(numbers, streets, suffixes)])
        if semantic == "phone_number":
            areas = self.rng.integers(200, 999, size=size)
            prefixes = self.rng.integers(200, 999, size=size)
            lines = self.rng.integers(1000, 9999, size=size)
            return np.array([f"({a}) {p}-{l}" for a, p, l in zip(areas, prefixes, lines)])
        if semantic == "url":
            slugs = self._slugify(self.generate(column_name, table_name, size, "company_name"))
            return np.array([f"https://www.{slug}.com" for slug in slugs])
        if semantic == "slug_source":
            words = self.rng.choice(["modern", "prime", "atlas", "core", "blue", "summit"], size=(size, 2))
            return np.array([f"{left}-{right}" for left, right in words])
        if semantic in {"product_name", "product_description"}:
            return self._generate_product_text(size=size, semantic=semantic, table_data=table_data)

        return np.array([
            self.rng.choice(self._vocabulary("product_description", PRODUCT_DESCRIPTION_TEMPLATES))
            for _ in range(size)
        ])

    def _infer_semantic(self, column_name: str, table_name: str) -> str:
        name = column_name.lower()
        table = table_name.lower()
        if name == "first_name":
            return "first_name"
        if name == "last_name":
            return "last_name"
        if "email" in name:
            return "email"
        if "company" in name or "organization" in name:
            return "company_name"
        if "username" in name:
            return "username"
        if "job" in name or "role" in name or "title" in name:
            return "job_title"
        if "country" in name:
            return "country"
        if "state" in name or "province" in name or "region" in name:
            return "state"
        if "city" in name:
            return "city"
        if "product" in table or "item" in table:
            return "product_name"
        if name == "name":
            return "person_name"
        return "description"

    def _generate_product_text(
        self,
        *,
        size: int,
        semantic: str,
        table_data: Optional[pd.DataFrame],
    ) -> np.ndarray:
        categories = self._series_from_table(table_data, "category", size)
        values = []
        for category in categories:
            normalized = str(category).lower()
            key = next((pool for pool in PRODUCT_NAME_POOLS if pool in normalized), None)
            key = key or "electronics"
            if semantic == "product_name":
                product_names = self._vocabulary("product_name", PRODUCT_NAME_POOLS[key])
                values.append(self.rng.choice(product_names))
            else:
                product_descriptions = self._vocabulary("product_description", PRODUCT_DESCRIPTION_TEMPLATES)
                values.append(self.rng.choice(product_descriptions))
        return np.array(values)

    def _series_from_table(self, table_data: Optional[pd.DataFrame], column: str, size: int) -> np.ndarray:
        if table_data is not None and column in table_data.columns and len(table_data[column]) >= size:
            return table_data[column].astype(str).values[:size]
        return np.array(["United States"] * size)

    def _slugify(self, values: Iterable[str]) -> np.ndarray:
        slugs = []
        for value in values:
            slug = re.sub(r"[^a-z0-9\s-]", "", str(value).lower())
            slug = re.sub(r"\s+", "-", slug).strip("-")
            slugs.append(slug or "site")
        return np.array(slugs)

    def _vocabulary(self, name: str, fallback: Iterable[str]) -> List[str]:
        if self.capsule is not None:
            values = self.capsule.get_values(name, list(fallback))
            if values:
                return values
        return list(fallback)


class EntityCoherenceEngine:
    """High-confidence cross-column coherence rules."""

    def __init__(
        self,
        rng: Optional[np.random.Generator] = None,
        capsule: Optional[DomainCapsule] = None,
    ):
        self.rng = rng or np.random.default_rng(42)
        self.text_generator = RealisticTextGenerator(self.rng, capsule=capsule)

    def apply(
        self,
        df: pd.DataFrame,
        table_name: str,
        *,
        mode: str = "standard",
        protected_columns: Optional[set[str]] = None,
    ) -> pd.DataFrame:
        if df.empty or mode == "off":
            return df

        protected_columns = protected_columns or set()
        output = df.copy()
        columns = set(output.columns)

        self._fix_email_from_name(output, columns, protected_columns, mode)
        self._fix_username_from_name(output, columns, protected_columns, mode)
        self._fix_geography(output, columns, protected_columns, mode)
        self._fix_age_role(output, columns, protected_columns)
        self._fix_product_category(output, columns, protected_columns, mode, table_name.lower())

        return output

    def _fix_email_from_name(self, df: pd.DataFrame, columns: set[str], protected: set[str], mode: str) -> None:
        if "email" in protected or "email" not in columns:
            return

        if {"first_name", "last_name"}.issubset(columns):
            firsts = df["first_name"].astype(str)
            lasts = df["last_name"].astype(str)
        elif "name" in columns:
            parts = df["name"].astype(str).str.split()
            firsts = parts.apply(lambda values: values[0] if values else "user")
            lasts = parts.apply(lambda values: values[-1] if len(values) > 1 else "")
        else:
            return

        desired = np.array([
            f"{re.sub(r'[^a-z]', '', str(first).lower())}.{re.sub(r'[^a-z]', '', str(last).lower())}@gmail.com".replace("..", ".").replace(".@", "@")
            for first, last in zip(firsts, lasts)
        ])
        current = df["email"].astype(str)
        mismatch = []
        for email, first in zip(current, firsts.astype(str)):
            normalized_first = re.sub(r"[^a-z]", "", first.lower())[:3]
            normalized_email = str(email).lower()
            mismatch.append("@" not in normalized_email or (normalized_first and normalized_first not in normalized_email))
        mismatch_mask = np.array(mismatch, dtype=bool)
        if mode == "strict":
            mismatch_mask[:] = True
        df.loc[mismatch_mask, "email"] = desired[mismatch_mask]

    def _fix_username_from_name(self, df: pd.DataFrame, columns: set[str], protected: set[str], mode: str) -> None:
        if "username" in protected or "username" not in columns:
            return
        if {"first_name", "last_name"}.issubset(columns):
            firsts = df["first_name"].astype(str)
            lasts = df["last_name"].astype(str)
        elif "name" in columns:
            parts = df["name"].astype(str).str.split()
            firsts = parts.apply(lambda values: values[0] if values else "user")
            lasts = parts.apply(lambda values: values[-1] if len(values) > 1 else "")
        else:
            return

        desired = np.array([
            f"{re.sub(r'[^a-z]', '', str(first).lower())}{re.sub(r'[^a-z]', '', str(last).lower())}"
            for first, last in zip(firsts, lasts)
        ])
        current = df["username"].astype(str)
        mismatch = []
        for username, first, last in zip(current, firsts.astype(str), lasts.astype(str)):
            normalized_username = re.sub(r"[^a-z]", "", str(username).lower())
            normalized_first = re.sub(r"[^a-z]", "", str(first).lower())[:3]
            normalized_last = re.sub(r"[^a-z]", "", str(last).lower())[:3]
            mismatch.append(
                len(normalized_username) < 4
                or (normalized_first and normalized_first not in normalized_username)
                or (normalized_last and normalized_last not in normalized_username)
            )
        mismatch_mask = np.array(mismatch, dtype=bool)
        if mode == "strict":
            mismatch_mask[:] = True
        df.loc[mismatch_mask, "username"] = desired[mismatch_mask]

    def _fix_geography(self, df: pd.DataFrame, columns: set[str], protected: set[str], mode: str) -> None:
        if "country" not in columns:
            return
        countries = df["country"].astype(str)
        capsule_states = self.text_generator._vocabulary("state", [])
        capsule_cities = self.text_generator._vocabulary("city", [])

        if "state" in columns and "state" not in protected:
            if capsule_states:
                desired_states = np.array([self.rng.choice(capsule_states) for _ in countries])
            else:
                desired_states = np.array([
                    self.rng.choice(COUNTRY_STATES.get(country, COUNTRY_STATES["United States"]))
                    for country in countries
                ])
            current = df["state"].astype(str)
            if capsule_states:
                mismatch = ~current.isin(capsule_states).to_numpy()
            else:
                mismatch = np.array([
                    current.iloc[i] not in COUNTRY_STATES.get(country, COUNTRY_STATES["United States"])
                    for i, country in enumerate(countries)
                ])
            if mode == "strict":
                mismatch[:] = True
            df.loc[mismatch, "state"] = desired_states[mismatch]

        if "city" in columns and "city" not in protected:
            if capsule_cities:
                desired_cities = np.array([self.rng.choice(capsule_cities) for _ in countries])
            else:
                desired_cities = np.array([
                    self.rng.choice(COUNTRY_CITIES.get(country, COUNTRY_CITIES["United States"]))
                    for country in countries
                ])
            current = df["city"].astype(str)
            if capsule_cities:
                mismatch = ~current.isin(capsule_cities).to_numpy()
            else:
                mismatch = np.array([
                    current.iloc[i] not in COUNTRY_CITIES.get(country, COUNTRY_CITIES["United States"])
                    for i, country in enumerate(countries)
                ])
            if mode == "strict":
                mismatch[:] = True
            df.loc[mismatch, "city"] = desired_cities[mismatch]

    def _fix_age_role(self, df: pd.DataFrame, columns: set[str], protected: set[str]) -> None:
        if "age" in protected or "age" not in columns:
            return
        role_column = next((name for name in ["job_title", "title", "role", "position"] if name in columns), None)
        if role_column is None:
            return

        minimum_age = {
            "manager": 30, "director": 35, "vp": 38, "vice president": 38,
            "cto": 38, "ceo": 40, "chief": 40, "intern": 18, "senior": 28,
        }
        ages = pd.to_numeric(df["age"], errors="coerce").fillna(18).astype(int).values
        roles = df[role_column].astype(str).str.lower()
        for index, role in enumerate(roles):
            floor = 18
            for keyword, age_floor in minimum_age.items():
                if keyword in role:
                    floor = max(floor, age_floor)
            if ages[index] < floor:
                ages[index] = int(self.rng.integers(floor, min(65, floor + 10)))
        df["age"] = ages

    def _fix_product_category(
        self,
        df: pd.DataFrame,
        columns: set[str],
        protected: set[str],
        mode: str,
        table_name: str,
    ) -> None:
        if "name" in protected or "category" not in columns or "name" not in columns:
            return
        if "product" not in table_name and "item" not in table_name:
            return

        categories = df["category"].astype(str).str.lower()
        current_names = df["name"].astype(str)
        desired_names = []
        mismatches = []
        for category, current_name in zip(categories, current_names):
            key = next((pool for pool in PRODUCT_NAME_POOLS if pool in category), None)
            key = key or "electronics"
            desired_name = self.rng.choice(PRODUCT_NAME_POOLS[key])
            desired_names.append(desired_name)
            generic = any(token in current_name.lower() for token in ["lorem", "ipsum", "dolor", "product"])
            mismatches.append(generic or mode == "strict")
        desired_series = np.array(desired_names)
        mismatch_array = np.array(mismatches, dtype=bool)
        df.loc[mismatch_array, "name"] = desired_series[mismatch_array]


def apply_realism_rules(
    df: pd.DataFrame,
    table_name: str = "",
    rng: Optional[np.random.Generator] = None,
) -> pd.DataFrame:
    """
    Apply cross-column realism rules to a DataFrame.

    Order matters: simpler fixes first, computed columns last.
    Pass a seeded ``rng`` to guarantee reproducible fixups.
    """
    if df.empty:
        return df

    _rng = rng if rng is not None else np.random.default_rng(42)

    df = df.copy()
    columns = set(df.columns)

    # ── Temporal consistency ──
    _fix_created_updated(df, columns, _rng)
    _fix_start_end_dates(df, columns, _rng)
    _fix_created_delivered(df, columns, _rng)
    _fix_delivered_requires_status(df, columns)

    # ── Monetary consistency ──
    _fix_cost_less_than_price(df, columns, _rng)
    _fix_discount_cap(df, columns)
    _fix_line_total(df, columns)
    _fix_order_total(df, columns)
    _apply_plan_price_mapping(df, columns)

    # ── Identity consistency ──
    _fix_email_from_name(df, columns, _rng)
    _fix_slug_from_name(df, columns)

    # ── Status consistency ──
    _apply_status_end_date(df, columns, _rng)

    return df


# ─── TEMPORAL RULES ───────────────────────────────────────────────────────────

def _fix_created_updated(df: pd.DataFrame, columns: Set[str], rng: np.random.Generator) -> None:
    """updated_at must be >= created_at."""
    if "created_at" in columns and "updated_at" in columns:
        created = pd.to_datetime(df["created_at"], errors="coerce")
        updated = pd.to_datetime(df["updated_at"], errors="coerce")
        mask = updated < created
        if mask.any():
            deltas = pd.to_timedelta(rng.integers(0, 7 * 24 * 60, size=mask.sum()), unit="m")
            updated.loc[mask] = created.loc[mask] + deltas
            df["updated_at"] = updated


def _fix_start_end_dates(df: pd.DataFrame, columns: Set[str], rng: np.random.Generator) -> None:
    """end_date must be >= start_date."""
    if "start_date" in columns and "end_date" in columns:
        start = pd.to_datetime(df["start_date"], errors="coerce")
        end = pd.to_datetime(df["end_date"], errors="coerce")
        mask = end < start
        if mask.any():
            deltas = pd.to_timedelta(rng.integers(1, 365, size=mask.sum()), unit="D")
            end.loc[mask] = start.loc[mask] + deltas
        df["start_date"] = start
        df["end_date"] = end


def _fix_created_delivered(df: pd.DataFrame, columns: Set[str], rng: np.random.Generator) -> None:
    """delivered_at must be after created_at. Only fixes rows where the order is violated."""
    if "created_at" in columns and "delivered_at" in columns:
        created = pd.to_datetime(df["created_at"], errors="coerce")
        delivered = pd.to_datetime(df["delivered_at"], errors="coerce")
        mask = delivered.notna() & created.notna() & (delivered <= created)
        if mask.any():
            deltas = pd.to_timedelta(
                rng.integers(1 * 24 * 60, 14 * 24 * 60, size=mask.sum()), unit="m"
            )
            delivered.loc[mask] = created.loc[mask] + deltas
            df["delivered_at"] = delivered


def _fix_delivered_requires_status(df: pd.DataFrame, columns: Set[str]) -> None:
    """delivered_at should be null unless status is 'delivered'/'completed'."""
    if "status" in columns and "delivered_at" in columns:
        status = df["status"].astype(str).str.strip().str.lower()
        not_delivered = ~status.isin(DELIVERED_STATUSES)
        if not_delivered.any():
            df.loc[not_delivered, "delivered_at"] = None


# ─── MONETARY RULES ──────────────────────────────────────────────────────────

def _fix_cost_less_than_price(df: pd.DataFrame, columns: Set[str], rng: np.random.Generator) -> None:
    """Ensure cost < price. Only corrects rows where the constraint is violated or cost is missing."""
    if "cost" in columns and "price" in columns:
        price = pd.to_numeric(df["price"], errors="coerce").fillna(0)
        cost = pd.to_numeric(df["cost"], errors="coerce")
        violating = cost.isna() | (cost >= price)
        if violating.any():
            margin = rng.uniform(0.30, 0.70, size=violating.sum())
            df.loc[violating, "cost"] = np.round(price[violating].values * margin, 2)


def _fix_discount_cap(df: pd.DataFrame, columns: Set[str]) -> None:
    """discount <= 30% of unit_price (or price)."""
    price_col = "unit_price" if "unit_price" in columns else ("price" if "price" in columns else None)
    if "discount" in columns and price_col:
        price = pd.to_numeric(df[price_col], errors="coerce").fillna(0)
        discount = pd.to_numeric(df["discount"], errors="coerce").fillna(0)
        max_discount = price * 0.30
        df["discount"] = np.round(np.minimum(discount, max_discount), 2)


def _fix_line_total(df: pd.DataFrame, columns: Set[str]) -> None:
    """line_total = quantity * unit_price - discount."""
    if {"quantity", "unit_price", "line_total"}.issubset(columns):
        qty = pd.to_numeric(df["quantity"], errors="coerce").fillna(1)
        unit_price = pd.to_numeric(df["unit_price"], errors="coerce").fillna(0)
        discount = pd.to_numeric(df.get("discount", 0), errors="coerce").fillna(0)
        df["line_total"] = np.round(qty * unit_price - discount, 2).clip(lower=0)


def _fix_order_total(df: pd.DataFrame, columns: Set[str]) -> None:
    """total = subtotal + tax + shipping_cost."""
    if {"subtotal", "total"}.issubset(columns):
        subtotal = pd.to_numeric(df["subtotal"], errors="coerce").fillna(0)
        tax = pd.to_numeric(df.get("tax", 0), errors="coerce").fillna(0) if "tax" in columns else 0
        shipping = pd.to_numeric(df.get("shipping_cost", 0), errors="coerce").fillna(0) if "shipping_cost" in columns else 0
        df["total"] = np.round(subtotal + tax + shipping, 2)
    elif {"quantity", "unit_price", "total"}.issubset(columns):
        qty = pd.to_numeric(df["quantity"], errors="coerce").fillna(1)
        unit_price = pd.to_numeric(df["unit_price"], errors="coerce").fillna(0)
        discount = pd.to_numeric(df.get("discount", 0), errors="coerce").fillna(0) if "discount" in columns else 0
        df["total"] = np.round(qty * unit_price - discount, 2).clip(lower=0)


def _apply_plan_price_mapping(df: pd.DataFrame, columns: Set[str]) -> None:
    """Map plan names to standard prices."""
    if "plan" in columns and "price" in columns:
        plan_prices = {
            "free": 0.0, "basic": 9.99, "starter": 9.99,
            "premium": 19.99, "pro": 19.99, "professional": 29.99,
            "enterprise": 49.99, "business": 49.99, "unlimited": 99.99,
        }
        plan_series = df["plan"].astype(str).str.strip().str.lower()
        mapped = plan_series.map(plan_prices)
        df.loc[mapped.notna(), "price"] = mapped[mapped.notna()].astype(float)


# ─── IDENTITY RULES ──────────────────────────────────────────────────────────

def _fix_email_from_name(df: pd.DataFrame, columns: Set[str], rng: np.random.Generator) -> None:
    """Compose email from first_name + last_name for consistency."""
    if {"first_name", "last_name", "email"}.issubset(columns):
        domains = [
            "gmail.com", "yahoo.com", "outlook.com", "protonmail.com",
            "icloud.com", "hotmail.com", "aol.com", "mail.com",
        ]
        domain_choices = rng.choice(domains, size=len(df))
        separators = rng.choice([".", "_", ""], size=len(df), p=[0.6, 0.2, 0.2])

        emails = []
        for i in range(len(df)):
            first = str(df.iloc[i]["first_name"]).lower().strip()
            last = str(df.iloc[i]["last_name"]).lower().strip()
            # Remove special chars
            first = re.sub(r'[^a-z]', '', first)
            last = re.sub(r'[^a-z]', '', last)
            sep = separators[i]
            domain = domain_choices[i]
            emails.append(f"{first}{sep}{last}@{domain}")

        df["email"] = emails


def _fix_slug_from_name(df: pd.DataFrame, columns: Set[str]) -> None:
    """Generate slug from name column."""
    if "slug" in columns and "name" in columns:
        df["slug"] = (
            df["name"].astype(str)
            .str.lower()
            .str.strip()
            .str.replace(r'[^a-z0-9\s-]', '', regex=True)
            .str.replace(r'\s+', '-', regex=True)
            .str.strip('-')
        )


# ─── STATUS-BASED RULES ──────────────────────────────────────────────────────

def _apply_status_end_date(df: pd.DataFrame, columns: Set[str], rng: np.random.Generator) -> None:
    """Clear end_date for active statuses, set for inactive."""
    if "status" in columns and "end_date" in columns:
        status = df["status"].astype(str).str.strip().str.lower()
        end = pd.to_datetime(df["end_date"], errors="coerce")

        active_mask = status.isin(ACTIVE_STATUSES)
        if active_mask.any():
            end.loc[active_mask] = pd.NaT

        inactive_mask = status.isin(INACTIVE_STATUSES) & end.isna()
        if inactive_mask.any() and "start_date" in columns:
            start = pd.to_datetime(df["start_date"], errors="coerce")
            deltas = pd.to_timedelta(rng.integers(1, 365, size=inactive_mask.sum()), unit="D")
            end.loc[inactive_mask] = start.loc[inactive_mask] + deltas

        df["end_date"] = end
