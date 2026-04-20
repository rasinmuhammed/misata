# Export

## Parquet

```python
misata.to_parquet(tables, "data/")
# writes data/users.parquet, data/orders.parquet, …
```

## DuckDB

```python
misata.to_duckdb(tables, "data/dataset.duckdb")
# each table becomes a DuckDB table; query with SQL immediately

import duckdb
con = duckdb.connect("data/dataset.duckdb")
print(con.execute("SELECT plan, count(*) FROM users GROUP BY plan").df())
```

## JSON Lines

```python
misata.to_jsonl(tables, "data/")
# writes data/users.jsonl, data/orders.jsonl, …
```

## Document generation

Render one document per row from any table — invoices, patient reports, transaction receipts.

```python
# Built-in templates: invoice, patient_report, transaction_receipt, user_profile, generic
paths = misata.generate_documents(
    tables,
    template="invoice",
    table="orders",
    output_dir="/tmp/invoices",
    format="html",           # "html" | "markdown" | "txt" | "pdf"
)

# Custom Jinja2 template
tmpl = "<h1>Order #{{ order_id }}</h1><p>Total: ${{ amount }}</p>"
paths = misata.generate_documents(tables, tmpl, table="orders", output_dir="/tmp/custom")

# List built-in templates
print(misata.list_document_templates())
```

PDF output requires `pip install "misata[documents]"` (weasyprint).
