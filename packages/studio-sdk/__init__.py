"""
MisataStudio SDK - Multi-agent pipeline and advanced generators

This package extends the core Misata library with advanced features:
- Multi-agent orchestration (LangGraph)
- Z3 constraint satisfaction
- SDV Copula generators
"""

from typing import TYPE_CHECKING

# Lazy imports for optional dependencies
if TYPE_CHECKING:
    from studio_sdk.agents.pipeline import (
        GenerationState,
        SchemaArchitectAgent,
        DomainExpertAgent,
        ValidationAgent,
        SimplePipeline,
        create_pipeline,
    )
    from studio_sdk.constraints.z3_solver import (
        ConstraintEngine,
        create_constraint_engine,
    )

__version__ = "0.1.0"

__all__ = [
    "GenerationState",
    "SchemaArchitectAgent",
    "DomainExpertAgent",
    "ValidationAgent",
    "SimplePipeline",
    "create_pipeline",
    "ConstraintEngine",
    "create_constraint_engine",
]


def get_pipeline():
    """Factory to get the agent pipeline."""
    from studio_sdk.agents.pipeline import create_pipeline
    return create_pipeline()


def get_constraint_engine():
    """Factory to get the constraint engine."""
    from studio_sdk.constraints.z3_solver import create_constraint_engine
    return create_constraint_engine()
