"""
Misata - AI-Powered Synthetic Data Engine

Generate realistic multi-table datasets from natural language descriptions.

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

__version__ = "0.7.1"
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


def generate(
    story: str,
    rows: int = 10_000,
    seed: "Optional[int]" = None,
) -> "Dict[str, Any]":
    """One-liner: story → dict of DataFrames.

    Parses the story with the rule-based StoryParser, generates data, and
    returns a ``{table_name: pd.DataFrame}`` dict.  No API key required.

    Args:
        story: Plain-English description of the dataset.
        rows:  Default row count for the primary table.
        seed:  Optional random seed for reproducibility.

    Returns:
        Dict mapping table name → ``pd.DataFrame``.

    Example::

        tables = misata.generate("A SaaS company with 5k users and 20% churn")
        print(tables["users"].head())
    """
    import pandas as pd
    from misata.story_parser import StoryParser
    from misata.simulator import DataSimulator

    schema = StoryParser().parse(story, default_rows=rows)
    if seed is not None:
        schema.seed = seed

    sim = DataSimulator(schema)
    tables: Dict[str, Any] = {}
    for name, batch in sim.generate_all():
        if name in tables:
            tables[name] = pd.concat([tables[name], batch], ignore_index=True)
        else:
            tables[name] = batch
    return tables


def generate_from_schema(
    schema: "SchemaConfig",
    custom_generators: "Optional[Dict[str, Dict[str, Any]]]" = None,
) -> "Dict[str, Any]":
    """Generate data from an already-built SchemaConfig.

    Args:
        schema:            A SchemaConfig (from ``misata.parse()``, an LLM generator,
                           or built manually).
        custom_generators: Optional ``{table: {column: callable}}`` overrides.
                           Each callable receives ``(partial_df, context_tables)``
                           and returns an array of length ``len(partial_df)``.

    Returns:
        Dict mapping table name → ``pd.DataFrame``.

    Example::

        schema = misata.parse("An ecommerce store")
        tables = misata.generate_from_schema(schema)
    """
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

from misata.schema import (
    Column,
    Constraint,
    NoiseConfig,
    RealismConfig,
    Relationship,
    ScenarioEvent,
    SchemaConfig,
    Table,
)
from misata.simulator import DataSimulator, GenerationResult
from misata.story_parser import StoryParser
from misata.llm_parser import LLMSchemaGenerator
from misata.validation import SchemaValidationError, validate_schema, validate_data
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
from misata.export import to_parquet, to_duckdb, to_jsonl
from misata.compat import from_dict_schema, verify_integrity, IntegrityReport
from misata.smart_values import SmartValueGenerator
from misata.noise import NoiseInjector, add_noise
from misata.customization import Customizer, ColumnOverride
from misata.quality import DataQualityChecker, check_quality
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
from misata.generators.base import (
    ConditionalCategoricalGenerator,
    CONDITIONAL_LOOKUPS,
    create_conditional_generator,
)

__all__ = [
    # One-liners
    "parse",
    "generate",
    "generate_from_schema",
    "generate_more",
    "from_dict_schema",
    "verify_integrity",
    "IntegrityReport",
    # Core
    "Column",
    "Constraint",
    "NoiseConfig",
    "RealismConfig",
    "Relationship",
    "ScenarioEvent",
    "SchemaConfig",
    "Table",
    "DataSimulator",
    "GenerationResult",
    "FactEngine",
    # Parsers
    "StoryParser",
    "LLMSchemaGenerator",
    # Validation
    "SchemaValidationError",
    "validate_schema",
    "validate_data",
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
    # Templates
    "load_template",
    "list_templates",
    # DB seeding
    # Export
    "to_parquet",
    "to_duckdb",
    "to_jsonl",
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
    "LOCALE_PACKS",
]
