"""Pytest plugin for Misata, registered automatically when misata is installed.

Kept outside the ``misata`` package on purpose: pytest imports every
installed plugin at startup, and importing ``misata`` itself takes a second or
more. This module imports nothing heavy until a fixture is actually used.

Fixtures
--------
``misata_tables``
    Tables generated from the test's ``@pytest.mark.misata(...)`` marker
    (or the module's ``pytestmark``)::

        @pytest.mark.misata(schema="misata.yaml", seed=7)
        def test_revenue_model(misata_tables):
            orders = misata_tables["orders"]

        @pytest.mark.misata(story="A SaaS company with 500 users", rows=500)
        def test_churn(misata_tables): ...

    The same marker arguments are generated once per session and shared, so a
    hundred tests on one schema pay for it once. Each test gets copies, so a
    test that mutates a frame does not leak into the next.

``misata_sqlite``
    The same tables seeded into a fresh SQLite file; yields its URL
    (``sqlite:///...``), for code under test that talks to a database.

``misata_generate``, ``misata_parse``, ``misata_preview``
    The library functions, for tests that build several datasets.

Disable with ``-p no:misata``.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

import pytest

_CACHE: Dict[Tuple, Dict[str, Any]] = {}


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "misata(schema=None, story=None, rows=None, seed=None): data for the "
        "misata_tables and misata_sqlite fixtures")


def _marker_args(request) -> Dict[str, Any]:
    marker = request.node.get_closest_marker("misata")
    if marker is None:
        raise pytest.UsageError(
            f"{request.node.nodeid} uses a misata fixture but has no "
            f"@pytest.mark.misata(schema=... or story=...) marker")
    kwargs = dict(marker.kwargs)
    if marker.args and "schema" not in kwargs and "story" not in kwargs:
        kwargs["schema"] = marker.args[0]
    if not kwargs.get("schema") and not kwargs.get("story"):
        raise pytest.UsageError("@pytest.mark.misata needs schema= or story=")
    return kwargs


def _build(kwargs: Dict[str, Any], rootdir) -> Dict[str, Any]:
    import misata

    schema_arg, story = kwargs.get("schema"), kwargs.get("story")
    seed, rows = kwargs.get("seed"), kwargs.get("rows")
    if story:
        return misata.generate(story, rows=rows or 100, seed=seed if seed is not None else 42)
    if isinstance(schema_arg, (str, bytes)) or hasattr(schema_arg, "__fspath__"):
        from pathlib import Path

        from misata.yaml_schema import load_yaml_schema
        path = Path(schema_arg)
        if not path.is_absolute():
            path = Path(rootdir) / path
        schema = load_yaml_schema(path)
    elif isinstance(schema_arg, dict):
        from misata.compat import from_dict_schema
        schema = from_dict_schema(schema_arg)
    else:
        schema = schema_arg
    if seed is not None:
        schema.seed = seed
    return misata.generate_from_schema(schema)


def _key(kwargs: Dict[str, Any]) -> Tuple:
    def freeze(v):
        if isinstance(v, dict):
            return tuple(sorted((k, freeze(x)) for k, x in v.items()))
        if isinstance(v, (list, tuple)):
            return tuple(freeze(x) for x in v)
        return v if isinstance(v, (str, int, float, bool, type(None))) else id(v)
    return freeze(kwargs)


@pytest.fixture
def misata_tables(request):
    kwargs = _marker_args(request)
    key = _key(kwargs)
    if key not in _CACHE:
        _CACHE[key] = _build(kwargs, request.config.rootpath)
    return {name: df.copy() for name, df in _CACHE[key].items()}


@pytest.fixture
def misata_sqlite(request, tmp_path):
    import misata

    kwargs = _marker_args(request)
    if kwargs.get("story"):
        schema = misata.parse(kwargs["story"], rows=kwargs.get("rows") or 100)
        if kwargs.get("seed") is not None:
            schema.seed = kwargs["seed"]
    else:
        tables_kwargs = dict(kwargs)
        schema = tables_kwargs.get("schema")
        if isinstance(schema, (str, bytes)) or hasattr(schema, "__fspath__"):
            from pathlib import Path

            from misata.yaml_schema import load_yaml_schema
            path = Path(schema)
            if not path.is_absolute():
                path = Path(request.config.rootpath) / path
            schema = load_yaml_schema(path)
        elif isinstance(schema, dict):
            from misata.compat import from_dict_schema
            schema = from_dict_schema(schema)
        if kwargs.get("seed") is not None:
            schema.seed = kwargs["seed"]
    url = f"sqlite:///{tmp_path / 'misata.db'}"
    misata.seed_database(schema, url, create=True)
    yield url


@pytest.fixture
def misata_generate():
    import misata
    return misata.generate


@pytest.fixture
def misata_parse():
    import misata
    return misata.parse


@pytest.fixture
def misata_preview():
    import misata
    return misata.preview
