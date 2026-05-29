---
title: Pytest Fixtures for Synthetic Data | Misata
description: Use misata.testing to create pytest fixtures that generate realistic synthetic data without database setup. Zero configuration, reproducible seeds, full FK integrity.
---

# Pytest Fixtures with Misata

`misata.testing` provides pytest fixture factories and built-in fixtures so your tests get realistic synthetic data without database setup, migrations, or fixture files.

## Install

```bash
pip install misata pytest
```

## Quick start

Define fixtures in `conftest.py` using `misata_fixture`:

```python
# conftest.py
from misata.testing import misata_fixture

saas_tables   = misata_fixture("A SaaS company with 500 users", rows=500)
fintech_tables = misata_fixture("A fintech with 200 customers and 2% fraud rate", rows=200)
hr_tables     = misata_fixture("An HR company with 300 employees", rows=300)
```

Use them in any test file — no imports needed:

```python
# test_billing.py
def test_invoice_fk_integrity(saas_tables):
    invoices = saas_tables["invoices"]
    subs     = saas_tables["subscriptions"]
    assert invoices["subscription_id"].isin(subs["subscription_id"]).all()

def test_churn_rate(saas_tables):
    users = saas_tables["users"]
    assert 0.10 <= users["is_active"].mean() <= 0.90

# test_fraud.py
def test_fraud_flag_rate(fintech_tables):
    txns = fintech_tables["transactions"]
    # ~2% fraud rate from the story description
    assert 0.01 <= txns["is_fraud"].mean() <= 0.05
```

## `misata_fixture(story, rows, seed, ...)`

| Parameter | Default | Description |
|:--|:--|:--|
| `story` | required | Plain-English dataset description |
| `rows` | `1000` | Row count for the primary table |
| `seed` | `42` | Random seed — same seed = identical data every run |
| `smart_correlations` | `False` | Auto-add Pearson correlations between related numeric columns |
| `min_quality_score` | `None` | Retry generation until FidelityChecker score meets threshold |

## `misata_schema_fixture(story, rows)`

Returns a `SchemaConfig` (no data generated) — useful for testing schema parsing and domain detection:

```python
# conftest.py
from misata.testing import misata_schema_fixture

saas_schema = misata_schema_fixture("A SaaS company with users and subscriptions")
```

```python
# test_schema.py
def test_domain_detection(saas_schema):
    assert saas_schema.domain == "saas"

def test_table_names(saas_schema):
    names = [t.name for t in saas_schema.tables]
    assert "users" in names
    assert "subscriptions" in names
```

## Built-in fixtures

Three fixtures are available to import directly without `conftest.py` setup:

### `misata_generate`

Injects `misata.generate` — use when you want to generate different datasets within a single test:

```python
from misata.testing import misata_generate   # imported for type hints only

def test_multi_domain(misata_generate):
    saas    = misata_generate("A SaaS company", rows=100, seed=1)
    fintech = misata_generate("A fintech company", rows=100, seed=2)
    assert "users" in saas
    assert "customers" in fintech
```

### `misata_parse`

Injects `misata.parse` for schema inspection tests:

```python
def test_saas_domain(misata_parse):
    schema = misata_parse("A SaaS company with 5k users")
    assert schema.domain == "saas"
```

### `misata_preview`

Injects `misata.preview` for DetectionReport tests:

```python
def test_detection_confidence(misata_preview):
    report = misata_preview("A fintech with fraud detection and 2% fraud rate")
    assert report.domain == "fintech"
    assert report.domain_confidence in ("high", "low")
```

## Reproducibility

Every `misata_fixture` call with the same `seed` produces identical data. Tests are fully deterministic:

```python
saas_a = misata_fixture("A SaaS company", rows=100, seed=42)
saas_b = misata_fixture("A SaaS company", rows=100, seed=42)

def test_determinism(saas_a, saas_b):
    import pandas as pd
    pd.testing.assert_frame_equal(saas_a["users"], saas_b["users"])
```

## Scope

By default fixtures have `scope="function"` — fresh data for each test. If you want shared data across a test module (faster), define the fixture manually:

```python
# conftest.py
import pytest
import misata

@pytest.fixture(scope="module")
def shared_ecommerce():
    return misata.generate("An ecommerce store", rows=5000, seed=42)
```
