"""
Misata - AI-Powered Synthetic Data Engine

Generate realistic multi-table datasets from natural language descriptions.
Supports OpenAI, Groq, Gemini, and Ollama for intelligent schema generation.

Usage:
    from misata import DataSimulator, SchemaConfig
    
    # Or use the CLI:
    #   misata generate --story "A SaaS with 50k users..."
"""

__version__ = "0.1.0-beta"
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
from misata.noise import NoiseInjector, add_noise
from misata.customization import Customizer, ColumnOverride

__all__ = [
    # Core
    "Column",
    "Constraint",
    "Relationship",
    "ScenarioEvent",
    "SchemaConfig",
    "Table",
    "DataSimulator",
    # Extensibility
    "TextGenerator",
    # ML-ready features
    "NoiseInjector",
    "add_noise",
    "Customizer",
    "ColumnOverride",
]


