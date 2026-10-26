"""Boundaries that keep Misata offline, deterministic and safe on hostile input."""

from __future__ import annotations

import socket

import pytest

import misata


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("generation attempted a network connection")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def test_schema_generation_never_touches_the_network(no_network):
    tables = misata.generate_from_schema({
        "__seed__": 3,
        "customers": {"rows": 50, "columns": {
            "id": {"type": "int", "primary_key": True},
            "email": {"type": "text", "text_type": "email"},
        }},
        "orders": {"rows": 200, "columns": {
            "id": {"type": "int", "primary_key": True},
            "customer_id": {"type": "foreign_key", "references": "customers.id"},
            "amount": {"type": "float", "min": 1, "max": 500, "decimals": 2},
        }},
    })
    assert len(tables["orders"]) == 200


def test_story_generation_never_touches_the_network(no_network):
    tables = misata.generate("An online shop with 100 customers and orders", rows=100, seed=2)
    assert tables


def test_wikidata_fetch_refuses_non_https_urls():
    pytest.importorskip("misata.wikidata")
    from misata.wikidata import _http_json

    for url in ("file:///etc/passwd", "http://query.wikidata.org/sparql", "ftp://x/y"):
        with pytest.raises(ValueError, match="non-https"):
            _http_json(url)


def test_html_documents_escape_row_values():
    pytest.importorskip("jinja2")
    from misata.documents import DocumentTemplate

    payload = '<script>alert("x")</script>'
    html = DocumentTemplate("{{ note }}", format="html").render({"note": payload})
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_markdown_documents_keep_row_values_verbatim():
    pytest.importorskip("jinja2")
    from misata.documents import DocumentTemplate

    text = "a < b & c"
    md = DocumentTemplate("{{ note }}", format="markdown").render({"note": text})
    assert text in md
