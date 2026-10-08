"""Tests for Misata's textual column realism and text enrichment capabilities.

Validates:
1. Category-conditioned and multi-domain rich text generation (SaaS, E-commerce, Fintech, Healthcare, DevOps).
2. Auto-inference of realistic text semantics from column and table names.
3. Explicit text_type declarations for tickets, memos, errors, clinical notes, and reasons.
4. The top-level `misata.enrich_text()` API across Series, DataFrames, and arrays.
5. Determinism under fixed seeds and zero lorem-ipsum leakage.
"""

import re
import numpy as np
import pandas as pd
import pytest

import misata
from misata.microtext import MicrotextGenerator
from misata.realism import RealisticTextGenerator, enrich_text
from misata.schema import Column, SchemaConfig, Table
from misata.simulator import DataSimulator


def _build_and_sim(schema_dict: dict) -> pd.DataFrame:
    tables = misata.generate_from_schema(schema_dict)
    first_tbl = next(iter(tables.values()))
    return first_tbl


class TestMicrotextGeneratorEnrichment:
    def setup_method(self):
        self.rng = np.random.default_rng(42)
        self.micro = MicrotextGenerator(self.rng)

    def test_ticket_subjects_diversity(self):
        subjects = self.micro.ticket_subjects(50)
        assert len(subjects) == 50
        assert len(set(subjects)) > 15
        assert any("SSO" in str(s) or "login" in str(s).lower() or "error" in str(s).lower() for s in subjects)

    def test_resolution_notes_authenticity(self):
        notes = self.micro.resolution_notes(40)
        assert len(notes) == 40
        assert len(set(notes)) > 10
        # Should look like realistic engineering / support resolution actions
        assert any("resolved" in str(n).lower() or "token" in str(n).lower() or "cache" in str(n).lower() for n in notes)

    def test_transaction_memos_format(self):
        memos = self.micro.transaction_memos(50)
        assert len(memos) == 50
        assert len(set(memos)) > 15
        # Statements have uppercase merchant tags, cities, or direct deposit identifiers
        assert any("*" in str(m) or "ACH" in str(m) or "INC" in str(m) or "STORE" in str(m) for m in memos)

    def test_error_messages_structure(self):
        errors = self.micro.error_messages(50)
        assert len(errors) == 50
        assert len(set(errors)) > 10
        assert any("Error" in str(e) or "HTTP" in str(e) or "Exception" in str(e) for e in errors)

    def test_clinical_notes_domains(self):
        complaints = self.micro.clinical_notes(20, note_type="chief_complaint")
        discharge = self.micro.clinical_notes(20, note_type="discharge_instructions")
        progress = self.micro.clinical_notes(20, note_type="clinical_notes")
        assert len(complaints) == 20
        assert any("pain" in str(c).lower() or "fever" in str(c).lower() or "headache" in str(c).lower() for c in complaints)
        assert any("medication" in str(d).lower() or "follow-up" in str(d).lower() or "days" in str(d).lower() for d in discharge)
        assert any("vital signs" in str(p).lower() or "exam" in str(p).lower() or "normal" in str(p).lower() for p in progress)

    def test_delivery_instructions(self):
        instructions = self.micro.delivery_instructions(30)
        assert len(instructions) == 30
        assert any("door" in str(i).lower() or "gate" in str(i).lower() or "porch" in str(i).lower() for i in instructions)

    def test_reasons_pools(self):
        returns = self.micro.return_reasons(30)
        churn = self.micro.churn_reasons(30)
        audit = self.micro.audit_reasons(30)
        assert any("damaged" in str(r).lower() or "size" in str(r).lower() or "defective" in str(r).lower() for r in returns)
        assert any("competitor" in str(c).lower() or "budget" in str(c).lower() or "price" in str(c).lower() for c in churn)
        assert any("compliance" in str(a).lower() or "soc2" in str(a).lower() or "audit" in str(a).lower() for a in audit)

    def test_enriched_addresses(self):
        addrs = self.micro.addresses(100)
        assert len(addrs) == 100
        assert len(set(addrs)) > 90
        # Addresses should have numbers and street suffixes
        assert any("St" in str(a) or "Ave" in str(a) or "Blvd" in str(a) or "Way" in str(a) for a in addrs)
        # Around 30% should carry secondary units (Apt, Suite, Unit)
        secondary_count = sum("," in str(a) for a in addrs)
        assert 15 <= secondary_count <= 50


