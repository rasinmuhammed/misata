"""Tests for misata.documents — template-based document generation."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from misata.documents import (
    DocumentTemplate,
    _detect_template,
    generate_documents,
    list_document_templates,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def orders_df():
    return pd.DataFrame([
        {"order_id": 1001, "customer_id": 5, "amount": 149.99, "placed_at": "2024-03-01"},
        {"order_id": 1002, "customer_id": 8, "amount": 59.00,  "placed_at": "2024-03-02"},
    ])


@pytest.fixture
def patients_df():
    return pd.DataFrame([
        {"patient_id": "P001", "name": "Alice Smith", "diagnosis": "Hypertension",
         "visit_date": "2024-02-10", "medication": "Lisinopril"},
    ])


@pytest.fixture
def users_df():
    return pd.DataFrame([
        {"user_id": 1, "email": "alice@example.com", "plan": "Pro",
         "status": "active", "signup_date": "2023-01-15"},
    ])


@pytest.fixture
def transactions_df():
    return pd.DataFrame([
        {"transaction_id": "TXN-001", "account_id": 42, "amount": 250.00,
         "transaction_date": "2024-03-05", "fraud_flag": False},
    ])


# ---------------------------------------------------------------------------
# list_document_templates
# ---------------------------------------------------------------------------

class TestListDocumentTemplates:
    def test_returns_list(self):
        result = list_document_templates()
        assert isinstance(result, list)
        assert len(result) >= 5

    def test_includes_expected_names(self):
        result = list_document_templates()
        for name in ("invoice", "patient_report", "user_profile",
                     "transaction_receipt", "generic"):
            assert name in result


# ---------------------------------------------------------------------------
# Template detection
# ---------------------------------------------------------------------------

class TestDetectTemplate:
    def test_invoice_columns(self):
        assert _detect_template(["order_id", "amount", "placed_at"]) == "invoice"

    def test_patient_columns(self):
        assert _detect_template(["patient_id", "diagnosis", "visit_date"]) == "patient_report"

    def test_user_columns(self):
        assert _detect_template(["user_id", "email", "plan", "status"]) == "user_profile"

    def test_transaction_columns(self):
        assert _detect_template(["transaction_id", "account_id", "fraud_flag"]) == "transaction_receipt"

    def test_unknown_columns_returns_generic(self):
        assert _detect_template(["foo", "bar", "baz"]) == "generic"


# ---------------------------------------------------------------------------
# DocumentTemplate.render
# ---------------------------------------------------------------------------

class TestDocumentTemplateRender:
    def test_builtin_invoice_produces_html(self, orders_df):
        tmpl = DocumentTemplate("invoice")
        html = tmpl.render(orders_df.iloc[0].to_dict())
        assert "<html" in html.lower()
        assert "1001" in html  # order_id

    def test_builtin_patient_report(self, patients_df):
        tmpl = DocumentTemplate("patient_report")
        html = tmpl.render(patients_df.iloc[0].to_dict())
        assert "Hypertension" in html

    def test_builtin_user_profile(self, users_df):
        tmpl = DocumentTemplate("user_profile")
        html = tmpl.render(users_df.iloc[0].to_dict())
        assert "Pro" in html   # plan badge

    def test_builtin_transaction_receipt(self, transactions_df):
        tmpl = DocumentTemplate("transaction_receipt")
        html = tmpl.render(transactions_df.iloc[0].to_dict())
        assert "TXN-001" in html

    def test_auto_resolves_to_invoice(self, orders_df):
        tmpl = DocumentTemplate("auto")
        html = tmpl.render(orders_df.iloc[0].to_dict())
        assert "<html" in html.lower()

    def test_custom_string_template(self):
        tmpl = DocumentTemplate("<p>Hello {{ name }}, your ID is {{ user_id }}.</p>")
        result = tmpl.render({"name": "Bob", "user_id": 99})
        assert "Bob" in result
        assert "99" in result

    def test_markdown_format(self, orders_df):
        tmpl = DocumentTemplate("invoice", format="markdown")
        md = tmpl.render(orders_df.iloc[0].to_dict())
        assert "# Invoice" in md

    def test_nan_values_handled(self):
        import numpy as np
        tmpl = DocumentTemplate("generic")
        row = {"order_id": 1, "amount": float("nan"), "note": None}
        # Should not raise
        html = tmpl.render(row)
        assert "1" in html

    def test_file_template(self, tmp_path):
        tpl_file = tmp_path / "my.html"
        tpl_file.write_text("<h1>{{ title }}</h1>", encoding="utf-8")
        tmpl = DocumentTemplate(str(tpl_file))
        result = tmpl.render({"title": "Hello World"})
        assert "Hello World" in result


# ---------------------------------------------------------------------------
# generate_documents()
# ---------------------------------------------------------------------------

class TestGenerateDocuments:
    def test_generates_correct_count(self, orders_df, tmp_path):
        tables = {"orders": orders_df}
        paths = generate_documents(tables, "invoice",
                                   table="orders", output_dir=str(tmp_path))
        assert len(paths) == 2

    def test_files_exist(self, orders_df, tmp_path):
        tables = {"orders": orders_df}
        paths = generate_documents(tables, "invoice",
                                   table="orders", output_dir=str(tmp_path))
        for p in paths:
            assert Path(p).exists()

    def test_html_format(self, orders_df, tmp_path):
        tables = {"orders": orders_df}
        paths = generate_documents(tables, "invoice",
                                   table="orders", output_dir=str(tmp_path),
                                   format="html")
        assert all(p.endswith(".html") for p in paths)

    def test_markdown_format(self, orders_df, tmp_path):
        tables = {"orders": orders_df}
        paths = generate_documents(tables, "invoice",
                                   table="orders", output_dir=str(tmp_path),
                                   format="markdown")
        assert all(p.endswith(".md") for p in paths)
        content = Path(paths[0]).read_text()
        assert "# Invoice" in content

    def test_txt_format(self, orders_df, tmp_path):
        tables = {"orders": orders_df}
        paths = generate_documents(tables, "<p>{{ order_id }}</p>",
                                   table="orders", output_dir=str(tmp_path),
                                   format="txt")
        assert all(p.endswith(".txt") for p in paths)

    def test_filename_col(self, orders_df, tmp_path):
        tables = {"orders": orders_df}
        paths = generate_documents(tables, "invoice",
                                   table="orders", output_dir=str(tmp_path),
                                   filename_col="order_id")
        names = [Path(p).name for p in paths]
        assert "1001.html" in names
        assert "1002.html" in names

    def test_limit(self, orders_df, tmp_path):
        tables = {"orders": orders_df}
        paths = generate_documents(tables, "invoice",
                                   table="orders", output_dir=str(tmp_path),
                                   limit=1)
        assert len(paths) == 1

    def test_defaults_to_first_table(self, orders_df, tmp_path):
        tables = {"orders": orders_df}
        # No table= argument — should pick 'orders'
        paths = generate_documents(tables, "auto", output_dir=str(tmp_path))
        assert len(paths) == 2

    def test_unknown_table_raises(self, orders_df, tmp_path):
        tables = {"orders": orders_df}
        with pytest.raises(ValueError, match="nope"):
            generate_documents(tables, "invoice",
                               table="nope", output_dir=str(tmp_path))

    def test_output_dir_created(self, orders_df, tmp_path):
        new_dir = tmp_path / "nested" / "output"
        tables = {"orders": orders_df}
        paths = generate_documents(tables, "invoice",
                                   table="orders", output_dir=str(new_dir))
        assert new_dir.exists()
        assert len(paths) == 2

    def test_document_template_instance(self, orders_df, tmp_path):
        tables = {"orders": orders_df}
        tmpl = DocumentTemplate("invoice")
        paths = generate_documents(tables, tmpl,
                                   table="orders", output_dir=str(tmp_path))
        assert len(paths) == 2

    def test_pdf_raises_without_weasyprint(self, orders_df, tmp_path, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "weasyprint":
                raise ImportError("weasyprint not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        tables = {"orders": orders_df}
        with pytest.raises(ImportError, match="weasyprint"):
            generate_documents(tables, "invoice",
                               table="orders", output_dir=str(tmp_path),
                               format="pdf")

    def test_integrates_with_misata_generate(self, tmp_path):
        """End-to-end: generate tables → generate_documents → files on disk."""
        import misata
        tables = misata.generate("A SaaS company with 10 users", seed=1)
        paths = misata.generate_documents(
            tables, "user_profile",
            output_dir=str(tmp_path),
            limit=3,
        )
        assert len(paths) == 3
        html = Path(paths[0]).read_text()
        assert "<html" in html.lower()
