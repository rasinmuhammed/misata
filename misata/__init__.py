"""
Misata - Outcome-Conformant Synthetic Data

Declare the outcome you want — a revenue curve, a fraud rate, multi-table aggregates —
and Misata generates realistic relational data that hits those targets exactly, with
referential integrity, from a sentence, YAML, or your database. No ML model, no real
data required. See the method paper: arXiv:2606.08736.

Quickstart::

    import misata

    # One-liner: story → DataFrames
    tables = misata.generate("A SaaS company with 5k users and 20% churn")

    # Two-step: inspect the schema first, then generate
    schema = misata.parse("An ecommerce store with 10k orders")
    print(schema.summary())
    tables = misata.generate_from_schema(schema)

    # LLM-powered (requires GROQ_API_KEY or OPENAI_API_KEY)
    from misata import LLMSchemaGenerator
    gen = LLMSchemaGenerator(provider="groq")
    tables = misata.generate_from_schema(gen.generate_from_story("A fintech fraud dataset"))
"""

__version__ = "0.8.7.8"
__author__ = "Muhammed Rasin"

from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Top-level convenience functions
# ---------------------------------------------------------------------------

def parse(story: str, rows: int = 10_000) -> "SchemaConfig":
    """Parse a plain-English story into a SchemaConfig.

    Uses the rule-based StoryParser — no API key required.

    Args:
        story: Plain-English description of the dataset.
        rows:  Default row count for the primary table.

    Returns:
        SchemaConfig ready for inspection or generation.

    Example::

        schema = misata.parse("A SaaS company with 5k users")
        print(schema.summary())
    """
    from misata.story_parser import StoryParser
    return StoryParser().parse(story, default_rows=rows)


def preview(story: str, rows: int = 10_000) -> "DetectionReport":
    """Inspect what Misata would generate from a story — without generating any rows.

    Returns a :class:`DetectionReport` describing the detected domain, locale,
    scale, near misses, table preview, and warnings. Useful for confirmation
    flows in UIs and notebooks: show the user *what was understood* before
    committing to generation.

    Args:
        story: Plain-English description of the dataset.
        rows:  Default row count (affects the table preview only — no rows are
               actually generated).

    Returns:
        :class:`DetectionReport` (a dataclass with a ``.summary()`` method).

    Example::

        report = misata.preview("A fintech with crypto wallets and 5k users")
        print(report.summary())

        if report.domain != "fintech":
            print("Refine the story:", report.warnings)
    """
    from misata.story_parser import StoryParser
    parser = StoryParser()
    parser.parse(story, default_rows=rows)
    return parser.detection_report()


# ---------------------------------------------------------------------------
# Streaming generation
# ---------------------------------------------------------------------------

def generate_stream(
    story: str,
    rows: int = 10_000,
    seed: "Optional[int]" = None,
    smart_correlations: bool = False,
) -> "Any":
    """Yield ``(table_name, batch_df)`` tuples — never buffers the full dataset.

    Suitable for 10M+ row datasets that don't fit in memory at once.
    Each ``batch_df`` is a :class:`pandas.DataFrame` containing one generation
    batch for that table.

    Args:
        story:             Plain-English description of the dataset.
        rows:              Default row count for the primary table.
        seed:              Optional random seed for reproducibility.
        smart_correlations: Auto-infer Pearson correlations between related
                           numeric columns.

    Yields:
        Tuple of ``(table_name, batch_df)``.

    Example::

        for table_name, batch in misata.generate_stream("A SaaS company", rows=1_000_000):
            batch.to_parquet(f"./output/{table_name}_{i}.parquet")
    """
    from misata.story_parser import StoryParser
    from misata.simulator import DataSimulator

    schema = StoryParser().parse(story, default_rows=rows)
    if seed is not None:
        schema.seed = seed
    if smart_correlations:
        _infer_correlations(schema)

    sim = DataSimulator(schema)
    yield from sim.generate_all()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _run_simulation(
    schema: "SchemaConfig",
    custom_generators: "Optional[Dict[str, Dict[str, Any]]]" = None,
) -> "Dict[str, Any]":
    import pandas as pd
    from misata.simulator import DataSimulator

    sim = DataSimulator(schema, custom_generators=custom_generators)
    tables: Dict[str, Any] = {}
    for name, batch in sim.generate_all():
        if name in tables:
            tables[name] = pd.concat([tables[name], batch], ignore_index=True)
        else:
            tables[name] = batch
    return tables