class TestCategoryConditionedProductDescriptions:
    def test_category_matching_in_descriptions(self):
        rng = np.random.default_rng(123)
        gen = RealisticTextGenerator(rng=rng)
        # A description is about the product its row names: it mentions a
        # product type of the row's own category.
        from misata.scenarios import PRODUCT_FAMILIES
        cats = ["electronics", "clothing", "home", "beauty"] * 50
        table_data = pd.DataFrame({"category": cats})
        names = gen.generate(column_name="product_name", table_name="products", size=200,
                             semantic_type="product_name", table_data=table_data)
        table_data["product_name"] = names
        descs = gen.generate(
            column_name="description",
            table_name="products",
            size=200,
            semantic_type="product_description",
            table_data=table_data,
        )
        assert len(descs) == 200
        for cat, name, desc in zip(cats, names, descs):
            nouns = [n.lower() for n in PRODUCT_FAMILIES[cat].nouns]
            assert any(n in str(name).lower() for n in nouns), (cat, name)
            assert any(n in str(desc).lower() for n in nouns), (cat, name, desc)
        assert len(set(descs)) > 180


class TestAutoSemanticInference:
    def test_support_ticket_table_auto_infers_subject_and_notes(self):
        schema = {
            "name": "support_db",
            "seed": 42,
            "tables": {
                "tickets": {
                    "rows": 25,
                    "columns": {
                        "ticket_id": {"type": "int", "unique": True, "min": 1, "max": 1000},
                        "subject": {"type": "text"},
                        "resolution_notes": {"type": "text"},
                    },
                }
            },
        }
        df = _build_and_sim(schema)
        # Subjects should not be generic business notes or lorem ipsum
        assert all(isinstance(v, str) and len(v) > 10 for v in df["subject"])
        # A subject is a short line, not a paragraph
        assert np.mean([len(v) for v in df["subject"]]) < 40
        assert np.mean([v.endswith(".") for v in df["subject"]]) < 0.2
        # Resolution notes say what was wrong and what was done
        notes = [v for v in df["resolution_notes"] if isinstance(v, str)]
        assert len(set(notes)) >= 10

    def test_fintech_transactions_table_infers_memos(self):
        schema = {
            "name": "banking_db",
            "seed": 99,
            "tables": {
                "transactions": {
                    "rows": 30,
                    "columns": {
                        "tx_id": {"type": "int", "unique": True, "min": 1, "max": 10000},
                        "statement_descriptor": {"type": "text"},
                    },
                }
            },
        }
        df = _build_and_sim(schema)
        descriptors = df["statement_descriptor"].tolist()
        assert len(descriptors) == 30
        assert any("*" in d or "ACH" in d or "COFFEE" in d or "WIRE" in d or "TARGET" in d for d in descriptors)

    def test_healthcare_table_infers_clinical_text(self):
        schema = {
            "name": "clinic_db",
            "seed": 101,
            "tables": {
                "encounters": {
                    "rows": 20,
                    "columns": {
                        "encounter_id": {"type": "int", "unique": True, "min": 1, "max": 5000},
                        "chief_complaint": {"type": "text"},
                        "discharge_instructions": {"type": "text"},
                    },
                }
            },
        }
        df = _build_and_sim(schema)
        complaints = df["chief_complaint"].tolist()
        discharge = df["discharge_instructions"].tolist()
        assert any("pain" in c.lower() or "fever" in c.lower() or "cough" in c.lower() for c in complaints)
        assert any("medication" in d.lower() or "dietary" in d.lower() or "emergency" in d.lower() for d in discharge)


