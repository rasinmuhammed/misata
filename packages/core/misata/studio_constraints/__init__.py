"""
MisataStudio Constraints - Advanced constraint satisfaction for studio features.

This module provides 100% business rule compliance using Z3 SMT solver.
These are optional studio features and don't affect the core pip package.
"""

try:
    from misata.studio_constraints.z3_solver import (
        ConstraintEngine,
        BusinessRule,
        add_common_business_rules,
        create_constraint_engine,
    )
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False
    ConstraintEngine = None
    BusinessRule = None
    add_common_business_rules = None
    create_constraint_engine = None

__all__ = [
    "ConstraintEngine",
    "BusinessRule",
    "add_common_business_rules",
    "create_constraint_engine",
    "Z3_AVAILABLE",
]