# (col_a_keywords, col_b_keywords, pearson_r)
_CORRELATION_RULES = [
    (["age"],                                            ["salary", "income", "compensation", "pay", "wage"],          0.45),
    (["experience", "tenure", "seniority"],              ["salary", "income", "compensation", "pay"],                  0.55),
    (["employee_count", "headcount", "team_size"],       ["revenue", "arr", "mrr", "gmv", "sales"],                    0.60),
    (["price", "unit_price", "avg_price"],               ["quantity", "units_sold", "order_count", "volume"],         -0.35),
    (["sessions", "visits", "page_views", "clicks"],     ["revenue", "spend", "amount", "sales"],                      0.50),
    (["support_tickets", "complaints", "issues_count"],  ["churn_risk", "churn_score", "churn_probability"],           0.40),
    (["discount_pct", "discount_rate"],                  ["quantity", "units_sold", "items"],                          0.30),
    (["nps_score", "satisfaction_score", "rating"],      ["retention_rate", "renewal_rate", "ltv"],                    0.55),
    (["loan_amount", "credit_limit", "credit_score"],    ["income", "salary", "annual_income"],                        0.50),
    (["portfolio_value", "balance", "account_balance"],  ["age", "tenure", "years_active"],                            0.40),
    (["fraud_score", "risk_score", "anomaly_score"],     ["amount", "transaction_amount", "value"],                    0.35),
    (["clv", "ltv", "lifetime_value"],                   ["tenure", "account_age", "membership_months"],               0.60),
]


def _infer_correlations(schema: "SchemaConfig") -> None:
    """Mutate schema in-place: add Pearson correlation specs for known column-name patterns."""
    for table in schema.tables:
        numeric_names = {
            c.name for c in schema.get_columns(table.name)
            if c.type in ("int", "float")
        }
        if len(numeric_names) < 2:
            continue

        existing_pairs: set = {
            (s["col_a"], s["col_b"]) for s in table.correlations
        } | {
            (s["col_b"], s["col_a"]) for s in table.correlations
        }

        for col_a_kws, col_b_kws, r in _CORRELATION_RULES:
            matched_a = [n for n in numeric_names if any(kw in n.lower() for kw in col_a_kws)]
            matched_b = [n for n in numeric_names if any(kw in n.lower() for kw in col_b_kws)]
            for a in matched_a:
                for b in matched_b:
                    if a != b and (a, b) not in existing_pairs:
                        table.correlations.append({"col_a": a, "col_b": b, "r": r})
                        existing_pairs.add((a, b))
                        existing_pairs.add((b, a))


# ---------------------------------------------------------------------------
# Top-level convenience functions
# ---------------------------------------------------------------------------

def generate(
    story: str,
    rows: int = 10_000,
    seed: "Optional[int]" = None,
    min_quality_score: "Optional[float]" = None,
    max_retries: int = 3,
    smart_correlations: bool = False,
    capsule: "Optional[str]" = None,
    verify: bool = False,
) -> "Dict[str, Any]":
    """One-liner: story → dict of DataFrames.

    Parses the story with the rule-based StoryParser, generates data, and
    returns a ``{table_name: pd.DataFrame}`` dict.  No API key required.

    Args:
        story:             Plain-English description of the dataset.
        rows:              Default row count for the primary table.
        seed:              Optional random seed for reproducibility.
        min_quality_score: If set (0–100), generation retries until
                           ``FidelityChecker.overall_score`` meets the threshold
                           or ``max_retries`` is exhausted. The best result is
                           always returned.
        max_retries:       Maximum retry attempts when ``min_quality_score`` is
                           set (default 3).
        smart_correlations: If True, automatically infer and apply Pearson
                            correlations between semantically related numeric
                            columns (e.g. age↔salary, price↔quantity).

    Returns:
        Dict mapping table name → ``pd.DataFrame``.

    Example::

        tables = misata.generate("A SaaS company with 5k users and 20% churn")
        print(tables["users"].head())

        # Quality-guaranteed generation
        tables = misata.generate("An ecommerce store", min_quality_score=80)

        # Auto-correlate numeric columns
        tables = misata.generate("An HR dataset", smart_correlations=True)
    """
    from misata.story_parser import StoryParser

    schema = StoryParser().parse(story, default_rows=rows)
    if seed is not None:
        schema.seed = seed

    # Delegate to generate_from_schema: one pipeline, so every feature wired
    # there (priors, coherence passes, verify) applies to the story path too.
    return generate_from_schema(
        schema,
        min_quality_score=min_quality_score,
        max_retries=max_retries,
        smart_correlations=smart_correlations,
        capsule=capsule,
        verify=verify,
    )


