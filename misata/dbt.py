"""
dbt integration utilities for Misata.

Provides:
  - Auto-detection of dbt projects (reads dbt_project.yml)
  - Generation of dbt-compatible schema.yml with tests
  - Generation of dbt 1.8+ unit test fixtures (CSV + YAML)
  - Seed file size intelligence and warnings

Usage from CLI::

    misata dbt-seed --story "SaaS with 1k users" --seeds-dir seeds/
    misata dbt-fixture --story "Ecommerce" --rows 50

Usage from Python::

    from misata.dbt import generate_dbt_schema_yml, generate_dbt_fixtures
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DbtProjectInfo:
    """Information extracted from a dbt_project.yml file."""

    project_root: Path
    project_name: str
    seeds_dir: Path
    test_paths: List[Path]
    model_paths: List[Path]
    dbt_version: Optional[str] = None

    @property
    def seeds_dir_abs(self) -> Path:
        return self.project_root / self.seeds_dir

    @property
    def fixtures_dir(self) -> Path:
        """Default fixture directory for dbt unit tests."""
        if self.test_paths:
            return self.project_root / self.test_paths[0] / "fixtures"
        return self.project_root / "tests" / "fixtures"


@dataclass
class SeedSizeReport:
    """Intelligence about a generated seed file's size."""

    table_name: str
    row_count: int
    file_size_bytes: int

    # dbt best practice thresholds
    RECOMMENDED_MAX_BYTES: int = 1_048_576   # 1 MB
    HARD_LIMIT_BYTES: int = 5_242_880        # 5 MB

    @property
    def exceeds_recommended(self) -> bool:
        return self.file_size_bytes > self.RECOMMENDED_MAX_BYTES

    @property
    def exceeds_hard_limit(self) -> bool:
        return self.file_size_bytes > self.HARD_LIMIT_BYTES

    @property
    def file_size_human(self) -> str:
        if self.file_size_bytes < 1024:
            return f"{self.file_size_bytes} B"
        if self.file_size_bytes < 1_048_576:
            return f"{self.file_size_bytes / 1024:.1f} KB"
        return f"{self.file_size_bytes / 1_048_576:.1f} MB"

    @property
    def recommendation(self) -> str:
        if self.exceeds_hard_limit:
            return (
                "File exceeds 5 MB — dbt seed will be very slow. "
                "Use `misata generate --db-url ...` and declare a dbt source instead."
            )
        if self.exceeds_recommended:
            return (
                "File exceeds 1 MB — consider reducing --rows or using "
                "`misata generate --db-url ...` for direct warehouse loading."
            )
        return "OK"


@dataclass
class DbtSeedResult:
    """Result of a dbt-seed generation run."""

    seeds_dir: Path
    tables_written: List[Tuple[str, int, Path]]  # (name, row_count, path)
    tables_skipped: List[str]
    schema_yml_path: Optional[Path] = None
    misata_yaml_path: Optional[Path] = None
    size_reports: List[SeedSizeReport] = field(default_factory=list)

    @property
    def has_size_warnings(self) -> bool:
        return any(r.exceeds_recommended for r in self.size_reports)


@dataclass
class DbtFixtureResult:
    """Result of a dbt-fixture generation run."""

    fixtures_dir: Path
    fixtures_written: List[Tuple[str, int, Path]]  # (name, row_count, path)
    unit_tests_yml_path: Optional[Path] = None


# ---------------------------------------------------------------------------
# dbt project detection
# ---------------------------------------------------------------------------

def detect_dbt_project(start_dir: Optional[Path] = None) -> Optional[DbtProjectInfo]:
    """Walk upward from *start_dir* looking for ``dbt_project.yml``.

    Returns a :class:`DbtProjectInfo` if found, else ``None``.
    """
    current = Path(start_dir or ".").resolve()

    # Walk up at most 10 levels
    for _ in range(10):
        candidate = current / "dbt_project.yml"
        if candidate.is_file():
            return _parse_dbt_project(candidate)
        parent = current.parent
        if parent == current:
            break
        current = parent

    return None


