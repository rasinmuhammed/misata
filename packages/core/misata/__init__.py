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

__version__ = "0.3.0b0"
__author__ = "Muhammed Rasin"

from misata.schema import (
    Column,
    Constraint,
    Relationship,
    ScenarioEvent,
    SchemaConfig,
    Table,
)
from misata.simulator import DataSimulator
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
from misata.profiles import (
    DistributionProfile,
    get_profile,
    list_profiles,
    generate_with_profile,
)
from misata.generators.base import (
    ConditionalCategoricalGenerator,
    CONDITIONAL_LOOKUPS,
    create_conditional_generator,
)

__all__ = [
    # Core
    "Column",
    "Constraint",
    "Relationship",
    "ScenarioEvent",
    "SchemaConfig",
    "Table",
    "DataSimulator",
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
]