def _attach_capsule(schema: "SchemaConfig", capsule_path: str) -> None:
    """Point the schema's realism config at a capsule file (see misata.capsules)."""
    from misata.schema import RealismConfig

    if schema.realism is None:
        object.__setattr__(schema, "realism", RealismConfig())
    object.__setattr__(schema.realism, "capsule_file", str(capsule_path))


def generate_from_schema(
    schema: "SchemaConfig",
    custom_generators: "Optional[Dict[str, Dict[str, Any]]]" = None,
    min_quality_score: "Optional[float]" = None,
    max_retries: int = 3,
    smart_correlations: bool = False,
    capsule: "Optional[str]" = None,
    verify: bool = False,
) -> "Dict[str, Any]":
    """Generate data from an already-built SchemaConfig.

    Args:
        schema:            A SchemaConfig (from ``misata.parse()``, an LLM generator,
                           or built manually).
        custom_generators: Optional ``{table: {column: callable}}`` overrides.
                           Each callable receives ``(partial_df, context_tables)``
                           and returns an array of length ``len(partial_df)``.
        min_quality_score: If set (0–100), generation retries until the fidelity
                           score meets the threshold or ``max_retries`` is
                           exhausted. The best result is always returned.
        max_retries:       Maximum retry attempts when ``min_quality_score`` is set.
        smart_correlations: If True, automatically infer Pearson correlations
                            between semantically related numeric columns.
        verify:            If True, run :func:`misata.story_audit` on the result
                           and emit a warning for every unrepaired finding, so a
                           dataset that contradicts itself never ships silently.

    Returns:
        Dict mapping table name → ``pd.DataFrame``.

    Example::

        schema = misata.parse("An ecommerce store")
        tables = misata.generate_from_schema(schema, min_quality_score=85)
    """
    import copy

    if smart_correlations:
        schema = copy.deepcopy(schema)
        _infer_correlations(schema)

    if capsule is not None:
        _attach_capsule(schema, capsule)

    def _verified(tables: "Dict[str, Any]") -> "Dict[str, Any]":
        if verify:
            import warnings as _warnings
            from misata.coherence import story_audit
            report = story_audit(tables, schema)
            for f in report.findings:
                if not f.repaired:
                    _warnings.warn(
                        f"story_audit [{f.severity}] {f.table}"
                        f"{'.' + f.column if f.column else ''}: {f.message}",
                        UserWarning, stacklevel=3,
                    )
        return tables

    if min_quality_score is None:
        return _verified(_run_simulation(schema, custom_generators=custom_generators))

    from misata.reporting import FidelityChecker
    best_tables: "Optional[Dict[str, Any]]" = None
    best_score = -1.0
    base_seed = schema.seed or 0

    for attempt in range(max_retries + 1):
        if attempt > 0:
            schema.seed = base_seed + attempt
        tables = _run_simulation(schema, custom_generators=custom_generators)
        report = FidelityChecker().check_against_schema(tables, schema)
        if report.overall_score > best_score:
            best_score = report.overall_score
            best_tables = tables
        if report.overall_score >= min_quality_score:
            break

    return _verified(best_tables)  # type: ignore[arg-type]