def _parse_dbt_project(yml_path: Path) -> DbtProjectInfo:
    """Parse a ``dbt_project.yml`` and extract relevant paths."""
    with open(yml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    project_root = yml_path.parent
    project_name = data.get("name", "unknown")

    # seed-paths: dbt >= 1.5 uses "seed-paths", older uses "data-paths"
    seed_paths = data.get("seed-paths", data.get("data-paths", ["seeds"]))
    seeds_dir = Path(seed_paths[0]) if seed_paths else Path("seeds")

    test_paths_raw = data.get("test-paths", ["tests"])
    test_paths = [Path(p) for p in test_paths_raw]

    model_paths_raw = data.get("model-paths", ["models"])
    model_paths = [Path(p) for p in model_paths_raw]

    dbt_version = data.get("version", None)

    return DbtProjectInfo(
        project_root=project_root,
        project_name=project_name,
        seeds_dir=seeds_dir,
        test_paths=test_paths,
        model_paths=model_paths,
        dbt_version=str(dbt_version) if dbt_version else None,
    )


# ---------------------------------------------------------------------------
# Schema.yml generation
# ---------------------------------------------------------------------------

def generate_dbt_schema_yml(
    schema_config: "SchemaConfig",
    tables: Dict[str, "pd.DataFrame"],
    *,
    resource_type: str = "seeds",
) -> str:
    """Generate a dbt-compatible schema YAML string.

    Produces a ``version: 2`` document with tests for:
      - ``unique`` on primary key columns
      - ``not_null`` on non-nullable columns
      - ``relationships`` for every FK relationship

    Args:
        schema_config: The Misata schema that generated the data.
        tables:        Dict of table_name → DataFrame.
        resource_type: ``"seeds"`` (default) or ``"sources"``.

    Returns:
        A YAML string suitable for writing to ``_misata_seeds.yml``.
    """
    from misata.schema import SchemaConfig  # noqa: F811 — deferred import

    doc: Dict[str, Any] = {"version": 2}
    resource_list: List[Dict[str, Any]] = []

    for table in schema_config.tables:
        if table.name not in tables:
            continue

        entry: Dict[str, Any] = {"name": table.name}
        if table.description:
            entry["description"] = table.description

        columns_spec: List[Dict[str, Any]] = []
        schema_columns = schema_config.get_columns(table.name)
        pk_columns = _infer_pk_columns(table.name, schema_columns, schema_config)

        for col in schema_columns:
            col_entry: Dict[str, Any] = {"name": col.name}
            if col.description:
                col_entry["description"] = col.description

            tests: List[Any] = []

            # unique test for PKs
            if col.name in pk_columns or col.unique:
                tests.append("unique")

            # not_null test for non-nullable columns
            if not col.nullable:
                tests.append("not_null")

            # relationships test for FK columns.
            # dbt 1.9+ requires generic-test args nested under `arguments`
            # (inline args are deprecated as of 1.11 / dbt Fusion).
            for rel in schema_config.relationships:
                if rel.child_table == table.name and rel.child_key == col.name:
                    tests.append({
                        "relationships": {
                            "arguments": {
                                "to": f"ref('{rel.parent_table}')",
                                "field": rel.parent_key,
                            }
                        }
                    })

            if tests:
                col_entry["tests"] = tests
            columns_spec.append(col_entry)

        if columns_spec:
            entry["columns"] = columns_spec
        resource_list.append(entry)

    doc[resource_type] = resource_list

    raw_yaml = yaml.dump(
        doc,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )

    return raw_yaml


# ---------------------------------------------------------------------------
# Unit test fixture generation
# ---------------------------------------------------------------------------

def generate_dbt_fixtures(
    schema_config: "SchemaConfig",
    tables: Dict[str, "pd.DataFrame"],
    output_dir: Path,
    *,
    max_rows: int = 50,
    table_filter: Optional[List[str]] = None,
) -> DbtFixtureResult:
    """Generate dbt 1.8+ unit test fixture CSVs.

    Creates small, focused CSV files suitable for use as dbt unit test
    fixtures. These go in ``tests/fixtures/`` and are referenced in
    unit test YAML definitions.

    Args:
        schema_config: The Misata schema that generated the data.
        tables:        Dict of table_name → DataFrame.
        output_dir:    Directory to write fixture CSVs into.
        max_rows:      Maximum rows per fixture (default: 50).
        table_filter:  If set, only generate fixtures for these tables.

    Returns:
        A :class:`DbtFixtureResult` with paths to all generated files.
    """
    import pandas as pd

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fixtures_written: List[Tuple[str, int, Path]] = []

    for table_name, df in tables.items():
        if table_filter and table_name not in table_filter:
            continue

        # Take a representative sample — preserve FK integrity by taking
        # the first N rows (which are generated in FK-dependency order)
        fixture_df = df.head(max_rows).copy()
        fixture_name = f"{table_name}_fixture"
        fixture_path = output_dir / f"{fixture_name}.csv"
        fixture_df.to_csv(fixture_path, index=False)
        fixtures_written.append((table_name, len(fixture_df), fixture_path))

    # Generate example unit test YAML
    unit_tests_yml_path = output_dir / "_unit_tests_example.yml"
    unit_test_content = generate_unit_test_yml(
        schema_config,
        tables,
        fixture_names={name: f"{name}_fixture" for name in tables if not table_filter or name in table_filter},
    )
    unit_tests_yml_path.write_text(unit_test_content, encoding="utf-8")

    return DbtFixtureResult(
        fixtures_dir=output_dir,
        fixtures_written=fixtures_written,
        unit_tests_yml_path=unit_tests_yml_path,
    )


def generate_unit_test_yml(
    schema_config: "SchemaConfig",
    tables: Dict[str, "pd.DataFrame"],
    *,
    fixture_names: Optional[Dict[str, str]] = None,
) -> str:
    """Generate example dbt 1.8+ unit test YAML blocks.

    This produces a commented YAML file showing how to wire Misata-generated
    fixtures into dbt unit tests. Users copy the relevant blocks into their
    ``models/schema.yml``.

    Args:
        schema_config: The Misata schema.
        tables:        Dict of table_name → DataFrame.
        fixture_names: Mapping of table_name → fixture file basename (no ext).

    Returns:
        YAML string with example unit test definitions.
    """
    if fixture_names is None:
        fixture_names = {name: f"{name}_fixture" for name in tables}

    lines: List[str] = [
        "# =============================================================================",
        "# Misata-generated dbt unit test fixtures",
        "#",
        "# Copy the relevant blocks below into your models/schema.yml or",
        "# models/<model_name>.yml to wire these fixtures into dbt unit tests.",
        "#",
        "# dbt docs: https://docs.getdbt.com/docs/build/unit-tests",
        "# Generated by: misata dbt-fixture",
        "# =============================================================================",
        "",
        "unit_tests:",
    ]

    for table_name in tables:
        if table_name not in fixture_names:
            continue

        fixture_name = fixture_names[table_name]
        test_name = f"test_{table_name}_fixture_loads"

        # Find FK dependencies — these become the `given` inputs
        parent_tables = []
        for rel in schema_config.relationships:
            if rel.child_table == table_name:
                parent_tables.append((rel.parent_table, rel.child_key))

        lines.append(f"  # --- {table_name} ---")
        lines.append(f"  - name: {test_name}")
        lines.append(f"    description: \"Validates {table_name} transformation with Misata-generated fixture data\"")
        lines.append(f"    model: stg_{table_name}  # ← replace with your actual model name")
        lines.append(f"    given:")
        lines.append(f"      - input: ref('{table_name}')")
        lines.append(f"        format: csv")
        lines.append(f"        fixture: {fixture_name}")

        for parent_table, fk_col in parent_tables:
            parent_fixture = fixture_names.get(parent_table, f"{parent_table}_fixture")
            lines.append(f"      - input: ref('{parent_table}')")
            lines.append(f"        format: csv")
            lines.append(f"        fixture: {parent_fixture}")

        lines.append(f"    expect:")
        lines.append(f"      format: csv")
        lines.append(f"      fixture: {table_name}_expected  # ← create this with your expected output")
        lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Seed writing with size intelligence
# ---------------------------------------------------------------------------

def write_seeds_with_report(
    tables: Dict[str, "pd.DataFrame"],
    seeds_dir: Path,
    *,
    force: bool = False,
) -> Tuple[List[Tuple[str, int, Path]], List[str], List[SeedSizeReport]]:
    """Write table DataFrames as CSVs and return size reports.

    Args:
        tables:    Dict of table_name → DataFrame.
        seeds_dir: Directory to write CSVs into.
        force:     Overwrite existing files.

    Returns:
        Tuple of (written, skipped, size_reports).
    """
    seeds_dir = Path(seeds_dir)
    seeds_dir.mkdir(parents=True, exist_ok=True)

    written: List[Tuple[str, int, Path]] = []
    skipped: List[str] = []
    size_reports: List[SeedSizeReport] = []

    for table_name, df in tables.items():
        dest = seeds_dir / f"{table_name}.csv"
        if dest.exists() and not force:
            skipped.append(table_name)
            continue

        df.to_csv(dest, index=False)
        file_size = dest.stat().st_size
        written.append((table_name, len(df), dest))

        size_reports.append(SeedSizeReport(
            table_name=table_name,
            row_count=len(df),
            file_size_bytes=file_size,
        ))

    return written, skipped, size_reports


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_pk_columns(
    table_name: str,
    columns: list,
    schema_config: "SchemaConfig",
) -> set:
    """Infer which columns are primary keys for a table.

    Heuristics:
      1. Columns explicitly marked ``unique=True``
      2. First column if its name ends with ``_id`` or equals ``id``
      3. Columns referenced as ``parent_key`` in relationships where this
         table is the parent
    """
    pk_cols: set = set()

    for col in columns:
        if col.unique:
            pk_cols.add(col.name)

    # First column heuristic
    if columns and not pk_cols:
        first = columns[0]
        if first.name == "id" or first.name.endswith("_id"):
            pk_cols.add(first.name)

    # Relationship parent keys
    for rel in schema_config.relationships:
        if rel.parent_table == table_name:
            pk_cols.add(rel.parent_key)

    return pk_cols
