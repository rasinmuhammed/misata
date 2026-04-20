# CLI Reference

```bash
pip install misata
misata --help
```

---

## `misata init`

Scaffold a `misata.yaml` schema file.

```bash
misata init                                          # blank template
misata init --story "A marketplace with sellers"     # story → YAML
misata init --db postgresql://localhost/myapp        # DB introspection → YAML
misata init --output custom.yaml                     # custom output path
misata init --force                                  # overwrite existing file
```

---

## `misata generate`

Generate data and write to files or a database.

```bash
misata generate                                      # reads misata.yaml
misata generate --story "A SaaS company with 5k users" --rows 5000
misata generate --output-dir data/
misata generate --format parquet                     # parquet | csv | jsonl | duckdb
misata generate --locale de_DE                       # force locale
misata generate --seed 42
misata generate --db-url postgresql://localhost/dev --db-create
```

| Flag | Default | Description |
|:--|:--|:--|
| `--story` | — | Plain-English story |
| `--rows` | 10 000 | Row count for primary table |
| `--locale` | auto-detected | BCP-47 locale code (e.g. `de_DE`) |
| `--seed` | random | Integer seed for reproducibility |
| `--output-dir` | `.` | Directory to write output files |
| `--format` | `csv` | Output format: `csv`, `parquet`, `jsonl`, `duckdb` |
| `--db-url` | — | Database URL for direct seeding |
| `--db-create` | false | Create tables if they don't exist |

---

## `misata validate`

Profile a CSV and optionally check it against a schema.

```bash
misata validate customers.csv
misata validate orders.csv --schema misata.yaml
misata validate orders.csv --story "A SaaS company with orders table"
misata validate orders.csv --table orders            # specify table name in schema
```

---

## `misata template`

Generate from a built-in industry template.

```bash
misata template saas --scale 0.1 --output-dir data/
misata template fintech --rows 5000
```

---

## `misata templates-list`

List all available industry templates.

```bash
misata templates-list
```

---

## `misata schema`

Introspect a database and print or save the schema.

```bash
misata schema --db-url postgresql://localhost/myapp
misata schema --db-url postgresql://localhost/myapp --output schema.yaml
```

---

## `misata studio`

Launch the visual schema designer (requires `pip install "misata[studio]"`).

```bash
misata studio
misata studio --port 8080 --no-browser
```