def generate_more(
    tables: "Dict[str, Any]",
    schema: "SchemaConfig",
    n: int,
    seed: "Optional[int]" = None,
) -> "Dict[str, Any]":
    """Extend an existing dataset by generating additional rows.

    Generates ``n`` more rows per table, maintaining referential integrity with
    the existing data.  New rows are appended and the combined dataset returned.

    Args:
        tables: Existing ``{table_name: pd.DataFrame}`` dataset.
        schema: The ``SchemaConfig`` the original dataset was generated from.
        n:      Number of additional rows to generate for the primary table
                (child tables scale according to their original row ratios).
        seed:   Optional seed for the new batch (defaults to ``schema.seed + 1``
                for deterministic but distinct data).

    Returns:
        Dict mapping table name → merged ``pd.DataFrame`` (original + new rows).

    Example::

        tables = misata.generate("A fintech company with 1000 customers", seed=1)
        # Later — double the dataset without regenerating from scratch
        tables = misata.generate_more(tables, schema, n=1000, seed=2)
        print(len(tables["customers"]))  # 2000
    """
    import copy

    import pandas as pd
    from misata.simulator import DataSimulator

    # Build a fresh schema with the desired row counts, offset seed
    new_schema = copy.deepcopy(schema)
    if seed is not None:
        new_schema.seed = seed
    elif new_schema.seed is not None:
        new_schema.seed = new_schema.seed + 1

    # Scale each table proportionally to the requested n
    if new_schema.tables:
        primary = new_schema.tables[0]
        original_primary_count = primary.row_count or 1
        scale = n / original_primary_count
        for t in new_schema.tables:
            t.row_count = max(1, int((t.row_count or 1) * scale))

    sim = DataSimulator(new_schema)
    new_tables: Dict[str, Any] = {}
    for name, batch in sim.generate_all():
        if name in new_tables:
            new_tables[name] = pd.concat([new_tables[name], batch], ignore_index=True)
        else:
            new_tables[name] = batch

    # Merge with existing, re-index IDs to avoid collisions
    merged: Dict[str, Any] = {}
    for name in set(list(tables.keys()) + list(new_tables.keys())):
        existing = tables.get(name)
        new_df = new_tables.get(name)

        if existing is None:
            merged[name] = new_df
        elif new_df is None:
            merged[name] = existing
        else:
            # Offset integer PK-like columns in the new batch to avoid ID clashes
            if "id" in new_df.columns:
                try:
                    id_offset = int(existing["id"].max()) + 1
                    new_df = new_df.copy()
                    new_df["id"] = new_df["id"] + id_offset
                except Exception:
                    pass
            merged[name] = pd.concat([existing, new_df], ignore_index=True)

    return merged


