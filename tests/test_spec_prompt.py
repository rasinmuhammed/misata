"""Tests for the structured spec-prompt parser (misata/spec_prompt.py).

The centerpiece is the field-reported prompt that motivated the feature: a
six-table B2B SaaS spec with exact row counts, FK rules in two syntaxes,
enumerations, a rating range, and a template-text column. It must parse
deterministically and the generated data must satisfy every translatable rule.
"""

import pandas as pd
import pytest

from misata.spec_prompt import looks_like_spec, parse_spec

FRIEND_PROMPT = """
Generate exactly 6 synthetic CSV tables for a B2B SaaS company dataset. Do not create additional tables. Do not merge tables. Generate exactly the row counts mentioned below.

Table 1: customers

Rows: exactly 500

Columns:

customer_id
company_name
industry
company_size
country
signup_date
plan_tier
health_score
churn_risk
nps_score
account_status
annual_revenue

Table 2: products

Rows: exactly 50

Columns:

product_id
product_name
category
version
release_date
average_rating
defect_rate
pricing_tier

Table 3: orders

Rows: exactly 3000

Columns:

order_id
customer_id
product_id
order_date
subscription_type
quantity
amount
payment_status
renewal_status

Rules:

customer_id must match values from customers table.
product_id must match values from products table.

Table 4: support_tickets

Rows: exactly 2000

Columns:

ticket_id
customer_id
product_id
category
subcategory
priority
severity
status
channel
created_date
resolved_date
assigned_team
assigned_agent
sentiment
csat_score
ticket_description

Ticket categories must only be:

Integration
Performance
Bug
Feature Request
Account
Access
Data
Onboarding

Generate ticket_description using template-based text with variables:

connector: Salesforce, Snowflake, HubSpot, BigQuery
error_code: AUTH-403, TIMEOUT-001, E-4001, E-5002
team: analytics, engineering, sales, marketing
data_type: customer data, sales data, transaction data
feature: API, dashboard, reporting, workflow

Example format:
"Salesforce integration stopped syncing data. Error AUTH-403 appears in logs. Analytics team cannot access customer data."

Table 5: product_reviews

Rows: exactly 1500

Columns:

review_id
customer_id
product_id
review_date
rating
title
review_text
sentiment
verified_purchase
helpful_votes

Rules:

Ratings must be 1 to 5.
Review sentiment must match rating.
Generate positive, neutral, and negative reviews.

Table 6: customer_interactions

Rows: exactly 5000

Columns:

interaction_id
customer_id
interaction_date
channel
interaction_type
agent_name
duration_minutes
sentiment_score
follow_up_required
outcome
notes

Interaction types:

Support
Sales Call
Renewal
Onboarding
Training
Complaint

Final validation requirements:

Row counts must be exactly:
customers: 500
products: 50
orders: 3000
support_tickets: 2000
product_reviews: 1500
customer_interactions: 5000
Maintain foreign keys:
customers.customer_id → orders.customer_id
customers.customer_id → support_tickets.customer_id
customers.customer_id → product_reviews.customer_id
customers.customer_id → customer_interactions.customer_id
products.product_id → orders.product_id
products.product_id → support_tickets.product_id
products.product_id → product_reviews.product_id
Do not generate any other tables.
"""

EXPECTED_ROWS = {
    "customers": 500,
    "products": 50,
    "orders": 3000,
    "support_tickets": 2000,
    "product_reviews": 1500,
    "customer_interactions": 5000,
}

TICKET_CATEGORIES = {
    "Integration", "Performance", "Bug", "Feature Request",
    "Account", "Access", "Data", "Onboarding",
}
INTERACTION_TYPES = {
    "Support", "Sales Call", "Renewal", "Onboarding", "Training", "Complaint",
}


def test_detection():
    assert looks_like_spec(FRIEND_PROMPT)
    assert not looks_like_spec("A SaaS company with 1k users and 20% churn")
    assert not looks_like_spec("An online store, orders peaking in December")


