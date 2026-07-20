"""Tests for user-declared template text columns (templates + variables).

Modeled on a field report: a user wants ticket descriptions generated from
their own TICKET_TEMPLATES structure — templates grouped by category, with
{placeholder} slots filled from declared variable pools — and expects an
Integration sentence to never land on a Bug ticket.
"""

import warnings

import pytest

from misata.schema import Column, SchemaConfig, Table
from misata.simulator import DataSimulator

VARIABLES = {
    "connector": ["Snowflake", "Salesforce", "HubSpot", "BigQuery"],
    "error_code": ["E-4001", "E-5002", "TIMEOUT-001", "AUTH-403"],
    "team": ["analytics", "engineering", "marketing", "sales"],
    "timeframe": ["2 hours", "yesterday", "3 days", "last week"],
    "data_type": ["customer", "sales", "transaction", "reporting"],
    "event": ["quarterly review", "product launch", "board meeting"],
    "browser": ["Chrome", "Firefox", "Safari", "Edge"],
    "feature": ["dashboard", "API", "report export", "workflow automation"],
}

INTEGRATION_TMPL = (
    "Our {connector} integration stopped syncing data about {timeframe} ago. "
    "We're seeing error code {error_code} in the logs. This is blocking our "
    "{team} team from accessing {data_type} data. This is critical as we have "
    "a {event} coming up and need the data flowing."
)
BUG_TMPL = "The {feature} crashes in {browser} since {timeframe}."

CATEGORIES = ["Integration", "Bug"]


def _schema(desc_params, rows=300):
    return SchemaConfig(
        name="tickets", description="", seed=7,
        tables=[Table(name="support_tickets", row_count=rows,
                      columns=["ticket_id", "category", "ticket_description"])],
        columns={"support_tickets": [
            Column(name="ticket_id", type="int", unique=True,
                   distribution_params={"min": 1, "max": 100000}),
            Column(name="category", type="categorical",
                   distribution_params={"choices": list(CATEGORIES)}),
            Column(name="ticket_description", type="text",
                   distribution_params=desc_params),
        ]},
        relationships=[],
    )


def _generate(schema):
    import pandas as pd
    sim = DataSimulator(schema)
    out = None
    for _, batch in sim.generate_all():
        out = batch if out is None else pd.concat([out, batch], ignore_index=True)
    return out


def test_flat_templates_fill_all_slots():
    df = _generate(_schema({
        "templates": [INTEGRATION_TMPL, BUG_TMPL],
        "variables": VARIABLES,
    }))
    descs = df["ticket_description"].astype(str)
    assert not descs.str.contains("{", regex=False).any()
    assert descs.nunique() > 50
    joined = " ".join(descs)
    assert any(v in joined for v in VARIABLES["connector"])
    assert any(v in joined for v in VARIABLES["error_code"])


def test_grouped_templates_match_category():
    df = _generate(_schema({
        "templates": {"Integration": [INTEGRATION_TMPL], "Bug": [BUG_TMPL]},
        "variables": VARIABLES,
        "depends_on": "category",
    }))
    for _, row in df.iterrows():
        d = str(row["ticket_description"])
        if row["category"] == "Integration":
            assert "integration stopped syncing" in d
        else:
            assert "crashes in" in d


def test_grouped_templates_autodetect_parent_column():
    # No depends_on declared: the engine finds the column whose values
    # overlap the group keys (category) on its own.
    df = _generate(_schema({
        "templates": {"Integration": [INTEGRATION_TMPL], "Bug": [BUG_TMPL]},
        "variables": VARIABLES,
    }))
    matches = [
        ("integration stopped syncing" in str(d)) == (c == "Integration")
        for c, d in zip(df["category"], df["ticket_description"])
    ]
    assert all(matches)


def test_missing_pool_is_reported_not_guessed():
    with pytest.warns(UserWarning, match="no variable pool for placeholder"):
        df = _generate(_schema({
            "templates": ["Error {error_code} on {mystery_slot}."],
            "variables": {"error_code": ["E-1"]},
        }, rows=20))
    descs = df["ticket_description"].astype(str)
    assert descs.str.contains("{mystery_slot}", regex=False).all()
    assert not descs.str.contains("{error_code}", regex=False).any()


def test_seeded_reproducibility():
    params = {
        "templates": {"Integration": [INTEGRATION_TMPL], "Bug": [BUG_TMPL]},
        "variables": VARIABLES,
        "depends_on": "category",
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        a = _generate(_schema(params))
        b = _generate(_schema(params))
    assert a["ticket_description"].tolist() == b["ticket_description"].tolist()