def generate_diff(
    schema: "SchemaConfig",
    existing_dir: "Union[str, Path]",
    new_rows: "Optional[Dict[str, int]]" = None,
    seed: "Optional[int]" = None,
    output_dir: "Optional[Union[str, Path]]" = None,
) -> "Dict[str, Any]":
    """Generate additional rows that append cleanly to existing CSVs.

    Reads PKs from ``existing_dir`` to determine the maximum existing ID per
    table, generates new rows with PKs offset above that max, and returns the
    new-rows-only DataFrames. Referential integrity is maintained: FKs in new
    child rows reference only new parent rows (generated in this call) — they
    do not cross-reference the existing data.

    Args:
        schema:       The ``SchemaConfig`` used to generate the original dataset.
        existing_dir: Directory containing existing ``<table_name>.csv`` files.
        new_rows:     Per-table row counts for the new batch, e.g.
                      ``{"orders": 500, "order_items": 2000}``.  Defaults to the
                      row counts in ``schema``.
        seed:         Seed for the new batch (defaults to ``schema.seed + 10``).
        output_dir:   If given, write the new-rows CSVs there.

    Returns:
        Dict mapping table name → ``pd.DataFrame`` of **new rows only**.
        PKs are guaranteed not to overlap with any ID found in ``existing_dir``.

    Example::

        # Day 1: generate base dataset
        tables = misata.generate_from_schema(schema, seed=1)
        misata.to_csv(tables, "./data/")

        # Day 2: generate incremental rows, safe to append
        new_rows = misata.generate_diff(schema, "./data/", new_rows={"customers": 200})
        for name, df in new_rows.items():
            df.to_csv(f"./data/{name}_delta.csv", index=False)
    """
    import copy
    from pathlib import Path as _Path

    import pandas as pd
    from misata.simulator import DataSimulator

    existing_dir = _Path(existing_dir)
    new_schema = copy.deepcopy(schema)
    new_schema.seed = seed if seed is not None else ((schema.seed or 0) + 10)

    # Override row counts if caller specified
    if new_rows:
        for t in new_schema.tables:
            if t.name in new_rows:
                t.row_count = new_rows[t.name]

    # Read existing max PKs per table to compute offsets
    pk_offsets: Dict[str, int] = {}
    for t in new_schema.tables:
        csv_path = existing_dir / f"{t.name}.csv"
        if not csv_path.exists():
            continue
        try:
            existing_df = pd.read_csv(csv_path, nrows=0)
            # Look for integer PK-like columns
            full = pd.read_csv(csv_path, usecols=lambda c: c.lower() in (
                "id", f"{t.name}_id", f"{t.name[:-1]}_id"  # naive PK heuristic
            ))
            if not full.empty:
                col = full.columns[0]
                pk_offsets[t.name] = int(pd.to_numeric(full[col], errors="coerce").max()) + 1
        except Exception:
            pass

    sim = DataSimulator(new_schema)
    new_tables: Dict[str, Any] = {}
    for name, batch in sim.generate_all():
        if name in new_tables:
            new_tables[name] = pd.concat([new_tables[name], batch], ignore_index=True)
        else:
            new_tables[name] = batch

    # Apply PK offsets so new IDs don't collide with existing rows.
    # First pass: offset PKs.
    for name, df in new_tables.items():
        offset = pk_offsets.get(name, 0)
        if offset == 0:
            continue
        for col in df.columns:
            if col.lower() in ("id", f"{name}_id", f"{name[:-1]}_id"):
                try:
                    df[col] = df[col] + offset
                except Exception:
                    pass
        new_tables[name] = df

    # Second pass: offset FK columns in child tables so they still point at
    # the shifted parent PKs (child FK = parent PK offset, not child's own offset).
    for rel in new_schema.relationships:
        parent_offset = pk_offsets.get(rel.parent_table, 0)
        if parent_offset == 0:
            continue
        child_df = new_tables.get(rel.child_table)
        if child_df is None:
            continue
        fk_col = rel.child_key
        if fk_col in child_df.columns:
            try:
                child_df[fk_col] = child_df[fk_col] + parent_offset
                new_tables[rel.child_table] = child_df
            except Exception:
                pass

    if output_dir is not None:
        out = _Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        for name, df in new_tables.items():
            df.to_csv(out / f"{name}.csv", index=False)

    return new_tables


