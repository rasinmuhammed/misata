"""
Realism rules for post-generation data adjustment.

These rules enforce cross-column mathematical and logical consistency
that the column-level generator cannot express. This is what separates
a realism engine from a random Faker.

Rules are applied conservatively — only when relevant columns exist.
"""

from __future__ import annotations

import re
from typing import Iterable, Set

import numpy as np
import pandas as pd


INACTIVE_STATUSES = {"inactive", "cancelled", "canceled", "ended", "expired", "churned"}
ACTIVE_STATUSES = {"active", "trialing", "trial", "enabled"}
DELIVERED_STATUSES = {"delivered", "completed", "fulfilled"}


def apply_realism_rules(df: pd.DataFrame, table_name: str = "") -> pd.DataFrame:
    """
    Apply cross-column realism rules to a DataFrame.

    Order matters: simpler fixes first, computed columns last.
    """
    if df.empty:
        return df

    df = df.copy()
    columns = set(df.columns)

    # ── Temporal consistency ──
    _fix_created_updated(df, columns)
    _fix_start_end_dates(df, columns)
    _fix_created_delivered(df, columns)
    _fix_delivered_requires_status(df, columns)

    # ── Monetary consistency ──
    _fix_cost_less_than_price(df, columns)
    _fix_discount_cap(df, columns)
    _fix_line_total(df, columns)
    _fix_order_total(df, columns)
    _apply_plan_price_mapping(df, columns)

    # ── Identity consistency ──
    _fix_email_from_name(df, columns)
    _fix_slug_from_name(df, columns)

    return df


# ─── TEMPORAL RULES ───────────────────────────────────────────────────────────

def _fix_created_updated(df: pd.DataFrame, columns: Set[str]) -> None:
    """updated_at must be >= created_at."""
    if "created_at" in columns and "updated_at" in columns:
        created = pd.to_datetime(df["created_at"], errors="coerce")
        updated = pd.to_datetime(df["updated_at"], errors="coerce")
        mask = updated < created
        if mask.any():
            deltas = pd.to_timedelta(np.random.randint(0, 7 * 24 * 60, size=mask.sum()), unit="m")
            updated.loc[mask] = created.loc[mask] + deltas
            df["updated_at"] = updated


def _fix_start_end_dates(df: pd.DataFrame, columns: Set[str]) -> None:
    """end_date must be >= start_date."""
    if "start_date" in columns and "end_date" in columns:
        start = pd.to_datetime(df["start_date"], errors="coerce")
        end = pd.to_datetime(df["end_date"], errors="coerce")
        mask = end < start
        if mask.any():
            deltas = pd.to_timedelta(np.random.randint(1, 365, size=mask.sum()), unit="D")
            end.loc[mask] = start.loc[mask] + deltas
        df["start_date"] = start
        df["end_date"] = end


def _fix_created_delivered(df: pd.DataFrame, columns: Set[str]) -> None:
    """delivered_at must be after created_at (1-14 days later)."""
    if "created_at" in columns and "delivered_at" in columns:
        created = pd.to_datetime(df["created_at"], errors="coerce")
        delivered = pd.to_datetime(df["delivered_at"], errors="coerce")
        mask = delivered.notna() & created.notna()
        if mask.any():
            # Force delivered = created + 1-14 days
            deltas = pd.to_timedelta(
                np.random.randint(1 * 24 * 60, 14 * 24 * 60, size=mask.sum()), unit="m"
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

def _fix_cost_less_than_price(df: pd.DataFrame, columns: Set[str]) -> None:
    """cost must be < price (margin = 30%-70% of price)."""
    if "cost" in columns and "price" in columns:
        price = pd.to_numeric(df["price"], errors="coerce").fillna(0)
        margin = np.random.uniform(0.30, 0.70, size=len(df))
        df["cost"] = np.round(price * margin, 2)


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

def _fix_email_from_name(df: pd.DataFrame, columns: Set[str]) -> None:
    """Compose email from first_name + last_name for consistency."""
    if {"first_name", "last_name", "email"}.issubset(columns):
        domains = [
            "gmail.com", "yahoo.com", "outlook.com", "protonmail.com",
            "icloud.com", "hotmail.com", "aol.com", "mail.com",
        ]
        domain_choices = np.random.choice(domains, size=len(df))
        separators = np.random.choice([".", "_", ""], size=len(df), p=[0.6, 0.2, 0.2])

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

def _apply_status_end_date(df: pd.DataFrame, columns: Set[str]) -> None:
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
            deltas = pd.to_timedelta(np.random.randint(1, 365, size=inactive_mask.sum()), unit="D")
            end.loc[inactive_mask] = start.loc[inactive_mask] + deltas

        df["end_date"] = end

