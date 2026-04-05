"""
Misata - AI-Powered Synthetic Data Engine

Generate realistic multi-table datasets from natural language descriptions.
Supports OpenAI, Groq, Gemini, and Ollama for intelligent schema generation.

Usage:
    from misata import DataSimulator, SchemaConfig

    # Or use the CLI:
    #   misata generate --story "A SaaS with 50k users..."
    
    # Or use pre-built templates:
    from misata.templates.library import load_template
    config = load_template("ecommerce")
"""

__version__ = "0.5.3"
__author__ = "Muhammed Rasin"

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
    SchemaValidationError,
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