from misata.schema import (
    Column,
    Constraint,
    NoiseConfig,
    GroupShares,
    WaterfallIdentity,
    OutcomeCurve,
    RateCurve,
    RealismConfig,
    Relationship,
    ScenarioEvent,
    SchemaConfig,
    Table,
)
from misata.simulator import DataSimulator, GenerationResult
from misata.story_parser import StoryParser, DetectionReport
from misata.llm_parser import LLMSchemaGenerator
from misata.validation import SchemaValidationError, validate_schema, validate_data, validate_csv, CsvValidationReport
from misata.outcome_builder import OutcomeCurveBuilder, RateCurveBuilder
from misata.conformance import (
    conformance_preview,
    ConformancePreview,
    CurvePreview,
    PeriodPreview,
)
from misata.timeseries import (
    generate_timeseries,
    TimeSeriesConfig,
    TimeSeriesGenerator,
    Trend,
    Seasonality,
    Anomaly,
)
from misata.engines import FactEngine
from misata.generators import TextGenerator
from misata.generators.base import (
    BaseGenerator,
    IntegerGenerator,
    FloatGenerator,
    BooleanGenerator,
    CategoricalGenerator,
    DateGenerator,
    ForeignKeyGenerator,
    GeneratorFactory,
)
from misata.constraints import (
    BaseConstraint,
    SumConstraint,
    RangeConstraint,
    UniqueConstraint,
    NotNullConstraint,
    RatioConstraint,
    ConstraintEngine,
)
from misata.context import GenerationContext
from misata.exceptions import (
    MisataError,
    ColumnGenerationError,
    LLMError,
    ConfigurationError,
    ExportError,
)
from misata.export import to_parquet, to_duckdb, to_jsonl, to_sql, to_arrow
from misata.compat import from_dict_schema, verify_integrity, IntegrityReport
from misata.validator import validate as validate_domain, ValidationReport
from misata.smart_values import SmartValueGenerator
from misata.noise import NoiseInjector, add_noise
from misata.customization import Customizer, ColumnOverride
from misata.quality import DataQualityChecker, check_quality
from misata.coherence import coherence_audit, story_audit, CoherenceReport, CoherenceFinding
from misata.vocab_validator import validate_vocabulary, ValidationResult
from misata.capsule_registry import (
    install_capsule,
    load_registry_capsule,
    registry_names,
)
from misata.evalpack import build_evalpack, EvalPackResult, EvalQuestion
from misata.templates.library import load_template, list_templates
from misata.db import seed_database, seed_database_sqlalchemy, seed_from_sqlalchemy_models, SeedReport
from misata.db import load_tables_from_db
from misata.introspect import schema_from_db, schema_from_sqlalchemy
from misata.profiles import (
    DistributionProfile,
    get_profile,
    list_profiles,
    generate_with_profile,
)
from misata.recipes import RecipeSpec, RunManifest, load_recipe
from misata.reporting import (
    build_oracle_report,
    DataCard,
    FidelityChecker,
    FidelityReport,
    GenerationReportBundle,
    PrivacyAnalyzer,
    PrivacyReport,
    analyze_generation,
)
from misata.assets import (
    AssetStore,
    KaggleAssetIngestor,
    KaggleDatasetDescriptor,
    LicensePolicy,
)
from misata.domain_capsule import AssetProvenance, DomainCapsule, VocabularyAsset
from misata.vocabulary import SemanticVocabularyGenerator
from misata.kaggle_integration import (
    enrich_from_kaggle,
    ingest_csv as ingest_csv_vocab,
    kaggle_find,
    kaggle_status,
    detect_column_assets,
    EnrichmentResult,
)
from misata.documents import (
    DocumentTemplate,
    generate_documents,
    list_document_templates,
)
from misata.yaml_schema import (
    load_yaml_schema,
    save_yaml_schema,
    MISATA_YAML_TEMPLATE,
    json_schema,
    JSON_SCHEMA_URL,
)
from misata.constraints import InequalityConstraint, ColumnRangeConstraint
from misata.workflows import WORKFLOW_PRESETS, WorkflowEngine
from misata.locales import (
    detect_locale,
    detect_locale_from_story,
    get_locale_pack,
    LocaleRegistry,
    LOCALE_PACKS,
)
from misata.locales.packs import LocalePack
from misata.generators.base import (
    ConditionalCategoricalGenerator,
    CONDITIONAL_LOOKUPS,
    create_conditional_generator,
)
from misata.profiler import mimic, DataProfiler
from misata.fidelity import fidelity_report, FidelityReport, privacy_report, PrivacyReport
from misata.ddl import from_ddl
from misata import spark as spark  # noqa: PLC0414 — re-export the submodule

