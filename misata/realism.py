"""
Realism rules for post-generation data adjustment.

Rules are applied conservatively and only when relevant columns exist.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


INACTIVE_STATUSES = {"inactive", "cancelled", "canceled", "ended", "expired", "churned"}
ACTIVE_STATUSES = {"active", "trialing", "trial", "enabled"}


def apply_realism_rules(df: pd.DataFrame, table_name: str = "") -> pd.DataFrame:
    """
    Apply light-weight realism rules to a DataFrame.

    This function is deterministic with Misata's seed because it uses
    numpy's global RNG (which is seeded by DataSimulator).
    """
    if df.empty:
        return df

    df = df.copy()
    columns = set(df.columns)

    _fix_created_updated(df, columns)
    _fix_start_end_dates(df, columns)
    _apply_quantity_unit_price_total(df, columns)
    _apply_plan_price_mapping(df, columns)
    _apply_status_end_date(df, columns)

    return df


def _fix_created_updated(df: pd.DataFrame, columns: Iterable[str]) -> None:
    if "created_at" in columns and "updated_at" in columns:
        created = pd.to_datetime(df["created_at"], errors="coerce")
        updated = pd.to_datetime(df["updated_at"], errors="coerce")
        mask = updated < created
        if mask.any():
            deltas = pd.to_timedelta(np.random.randint(0, 7 * 24 * 60, size=mask.sum()), unit="m")
            updated.loc[mask] = created.loc[mask] + deltas
            df["updated_at"] = updated


def _fix_start_end_dates(df: pd.DataFrame, columns: Iterable[str]) -> None:
    if "start_date" in columns and "end_date" in columns:
        start = pd.to_datetime(df["start_date"], errors="coerce")
        end = pd.to_datetime(df["end_date"], errors="coerce")

        mask = end < start
        if mask.any():
            deltas = pd.to_timedelta(np.random.randint(1, 365, size=mask.sum()), unit="D")
            end.loc[mask] = start.loc[mask] + deltas

        df["start_date"] = start
        df["end_date"] = end


def _apply_quantity_unit_price_total(df: pd.DataFrame, columns: Iterable[str]) -> None:
    if {"quantity", "unit_price", "total"}.issubset(columns):
        qty = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
        unit_price = pd.to_numeric(df["unit_price"], errors="coerce").fillna(0)
        noise = np.random.normal(0, 0.02, size=len(df))
        total = (qty * unit_price * (1 + noise)).clip(lower=0)
        df["total"] = total.round(2)


def _apply_plan_price_mapping(df: pd.DataFrame, columns: Iterable[str]) -> None:
    if "plan" in columns and "price" in columns:
        plan_prices = {
            "free": 0.0,
            "basic": 9.99,
            "starter": 9.99,
            "premium": 19.99,
            "pro": 19.99,
            "professional": 29.99,
            "enterprise": 49.99,
            "business": 49.99,
            "unlimited": 99.99,
        }
        plan_series = df["plan"].astype(str).str.strip().str.lower()
        mapped = plan_series.map(plan_prices)
        df.loc[mapped.notna(), "price"] = mapped[mapped.notna()].astype(float)


def _apply_status_end_date(df: pd.DataFrame, columns: Iterable[str]) -> None:
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