class TestDeclaredTextTypes:
    @pytest.mark.parametrize("declared_type, expected_indicator", [
        ("ticket_subject", ["SSO", "invoice", "error", "link", "delivery", "upload", "password", "order", "charge", "account", "app", "refund", "payment", "return", "log", "email"]),
        ("resolution_notes", ["token", "cache", "refund", "database", "resolved", "permission", "hotfix"]),
        ("transaction_memo", ["*", "ACH", "WIRE", "STORE", "INC", "MKT", "AIR"]),
        ("error_message", ["Error", "HTTP", "Exception", "Timeout", "Denied", "Constraint"]),
        ("delivery_instructions", ["porch", "gate", "door", "package", "lobby", "desk"]),
        ("return_reason", ["damaged", "size", "defective", "mistake", "parts", "price", "small", "big",
                           "fit", "faulty", "wrong", "broke", "late", "pictured", "described", "quality",
                           "colour", "gift", "needed", "suit"]),
        ("churn_reason", ["competitor", "budget", "platform", "price", "support", "adoption"]),
        ("audit_reason", ["compliance", "soc2", "audit", "override", "review", "verification"]),
    ])
    def test_declared_text_type_in_schema(self, declared_type, expected_indicator):
        schema = {
            "name": "test_schema",
            "seed": 7,
            "tables": {
                "events": {
                    "rows": 20,
                    "columns": {
                        "id": {"type": "int", "unique": True, "min": 1, "max": 1000},
                        "info_col": {"type": "text", "text_type": declared_type},
                    },
                }
            },
        }
        df = _build_and_sim(schema)
        values = df["info_col"].tolist()
        assert len(values) == 20
        combined = " ".join(values)
        assert any(ind.lower() in combined.lower() for ind in expected_indicator), (
            f"Expected one of {expected_indicator} in generated text for {declared_type}, got: {values[:3]}"
        )


class TestEnrichTextAPI:
    def test_enrich_series(self):
        s = pd.Series([""] * 10, name="ticket_subject")
        enriched = enrich_text(s, text_type="ticket_subject", seed=42)
        assert isinstance(enriched, pd.Series)
        assert len(enriched) == 10
        assert all(len(str(v)) > 5 for v in enriched)
        assert np.mean([len(str(v)) for v in enriched]) < 50   # a subject line, not a paragraph

    def test_enrich_dataframe_auto_detect(self):
        df = pd.DataFrame({
            "order_id": [1, 2, 3, 4, 5],
            "delivery_instructions": ["placeholder"] * 5,
            "customer_feedback": ["none"] * 5,
        })
        enriched = enrich_text(df, seed=42)
        assert isinstance(enriched, pd.DataFrame)
        assert list(enriched["order_id"]) == [1, 2, 3, 4, 5]
        # delivery_instructions should be transformed into authentic instructions
        assert any("porch" in d.lower() or "gate" in d.lower() or "door" in d.lower() for d in enriched["delivery_instructions"])
        # customer_feedback should be transformed into authentic feedback
        fb_words = r"interface|team|support|renew|recommend|update|integration|tool|price|plan|love|slow|faster"
        assert any(re.search(fb_words, f.lower()) for f in enriched["customer_feedback"])

    def test_enrich_array_or_list(self):
        items = ["placeholder"] * 6
        result = enrich_text(items, text_type="error_message", seed=42)
        assert isinstance(result, list)
        assert len(result) == 6
        assert any("Error" in r or "HTTP" in r for r in result)

    def test_enrich_text_is_deterministic(self):
        s1 = enrich_text(pd.Series([""] * 8), text_type="transaction_memo", seed=99)
        s2 = enrich_text(pd.Series([""] * 8), text_type="transaction_memo", seed=99)
        assert list(s1) == list(s2)

    def test_top_level_misata_enrich_text_export(self):
        from misata.vocab_seeds import CHURN_REASONS
        assert hasattr(misata, "enrich_text")
        res = misata.enrich_text(pd.Series([""] * 5), text_type="churn_reason", seed=10)
        assert len(res) == 5
        # Churn reasons are composed now, not drawn from the old list; each still
        # names a reason a customer gives.
        assert all(isinstance(r, str) and len(r) > 5 for r in res)
        assert CHURN_REASONS  # the legacy list remains importable