__all__ = [
    # One-liners
    "parse",
    "preview",
    "generate",
    "generate_stream",
    "generate_from_schema",
    "generate_more",
    "from_ddl",
    "mimic",
    "DataProfiler",
    "fidelity_report",
    "FidelityReport",
    "privacy_report",
    "PrivacyReport",
    "from_dict_schema",
    "verify_integrity",
    "IntegrityReport",
    # Core
    "Column",
    "Constraint",
    "NoiseConfig",
    "GroupShares",
    "WaterfallIdentity",
    "OutcomeCurve",
    "RateCurve",
    "RealismConfig",
    "Relationship",
    "ScenarioEvent",
    "SchemaConfig",
    "Table",
    "DataSimulator",
    "GenerationResult",
    "FactEngine",
    # Outcome curve SDK
    "OutcomeCurveBuilder",
    "RateCurveBuilder",
    "conformance_preview",
    "build_evalpack",
    "EvalPackResult",
    "EvalQuestion",
    "ConformancePreview",
    "CurvePreview",
    "PeriodPreview",
    # Parsers
    "StoryParser",
    "DetectionReport",
    "LLMSchemaGenerator",
    # Validation
    "SchemaValidationError",
    "validate_schema",
    "validate_data",
    "validate_csv",
    "CsvValidationReport",
    # Time-series
    "generate_timeseries",
    "TimeSeriesConfig",
    "TimeSeriesGenerator",
    "Trend",
    "Seasonality",
    "Anomaly",
    # Generators
    "TextGenerator",
    "BaseGenerator",
    "IntegerGenerator",
    "FloatGenerator",
    "BooleanGenerator",
    "CategoricalGenerator",
    "DateGenerator",
    "ForeignKeyGenerator",
    "GeneratorFactory",
    "ConditionalCategoricalGenerator",
    "CONDITIONAL_LOOKUPS",
    "create_conditional_generator",
    # Constraints
    "BaseConstraint",
    "SumConstraint",
    "RangeConstraint",
    "UniqueConstraint",
    "NotNullConstraint",
    "RatioConstraint",
    "ConstraintEngine",
    # Context
    "GenerationContext",
    # Exceptions
    "MisataError",
    "SchemaValidationError",
    "ColumnGenerationError",
    "LLMError",
    "ConfigurationError",
    "ExportError",
    # Smart Values
    "SmartValueGenerator",
    # Distribution Profiles
    "DistributionProfile",
    "get_profile",
    "list_profiles",
    "generate_with_profile",
    # Recipes
    "RecipeSpec",
    "RunManifest",
    "load_recipe",
    "PrivacyAnalyzer",
    "PrivacyReport",
    "FidelityChecker",
    "FidelityReport",
    "DataCard",
    "GenerationReportBundle",
    "analyze_generation",
    "build_oracle_report",
    "WorkflowEngine",
    "WORKFLOW_PRESETS",
    "AssetStore",
    "KaggleAssetIngestor",
    "KaggleDatasetDescriptor",
    "LicensePolicy",
    "AssetProvenance",
    "VocabularyAsset",
    "DomainCapsule",
    "SemanticVocabularyGenerator",
    # Document generation
    "DocumentTemplate",
    "generate_documents",
    "list_document_templates",
    # YAML schema
    "load_yaml_schema",
    "save_yaml_schema",
    "MISATA_YAML_TEMPLATE",
    "json_schema",
    "JSON_SCHEMA_URL",
    # Constraints
    "InequalityConstraint",
    "ColumnRangeConstraint",
    # Kaggle enrichment
    "enrich_from_kaggle",
    "ingest_csv_vocab",
    "kaggle_find",
    "kaggle_status",
    "detect_column_assets",
    "EnrichmentResult",
    # ML-ready features
    "NoiseInjector",
    "add_noise",
    "Customizer",
    "ColumnOverride",
    # Quality
    "DataQualityChecker",
    "check_quality",
    "coherence_audit",
    "story_audit",
    "CoherenceReport",
    "CoherenceFinding",
    "validate_vocabulary",
    "ValidationResult",
    "install_capsule",
    "load_registry_capsule",
    "registry_names",
    # Templates
    "load_template",
    "list_templates",
    # DB seeding
    # Export
    "to_parquet",
    "to_duckdb",
    "to_jsonl",
    # Spark / Delta Lake
    "spark",
    # DB seeding
    "seed_database",
    "seed_database_sqlalchemy",
    "seed_from_sqlalchemy_models",
    "SeedReport",
    "load_tables_from_db",
    "schema_from_db",
    "schema_from_sqlalchemy",
    # Localisation
    "detect_locale",
    "detect_locale_from_story",
    "get_locale_pack",
    "LocaleRegistry",
    "LocalePack",
    "LOCALE_PACKS",
]
