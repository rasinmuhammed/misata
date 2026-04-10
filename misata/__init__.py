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

__version__ = "0.5.3"
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


def generate_from_schema(schema: "SchemaConfig") -> "Dict[str, Any]":
    """Generate data from an already-built SchemaConfig.

    Args:
        schema: A SchemaConfig (from ``misata.parse()``, an LLM generator,
                or built manually).

    Returns:
        Dict mapping table name → ``pd.DataFrame``.

    Example::

        schema = misata.parse("An ecommerce store")
        tables = misata.generate_from_schema(schema)
    """
    import pandas as pd
    from misata.simulator import DataSimulator

    sim = DataSimulator(schema)
    tables: Dict[str, Any] = {}
    for name, batch in sim.generate_all():
        if name in tables:
            tables[name] = pd.concat([tables[name], batch], ignore_index=True)
        else:
            tables[name] = batch
    return tables

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
from misata.workflows import WORKFLOW_PRESETS, WorkflowEngine
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
    "seed_database",
    "seed_database_sqlalchemy",
    "seed_from_sqlalchemy_models",
    "SeedReport",
    "load_tables_from_db",
    "schema_from_db",
    "schema_from_sqlalchemy",
]
