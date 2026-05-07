"""JSON Schema sanity tests.

These guard the contract between misata's generated YAML and the
``misata.schema.json`` published for IDE autocomplete.  If a domain
schema is changed (new text_type, new column param, new domain enum,
etc.) without updating the JSON Schema, this file fails loudly.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

import misata

jsonschema = pytest.importorskip("jsonschema")
from jsonschema import Draft202012Validator


# ---------------------------------------------------------------------------
# Static schema invariants
# ---------------------------------------------------------------------------


def test_json_schema_loads():
    schema = misata.json_schema()
    assert schema["$schema"].startswith("https://json-schema.org/")
    assert "title" in schema
    assert "tables" in schema["properties"]


def test_json_schema_is_self_valid_against_meta_schema():
    schema = misata.json_schema()
    # Will raise if our schema is itself malformed
    Draft202012Validator.check_schema(schema)


def test_template_validates_clean():
    """The bundled misata.yaml template must always validate."""
    schema = misata.json_schema()
    template = yaml.safe_load(misata.MISATA_YAML_TEMPLATE)
    errors = list(Draft202012Validator(schema).iter_errors(template))
    assert errors == [], "\n".join(str(e) for e in errors)


def test_domain_enum_matches_story_parser():
    """Every domain the StoryParser detects must be listed in the JSON Schema."""
    from misata.story_parser import StoryParser

    schema = misata.json_schema()
    schema_domains = set(schema["properties"]["domain"]["enum"])
    parser_domains = set(StoryParser.DOMAIN_KEYWORDS.keys()) | {"generic"}

    missing = parser_domains - schema_domains
    assert not missing, (
        f"Domains exist in StoryParser but not in misata.schema.json: {missing}. "
        "Add them to schema/misata.schema.json domain enum."
    )


# ---------------------------------------------------------------------------
# Round-trip: every domain must produce a YAML that validates
# ---------------------------------------------------------------------------


_DOMAIN_STORIES = {
    "saas": "A SaaS company with 5k users and 20% churn",
    "ecommerce": "An ecommerce store with 10k orders",
    "fintech": "A fintech with payments and fraud detection",
    "healthcare": "A healthcare clinic with patients and doctors",
    "marketplace": "A freelance marketplace with sellers and buyers",
    "logistics": "A logistics fleet with drivers and shipments",
    "hr": "An HR system with employees and payroll",
    "social": "A social media app with influencers and reels",
    "realestate": "A real estate platform with property listings",
    "pharma": "A pharma research company with clinical trials",
    "fooddelivery": "A food delivery app with restaurants and couriers",
    "edtech": "An edtech platform with courses and quizzes",
    "gaming": "A gaming platform with players and achievements",
    "crm": "A CRM with contacts and deals pipeline",
    "crypto": "A crypto exchange with wallets and blockchain transactions",
    "insurance": "An insurance company with policies and claims",
    "travel": "A travel booking platform with hotels and flights",
    "streaming": "A Netflix streaming service with subscribers",
}


@pytest.mark.parametrize("domain,story", list(_DOMAIN_STORIES.items()))
def test_each_domain_yaml_validates(domain, story, tmp_path):
    """Generate a schema for every domain, save as YAML, validate against JSON Schema.

    This is the strong guarantee that misata.yaml files written by
    `misata init` for any domain will be accepted by IDEs that consume
    the published JSON Schema.
    """
    schema = misata.parse(story)
    path = tmp_path / f"{domain}.yaml"
    misata.save_yaml_schema(schema, path)

    yaml_doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    json_schema = misata.json_schema()

    errors = sorted(
        Draft202012Validator(json_schema).iter_errors(yaml_doc),
        key=lambda e: list(e.absolute_path),
    )
    assert errors == [], (
        f"Domain '{domain}' YAML failed JSON Schema validation:\n"
        + "\n".join(
            f"  - {list(e.absolute_path)}: {e.message[:200]}" for e in errors[:10]
        )
    )
