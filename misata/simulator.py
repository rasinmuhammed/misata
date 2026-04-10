"""
Core DataSimulator class for high-performance synthetic data generation.

This module implements vectorized data generation with support for:
- Topological sorting of table dependencies
- Vectorized column generation (NO LOOPS)
- Referential integrity enforcement
- Scenario event application
- Pure Python text generation (no external dependencies)
"""

import warnings
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from misata.assets import AssetStore
from misata.engines import FactEngine
from misata.generators.base import TextGenerator as _FactoryTextGenerator  # Generator factory version
# Use the original generators.py TextGenerator which supports seed
from misata.generators_legacy import TextGenerator
from misata.noise import NoiseInjector
from misata.domain_priors import apply_domain_priors
from misata.planning import GenerationPlanner
from misata.realism import EntityCoherenceEngine, RealisticTextGenerator, apply_realism_rules
from misata.reporting import ReservoirTableSampler, build_generation_report_bundle
from misata.schema import Column, Relationship, ScenarioEvent, SchemaConfig
from misata.validation import StreamingDataValidator
from misata.vocabulary import SemanticVocabularyGenerator
from misata.workflows import WorkflowEngine


@dataclass
class GenerationResult:
    """Collected generation output with validation and advisory reports."""

    tables: Dict[str, pd.DataFrame]
    validation_report: Any
    reports: Dict[str, Any]
    tables_are_samples: bool = False
    table_row_counts: Dict[str, int] = field(default_factory=dict)


