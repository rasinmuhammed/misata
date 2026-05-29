"""
Pytest integration for Misata.

Provides fixture factories that make synthetic data available to test functions
without any database setup or file I/O.

Usage::

    # conftest.py
    from misata.testing import misata_fixture

    saas_tables = misata_fixture("A SaaS company with 500 users", rows=500)
    ecommerce_tables = misata_fixture("An ecommerce store with 200 orders", rows=200)

    # test_my_feature.py
    def test_user_count(saas_tables):
        assert len(saas_tables["users"]) == 500

    def test_order_fk_integrity(ecommerce_tables):
        orders = ecommerce_tables["orders"]
        customers = ecommerce_tables["customers"]
        assert orders["customer_id"].isin(customers["customer_id"]).all()

Built-in fixtures (import directly)::

    from misata.testing import misata_generate, misata_parse

    def test_parsing(misata_parse):
        schema = misata_parse("A fintech with 1k customers")
        assert schema.domain == "fintech"
"""

from typing import Any, Callable, Dict, Optional

try:
    import pytest
    _PYTEST_AVAILABLE = True
except ImportError:
    _PYTEST_AVAILABLE = False


def misata_fixture(
    story: str,
    rows: int = 1000,
    seed: int = 42,
    smart_correlations: bool = False,
    min_quality_score: Optional[float] = None,
    max_retries: int = 3,
) -> Callable:
    """Create a pytest fixture that generates Misata synthetic tables.

    Call this at module level in ``conftest.py`` to define fixtures usable
    across your test suite.

    Args:
        story:             Plain-English description of the dataset.
        rows:              Row count for the primary table (default 1000).
        seed:              Random seed for reproducibility (default 42).
        smart_correlations: Auto-infer Pearson correlations between related
                           numeric columns (default False).
        min_quality_score: Retry generation until FidelityChecker score meets
                           this threshold (0–100). None = no retry (default).
        max_retries:       Maximum retry attempts if min_quality_score is set.

    Returns:
        A pytest fixture function — assign it to a module-level variable.

    Example::

        # conftest.py
        from misata.testing import misata_fixture

        saas_tables = misata_fixture("A SaaS company with 500 users", rows=500)

        # test_billing.py
        def test_invoice_fk(saas_tables):
            invoices = saas_tables["invoices"]
            subs = saas_tables["subscriptions"]
            assert invoices["subscription_id"].isin(subs["subscription_id"]).all()
    """
    if not _PYTEST_AVAILABLE:
        raise ImportError(
            "pytest is required to use misata.testing. "
            "Install it with: pip install pytest"
        )

    @pytest.fixture(name=None, scope="function")
    def _fixture() -> Dict[str, Any]:
        import misata
        return misata.generate(
            story,
            rows=rows,
            seed=seed,
            smart_correlations=smart_correlations,
            min_quality_score=min_quality_score,
            max_retries=max_retries,
        )

    return _fixture


def misata_schema_fixture(
    story: str,
    rows: int = 1000,
) -> Callable:
    """Create a pytest fixture that returns a SchemaConfig (no data generated).

    Useful for testing schema parsing, validation, and introspection.

    Example::

        # conftest.py
        from misata.testing import misata_schema_fixture

        hr_schema = misata_schema_fixture("An HR company with employees and payroll")

        # test_schema.py
        def test_domain_detection(hr_schema):
            assert hr_schema.domain == "hr"

        def test_tables_present(hr_schema):
            table_names = [t.name for t in hr_schema.tables]
            assert "employees" in table_names
    """
    if not _PYTEST_AVAILABLE:
        raise ImportError(
            "pytest is required to use misata.testing. "
            "Install it with: pip install pytest"
        )

    @pytest.fixture(name=None, scope="function")
    def _fixture():
        import misata
        return misata.parse(story, rows=rows)

    return _fixture


if _PYTEST_AVAILABLE:
    @pytest.fixture
    def misata_generate():
        """Pytest fixture providing a pre-configured ``misata.generate`` callable.

        Use when you want to generate different datasets within the same test
        without declaring a separate fixture per dataset.

        Example::

            def test_multi_domain(misata_generate):
                saas = misata_generate("A SaaS company", rows=100, seed=1)
                fintech = misata_generate("A fintech company", rows=100, seed=2)
                assert "users" in saas
                assert "customers" in fintech
        """
        import misata
        return misata.generate

    @pytest.fixture
    def misata_parse():
        """Pytest fixture providing ``misata.parse`` for schema inspection tests.

        Example::

            def test_saas_domain(misata_parse):
                schema = misata_parse("A SaaS company with 5k users")
                assert schema.domain == "saas"
                assert any(t.name == "users" for t in schema.tables)
        """
        import misata
        return misata.parse

    @pytest.fixture
    def misata_preview():
        """Pytest fixture providing ``misata.preview`` for DetectionReport tests.

        Example::

            def test_fintech_detection(misata_preview):
                report = misata_preview("A fintech with fraud detection")
                assert report.domain == "fintech"
                assert report.domain_confidence in ("high", "low")
        """
        import misata
        return misata.preview