def test_parse_structure():
    schema, report = parse_spec(FRIEND_PROMPT)

    assert {t.name for t in schema.tables} == set(EXPECTED_ROWS)
    for t in schema.tables:
        assert t.row_count == EXPECTED_ROWS[t.name], t.name

    rels = {(r.parent_table, r.child_table, r.child_key) for r in schema.relationships}
    assert ("customers", "orders", "customer_id") in rels
    assert ("products", "orders", "product_id") in rels
    assert ("customers", "support_tickets", "customer_id") in rels
    assert ("products", "support_tickets", "product_id") in rels
    assert ("customers", "product_reviews", "customer_id") in rels
    assert ("products", "product_reviews", "product_id") in rels
    assert ("customers", "customer_interactions", "customer_id") in rels
    assert report.relationships == len(rels)

    tickets = {c.name: c for c in schema.columns["support_tickets"]}
    assert set(tickets["category"].distribution_params["choices"]) == TICKET_CATEGORIES
    # the example sentence became a slotted template + variable pools
    desc = tickets["ticket_description"].distribution_params
    assert "{connector}" in desc["templates"][0]
    assert "{error_code}" in desc["templates"][0]
    assert "Snowflake" in desc["variables"]["connector"]
    assert "TIMEOUT-001" in desc["variables"]["error_code"]

    reviews = {c.name: c for c in schema.columns["product_reviews"]}
    assert reviews["rating"].distribution_params["min"] == 1
    assert reviews["rating"].distribution_params["max"] == 5
    assert set(reviews["sentiment"].distribution_params["choices"]) == {
        "positive", "neutral", "negative",
    }
    assert reviews["verified_purchase"].type == "boolean"

    interactions = {c.name: c for c in schema.columns["customer_interactions"]}
    assert set(interactions["interaction_type"].distribution_params["choices"]) == INTERACTION_TYPES

    # The untranslatable coupling is reported, not silently faked
    assert any("sentiment must match rating" in u for u in report.untranslated)


def test_generated_data_satisfies_spec():
    from misata.simulator import DataSimulator

    schema, _ = parse_spec(FRIEND_PROMPT)
    sim = DataSimulator(schema)
    tables: dict = {}
    for name, batch in sim.generate_all():
        tables[name] = pd.concat([tables[name], batch], ignore_index=True) \
            if name in tables else batch

    assert set(tables) == set(EXPECTED_ROWS)
    for name, n in EXPECTED_ROWS.items():
        assert len(tables[name]) == n, f"{name}: {len(tables[name])} != {n}"

    customers = set(tables["customers"]["customer_id"])
    products = set(tables["products"]["product_id"])
    for child in ("orders", "support_tickets", "product_reviews", "customer_interactions"):
        assert set(tables[child]["customer_id"]).issubset(customers), child
    for child in ("orders", "support_tickets", "product_reviews"):
        assert set(tables[child]["product_id"]).issubset(products), child

    assert set(tables["support_tickets"]["category"]).issubset(TICKET_CATEGORIES)
    assert set(tables["customer_interactions"]["interaction_type"]).issubset(INTERACTION_TYPES)
    assert tables["product_reviews"]["rating"].between(1, 5).all()
    assert set(tables["product_reviews"]["sentiment"]).issubset(
        {"positive", "neutral", "negative"}
    )
    # template descriptions come out as filled sentences, not placeholders
    descs = tables["support_tickets"]["ticket_description"].astype(str)
    assert not descs.str.contains("{", regex=False).any()
    assert (descs.str.len() > 30).all()
    # variety: the {slots} actually vary across rows
    assert descs.nunique() > 10


SENTIMENT_COUPLING = {
    "product_reviews": {
        "sentiment": {
            "distribution_params": {
                "depends_on": "rating",
                "mapping": {
                    "1": ["negative"], "2": ["negative"], "3": ["neutral"],
                    "4": ["positive"], "5": ["positive"],
                },
            }
        }
    }
}