class DataSimulator:
    """
    High-performance synthetic data simulator.

    Generates synthetic datasets based on SchemaConfig definitions,
    using vectorized operations for maximum performance.

    Attributes:
        config: Schema configuration
        data: Generated dataframes (table_name -> DataFrame)
        text_gen: TextGenerator for entity generation
        rng: NumPy random generator for reproducibility
    """

    # Performance constants
    MAX_CONTEXT_ROWS = 50000  # Cap context storage for memory efficiency
    TEXT_POOL_SIZE = 10000    # Size of text value pools for vectorized sampling

    def __init__(self, config: SchemaConfig,
                 apply_semantic_fixes: bool = True, batch_size: int = 10_000,
                 smart_mode: bool = False, use_llm: bool = True):
        """
        Initialize the simulator.

        Args:
            config: Schema configuration defining tables, columns, and relationships
            apply_semantic_fixes: Auto-fix column types based on semantic patterns
            batch_size: Number of rows to generate per batch
            smart_mode: Enable LLM-powered context-aware value generation
            use_llm: If smart_mode is True, whether to use LLM (vs curated fallbacks)
        """
        self.config = config
        self.context: Dict[str, pd.DataFrame] = {}  # Lightweight context (IDs only)
        self.text_gen = TextGenerator(seed=config.seed)
        self.batch_size = batch_size
        self.smart_mode = smart_mode
        self.use_llm = use_llm
        self._smart_gen = None  # Lazy init
        self._unique_pools: Dict[str, np.ndarray] = {}  # Store pre-generated unique values
        self._unique_counters: Dict[str, int] = {}      # Track usage of unique pools
        self._sequence_counters: Dict[str, int] = {}    # Stable counters for primary keys
        self._smart_pools: Dict[str, np.ndarray] = {}   # Cache smart value pools
        self._text_pools: Dict[str, np.ndarray] = {}    # Cache text pools for vectorized sampling

        # Apply semantic inference to fix column types
        if apply_semantic_fixes:
            from misata.semantic import apply_semantic_inference
            self.config.columns = apply_semantic_inference(self.config.columns)

        # Set random seed if provided
        seed = config.seed if config.seed is not None else np.random.randint(0, 2**32 - 1)
        self.rng = np.random.default_rng(seed)
        np.random.seed(seed)  # For legacy numpy.random calls
        self.fact_engine = FactEngine(self.rng)
        self.noise_injector = NoiseInjector(seed)
        self.generation_plan = GenerationPlanner(self.config, self.rng).build()
        realism = getattr(self.config, "realism", None)
        asset_store = AssetStore(getattr(realism, "asset_store_dir", None))
        self.domain_capsule = SemanticVocabularyGenerator(asset_store=asset_store).build_capsule(self.config)
        self.realistic_text = RealisticTextGenerator(self.rng, capsule=self.domain_capsule)
        self.coherence_engine = EntityCoherenceEngine(self.rng, capsule=self.domain_capsule)
        self.workflow_engine = WorkflowEngine(self.rng)
    
    def _get_smart_gen(self):
        """Lazy initialize SmartValueGenerator."""
        if self._smart_gen is None:
            try:
                from misata.smart_values import SmartValueGenerator
                self._smart_gen = SmartValueGenerator()
            except Exception as exc:
                warnings.warn(f"Smart value generation unavailable: {exc}")
                self._smart_gen = None
        return self._smart_gen

    def _get_realism_config(self) -> Any:
        """Return the optional realism configuration."""
        return getattr(self.config, "realism", None)

    def _planned_row_count(self, table_name: str, fallback: int) -> int:
        """Resolve row count from the planning stage."""
        return self.generation_plan.row_count_for(table_name, fallback)

    def _text_strategy_for(self, table_name: str, column_name: str) -> Optional[str]:
        """Resolve planner-selected text strategy for a column."""
        realism = self._get_realism_config()
        if realism is None or realism.text_mode != "realistic_catalog":
            return None
        return self.generation_plan.text_strategy_for(table_name, column_name)

    def _workflow_for_table(self, table: Any) -> Optional[str]:
        """Return configured workflow preset for a table."""
        realism = self._get_realism_config()
        if realism is None or realism.workflow_mode == "off":
            return None
        workflow_preset = getattr(table, "workflow_preset", None)
        if not workflow_preset:
            return None
        return workflow_preset

    def topological_sort(self) -> List[str]:
        """
        Determine table generation order using topological sort.

        Parent tables must be generated before child tables to ensure
        referential integrity.

        Returns:
            List of table names in dependency order

        Raises:
            ValueError: If circular dependencies are detected
        """
        # Build adjacency list and in-degree map
        graph = defaultdict(list)
        in_degree = {table.name: 0 for table in self.config.tables}

        for rel in self.config.relationships:
            graph[rel.parent_table].append(rel.child_table)
            in_degree[rel.child_table] += 1

        # Kahn's algorithm for topological sort
        queue = deque([name for name, degree in in_degree.items() if degree == 0])
        sorted_tables = []

        while queue:
            table_name = queue.popleft()
            sorted_tables.append(table_name)

            for neighbor in graph[table_name]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Check for circular dependencies
        if len(sorted_tables) != len(self.config.tables):
            raise ValueError(
                f"Circular dependency detected in relationships. "
                f"Generated {len(sorted_tables)} / {len(self.config.tables)} tables."
            )

        return sorted_tables

    def _get_parent_ids(self, relationship: Relationship) -> np.ndarray:
        """
        Get valid parent IDs for foreign key generation, applying filters if defined.

        Args:
            relationship: Relationship definition

        Returns:
            Array of valid parent IDs
        """
        if relationship.parent_table not in self.context:
            return np.array([])

        parent_df = self.context[relationship.parent_table]
        if relationship.parent_key not in parent_df.columns:
             return np.array([])

        # Apply filters if defined (Logic Gap Fix)
        # Apply filters if defined (Logic Gap Fix)
        if relationship.filters:
            mask = np.ones(len(parent_df), dtype=bool)
            for col, val in relationship.filters.items():
                if col in parent_df.columns:
                    mask &= (parent_df[col] == val)
                else:
                    # If filter column missing from context, can't filter.
                    # Assume mismatch if column missing.
                    mask[:]=False

            valid_ids = parent_df.loc[mask, relationship.parent_key].values
        else:
            valid_ids = parent_df[relationship.parent_key].values

        return valid_ids

    def _collect_context_columns(self, table_name: str, df: pd.DataFrame) -> List[str]:
        """Return the columns that must be retained for future FK/date/depends_on lookups."""
        table = self.config.get_table(table_name)
        if table and table.is_reference:
            return list(df.columns)

        needed_cols = {"id"}

        for rel in self.config.relationships:
            if rel.parent_table == table_name:
                needed_cols.add(rel.parent_key)
                if rel.filters:
                    needed_cols.update(rel.filters.keys())

        for child_table in self.config.tables:
            child_cols = self.config.get_columns(child_table.name)
            for col in child_cols:
                if col.type == "date" and "relative_to" in col.distribution_params:
                    try:
                        parent_table, parent_col = col.distribution_params["relative_to"].split(".")
                    except ValueError:
                        continue
                    if parent_table == table_name:
                        needed_cols.add(parent_col)

                depends_on = col.distribution_params.get("depends_on")
                if not depends_on:
                    continue

                try:
                    fk_col, target_col = depends_on.split(".", 1)
                except ValueError:
                    continue

                for rel in self.config.relationships:
                    if (
                        rel.child_table == child_table.name
                        and rel.child_key == fk_col
                        and rel.parent_table == table_name
                    ):
                        needed_cols.add(target_col)

        return [column for column in needed_cols if column in df.columns]

    def generate_column(
        self,
        table_name: str,
        column: Column,
        size: int,
        table_data: Optional[pd.DataFrame] = None,
    ) -> np.ndarray:
        """
        Generate a single column using vectorized operations.

        Args:
            table_name: Name of the table being generated
            column: Column definition
            size: Number of values to generate
            table_data: Partially generated table (for columns that depend on other columns)

        Returns:
            Numpy array of generated values
        """
        # Apply domain priors as defaults — user-defined params always win.
        _domain = getattr(self.config, "domain", None) or getattr(
            getattr(self.config, "realism", None), "domain_hint", None
        )
        if _domain and column.type in ("int", "float"):
            params = apply_domain_priors(_domain, column.name, column.distribution_params)
        else:
            params = column.distribution_params

        # ========== CORRELATED COLUMN GENERATION ==========
        # If this column depends on another column's value, use conditional distribution
        if "depends_on" in params and table_data is not None:
            parent_col = params["depends_on"]
            mapping = params.get("mapping", {})

            parent_values = None
            if parent_col in table_data.columns:
                parent_values = table_data[parent_col].values
            elif "." in parent_col:
                # Handle foreign-key path lookup (e.g., "tenant_id.plan_type_id")
                try:
                    fk_col, target_col = parent_col.split(".", 1)
                    if fk_col in table_data.columns:
                        fk_values = table_data[fk_col].values
                        rel = next((r for r in self.config.relationships if r.child_table == table_name and r.child_key == fk_col), None)
                        if rel and rel.parent_table in self.context:
                            parent_df = self.context[rel.parent_table]
                            if target_col in parent_df.columns:
                                parent_map = parent_df.set_index(rel.parent_key)[target_col]
                                parent_values = parent_map.reindex(fk_values).values
                    else:
                        parent_values = None
                except Exception as e:
                    warnings.warn(f"Failed to resolve cross-table dependency {parent_col}: {e}")
            
            if parent_values is not None and mapping:
                
                # Check if it's numeric or categorical mapping
                first_key = next(iter(mapping.keys()))
                first_val = next(iter(mapping.values()))
                
                # Magic Reference Table Resolver: If mapping keys are strings but our values are ints (FKs)
                if isinstance(first_key, str):
                    for r_name, r_df in self.context.items():
                        r_table_config = self.config.get_table(r_name)
                        if r_table_config and r_table_config.is_reference and 'id' in r_df.columns:
                            str_cols = [c for c in r_df.columns if c != 'id']
                            if str_cols:
                                # Get the values
                                ref_vals = r_df[str_cols[0]].values
                                # If any key in mapping exists in the reference table values
                                if any(k in ref_vals for k in mapping.keys()):
                                    id_to_name = {str(k): v for k, v in r_df.set_index('id')[str_cols[0]].to_dict().items()}
                                    
                                    # Convert parent_values to strings if possible to match against id_to_name keys (which are also strings now)
                                    # Handle case where parent_values contains floats like 1.0 instead of 1
                                    def safe_str(v):
                                        return str(int(v)) if isinstance(v, (float, np.floating)) and not np.isnan(v) else str(v)
                                        
                                    parent_values = np.array([id_to_name.get(safe_str(val), val) for val in parent_values])
                                    break

                if isinstance(first_val, dict) and "mean" in first_val:
                    # Numeric conditional distribution (e.g., salary based on job_title)
                    # mapping = {"Intern": {"mean": 40000, "std": 5000}, "CTO": {"mean": 200000, "std": 30000}}
                    values = np.zeros(size)
                    for key, dist in mapping.items():
                        # Ensure types match for numpy comparison (e.g. key="1", parent_values=[1, 2])
                        compare_key = key
                        if len(parent_values) > 0:
                            target_type = type(parent_values[0])
                            try:
                                compare_key = target_type(key)
                            except (TypeError, ValueError):
                                pass
                        
                        mask = parent_values == compare_key
                        count = mask.sum()
                        if count > 0:
                            mean = dist.get("mean", 50000)
                            std = dist.get("std", mean * 0.1)
                            values[mask] = self.rng.normal(mean, std, count)
                    
                    # Handle values that didn't match any key (use default)
                    default = params.get("default", {"mean": 50000, "std": 10000})
                    
                    if len(parent_values) > 0:
                        target_type = type(parent_values[0])
                        safe_keys = [target_type(k) if isinstance(k, str) and k.isdigit() else k for k in mapping.keys()]
                        try:
                            safe_keys = [target_type(k) for k in mapping.keys()]
                        except (TypeError, ValueError):
                            pass
                    else:
                        safe_keys = list(mapping.keys())
                        
                    unmatched = ~np.isin(parent_values, safe_keys)
                    if unmatched.sum() > 0:
                        values[unmatched] = self.rng.normal(
                            default.get("mean", 50000), 
                            default.get("std", 10000), 
                            unmatched.sum()
                        )
                    return values
                    
                elif isinstance(first_val, list):
                    # Categorical conditional (e.g., state based on country)
                    # mapping = {"USA": ["CA", "TX", "NY"], "UK": ["England", "Scotland"]}
                    values = np.empty(size, dtype=object)
                    for key, choices in mapping.items():
                        mask = parent_values == key
                        count = mask.sum()
                        if count > 0:
                            values[mask] = self.rng.choice(choices, count)
                    
                    # Default for unmatched
                    default_choices = params.get("default", ["Unknown"])
                    unmatched = values == None  # noqa
                    if unmatched.sum() > 0:
                        values[unmatched] = self.rng.choice(default_choices, unmatched.sum())
                    return values
                    
                elif isinstance(first_val, (int, float)):
                    # Probability-based boolean (e.g., churn probability based on plan)
                    # mapping = {"free": 0.3, "pro": 0.1, "enterprise": 0.05}
                    values = np.zeros(size, dtype=bool)
                    for key, prob in mapping.items():
                        mask = parent_values == key
                        count = mask.sum()
                        if count > 0:
                            values[mask] = self.rng.random(count) < prob
                    return values

        # ========== STANDARD COLUMN GENERATION ==========
        
        # CATEGORICAL
        if column.type == "categorical":
            choices = params.get("choices", ["A", "B", "C"])
            probabilities = params.get("probabilities", None)

            # Ensure choices is a list
            if not isinstance(choices, list):
                choices = list(choices)

            # Zipf / power-law sampling: when no explicit probabilities are
            # provided and sampling="zipf", derive weights from a Zipf law so
            # the first choice dominates and the tail is long — just like real
            # categorical data (statuses, countries, product categories, …).
            sampling = params.get("sampling", "uniform")
            if probabilities is None and sampling == "zipf":
                exponent = float(params.get("zipf_exponent", 1.2))
                ranks = np.arange(1, len(choices) + 1, dtype=float)
                weights = 1.0 / np.power(ranks, exponent)
                probabilities = weights / weights.sum()

            if probabilities is not None:
                if len(probabilities) != len(choices):
                    probabilities = None
                else:
                    probabilities = np.array(probabilities, dtype=float)
                    prob_sum = probabilities.sum()
                    probabilities = probabilities / prob_sum if prob_sum > 0 else None

            values = self.rng.choice(choices, size=size, p=probabilities)
            return values

        # INTEGER
        elif column.type == "int":
            # Treat primary-key style columns as stable unique sequences.
            if column.name == "id":
                pool_key = f"{table_name}.{column.name}"
                start = params.get("min", 1)
                current = self._sequence_counters.get(pool_key, start)
                values = np.arange(current, current + size)
                self._sequence_counters[pool_key] = current + size
                return values.astype(int)

            # Handle unique integer generation
            if column.unique:
                pool_key = f"{table_name}.{column.name}"

                # Verify we aren't asking for more uniques than possible
                low = params.get("min", 0)
                high = params.get("max", 1000)
                total_needed_for_table = self.config.get_table(table_name).row_count

                if pool_key not in self._unique_pools:
                    # Check range capacity
                    if (high - low) < total_needed_for_table:
                        # Auto-expand range to fix user error (common in tests/small ranges)
                        warnings.warn(f"Range {high-low} too small for unique column {column.name} (needs {total_needed_for_table}). Extending max.")
                        high = low + total_needed_for_table + 100

                    # Generate full permutation
                    pool = np.arange(low, high)
                    self.rng.shuffle(pool)
                    self._unique_pools[pool_key] = pool
                    self._unique_counters[pool_key] = 0

                # Fetch chunk
                current_idx = self._unique_counters[pool_key]
                if current_idx + size > len(self._unique_pools[pool_key]):
                     raise ValueError(f"Exhausted unique values for {column.name}")

                values = self._unique_pools[pool_key][current_idx : current_idx + size]
                self._unique_counters[pool_key] += size
                return values.astype(int)

            distribution = params.get("distribution", "normal")

            # Handle categorical distribution (fixed choices)
            if distribution == "categorical" or "choices" in params:
                choices = params.get("choices", [1, 2, 3, 4, 5])
                probabilities = params.get("probabilities", None)
                if probabilities is not None:
                    probabilities = np.array(probabilities)
                    probabilities = probabilities / probabilities.sum()
                values = self.rng.choice(choices, size=size, p=probabilities)
                return np.array(values).astype(int)
            elif distribution == "normal":
                mean = params.get("mean", 100)
                std = params.get("std", 20)
                values = self.rng.normal(mean, std, size=size).astype(int)
            elif distribution in ("lognormal", "log_normal"):
                # mu/sigma are in log-space; alternatively accept mean/std and convert
                if "mu" in params or "sigma" in params:
                    mu = params.get("mu", 4.5)
                    sigma = params.get("sigma", 0.8)
                else:
                    mean = float(params.get("mean", 100))
                    std = float(params.get("std", 50))
                    sigma = np.sqrt(np.log(1 + (std / mean) ** 2))
                    mu = np.log(mean) - 0.5 * sigma ** 2
                values = self.rng.lognormal(mu, sigma, size=size).astype(int)
            elif distribution in ("power_law", "pareto"):
                alpha = float(params.get("alpha", 1.5))
                scale = float(params.get("scale", params.get("min", 1)))
                # Pareto: X = scale / U^(1/alpha), U ~ Uniform(0,1)
                u = self.rng.uniform(0, 1, size=size)
                values = (scale / np.power(u, 1.0 / alpha)).astype(int)
            elif distribution == "uniform":
                low = params.get("min", 0)
                high = params.get("max", 1000)
                values = self.rng.integers(low, high, size=size)
            elif distribution == "poisson":
                lam = params.get("lambda", 10)
                values = self.rng.poisson(lam, size=size)
            else:
                low = params.get("min", 0)
                high = params.get("max", 1000)
                values = self.rng.integers(low, high, size=size)

            if "min" in params:
                values = np.maximum(values, params["min"])
            if "max" in params:
                values = np.minimum(values, params["max"])

            return values

        # FLOAT
        elif column.type == "float":
            distribution = params.get("distribution", "normal")

            if distribution == "categorical" or "choices" in params:
                choices = params.get("choices", [1.0, 2.0, 3.0])
                probabilities = params.get("probabilities", None)
                if probabilities is not None:
                    probabilities = np.array(probabilities)
                    probabilities = probabilities / probabilities.sum()
                values = self.rng.choice(choices, size=size, p=probabilities)
                return np.array(values).astype(float)
            elif distribution == "normal":
                mean = params.get("mean", 100.0)
                std = params.get("std", 20.0)
                values = self.rng.normal(mean, std, size=size)
            elif distribution in ("lognormal", "log_normal"):
                if "mu" in params or "sigma" in params:
                    mu = float(params.get("mu", 4.5))
                    sigma = float(params.get("sigma", 0.8))
                else:
                    mean = float(params.get("mean", 100.0))
                    std = float(params.get("std", 50.0))
                    sigma = np.sqrt(np.log(1 + (std / mean) ** 2))
                    mu = np.log(mean) - 0.5 * sigma ** 2
                values = self.rng.lognormal(mu, sigma, size=size)
            elif distribution in ("power_law", "pareto"):
                alpha = float(params.get("alpha", 1.5))
                scale = float(params.get("scale", params.get("min", 1.0)))
                u = self.rng.uniform(0, 1, size=size)
                values = scale / np.power(u, 1.0 / alpha)
            elif distribution == "uniform":
                low = params.get("min", 0.0)
                high = params.get("max", 1000.0)
                values = self.rng.uniform(low, high, size=size)
            elif distribution == "exponential":
                scale = params.get("scale", 1.0)
                values = self.rng.exponential(scale, size=size)
            elif distribution == "beta":
                a = float(params.get("a", 2.0))
                b = float(params.get("b", 5.0))
                low = float(params.get("min", 0.0))
                high = float(params.get("max", 1.0))
                values = self.rng.beta(a, b, size=size) * (high - low) + low
            else:
                low = params.get("min", 0.0)
                high = params.get("max", 1000.0)
                values = self.rng.uniform(low, high, size=size)

            if "min" in params:
                values = np.maximum(values, params["min"])
            if "max" in params:
                values = np.minimum(values, params["max"])
            if "decimals" in params:
                values = np.round(values, params["decimals"])

            return values

        # DATE
        elif column.type == "date":
            # Parent-Relative Date Generation (Time Travel Fix)
            if "relative_to" in params:
                # Format: "parent_table.column_name"
                try:
                    rel_table, rel_col = params["relative_to"].split(".")
                    # Find relationship
                    relationship = None
                    for rel in self.config.relationships:
                        if rel.child_table == table_name and rel.parent_table == rel_table:
                            relationship = rel
                            break

                    if relationship and table_data is not None and relationship.child_key in table_data.columns:
                        # Vectorized lookup!
                        child_fk_values = table_data[relationship.child_key].values
                        parent_df = self.context.get(rel_table)

                        if parent_df is not None and rel_col in parent_df.columns:
                            # Map FK to Parent Date
                            # Create a lookup series/dict
                            parent_date_map = parent_df.set_index(relationship.parent_key)[rel_col]
                            parent_dates = parent_date_map.reindex(child_fk_values).values

                            # Generate deltas
                            min_delta = params.get("min_delta_days", 0)
                            max_delta = params.get("max_delta_days", 365)
                            deltas = self.rng.integers(min_delta, max_delta, size=size)
                            deltas_ns = deltas.astype('timedelta64[D]')

                            # Child Date = Parent Date + Delta
                            values = parent_dates + deltas_ns
                            return values
                except Exception as e:
                    warnings.warn(f"Failed to generate relative date: {e}. Falling back to random range.")

            start = pd.to_datetime(params.get("start", "2020-01-01"))
            end = pd.to_datetime(params.get("end", "2024-12-31"))

            start_int = start.value
            end_int = end.value
            random_ints = self.rng.integers(start_int, end_int, size=size)
            values = pd.to_datetime(random_ints)

            return values

        # FOREIGN KEY
        elif column.type == "foreign_key":
            relationship = None
            for rel in self.config.relationships:
                if rel.child_table == table_name and rel.child_key == column.name:
                    relationship = rel
                    break

            if relationship is None:
                warnings.warn(
                    f"No relationship defined for foreign key '{column.name}' "
                    f"in table '{table_name}'. Generating sequential IDs instead."
                )
                values = self.rng.integers(1, max(size // 10, 100), size=size)
                return values

            # Check context instead of data
            if relationship.parent_table not in self.context:
                warnings.warn(
                    f"Parent table '{relationship.parent_table}' not yet generated for "
                    f"foreign key '{column.name}'. Generating sequential IDs instead."
                )
                values = self.rng.integers(1, max(size // 10, 100), size=size)
                return values

            parent_ids = self._get_parent_ids(relationship)

            if len(parent_ids) == 0:
                warnings.warn(
                    f"Parent table '{relationship.parent_table}' has no valid IDs in context (after filters). "
                    f"Generating sequential IDs for foreign key '{column.name}'."
                )
                values = self.rng.integers(1, max(size // 10, 100), size=size)
                return values

            sampling = params.get("sampling", "uniform")
            if sampling == "pareto":
                alpha = max(float(params.get("alpha", 1.5)), 0.1)
                weights = self.rng.pareto(alpha, len(parent_ids)) + 1.0
                probabilities = weights / weights.sum()
                values = self.rng.choice(parent_ids, size=size, p=probabilities)
            else:
                values = self.rng.choice(parent_ids, size=size)
            return values

        # TEXT
        elif column.type == "text":
            text_type = params.get("text_type", "sentence")
            text_strategy = self._text_strategy_for(table_name, column.name)
            
            # Smart value generation - check for domain-specific content
            smart_generate = params.get("smart_generate", False) or self.smart_mode
            if smart_generate:
                smart_gen = self._get_smart_gen()
                if smart_gen:
                    # Check for explicit domain hint or auto-detect
                    domain_hint = params.get("domain_hint")
                    context = params.get("context", "")
                    
                    # Create cache key for this column's pool
                    pool_key = f"{table_name}.{column.name}"
                    
                    if pool_key not in self._smart_pools:
                        pool = smart_gen.get_pool(
                            column_name=column.name,
                            table_name=table_name,
                            domain_hint=domain_hint,
                            context=context,
                            size=100,
                            use_llm=self.use_llm,
                        )
                        if pool:
                            self._smart_pools[pool_key] = np.array(pool)
                    
                    if pool_key in self._smart_pools:
                        pool = self._smart_pools[pool_key]
                        values = self.rng.choice(pool, size=size)
                        return values

            if text_strategy:
                return self.realistic_text.generate(
                    column_name=column.name,
                    table_name=table_name,
                    size=size,
                    semantic_type=text_strategy,
                    table_data=table_data,
                )

            if text_type == "name":
                pool_key = "text_name"
                if pool_key not in self._text_pools:
                    pool_size = min(size, self.TEXT_POOL_SIZE)
                    self._text_pools[pool_key] = np.array([self.text_gen.name() for _ in range(pool_size)])
                values = self.rng.choice(self._text_pools[pool_key], size=size)
            elif text_type == "email":
                pool_key = "text_email"
                if pool_key not in self._text_pools:
                    pool_size = min(size, self.TEXT_POOL_SIZE)
                    self._text_pools[pool_key] = np.array([self.text_gen.email() for _ in range(pool_size)])
                values = self.rng.choice(self._text_pools[pool_key], size=size)
            elif text_type == "company":
                pool_key = "text_company"
                if pool_key not in self._text_pools:
                    pool_size = min(size, self.TEXT_POOL_SIZE)
                    self._text_pools[pool_key] = np.array([self.text_gen.company() for _ in range(pool_size)])
                values = self.rng.choice(self._text_pools[pool_key], size=size)
            elif text_type == "sentence":
                pool_key = "text_sentence"
                if pool_key not in self._text_pools:
                    pool_size = min(size, self.TEXT_POOL_SIZE)
                    self._text_pools[pool_key] = np.array([self.text_gen.sentence() for _ in range(pool_size)])
                values = self.rng.choice(self._text_pools[pool_key], size=size)
            elif text_type == "word":
                pool_key = "text_word"
                if pool_key not in self._text_pools:
                    pool_size = min(size, self.TEXT_POOL_SIZE)
                    self._text_pools[pool_key] = np.array([self.text_gen.word() for _ in range(pool_size)])
                values = self.rng.choice(self._text_pools[pool_key], size=size)
            elif text_type == "address":
                pool_key = "text_address"
                if pool_key not in self._text_pools:
                    pool_size = min(size, self.TEXT_POOL_SIZE)
                    self._text_pools[pool_key] = np.array([self.text_gen.full_address() for _ in range(pool_size)])
                values = self.rng.choice(self._text_pools[pool_key], size=size)
            elif text_type == "phone":
                pool_key = "text_phone"
                if pool_key not in self._text_pools:
                    pool_size = min(size, self.TEXT_POOL_SIZE)
                    self._text_pools[pool_key] = np.array([self.text_gen.phone_number() for _ in range(pool_size)])
                values = self.rng.choice(self._text_pools[pool_key], size=size)
            elif text_type == "url":
                pool_key = "text_url"
                if pool_key not in self._text_pools:
                    pool_size = min(size, self.TEXT_POOL_SIZE)
                    self._text_pools[pool_key] = np.array([self.text_gen.url() for _ in range(pool_size)])
                values = self.rng.choice(self._text_pools[pool_key], size=size)
            else:
                pool_key = "text_sentence"
                if pool_key not in self._text_pools:
                    pool_size = min(size, self.TEXT_POOL_SIZE)
                    self._text_pools[pool_key] = np.array([self.text_gen.sentence() for _ in range(pool_size)])
                values = self.rng.choice(self._text_pools[pool_key], size=size)

            return values

        # BOOLEAN
        elif column.type == "boolean":
            probability = params.get("probability", 0.5)
            values = self.rng.random(size) < probability
            return values

        # TIME
        elif column.type == "time":
            # Generate random times as HH:MM:SS strings
            start_hour = params.get("start_hour", 0)
            end_hour = params.get("end_hour", 24)
            hours = self.rng.integers(start_hour, end_hour, size=size)
            minutes = self.rng.integers(0, 60, size=size)
            seconds = self.rng.integers(0, 60, size=size)
            values = np.array([f"{h:02d}:{m:02d}:{s:02d}" for h, m, s in zip(hours, minutes, seconds)])
            return values

        # DATETIME
        elif column.type == "datetime":
            # Generate random datetimes within a range
            start = pd.to_datetime(params.get("start", "2020-01-01"))
            end = pd.to_datetime(params.get("end", "2024-12-31"))
            start_int = start.value
            end_int = end.value
            random_ints = self.rng.integers(start_int, end_int, size=size)
            values = pd.to_datetime(random_ints)
            return values

        else:
            raise ValueError(f"Unknown column type: {column.type}")

    def apply_event(self, df: pd.DataFrame, event: ScenarioEvent) -> pd.DataFrame:
        """Apply a scenario event to modify data based on conditions."""
        try:
            mask = df.eval(event.condition)
        except Exception as e:
            warnings.warn(f"Failed to evaluate condition '{event.condition}' for event '{event.name}': {e}")
            return df

        if event.modifier_type == "multiply":
            df.loc[mask, event.column] *= event.modifier_value
        elif event.modifier_type == "add":
            df.loc[mask, event.column] += event.modifier_value
        elif event.modifier_type == "set":
            df.loc[mask, event.column] = event.modifier_value
        elif event.modifier_type == "function":
            warnings.warn(f"Function modifiers not yet implemented for event '{event.name}'")

        return df

    def propagate_event_cascade(
        self,
        all_tables: Dict[str, pd.DataFrame],
        event: ScenarioEvent,
    ) -> None:
        """Cascade an event's affected parent rows into child tables via FK relationships.

        After ``event`` is applied on ``event.table``, this method looks up the
        FK edges from that table to its children and applies the per-child column
        overrides declared in ``event.propagate_to``.

        ``all_tables`` is mutated in-place.

        Example
        -------
        A churn event sets ``users.churned = True`` for some rows.  With::

            propagate_to={"subscriptions": {"status": "cancelled"}}

        this method finds all ``subscriptions`` rows whose ``user_id`` is in the
        set of churned user IDs and sets their ``status`` to ``"cancelled"``.
        """
        if not event.propagate_to:
            return

        parent_df = all_tables.get(event.table)
        if parent_df is None:
            return

        # Identify affected parent rows
        try:
            affected_mask = parent_df.eval(event.condition)
        except Exception as e:
            warnings.warn(
                f"Cascade failed: could not evaluate condition '{event.condition}' "
                f"on parent table '{event.table}': {e}"
            )
            return

        for child_table_name, column_overrides in event.propagate_to.items():
            child_df = all_tables.get(child_table_name)
            if child_df is None:
                warnings.warn(
                    f"Cascade skipped: child table '{child_table_name}' not found "
                    f"(event '{event.name}'). Was it generated?"
                )
                continue

            # Find the FK relationship linking parent → child
            rel = next(
                (
                    r for r in self.config.relationships
                    if r.parent_table == event.table and r.child_table == child_table_name
                ),
                None,
            )
            if rel is None:
                warnings.warn(
                    f"Cascade skipped: no relationship from '{event.table}' to "
                    f"'{child_table_name}' found (event '{event.name}')."
                )
                continue

            affected_parent_ids = set(parent_df.loc[affected_mask, rel.parent_key].dropna())
            child_mask = child_df[rel.child_key].isin(affected_parent_ids)

            if not child_mask.any():
                continue

            for col, value in column_overrides.items():
                if col not in child_df.columns:
                    warnings.warn(
                        f"Cascade skipped column '{col}': not present in '{child_table_name}'."
                    )
                    continue
                all_tables[child_table_name].loc[child_mask, col] = value

    def _get_exact_outcome_curves(self, table_name: str) -> List[Any]:
        """Return exact target curves that should be generated top-down."""
        if not getattr(self.config, "outcome_curves", None):
            return []

        exact_curves = []
        for curve in self.config.outcome_curves:
            if getattr(curve, "table", None) != table_name:
                continue
            if self.fact_engine.curve_has_exact_targets(curve):
                exact_curves.append(curve)
        return exact_curves

    def _generate_fact_table(
        self,
        table_name: str,
        table: Any,
        columns: List[Column],
        curves: List[Any],
    ) -> Optional[pd.DataFrame]:
        """Generate a constrained fact table from exact period targets."""
        planned_row_count = self._planned_row_count(table_name, table.row_count)
        plan_table = table.model_copy(update={"row_count": planned_row_count}) if hasattr(table, "model_copy") else table
        plan = self.fact_engine.build_plan(plan_table, columns, curves)
        if plan is None:
            warnings.warn(
                f"Exact outcome curves for table '{table_name}' are incompatible. "
                "Falling back to legacy row-wise generation."
            )
            return None

        column_map = {column.name: column for column in columns}
        df_batch = self.fact_engine.generate(plan, column_map)

        for column in columns:
            if column.name in df_batch.columns:
                continue
            values = self.generate_column(table_name, column, len(df_batch), df_batch)
            df_batch[column.name] = values

        df_batch = self._apply_formula_columns(df_batch, table_name)
        df_batch = self._fix_correlated_columns(df_batch, table_name)

        constrained_columns = plan.constrained_columns
        table_events = [event for event in self.config.events if event.table == table_name]
        for event in table_events:
            if event.column in constrained_columns:
                warnings.warn(
                    f"Skipping event '{event.name}' on constrained column "
                    f"'{table_name}.{event.column}' to preserve exact targets."
                )
                continue
            df_batch = self.apply_event(df_batch, event)

        df_batch = self.apply_constraints(df_batch, table)
        df_batch = self.fact_engine.rebalance(df_batch, plan, column_map)
        df_batch = self.fact_engine.drop_internal_columns(df_batch)

        ordered_columns = [column.name for column in columns if column.name in df_batch.columns]
        remaining_columns = [col for col in df_batch.columns if col not in ordered_columns]
        return df_batch[ordered_columns + remaining_columns]

    def _get_formula_columns(self, table_name: str) -> set[str]:
        """Return derived formula columns that should stay protected."""
        return {
            column.name
            for column in self.config.get_columns(table_name)
            if column.distribution_params.get("formula")
        }

    def _get_protected_generation_columns(self, table_name: str, table: Any) -> set[str]:
        """Columns that coherence/workflows should avoid mutating."""
        protected = set()
        for relationship in self.config.relationships:
            if relationship.parent_table == table_name:
                protected.add(relationship.parent_key)
            if relationship.child_table == table_name:
                protected.add(relationship.child_key)

        for curve in getattr(self.config, "outcome_curves", []):
            if getattr(curve, "table", None) != table_name:
                continue
            protected.add(curve.column)
            protected.add(curve.time_column)

        for constraint in getattr(table, "constraints", []):
            protected.update(constraint.group_by)
            if constraint.column:
                protected.add(constraint.column)

        protected.update(self._get_formula_columns(table_name))
        return protected

    def _get_protected_noise_columns(self, table_name: str, table: Any) -> set[str]:
        """Columns that should not be mutated in analytics-safe noise mode."""
        protected = self._get_protected_generation_columns(table_name, table)

        for column in self.config.get_columns(table_name):
            if column.name == "id" or column.type == "foreign_key" or column.unique:
                protected.add(column.name)

        return protected

    def _resolve_noise_column_list(
        self,
        df: pd.DataFrame,
        configured_columns: Optional[List[str]],
        *,
        protected_columns: set[str],
        kind: str,
        force_resolution: bool = False,
    ) -> Optional[List[str]]:
        """Resolve explicit or default noise columns while honoring protections."""
        if configured_columns is not None:
            return [col for col in configured_columns if col in df.columns and col not in protected_columns]
        if not protected_columns and not force_resolution:
            return None

        if kind == "outlier":
            candidate_columns = df.select_dtypes(include=[np.number]).columns.tolist()
        elif kind == "typo":
            candidate_columns = df.select_dtypes(include=["object", "string"]).columns.tolist()
            candidate_columns = [
                col for col in candidate_columns
                if "id" not in col.lower() and "email" not in col.lower()
            ]
        else:
            candidate_columns = list(df.columns)

        return [col for col in candidate_columns if col not in protected_columns]

    def _resolve_noise_config(
        self,
        table_name: str,
        table: Any,
        df: pd.DataFrame,
    ) -> Optional[Dict[str, Any]]:
        """Build a safe runtime noise config for a specific table batch."""
        if not self.config.noise_config:
            return None

        raw_config = (
            self.config.noise_config.model_dump()
            if hasattr(self.config.noise_config, "model_dump")
            else dict(self.config.noise_config)
        )
        mode = raw_config.get("mode", "custom")
        if mode == "off":
            return None

        protected_columns = set(raw_config.get("protected_columns", []))
        if mode == "analytics_safe":
            protected_columns.update(self._get_protected_noise_columns(table_name, table))
            duplicate_rate = 0.0
        else:
            duplicate_rate = raw_config.get("duplicate_rate", 0.0)

        resolved = {
            "null_rate": raw_config.get("null_rate", 0.0),
            "outlier_rate": raw_config.get("outlier_rate", 0.0),
            "typo_rate": raw_config.get("typo_rate", 0.0),
            "duplicate_rate": duplicate_rate,
            "exact_duplicates": raw_config.get("exact_duplicates", True),
            "null_columns": self._resolve_noise_column_list(
                df,
                raw_config.get("null_columns"),
                protected_columns=protected_columns,
                kind="null",
                force_resolution=(mode == "analytics_safe"),
            ),
            "outlier_columns": self._resolve_noise_column_list(
                df,
                raw_config.get("outlier_columns"),
                protected_columns=protected_columns,
                kind="outlier",
                force_resolution=(mode == "analytics_safe"),
            ),
            "typo_columns": self._resolve_noise_column_list(
                df,
                raw_config.get("typo_columns"),
                protected_columns=protected_columns,
                kind="typo",
                force_resolution=(mode == "analytics_safe"),
            ),
        }

        if not any(
            resolved.get(key, 0) > 0
            for key in ["null_rate", "outlier_rate", "typo_rate", "duplicate_rate"]
        ):
            return None
        return resolved

    def _apply_configured_noise(
        self,
        df: pd.DataFrame,
        table_name: str,
        table: Any,
    ) -> pd.DataFrame:
        """Apply optional post-generation noise without contaminating context."""
        noise_config = self._resolve_noise_config(table_name, table, df)
        if not noise_config:
            return df
        return self.noise_injector.apply(df, noise_config)

    def _update_context(self, table_name: str, df: pd.DataFrame) -> None:
        """
        Update the context with key columns from the generated batch.

        Smart Context Logic:
        1. Store Primary Key ('id')
        2. Store columns used as foreign keys by children (parent_key)
        3. Store columns used in Relationship filters (Logic Gap fix)
        4. Store columns used in 'relative_to' date constraints (Time Travel fix)
        """
        cols_to_store = self._collect_context_columns(table_name, df)
        if not cols_to_store:
            return

        ctx_df = df[cols_to_store].copy()

        if table_name not in self.context:
            if len(ctx_df) > self.MAX_CONTEXT_ROWS:
                warnings.warn(
                    f"Table '{table_name}' has {len(ctx_df):,} rows but context is capped at "
                    f"{self.MAX_CONTEXT_ROWS:,}. Foreign keys referencing this table will only "
                    f"sample from the first {self.MAX_CONTEXT_ROWS:,} rows.",
                    UserWarning,
                )
                ctx_df = ctx_df.sample(n=self.MAX_CONTEXT_ROWS, random_state=self.config.seed)
            self.context[table_name] = ctx_df
        else:
            current_len = len(self.context[table_name])
            if current_len >= self.MAX_CONTEXT_ROWS:
                return

            remaining_space = self.MAX_CONTEXT_ROWS - current_len
            rows_to_add = ctx_df.iloc[:remaining_space]
            self.context[table_name] = pd.concat(
                [self.context[table_name], rows_to_add],
                ignore_index=True,
            )

    def generate_batches(self, table_name: str) -> Any:
        """
        Yield batches of generated data for a table.

        Args:
            table_name: Name of the table to generate

        Yields:
            DataFrame batch
        """
        table = self.config.get_table(table_name)
        if table is None:
            raise ValueError(f"Table '{table_name}' not found in schema")

        # Reference table with inline data - yield as single batch
        if table.is_reference and table.inline_data:
            df = pd.DataFrame(table.inline_data)
            self._update_context(table_name, df)
            yield df
            return

        columns = self.config.get_columns(table_name)
        total_rows = self._planned_row_count(table_name, table.row_count)

        exact_curves = self._get_exact_outcome_curves(table_name)
        if exact_curves:
            fact_df = self._generate_fact_table(table_name, table, columns, exact_curves)
            if fact_df is not None:
                self._update_context(table_name, fact_df)
                output_df = self._apply_configured_noise(fact_df.copy(), table_name, table)
                yield output_df
                return

        rows_generated = 0

        while rows_generated < total_rows:
            batch_size = min(self.batch_size, total_rows - rows_generated)

            # Generate batch
            data = {}
            df_batch = pd.DataFrame()

            for column in columns:
                values = self.generate_column(table_name, column, batch_size, df_batch)
                data[column.name] = values
                df_batch[column.name] = values

            df_batch = pd.DataFrame(data)

            # Apply formulas
            df_batch = self._apply_formula_columns(df_batch, table_name)

            # Post-process
            df_batch = self._fix_correlated_columns(df_batch, table_name)

            # Apply events
            table_events = [e for e in self.config.events if e.table == table_name]
            for event in table_events:
                df_batch = self.apply_event(df_batch, event)

            # Apply business rule constraints
            df_batch = self.apply_constraints(df_batch, table)
            
            # Apply outcome curves (Trends/Seasonality)
            df_batch = self.apply_outcome_curves(df_batch, table_name)

            # Update context for future batches/tables
            self._update_context(table_name, df_batch)
            output_df = self._apply_configured_noise(df_batch.copy(), table_name, table)
            yield output_df

            rows_generated += batch_size

    def apply_constraints(self, df: pd.DataFrame, table: Any) -> pd.DataFrame:
        """
        Apply business rule constraints to generated data.

        Args:
            df: DataFrame batch to constrain
            table: Table definition containing constraints

        Returns:
            Constrained DataFrame
        """
        if not hasattr(table, 'constraints') or not table.constraints:
            return df

        for constraint in table.constraints:
            df = self._apply_single_constraint(df, constraint)

        return df

    def apply_outcome_curves(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """
        Apply temporal outcome curves to force data to match trends/seasonality.
        
        This overrides the base distribution with the high-level constraints
        defined in the prompt (e.g. "seasonal peaks", "upward trend").
        """
        if not hasattr(self.config, 'outcome_curves') or not self.config.outcome_curves:
            return df
        
        # Filter curves for this table - handle both dict and Pydantic object
        curves = []
        for c in self.config.outcome_curves:
            # Get table name from curve (handle both dict and object)
            c_table = c.table if hasattr(c, 'table') else c.get('table')
            if c_table == table_name:
                curves.append(c)

        for curve in curves:
            try:
                # Access attributes (Pydantic) or dict keys
                target_col = curve.column if hasattr(curve, 'column') else curve['column']
                time_col = curve.time_column if hasattr(curve, 'time_column') else curve['time_column']
                points = curve.curve_points if hasattr(curve, 'curve_points') else curve.get('curve_points', [])
                pattern_type = curve.pattern_type if hasattr(curve, 'pattern_type') else curve.get('pattern_type', 'seasonal')
                
                if target_col not in df.columns:
                    continue
                if time_col not in df.columns:
                    continue
                    
                if not points:
                    continue
                
                # Convert Pydantic CurvePoint objects to dicts if needed
                point_dicts = []
                for p in points:
                    p_dict = {}
                    if hasattr(p, 'month'):
                        p_dict = {'month': p.month, 'relative_value': p.relative_value}
                    elif isinstance(p, dict):
                        p_dict = p.copy()
                    
                    # Normalize X axis to 'month'
                    x_val = p_dict.get('month', p_dict.get('day', p_dict.get('x', 1)))
                    if isinstance(x_val, str) and '-' in x_val:
                        try:
                            x_val = pd.to_datetime(x_val).month
                        except Exception:
                            x_val = 1
                    p_dict['month'] = pd.to_numeric(x_val, errors='coerce')
                    
                    # Normalize Y axis to 'relative_value'
                    y_val = p_dict.get('relative_value', p_dict.get('target_value', p_dict.get('value', 1.0)))
                    p_dict['relative_value'] = pd.to_numeric(y_val, errors='coerce')
                    
                    if not pd.isna(p_dict['month']) and not pd.isna(p_dict['relative_value']):
                        point_dicts.append(p_dict)
                        
                points = point_dicts
                
                # Sort points by order (month or progress)
                points.sort(key=lambda x: x.get('month', 1))

                # Extract time components
                if not pd.api.types.is_datetime64_any_dtype(df[time_col]):
                    timestamps = pd.to_datetime(df[time_col], errors='coerce')
                else:
                    timestamps = df[time_col]

                if target_col == time_col or pd.api.types.is_datetime64_any_dtype(df[target_col]):
                    df[target_col] = self._apply_time_density_curve(
                        timestamps=timestamps,
                        points=points,
                        pattern_type=pattern_type,
                        time_unit=getattr(curve, "time_unit", "month"),
                        params=self._get_column_params(table_name, time_col),
                    )
                    continue

                # Initialize factors
                row_factors = np.ones(len(df))

                # STRATEGY 1: SEASONAL (Cyclic 1-12)
                if pattern_type in ['seasonal', 'cyclic']:
                    months = timestamps.dt.month
                    scaling_factors = np.ones(13) # Index 1-12
                    
                    x_known = np.array([p['month'] for p in points])
                    y_known = np.array([p['relative_value'] for p in points])
                    
                    for m in range(1, 13):
                        if m < x_known.min():
                            scaling_factors[m] = y_known[0]
                        elif m > x_known.max():
                            scaling_factors[m] = y_known[-1]
                        else:
                            scaling_factors[m] = np.interp(m, x_known, y_known)
                    
                    row_factors = scaling_factors[months.fillna(1).astype(int).values]

                # STRATEGY 2: GROWTH/TREND (Linear over absolute time)
                elif pattern_type in ['growth', 'trend', 'increase', 'decline']:
                    # Normalize time to 0.0 - 1.0 range
                    t_min = timestamps.min()
                    t_max = timestamps.max()
                    
                    if t_min == t_max:
                        row_factors = np.ones(len(df))
                    else:
                        # Convert to numeric (timestamps)
                        t_numerics = timestamps.astype(np.int64)
                        t_start = t_numerics.min()
                        t_range = t_numerics.max() - t_start
                        
                        # Normalize 0.0 to 1.0
                        t_norm = (t_numerics - t_start) / t_range
                        
                        # Map points (assume points are mapped 1-12 or 0.0-1.0?)
                        # The LLM outputs "month" 1-12 usually. Let's map 1=Start, 12=End?
                        # Or safer: interpolating 1-12 across the whole range.
                        
                        x_known = np.array([p['month'] for p in points])
                        y_known = np.array([p['relative_value'] for p in points])
                        
                        # Normalize x_known to 0.0-1.0 range (assuming 1..12 scale from LLM)
                        # If LLM says Month 1 to 12, we treat 1 as 0.0 and 12 as 1.0
                        x_known_norm = (x_known - 1) / 11.0 # 1->0, 12->1
                        
                        # Interpolate
                        row_factors = np.interp(t_norm, x_known_norm, y_known)

                # Apply!
                df[target_col] = df[target_col] * row_factors
                
            except Exception as e:
                warnings.warn(f"Failed to apply outcome curve for {table_name}: {e}")
                continue
                
        return df

    def _get_column_params(self, table_name: str, column_name: str) -> Dict[str, Any]:
        """Return distribution params for a column if present."""
        for column in self.config.get_columns(table_name):
            if column.name == column_name:
                return dict(column.distribution_params)
        return {}

    def _apply_time_density_curve(
        self,
        *,
        timestamps: pd.Series,
        points: List[Dict[str, Any]],
        pattern_type: str,
        time_unit: str,
        params: Dict[str, Any],
    ) -> pd.Series:
        """Resample timestamps by weighted time density instead of multiplying datetimes."""
        clean_timestamps = pd.to_datetime(timestamps, errors="coerce")
        if clean_timestamps.isna().all() or not points:
            return clean_timestamps

        start = pd.to_datetime(params.get("start"), errors="coerce")
        end = pd.to_datetime(params.get("end"), errors="coerce")
        if pd.isna(start):
            start = clean_timestamps.min()
        if pd.isna(end):
            end = clean_timestamps.max()
        if pd.isna(start) or pd.isna(end) or start >= end:
            return clean_timestamps

        if time_unit != "month":
            return clean_timestamps

        windows = list(pd.date_range(start.normalize().replace(day=1), end.normalize().replace(day=1), freq="MS"))
        if not windows:
            return clean_timestamps

        weights = self._resolve_time_density_weights(windows, points, pattern_type)
        if weights.sum() <= 0:
            return clean_timestamps
        probabilities = weights / weights.sum()

        counts = self.rng.multinomial(len(clean_timestamps), probabilities)
        sampled: List[pd.Timestamp] = []
        for window_start, count in zip(windows, counts):
            if count <= 0:
                continue
            next_window = window_start + pd.offsets.MonthBegin(1)
            bucket_start = max(window_start, start)
            bucket_end = min(next_window, end + pd.Timedelta(days=1))
            if bucket_start >= bucket_end:
                continue
            start_ns = bucket_start.value
            end_ns = bucket_end.value
            random_ints = self.rng.integers(start_ns, end_ns, size=count)
            sampled.extend(pd.to_datetime(random_ints).tolist())

        if not sampled:
            return clean_timestamps

        sampled_series = pd.Series(pd.to_datetime(sampled))
        if len(sampled_series) < len(clean_timestamps):
            extra = clean_timestamps.sample(
                n=len(clean_timestamps) - len(sampled_series),
                replace=True,
                random_state=self.config.seed,
            ).reset_index(drop=True)
            sampled_series = pd.concat([sampled_series, extra], ignore_index=True)
        elif len(sampled_series) > len(clean_timestamps):
            sampled_series = sampled_series.iloc[:len(clean_timestamps)].reset_index(drop=True)

        return sampled_series.sample(frac=1.0, random_state=self.config.seed).reset_index(drop=True)

    def _resolve_time_density_weights(
        self,
        windows: List[pd.Timestamp],
        points: List[Dict[str, Any]],
        pattern_type: str,
    ) -> np.ndarray:
        """Convert relative curve points into per-window density weights."""
        if not windows:
            return np.array([], dtype=float)

        x_known = np.array([point["month"] for point in points], dtype=float)
        y_known = np.array([point["relative_value"] for point in points], dtype=float)
        y_known = np.maximum(y_known, 0.0)
        weights = np.ones(len(windows), dtype=float)

        if pattern_type in ["seasonal", "cyclic"]:
            for index, window in enumerate(windows):
                month_value = float(window.month)
                if month_value <= x_known.min():
                    weights[index] = y_known[0]
                elif month_value >= x_known.max():
                    weights[index] = y_known[-1]
                else:
                    weights[index] = np.interp(month_value, x_known, y_known)
        else:
            if len(windows) == 1:
                weights[0] = y_known[-1] if len(y_known) else 1.0
            else:
                x_norm = np.linspace(0.0, 1.0, len(windows))
                x_known_norm = (x_known - x_known.min()) / max(x_known.max() - x_known.min(), 1.0)
                weights = np.interp(x_norm, x_known_norm, y_known)

        return np.maximum(weights, 0.0)

    def _apply_single_constraint(self, df: pd.DataFrame, constraint: Any) -> pd.DataFrame:
        """Apply a single constraint to the DataFrame."""

        # Validate required columns exist
        for col in constraint.group_by:
            if col not in df.columns:
                warnings.warn(f"Constraint '{constraint.name}': Column '{col}' not found. Skipping.")
                return df

        if constraint.column and constraint.column not in df.columns:
            warnings.warn(f"Constraint '{constraint.name}': Target column '{constraint.column}' not found. Skipping.")
            return df

        if constraint.type == "max_per_group":
            # Cap values per group (e.g., max 8 hours per employee per day)
            if constraint.action == "cap":
                # Simple cap: clip the value column
                df[constraint.column] = df.groupby(constraint.group_by)[constraint.column].transform(
                    lambda x: x.clip(upper=constraint.value)
                )
            elif constraint.action == "redistribute":
                # More complex: redistribute excess across the group
                # For now, just cap
                df[constraint.column] = df.groupby(constraint.group_by)[constraint.column].transform(
                    lambda x: x.clip(upper=constraint.value)
                )

        elif constraint.type == "sum_limit":
            # Limit sum per group (e.g., max 8 total hours per employee per day across projects)
            group_totals = df.groupby(constraint.group_by)[constraint.column].transform("sum")
            over_limit = group_totals > constraint.value
            scale = constraint.value / group_totals
            df.loc[over_limit, constraint.column] = df.loc[over_limit, constraint.column] * scale.loc[over_limit]

        elif constraint.type == "unique_combination":
            # Ensure unique combinations (e.g., one timesheet per employee-project-date)
            if constraint.action == "drop":
                df = df.drop_duplicates(subset=constraint.group_by, keep='first')

        elif constraint.type == "min_per_group":
            # Floor values per group
            if constraint.action == "cap":
                df[constraint.column] = df.groupby(constraint.group_by)[constraint.column].transform(
                    lambda x: x.clip(lower=constraint.value)
                )

        return df

    def _apply_formula_columns(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Apply formula-based derived columns using context for lookups."""
        try:
            from misata.formulas import FormulaEngine
        except ImportError:
            return df

        columns = self.config.get_columns(table_name)
        formula_cols = [c for c in columns if c.distribution_params.get("formula")]

        if not formula_cols:
            return df

        # FormulaEngine now needs context, not full data
        # BUT FormulaEngine expects full DataFrames in tables dict for lookups
        # Our self.context IS a Dict[str, pd.DataFrame], just restricted columns
        # So it should work if the formulas only ref columns in context (like id, price)
        # Note: We need to make sure context has columns needed for formulas!
        # Current _update_context only saves PK/FKs.
        # TODO: Analyze formulas to find required context columns?
        # For now, simplistic approach: formulas usually look up 'price', 'cost' etc.
        # We might need to store more in context.
        # Let's trust user or update _update_context to be smarter later.

        engine = FormulaEngine(self.context)

        for col in formula_cols:
            formula = col.distribution_params["formula"]
            # For correctness, lookups should work.
            # If context doesn't have the column, FormulaEngine raises Error.
            try:
                result = engine.evaluate_with_lookups(df, formula)
                df[col.name] = result
            except ValueError as e:
                # Warn and skip if context missing
                warnings.warn(f"Formula evaluation failed (context missing?): {e}")

        return df

    def _fix_correlated_columns(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Post-process to fix common semantically correlated columns."""
        table = self.config.get_table(table_name)
        protected_columns = self._get_protected_generation_columns(table_name, table) if table else set()

        df = apply_realism_rules(df, table_name, rng=self.rng)

        realism = self._get_realism_config()
        if realism and realism.coherence != "off":
            df = self.coherence_engine.apply(
                df,
                table_name,
                mode=realism.coherence,
                protected_columns=protected_columns,
            )

        workflow_name = self._workflow_for_table(table) if table else None
        if workflow_name:
            df = self.workflow_engine.apply_workflow(
                df,
                workflow_name,
                protected_columns=protected_columns,
            )

        return df

    def generate_all(self):
        """
        Generate all tables in dependency order, then cascade story events
        through the relational graph.

        Yields:
            Tuple[str, pd.DataFrame]: (table_name, batch_df)
        """
        sorted_tables = self.topological_sort()

        # Phase 1: generate every table and accumulate in memory for cascade pass
        accumulated: Dict[str, pd.DataFrame] = {}
        for table_name in sorted_tables:
            batches = []
            for batch in self.generate_batches(table_name):
                batches.append(batch)
            if batches:
                accumulated[table_name] = pd.concat(batches, ignore_index=True)

        # Phase 2: cascade events that propagate to child tables
        cascade_events = [e for e in (self.config.events or []) if e.propagate_to]
        if cascade_events:
            for event in cascade_events:
                self.propagate_event_cascade(accumulated, event)

        # Phase 3: yield final tables
        for table_name in sorted_tables:
            if table_name in accumulated:
                yield table_name, accumulated[table_name]

    def generate_with_reports(
        self,
        *,
        include_tables: bool = False,
        sample_size: int = 5000,
    ) -> GenerationResult:
        """
        Generate all tables and return validation plus optional advisory reports.

        By default, reports are built from bounded reservoir samples so this
        method stays safe for large runs. Pass `include_tables=True` only when
        you explicitly want full in-memory tables returned.
        """
        full_tables: Dict[str, pd.DataFrame] = {}
        sampler = ReservoirTableSampler(sample_size=sample_size, rng=self.rng)
        validator = StreamingDataValidator(self.config)

        for table_name, batch_df in self.generate_all():
            validator.consume(table_name, batch_df)
            sampler.consume(table_name, batch_df)

            if include_tables:
                existing = full_tables.get(table_name)
                full_tables[table_name] = batch_df if existing is None else pd.concat([existing, batch_df], ignore_index=True)

        realism = self._get_realism_config()
        requested_reports = list(realism.reports) if realism else []
        validation_report = validator.finalize()
        sampled_tables = sampler.get_tables()
        report_tables = full_tables if include_tables else sampled_tables
        bundle = build_generation_report_bundle(
            report_tables,
            self.config,
            reports=requested_reports,
            validation_report=validation_report,
            row_counts=dict(sampler.row_counts),
            sampled=not include_tables,
        )
        return GenerationResult(
            tables=report_tables,
            validation_report=bundle.validation,
            reports=bundle.reports,
            tables_are_samples=not include_tables,
            table_row_counts=dict(sampler.row_counts),
        )

    def export_to_csv(self, output_dir: str = ".") -> None:
        """
        Export all generated tables to CSV files, creating files progressively.
        """
        import os
        os.makedirs(output_dir, exist_ok=True)

        # Track open file handles or just append?
        # Appending is safer.
        files_created = set()

        for table_name, batch_df in self.generate_all():
            output_path = os.path.join(output_dir, f"{table_name}.csv")
            mode = 'a' if table_name in files_created else 'w'
            header = table_name not in files_created

            batch_df.to_csv(output_path, mode=mode, header=header, index=False)
            files_created.add(table_name)

    def get_summary(self) -> str:
        """
        Get a summary of generated data (from context).
        Only shows context info since full data isn't kept.
        """
        summary_lines = ["Generated Context Summary (Lightweight):", "=" * 50]

        for table_name, df in self.context.items():
            summary_lines.append(f"\n{table_name}: {len(df):,} rows tracked in context")
            summary_lines.append(f"  Context Columns: {list(df.columns)}")
            summary_lines.append(f"  Context Memory: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")

        return "\n".join(summary_lines)