def test_merge_refinements_enforces_contract():
    from misata.spec_prompt import merge_refinements

    schema, report = parse_spec(FRIEND_PROMPT)

    # A coupling on a locked column with in-vocabulary values is accepted.
    assert merge_refinements(schema, report, SENTIMENT_COUPLING) == 1
    sent = {c.name: c for c in schema.columns["product_reviews"]}["sentiment"]
    assert sent.distribution_params["depends_on"] == "rating"
    assert sent.distribution_params["mapping"]["5"] == ["positive"]

    # Everything below is rejected: out-of-vocab mapping on a locked enum,
    # pool change on a locked enum, retyping an FK, retyping a PK.
    hostile = {
        "support_tickets": {
            "category": {"distribution_params": {
                "depends_on": "priority",
                "mapping": {"high": ["Escalation"]},
            }},
            "customer_id": {"type": "text"},
            "ticket_id": {"type": "text"},
        },
        "product_reviews": {
            "rating": {"distribution_params": {"min": 0, "max": 10}},
        },
        "no_such_table": {"x": {"type": "int"}},
    }
    assert merge_refinements(schema, report, hostile) == 0
    tickets = {c.name: c for c in schema.columns["support_tickets"]}
    assert set(tickets["category"].distribution_params["choices"]) == TICKET_CATEGORIES
    assert "mapping" not in tickets["category"].distribution_params
    assert tickets["customer_id"].type == "foreign_key"
    reviews = {c.name: c for c in schema.columns["product_reviews"]}
    assert reviews["rating"].distribution_params["max"] == 5

    # An unlocked column accepts a realism override.
    ok = {"customers": {"health_score": {
        "type": "int", "distribution_params": {"min": 0, "max": 100},
    }}}
    assert merge_refinements(schema, report, ok) == 1
    hs = {c.name: c for c in schema.columns["customers"]}["health_score"]
    assert hs.type == "int" and hs.distribution_params["max"] == 100


def test_refined_coupling_holds_in_generated_data():
    import numpy as np
    from misata.spec_prompt import merge_refinements
    from misata.simulator import DataSimulator

    schema, report = parse_spec(FRIEND_PROMPT)
    merge_refinements(schema, report, SENTIMENT_COUPLING)

    sim = DataSimulator(schema)
    reviews = None
    for name, batch in sim.generate_all():
        if name == "product_reviews":
            reviews = batch if reviews is None else pd.concat(
                [reviews, batch], ignore_index=True
            )
    want = {1: "negative", 2: "negative", 3: "neutral", 4: "positive", 5: "positive"}
    got = [want[int(r)] == s for r, s in zip(reviews["rating"], reviews["sentiment"])]
    assert np.mean(got) == 1.0


def test_story_parser_short_circuits():
    from misata.story_parser import StoryParser

    with pytest.warns(UserWarning, match="Structured spec parsed deterministically"):
        schema = StoryParser().parse(FRIEND_PROMPT)
    assert {t.name for t in schema.tables} == set(EXPECTED_ROWS)


def test_llm_path_survives_without_client():
    """When the model is unavailable, the deterministic parse stands alone."""
    from misata.llm_parser import LLMSchemaGenerator

    gen = LLMSchemaGenerator.__new__(LLMSchemaGenerator)
    gen.client = None
    with pytest.warns(UserWarning, match="Structured spec parsed deterministically"):
        schema = gen.generate_from_story(FRIEND_PROMPT)
    assert {t.name for t in schema.tables} == set(EXPECTED_ROWS)
    for t in schema.tables:
        assert t.row_count == EXPECTED_ROWS[t.name]


def test_llm_refinement_end_to_end_with_mock():
    """A mocked model answer flows through _refine_spec_schema into the schema."""
    import json
    from misata.llm_parser import LLMSchemaGenerator

    gen = LLMSchemaGenerator.__new__(LLMSchemaGenerator)
    gen.client = object()  # anything non-None; _call_api is stubbed below
    gen._call_api = lambda messages, max_tokens=2500, temperature=0.3: json.dumps(
        {"overrides": SENTIMENT_COUPLING}
    )
    with pytest.warns(UserWarning, match="LLM refined 1 column"):
        schema = gen.generate_from_story(FRIEND_PROMPT)
    sent = {c.name: c for c in schema.columns["product_reviews"]}["sentiment"]
    assert sent.distribution_params["depends_on"] == "rating"
