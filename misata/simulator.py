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
import zlib
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from misata.assets import AssetStore
from misata.curve_inheritance import TemporalDensityMap, resolve_inherits_curve_from
from misata.engines import FactEngine
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


def _null_column(df: pd.DataFrame, col_name: str, mask: "pd.Series") -> None:
    """Assign null to rows matching *mask* while preserving integer dtype fidelity.

    pandas upcasts int64 → float64 when you assign np.nan; the result is that ID
    and count columns print as 1.0 instead of 1.  This helper uses pandas nullable
    Int64 to keep the column integer-typed through null assignment.
    """
    if not mask.any():
        return
    if pd.api.types.is_integer_dtype(df[col_name].dtype):
        df[col_name] = df[col_name].astype("Int64")
        df.loc[mask, col_name] = pd.NA
    else:
        df.loc[mask, col_name] = np.nan


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
                 smart_mode: bool = False, use_llm: bool = True,
                 custom_generators: Optional[Dict[str, Dict[str, Any]]] = None):
        """
        Initialize the simulator.

        Args:
            config: Schema configuration defining tables, columns, and relationships
            apply_semantic_fixes: Auto-fix column types based on semantic patterns
            batch_size: Number of rows to generate per batch
            smart_mode: Enable LLM-powered context-aware value generation
            use_llm: If smart_mode is True, whether to use LLM (vs curated fallbacks)
            custom_generators: Optional dict of ``{table: {column: callable}}`` where
                each callable receives ``(partial_df, context_tables)`` and returns a
                ``pd.Series`` or array of length ``len(partial_df)``.
        """
        from misata.validation import validate_schema
        validate_schema(config)

        self.config = config
        self.context: Dict[str, pd.DataFrame] = {}  # Lightweight context (IDs only)
        self._pk_store: Dict[str, np.ndarray] = {}  # Full PK arrays for FK sampling
        self.text_gen = TextGenerator(seed=config.seed)
        self.batch_size = batch_size
        self.smart_mode = smart_mode
        self.use_llm = use_llm
        # custom_generators: {table_name: {col_name: callable(df, context) -> array}}
        self.custom_generators: Dict[str, Dict[str, Any]] = custom_generators or {}
        self._smart_gen = None  # Lazy init
        self._unique_pools: Dict[str, np.ndarray] = {}  # Store pre-generated unique values
        self._unique_counters: Dict[str, int] = {}      # Track usage of unique pools
        self._sequence_counters: Dict[str, int] = {}    # Stable counters for primary keys
        self._smart_pools: Dict[str, np.ndarray] = {}   # Cache smart value pools
        self._text_pools: Dict[str, np.ndarray] = {}    # Cache text pools for vectorized sampling
        # Gap 3: parent table temporal density maps for child-table curve inheritance.
        # Populated after _generate_fact_table() and used during FK + date generation.
        self._parent_temporal_density: Dict[str, TemporalDensityMap] = {}
        # Gap B: per-table, per-period running totals for relative-curve accumulation.
        # Structure: {table_name: {period_key: running_sum}}
        self._relative_curve_totals: Dict[str, Dict[str, float]] = {}

        # Apply semantic inference to fix column types
        if apply_semantic_fixes:
            from misata.semantic import apply_semantic_inference
            self.config.columns = apply_semantic_inference(self.config.columns)

        # Set random seed if provided — use default_rng only; never mutate
        # the process-global np.random state (makes concurrent generation safe).
        _init_seed = config.seed if config.seed is not None else None
        self.rng = np.random.default_rng(_init_seed)
        self.fact_engine = FactEngine(self.rng)
        self.noise_injector = NoiseInjector(_init_seed)
        self.generation_plan = GenerationPlanner(self.config, self.rng).build()
        realism = getattr(self.config, "realism", None)
        asset_store = AssetStore(getattr(realism, "asset_store_dir", None))
        self.domain_capsule = SemanticVocabularyGenerator(asset_store=asset_store).build_capsule(self.config)
        # User-supplied capsule file: its vocabularies beat built-in pools.
        capsule_file = getattr(realism, "capsule_file", None)
        if capsule_file:
            from misata.capsules import load_capsule, merge_into
            self.domain_capsule = merge_into(self.domain_capsule, load_capsule(capsule_file))
        # Resolve locale: schema.realism.locale → schema.domain hint → default en_US
        self.locale = getattr(realism, "locale", None) or "en_US"
        self.realistic_text = RealisticTextGenerator(self.rng, capsule=self.domain_capsule, locale=self.locale)
        self.coherence_engine = EntityCoherenceEngine(self.rng, capsule=self.domain_capsule)
        # Locale-aware Faker for address/phone (legacy path)
        try:
            from misata.locales.registry import LocaleRegistry
            self._locale_faker = LocaleRegistry.global_instance().get_faker(self.locale)
        except Exception:
            self._locale_faker = None
        self.workflow_engine = WorkflowEngine(self.rng)
    
    def _capsule_vocab_for_column(self, column_name: str):
        """User-capsule vocabulary keyed by column name, else None.

        Only non-default provenance counts: built-in fallback pools must not
        hijack column-name matches.
        """
        capsule = self.domain_capsule
        if capsule is None:
            return None
        key = column_name.lower()
        values = capsule.vocabularies.get(key)
        if not values:
            return None
        provenances = capsule.provenance.get(key, [])
        if any(getattr(p, "source_name", "") != "misata-defaults" for p in provenances):
            return values
        return None

    def _generate_unique_text(self, text_type: str, size: int) -> np.ndarray:
        """Generate exactly `size` distinct text values for a unique column."""
        _note_fn = lambda: str(self.realistic_text.microtext.notes(1)[0])  # noqa: E731
        method_map = {
            "name":       self.text_gen.name,
            "email":      self.text_gen.email,
            "company":    self.text_gen.company,
            "address":    self.text_gen.full_address,
            "phone":      self.text_gen.phone_number,
            "url":        self.text_gen.url,
            "sentence":   _note_fn,
            "word":       self.text_gen.word,
        }
        gen_fn = method_map.get(text_type, _note_fn)
        seen: set = set()
        results: list = []
        max_attempts = size * 10
        attempts = 0
        while len(results) < size and attempts < max_attempts:
            val = gen_fn()
            if val not in seen:
                seen.add(val)
                results.append(val)
            attempts += 1
        # If we still need more (pool exhausted), append with suffix
        while len(results) < size:
            results.append(f"{gen_fn()}_{len(results)}")
        return np.array(results)

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
            # Skip self-referential FKs (e.g. employee.manager_id → employee).
            # The table must be generated first as a whole; the self-FK is
            # handled by sampling from already-generated rows in the same table.
            if rel.parent_table == rel.child_table:
                continue
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
        # Self-referential FK (e.g. employee.manager_id → employee):
        # the "parent" is the table being generated right now — sample PKs
        # from the batch that's already in context (or return empty so the
        # caller falls back to sequential IDs for root rows).
        if relationship.parent_table == relationship.child_table:
            if relationship.parent_table not in self.context:
                return np.array([])
            self_df = self.context[relationship.parent_table]
            if relationship.parent_key not in self_df.columns:
                return np.array([])
            return self_df[relationship.parent_key].dropna().values

        if relationship.parent_table not in self.context:
            return np.array([])

        # If _pk_store has the full parent PK array (not capped), use it for
        # unfiltered FK sampling — avoids child-distribution skew on large parents.
        if (
            not relationship.filters
            and relationship.parent_key == "id"
            and relationship.parent_table in self._pk_store
        ):
            return self._pk_store[relationship.parent_table]

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
        """Return the columns that must be retained for future FK/date/depends_on lookups.

        Gap 3 extension: also retains the time column from any OutcomeCurve or RateCurve
        attached to this table, so that child tables can weight FK sampling by temporal
        density (Level-1 inheritance) without any additional config.
        """
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

        # Gap 3: retain the outcome/rate curve time column so child tables can
        # perform temporal FK weighting (Level-1 curve inheritance).
        for curve in getattr(self.config, "outcome_curves", []):
            if getattr(curve, "table", None) == table_name:
                needed_cols.add(getattr(curve, "time_column", "date"))
        for curve in getattr(self.config, "rate_curves", []):
            if getattr(curve, "table", None) == table_name:
                needed_cols.add(getattr(curve, "time_column", "date"))

        # Enterprise coherence: retain any column that a child-table FORMULA references
        # via `@this_table.column` (e.g. timesheets.billed = hours * @employees.hourly_rate
        # needs employees.hourly_rate in context, not just the PK). Without this the lookup
        # falls back to 0 and the derived value is wrong.
        import re as _re
        for child_table in self.config.tables:
            for col in self.config.get_columns(child_table.name):
                # row-formula references: formula: "hours * @employees.hourly_rate"
                formula = col.distribution_params.get("formula")
                if formula:
                    for ref_table, ref_col in _re.findall(r"@(\w+)\.(\w+)", formula):
                        if ref_table == table_name:
                            needed_cols.add(ref_col)
                # distribution.mean / distribution.std formula references:
                # mean: {formula: "@patients.hba1c_baseline"}
                for dist_param_key in ("mean", "std", "mu", "sigma"):
                    dist_val = col.distribution_params.get(dist_param_key)
                    if isinstance(dist_val, dict) and "formula" in dist_val:
                        for ref_table, ref_col in _re.findall(r"@(\w+)\.(\w+)", str(dist_val["formula"])):
                            if ref_table == table_name:
                                needed_cols.add(ref_col)

        return [column for column in needed_cols if column in df.columns]

    def _quantize_numeric(
        self,
        values: np.ndarray,
        table_name: str,
        column: Column,
        params: Dict[str, Any],
    ) -> np.ndarray:
        """Post-draw quantization: human-chosen quantities land on the values
        humans actually choose (slot-grid durations, charm prices, integer
        ages). Skipped when the column declares explicit choices/probabilities
        and opted out per column with ``quantize: False``."""
        if params.get("quantize") is False:
            return values
        if "choices" in params or params.get("probabilities") is not None or "formula" in params:
            return values

        from misata.quantization import apply_quantization, classify_quantization

        domain = getattr(self.config, "domain", None) or getattr(
            self._get_realism_config(), "domain_hint", None
        )
        profile = classify_quantization(column.name, table_name, domain)
        if profile is None:
            return values
        # Explicit decimals already define this percentage's precision.
        if profile == "percentage" and "decimals" in params:
            return values

        # Per-column stream: quantization never perturbs the main RNG sequence,
        # so adding/removing it leaves every other column's draws unchanged.
        quant_seed = zlib.crc32(
            f"quantize:{table_name}.{column.name}".encode()
        ) ^ (self.config.seed or 0)
        quant_rng = np.random.default_rng(quant_seed)

        arr = np.asarray(values)
        was_integer = np.issubdtype(arr.dtype, np.integer)
        out = apply_quantization(arr, profile, quant_rng)
        if "min" in params:
            out = np.maximum(out, params["min"])
        if "max" in params:
            out = np.minimum(out, params["max"])
        return out.astype(int) if was_integer else out

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
        # ========== CUSTOM CALLABLE GENERATOR ==========
        # Check before any other dispatch so user logic always wins.
        # Two calling conventions are accepted:
        #   vectorized: fn(partial_df, context_tables)  → array of length size
        #   per-row:    fn(row, col_name, context_tables) → scalar per row
        # The per-row form is detected by inspecting the callable's signature.
        _custom_fn = self.custom_generators.get(table_name, {}).get(column.name)
        if callable(_custom_fn):
            partial_df = table_data if table_data is not None else pd.DataFrame()
            try:
                import inspect as _inspect
                _sig = _inspect.signature(_custom_fn)
                _nparams = len(_sig.parameters)
            except (TypeError, ValueError):
                _nparams = 2  # default to vectorized

            if _nparams >= 3:
                # Per-row signature: fn(row, col_name, context_tables) → scalar
                # Graceful fallback: if partial_df is empty generate zeros
                if partial_df.empty or len(partial_df) == 0:
                    return np.zeros(size, dtype=object)
                result = partial_df.apply(
                    lambda row: _custom_fn(row, column.name, self.context), axis=1
                )
            else:
                # Vectorized signature: fn(partial_df, context_tables) → array
                result = _custom_fn(partial_df, self.context)

            if isinstance(result, pd.Series):
                return result.to_numpy()
            return np.asarray(result)

        # Apply domain priors as defaults — user-defined params always win.
        _domain = getattr(self.config, "domain", None) or getattr(
            getattr(self.config, "realism", None), "domain_hint", None
        )
        if _domain and column.type in ("int", "float"):
            params = apply_domain_priors(_domain, column.name, column.distribution_params)
        else:
            params = column.distribution_params

        # Apply locale-specific priors (salary/age) — overrides en_US domain defaults
        if column.type in ("int", "float") and self.locale != "en_US":
            from misata.domain_priors import apply_locale_priors
            params = apply_locale_priors(column.name, params, self.locale)

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

                if isinstance(first_val, dict) and any(k in first_val for k in ("mean", "mu", "value")):
                    # Numeric conditional distribution — supports three sub-types per key:
                    #   normal:    {"mean": 150, "std": 30}
                    #   lognormal: {"distribution": "lognormal", "mu": 5.0, "sigma": 0.4}
                    #   constant:  {"value": 0}
                    # Example: {"free": {"value": 0}, "pro": {"distribution": "lognormal", "mu": 5.0, "sigma": 0.3}}
                    values = np.zeros(size, dtype=float)
                    for key, dist in mapping.items():
                        compare_key = key
                        if len(parent_values) > 0:
                            target_type = type(parent_values[0])
                            try:
                                compare_key = target_type(key)
                            except (TypeError, ValueError):
                                pass

                        mask = parent_values == compare_key
                        count = int(mask.sum())
                        if count == 0:
                            continue

                        sub_dist = dist.get("distribution", "normal")
                        if "value" in dist:
                            values[mask] = float(dist["value"])
                        elif sub_dist == "lognormal":
                            mu    = float(dist.get("mu", 4.5))
                            sigma = float(dist.get("sigma", 0.5))
                            raw   = self.rng.lognormal(mu, sigma, count)
                            lo    = dist.get("min")
                            hi    = dist.get("max")
                            if lo is not None:
                                raw = np.clip(raw, lo, None)
                            if hi is not None:
                                raw = np.clip(raw, None, hi)
                            dec = dist.get("decimals")
                            if dec is not None:
                                raw = np.round(raw, dec)
                            values[mask] = raw
                        else:
                            mean = float(dist.get("mean", 50000))
                            std  = float(dist.get("std", mean * 0.1))
                            raw  = self.rng.normal(mean, std, count)
                            lo   = dist.get("min")
                            hi   = dist.get("max")
                            if lo is not None:
                                raw = np.clip(raw, lo, None)
                            if hi is not None:
                                raw = np.clip(raw, None, hi)
                            dec = dist.get("decimals")
                            if dec is not None:
                                raw = np.round(raw, dec)
                            values[mask] = raw

                    # Fill any unmatched rows with the default distribution
                    default = params.get("default", {"mean": 50000, "std": 10000})
                    if len(parent_values) > 0:
                        try:
                            target_type = type(parent_values[0])
                            safe_keys = [target_type(k) for k in mapping.keys()]
                        except (TypeError, ValueError):
                            safe_keys = list(mapping.keys())
                    else:
                        safe_keys = list(mapping.keys())

                    unmatched = ~np.isin(parent_values, safe_keys)
                    if unmatched.sum() > 0:
                        if default.get("distribution") == "lognormal":
                            values[unmatched] = self.rng.lognormal(
                                default.get("mu", 4.5), default.get("sigma", 0.5), int(unmatched.sum())
                            )
                        else:
                            values[unmatched] = self.rng.normal(
                                default.get("mean", 50000), default.get("std", 10000), int(unmatched.sum())
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

        # ========== STRATIFIED PROFILES ==========
        # ``profiles`` lets one column carry different distributions per subgroup:
        #   profiles:
        #     - when: "arm == 'placebo'"
        #       distribution: normal
        #       mean: -0.35
        #       std: 0.50
        #     - when: "arm == 'high_dose'"
        #       distribution: normal
        #       mean: -1.25
        #       std: 0.55
        # Rows that don't match any profile get the column's top-level distribution.
        if "profiles" in params and table_data is not None and not table_data.empty:
            return self._generate_column_with_profiles(
                column, params["profiles"], params, table_data, size
            )

        # ========== STANDARD COLUMN GENERATION ==========

        # CATEGORICAL
        if column.type == "categorical":
            if column.name.lower() == "country" and self.locale != "en_US":
                try:
                    from misata.locales.registry import LocaleRegistry
                    pack = LocaleRegistry.global_instance().get_pack(self.locale)
                    return np.array([pack.country_name] * size)
                except Exception:
                    pass

            choices = params.get("choices", ["A", "B", "C"])
            # Accept "weights" as an alias for "probabilities" (matches dbldatagen
            # and user intuition; "probabilities" takes precedence if both given)
            user_declared_probs = bool(params.get("probabilities") or params.get("weights"))
            probabilities = params.get("probabilities") or params.get("weights") or None

            # Ensure choices is a list
            if not isinstance(choices, list):
                choices = list(choices)

            # Lookup/reference tables: when the table has ≤ len(choices) rows and
            # no explicit distribution was declared, sample without replacement so
            # every row carries a distinct label (e.g. a 4-row order_status table
            # gets four distinct statuses, not four draws that may repeat).
            sampling = params.get("sampling", "auto")
            if size <= len(choices) and not user_declared_probs:
                values = self.rng.choice(choices, size=size, replace=False)
                return values

            # Real categorical data is never uniform: statuses, categories,
            # countries and payment methods all follow rank-frequency power
            # laws (Zipf 1949). Uniform marginals are one of the strongest
            # statistical "this data is synthetic" tells, so when no explicit
            # probabilities are declared we default to a mild Zipf–Mandelbrot
            # law  w_k ∝ (k + q)^(−s)  with the rank order shuffled
            # deterministically per column (the dominant category shouldn't
            # always be the first one listed). Declared probabilities always
            # win; ``sampling="uniform"`` opts out; legacy ``sampling="zipf"``
            # keeps its documented listed-order behaviour.
            if probabilities is None and len(choices) > 1:
                if sampling == "zipf":
                    exponent = float(params.get("zipf_exponent", 1.2))
                    ranks = np.arange(1, len(choices) + 1, dtype=float)
                    weights = 1.0 / np.power(ranks, exponent)
                    probabilities = weights / weights.sum()
                elif sampling == "auto":
                    s = float(params.get("zipf_exponent", 0.85))
                    q = float(params.get("zipf_offset", 2.0))
                    ranks = np.arange(1, len(choices) + 1, dtype=float)
                    weights = np.power(ranks + q, -s)
                    perm_seed = zlib.crc32(
                        f"{table_name}.{column.name}".encode()
                    ) ^ (self.config.seed or 0)
                    perm = np.random.default_rng(perm_seed).permutation(len(choices))
                    probabilities = weights[perm] / weights.sum()

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
                    # Check range capacity. The inclusive range [low, high] holds
                    # (high - low + 1) distinct integers.
                    if (high - low + 1) < total_needed_for_table:
                        # Auto-expand range to fix user error (common in tests/small ranges)
                        warnings.warn(f"Range {high-low+1} too small for unique column {column.name} (needs {total_needed_for_table}). Extending max.")
                        high = low + total_needed_for_table + 100

                    # Generate full permutation over the inclusive range.
                    pool = np.arange(low, high + 1)
                    self.rng.shuffle(pool)
                    self._unique_pools[pool_key] = pool
                    self._unique_counters[pool_key] = 0

                # Fetch chunk — auto-extend pool if exhausted (e.g. multi-batch curves)
                current_idx = self._unique_counters[pool_key]
                if current_idx + size > len(self._unique_pools[pool_key]):
                    # Grow by another block the same size as the original pool
                    existing_max = self._unique_pools[pool_key].max()
                    extension = np.arange(existing_max + 1, existing_max + 1 + size + 1000)
                    self.rng.shuffle(extension)
                    self._unique_pools[pool_key] = np.concatenate(
                        [self._unique_pools[pool_key], extension]
                    )

                values = self._unique_pools[pool_key][current_idx : current_idx + size]
                self._unique_counters[pool_key] += size
                return values.astype(int)

            distribution = params.get("distribution", "normal")
            # When no explicit distribution is specified but min/max are present
            # (and no mean/mu), default to uniform instead of normal so that
            # reference ID columns (parent_comment_id, followee_id, etc.) span
            # their full declared range rather than clustering around mean=100.
            if distribution == "normal" and "mean" not in params and "min" in params:
                distribution = "uniform"

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
            elif distribution in ("power_law", "pareto", "zipf"):
                # "zipf" is accepted as an alias (its shape param is "a"); mapped
                # onto the same Pareto sampler so a heavy-tail request never
                # silently degrades to uniform noise.
                alpha = float(params.get("alpha", params.get("a", 1.5)))
                scale = float(params.get("scale", params.get("min", 1)))
                # Pareto: X = scale / U^(1/alpha), U ~ Uniform(0,1)
                u = self.rng.uniform(0, 1, size=size)
                values = (scale / np.power(u, 1.0 / alpha)).astype(int)
            elif distribution == "uniform":
                low = params.get("min", 0)
                high = params.get("max", 1000)
                # endpoint=True: an integer column declared max=N must be able to
                # produce N (a 1..5 rating must reach 5; a 0..1 flag must reach 1).
                values = self.rng.integers(low, high, size=size, endpoint=True)
            elif distribution == "poisson":
                lam = params.get("lambda", 10)
                values = self.rng.poisson(lam, size=size)
            elif distribution == "binomial":
                n = int(params.get("n", 10))
                p = float(params.get("p", 0.5))
                values = self.rng.binomial(n, p, size=size)
            elif distribution == "empirical":
                # Inverse-CDF sampling from stored quantiles — reproduces any
                # marginal shape (used by mimic when no parametric fit is good).
                q = params.get("quantiles") or []
                if len(q) >= 2:
                    qs = np.linspace(0.0, 1.0, len(q))
                    u = self.rng.uniform(0, 1, size=size)
                    values = np.round(np.interp(u, qs, np.asarray(q, dtype=float))).astype(int)
                else:
                    low = params.get("min", 0)
                    high = params.get("max", 1000)
                    values = self.rng.integers(low, high, size=size, endpoint=True)
            else:
                low = params.get("min", 0)
                high = params.get("max", 1000)
                values = self.rng.integers(low, high, size=size, endpoint=True)

            if "min" in params:
                values = np.maximum(values, params["min"])
            if "max" in params:
                values = np.minimum(values, params["max"])

            return self._quantize_numeric(values, table_name, column, params)

        # FLOAT
        elif column.type == "float":
            # Derive float from days between a date column and today (e.g. tenure_years)
            if "date_diff_to" in params and table_data is not None:
                ref_col = params["date_diff_to"]
                if ref_col in table_data.columns:
                    ref_dates = pd.to_datetime(table_data[ref_col], errors="coerce")
                    today = pd.Timestamp.now().normalize()
                    diff_years = (today - ref_dates).dt.days / 365.25
                    decimals = params.get("decimals", 1)
                    max_val = float(params.get("max", 50.0))
                    return np.round(diff_years.clip(0, max_val).values, decimals)

            distribution = params.get("distribution", "normal")

            # ------ @parent in distribution.mean / distribution.std ------
            # Allows child column distributions to be anchored to a parent
            # entity value via a formula reference:
            #   mean: {formula: "@patients.hba1c_baseline"}
            #   std:  {formula: "@patients.hba1c_sd"}
            # Resolves the FK → parent lookup per-row and uses per-row arrays
            # as the mean/std for vectorised sampling.
            def _resolve_dist_param(param_val, default):
                """Return a scalar or per-row array for mean/std params."""
                if not isinstance(param_val, dict) or "formula" not in param_val:
                    return param_val if param_val is not None else default
                formula = str(param_val["formula"]).strip()
                if not formula.startswith("@") or table_data is None or table_data.empty:
                    return default
                # Parse "@table.column"
                ref = formula[1:]
                if "." not in ref:
                    return default
                ref_table, ref_col = ref.split(".", 1)
                # Find FK from this child table to ref_table
                rel = next(
                    (r for r in self.config.relationships
                     if r.child_table == table_name and r.parent_table == ref_table),
                    None,
                )
                if rel is None or rel.child_key not in table_data.columns:
                    return default
                parent_df = self.context.get(ref_table)
                if parent_df is None or ref_col not in parent_df.columns:
                    return default
                pk = rel.parent_key
                fk_vals = table_data[rel.child_key].values
                parent_map = parent_df.set_index(pk)[ref_col]
                per_row = parent_map.reindex(fk_vals).values.astype(float)
                return per_row

            # Default mean/std must respect declared bounds. A normal with no
            # explicit mean/std used to fall back to N(100, 20) regardless of
            # min/max; with max below ~40 the post-clip collapsed the column
            # to a constant (min 0, max 5 → every value 5.0), and the clip
            # ties silently wrecked declared correlations.
            _lo, _hi = params.get("min"), params.get("max")
            if (
                distribution == "normal"
                and "mean" not in params
                and "std" not in params
                and isinstance(_lo, (int, float))
                and isinstance(_hi, (int, float))
                and float(_hi) > float(_lo)
            ):
                _default_mean = (float(_lo) + float(_hi)) / 2.0
                _default_std = (float(_hi) - float(_lo)) / 6.0
            else:
                _default_mean, _default_std = 100.0, 20.0
            mean_param = _resolve_dist_param(params.get("mean"), _default_mean)
            std_param  = _resolve_dist_param(params.get("std"),  _default_std)
            # ------ end @parent resolution ------

            if distribution == "categorical" or "choices" in params:
                choices = params.get("choices", [1.0, 2.0, 3.0])
                probabilities = params.get("probabilities", None)
                if probabilities is not None:
                    probabilities = np.array(probabilities)
                    probabilities = probabilities / probabilities.sum()
                values = self.rng.choice(choices, size=size, p=probabilities)
                return np.array(values).astype(float)
            elif distribution == "normal":
                mean = mean_param if not isinstance(mean_param, (int, float)) else float(mean_param)
                std  = std_param  if not isinstance(std_param,  (int, float)) else float(std_param)
                # Per-row mean/std: sample element-wise
                if isinstance(mean, np.ndarray) or isinstance(std, np.ndarray):
                    mean_arr = np.broadcast_to(np.asarray(mean, dtype=float), (size,))
                    std_arr  = np.broadcast_to(np.asarray(std,  dtype=float), (size,))
                    std_arr  = np.abs(std_arr)
                    values = mean_arr + std_arr * self.rng.standard_normal(size)
                else:
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
            elif distribution in ("power_law", "pareto", "zipf"):
                alpha = float(params.get("alpha", params.get("a", 1.5)))
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
            elif distribution == "empirical":
                # Inverse-CDF sampling from stored quantiles — reproduces any
                # marginal shape (used by mimic when no parametric fit is good).
                q = params.get("quantiles") or []
                if len(q) >= 2:
                    qs = np.linspace(0.0, 1.0, len(q))
                    u = self.rng.uniform(0, 1, size=size)
                    values = np.interp(u, qs, np.asarray(q, dtype=float))
                else:
                    low = params.get("min", 0.0)
                    high = params.get("max", 1000.0)
                    values = self.rng.uniform(low, high, size=size)
            else:
                low = params.get("min", 0.0)
                high = params.get("max", 1000.0)
                values = self.rng.uniform(low, high, size=size)

            if "min" in params:
                values = np.maximum(values, params["min"])
            if "max" in params:
                values = np.minimum(values, params["max"])

            # Zero inflation: a fraction of rows are *structural* zeros, applied AFTER the
            # min clamp so a structural 0 is not lifted to `min`. Real monetary/usage columns
            # often have a spike at 0 (free-tier MRR, no-spend months, dormant accounts) on
            # top of a positive continuous tail — a uniformly-positive column reads as fake.
            zi = params.get("zero_inflate")
            if zi:
                p_zero = float(zi if isinstance(zi, (int, float)) else zi.get("p", 0.0))
                if 0.0 < p_zero < 1.0:
                    zero_mask = self.rng.random(size) < p_zero
                    values = np.where(zero_mask, 0.0, values)

            if "decimals" in params:
                values = np.round(values, params["decimals"])

            return self._quantize_numeric(values, table_name, column, params)

        # DATE
        elif column.type == "date":
            # Same-row date dependency: delivered_at = shipped_at + delta
            if "after_column" in params and table_data is not None:
                base_col = params["after_column"]
                if base_col in table_data.columns:
                    min_delta = params.get("min_delta_days", 1)
                    max_delta = params.get("max_delta_days", 30)
                    deltas = self.rng.integers(min_delta, max_delta + 1, size=size)
                    base_dates = pd.to_datetime(table_data[base_col], errors="coerce")
                    dates = base_dates + pd.to_timedelta(deltas, unit="D")
                    if params.get("max_date") == "today":
                        today = pd.Timestamp.now().normalize()
                        dates = dates.clip(upper=today)
                    return pd.to_datetime(dates).values

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

            # Gap 3 — Level-2 curve inheritance: ``inherits_curve_from: "parent_table.time_col"``
            # Samples dates using the parent table's temporal density so that child row
            # timestamps cluster around the same periods as their parent rows.
            inherits_from = params.get("inherits_curve_from")
            if inherits_from:
                density_map = resolve_inherits_curve_from(inherits_from, self._parent_temporal_density)
                if density_map is not None:
                    start = pd.to_datetime(params.get("start", "2020-01-01"))
                    end = pd.to_datetime(params.get("end", "2024-12-31"))
                    inherited_dates = density_map.sample_dates(size, self.rng, start=start, end=end)
                    if len(inherited_dates) == size:
                        values = pd.to_datetime(inherited_dates)
                        return self._add_realistic_time(values, table_name, size, column.name)

            start = pd.to_datetime(params.get("start", "2020-01-01"))
            end = pd.to_datetime(params.get("end", "2024-12-31"))

            start_int = start.value
            end_int = end.value
            random_ints = self.rng.integers(start_int, end_int, size=size)
            values = pd.to_datetime(random_ints)

            # Every datetime gets semantically-correct granularity: appointments
            # snap to 15-min business-hour grids, signups follow waking-hour
            # rhythms, logs keep sub-second precision, birth dates are dates.
            # Raw nanosecond noise never survives to output.
            return self._add_realistic_time(values, table_name, size, column.name)

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
                # The parent has no rows to reference (e.g. a 0-row parent). Emit
                # NULL foreign keys rather than fabricating orphan IDs — preserving
                # the engine's referential-integrity guarantee.
                warnings.warn(
                    f"Parent table '{relationship.parent_table}' has no rows; foreign key "
                    f"'{column.name}' in '{table_name}' will be null (nothing to reference)."
                )
                return np.array([None] * size, dtype=object)

            sampling = params.get("sampling", "uniform")
            if sampling == "pareto":
                alpha = max(float(params.get("alpha", 1.5)), 0.1)
                weights = self.rng.pareto(alpha, len(parent_ids)) + 1.0
                probabilities = weights / weights.sum()
                values = self.rng.choice(parent_ids, size=size, p=probabilities)
            else:
                # Gap 3 — Level-1 temporal FK weighting:
                # If the parent table was generated with an exact OutcomeCurve, its rows
                # are non-uniformly distributed in time.  Weight FK selection by the
                # parent row's temporal density so child rows cluster around the same
                # time periods as their parents (realistic parent-child temporal coherence).
                density_map = self._parent_temporal_density.get(relationship.parent_table)
                if density_map is not None and relationship.parent_table in self.context:
                    parent_ctx = self.context[relationship.parent_table]
                    if density_map.time_column in parent_ctx.columns:
                        # Compute per-row weights aligned with parent_ids
                        pk_col = relationship.parent_key
                        if pk_col in parent_ctx.columns:
                            try:
                                pk_to_idx = {pk: i for i, pk in enumerate(parent_ctx[pk_col].values)}
                                id_indices = np.array([pk_to_idx.get(pid, -1) for pid in parent_ids])
                                valid_mask = id_indices >= 0
                                if valid_mask.any():
                                    all_weights = density_map.compute_fk_weights(parent_ctx)
                                    row_weights = np.ones(len(parent_ids), dtype=float)
                                    row_weights[valid_mask] = all_weights[id_indices[valid_mask]]
                                    probabilities = row_weights / row_weights.sum()
                                    values = self.rng.choice(parent_ids, size=size, p=probabilities)
                                    return values
                            except Exception:
                                pass  # Fall through to uniform sampling on any error
                values = self.rng.choice(parent_ids, size=size)
            return values

        # TEXT
        elif column.type == "text":
            text_type = params.get("text_type", "sentence")
            # User capsule vocabularies keyed by this column's name take top
            # priority: a capsule that defines "species" drives any species
            # column. Built-in fallback vocab (misata-defaults) never
            # short-circuits here.
            capsule_vocab = self._capsule_vocab_for_column(column.name)
            if capsule_vocab is not None:
                return self.rng.choice(capsule_vocab, size=size)
            # Pattern-based codes (SKUs, reference numbers, ticket ids):
            # ``pattern: "REC-\\d{5}"`` expands via the locale-pack pattern
            # syntax (\d, [A-Z], [a-z], literals, {n} repeats). A list draws
            # one pattern per row, optionally weighted by ``pattern_weights``;
            # this is how mimic reproduces columns whose codes come in several
            # shapes (Titanic tickets: "A/5 21171" next to "349207").
            if "pattern" in params:
                pats = params["pattern"]
                if isinstance(pats, (list, tuple)):
                    pats = [str(p) for p in pats if str(p)] or [""]
                    weights = params.get("pattern_weights")
                    w = None
                    if weights is not None and len(weights) == len(pats):
                        arr = np.asarray(weights, dtype=float)
                        if arr.sum() > 0:
                            w = arr / arr.sum()
                    idx = self.rng.choice(len(pats), size=size, p=w)
                    return np.array([
                        self.realistic_text._expand_pattern(pats[i]) for i in idx
                    ])
                return np.array([
                    self.realistic_text._expand_pattern(str(pats))
                    for _ in range(size)
                ])
            # For unique text columns, generate exactly `size` distinct values.
            if column.unique:
                return self._generate_unique_text(text_type, size)
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

            # Map simulator text_type → RealisticTextGenerator semantic types.
            # RealisticTextGenerator uses the domain capsule (vocab seeds +
            # Kaggle-enriched asset store) so these paths get real, diverse,
            # domain-appropriate values automatically.
            _REALISTIC_TYPE_MAP = {
                "name":                   "name",
                "email":                  "email",
                "company":                "company_name",
                "first_name":             "first_name",
                "last_name":              "last_name",
                "job":                    "job_title",
                "city":                   "city",
                "state":                  "state",
                "country":                "country",
                "username":               "username",
                "product_name":           "product_name",
                "description":            "product_description",
                "bio":                    "bio",
                "caption":                "caption",
                "restaurant_name":        "restaurant_name",
                "menu_item":              "menu_item",
                "comment_body":           "comment_body",
                "research_project_name":  "research_project_name",
                "latitude":               "latitude",
                "longitude":              "longitude",
                "postal_code":            "postal_code",
                "review":                 "review",
                "short_review_title":     "short_review_title",
                "support_ticket":         "support_ticket",
                "email_body":             "email_body",
                "phone":                  "phone_number",
                "phone_number":           "phone_number",
                "national_id":            "national_id",
                "ssn":                    "national_id",
                "cpf":                    "national_id",
                "aadhaar":                "national_id",
                "nid":                    "national_id",
            }
            # An explicitly declared text_type always wins; name-based
            # inference (text_strategy) only fills the gap when the schema
            # says nothing. Unknown declared types pass through as-is so the
            # full semantic vocabulary is reachable from dict schemas, not
            # just the simulator aliases.
            declared = params.get("text_type")
            if declared in ("sentence", "word", "address", "phone", "url"):
                declared = None  # legacy free-text types: handled below
            semantic = (
                (_REALISTIC_TYPE_MAP.get(declared, declared) if declared else None)
                or text_strategy
                or _REALISTIC_TYPE_MAP.get(text_type)
            )
            # When no text_type was declared and the semantic map didn't fire,
            # try column-name inference so columns like "industry", "event_name",
            # "sector" get category labels instead of falling to business-note sentences.
            # "description" is _infer_semantic's own catch-all — skip it here so
            # truly generic columns (notes, feedback, details) stay on the sentence path.
            if not declared and not semantic:
                _name_inferred = self.realistic_text._infer_semantic(column.name, table_name)
                if _name_inferred and _name_inferred != "description":
                    semantic = _name_inferred
            # Route to RealisticTextGenerator for known types OR any unrecognised
            # type that is not a legacy free-text type (sentence, word, etc.)
            _LEGACY_ONLY = {"sentence", "word", "address", "phone", "url"}
            if semantic or text_type not in _LEGACY_ONLY:
                return self.realistic_text.generate(
                    column_name=column.name,
                    table_name=table_name,
                    size=size,
                    semantic_type=semantic,  # None → _infer_semantic uses column name
                    table_data=table_data,
                )

            # Legacy pool sampler for free-text types (sentence, word, address, phone, url)
            _pool_size = min(max(size * 5, 200), self.TEXT_POOL_SIZE)
            _lf = self._locale_faker
            _addr_fn = (_lf.address if _lf else None) or self.text_gen.full_address
            _phone_fn = (_lf.phone_number if _lf else None) or self.text_gen.phone_number
            # "sentence" no longer means lorem ipsum: free-text notes come from
            # the seeded business-note grammar, which composes thousands of
            # distinct human-looking sentences.
            _note_fn = lambda: str(self.realistic_text.microtext.notes(1)[0])  # noqa: E731
            _LEGACY_GEN_MAP = {
                "sentence": (_note_fn,               "text_sentence"),
                "word":     (self.text_gen.word,     "text_word"),
                "address":  (_addr_fn,               f"text_address_{self.locale}"),
                "phone":    (_phone_fn,               f"text_phone_{self.locale}"),
                "url":      (self.text_gen.url,       "text_url"),
            }
            gen_fn, pool_key = _LEGACY_GEN_MAP.get(text_type, (_note_fn, "text_sentence"))
            if pool_key not in self._text_pools:
                self._text_pools[pool_key] = np.array([gen_fn() for _ in range(_pool_size)])
            elif len(self._text_pools[pool_key]) < size:
                extra = [gen_fn() for _ in range(_pool_size - len(self._text_pools[pool_key]))]
                self._text_pools[pool_key] = np.concatenate([self._text_pools[pool_key], extra])
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
        df_batch = self._apply_correlations(df_batch, table_name)
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

        # Always accumulate the full PK array so FK sampling is unbiased
        # regardless of how large the parent table grows.  The context itself
        # is still capped (for memory), but _pk_store is PK-only and cheap.
        if "id" in df.columns:
            pk_vals = df["id"].dropna().values
            if table_name in self._pk_store:
                self._pk_store[table_name] = np.concatenate(
                    [self._pk_store[table_name], pk_vals]
                )
            else:
                self._pk_store[table_name] = pk_vals

        ctx_df = df[cols_to_store].copy()

        if table_name not in self.context:
            if len(ctx_df) > self.MAX_CONTEXT_ROWS:
                ctx_df = ctx_df.sample(n=self.MAX_CONTEXT_ROWS, random_state=int(self.rng.integers(0, 2**31)))
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
                # Gap 3: build temporal density map from the FactGenerationPlan so
                # child tables can weight FK/date sampling by parent temporal density.
                # We derive the density from the actual data since the plan is local
                # to _generate_fact_table.  Using the first exact curve's time column.
                _curve_time_col = getattr(exact_curves[0], "time_column", "date")
                self._parent_temporal_density[table_name] = TemporalDensityMap.from_dataframe(
                    table=table_name,
                    time_column=_curve_time_col,
                    df=fact_df,
                )
                # Gap 1: enforce RateCurve targets (proportional pass — preserves AME=0).
                fact_df = self._apply_rate_curves(fact_df, table_name)
                self._update_context(table_name, fact_df)
                output_df = self._apply_configured_noise(fact_df.copy(), table_name, table)
                yield output_df
                return

        # A 0-row table is a valid (empty) table — emit it with its columns so it
        # still appears in the output and any child FK lookup finds an empty parent
        # rather than a missing key.
        if total_rows == 0:
            empty = pd.DataFrame({c.name: pd.Series(dtype="object") for c in columns})
            self._update_context(table_name, empty)
            yield empty
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

            # Apply conditional / MAR missingness (null_when, missing_if)
            df_batch = self._apply_informative_missingness(df_batch, table_name)

            # Apply legacy conditional nulls (null_if)
            df_batch = self._apply_null_if(df_batch, table_name)

            # Apply exact incidence control (exact_incidence mode)
            df_batch = self._apply_exact_incidence(df_batch, table_name)

            # Apply within-entity time-series autocorrelation (time_series spec)
            df_batch = self._apply_time_series_columns(df_batch, table_name)

            # Apply state machine terminal states (__state_machine__)
            df_batch = self._apply_state_machine(df_batch, table_name)

            # Apply hierarchical ICC cluster effects from parent tables
            df_batch = self._apply_cluster_effects(df_batch, table_name)

            # Apply column correlations (Iman-Conover)
            df_batch = self._apply_correlations(df_batch, table_name)

            # Post-process
            df_batch = self._fix_correlated_columns(df_batch, table_name)

            # Apply events
            table_events = [e for e in self.config.events if e.table == table_name]
            for event in table_events:
                df_batch = self.apply_event(df_batch, event)

            # Apply business rule constraints
            df_batch = self.apply_constraints(df_batch, table)

            # Re-apply formulas AFTER constraints: a constraint may change a base column
            # (e.g. cap daily hours), and any formula derived from it (billed = hours * rate)
            # must reflect the constrained value, not the pre-constraint one. Formulas are
            # idempotent, so re-running is safe when nothing changed.
            df_batch = self._apply_formula_columns(df_batch, table_name)

            # Apply per-column anomaly injection
            df_batch = self._apply_anomalies(df_batch, table_name)

            # Apply outcome curves (Trends/Seasonality)
            df_batch = self.apply_outcome_curves(df_batch, table_name)

            # Gap 1: enforce RateCurve targets (post-generation proportional pass).
            # Runs after apply_outcome_curves so numeric aggregates are untouched.
            df_batch = self._apply_rate_curves(df_batch, table_name)

            # Gap B: relative-curve cross-batch sum correction.
            # For tables using relative curves (not exact), accumulate running
            # per-period totals and apply a correction factor per batch so the
            # final sum per period converges to the implied target.
            df_batch = self._rebalance_relative_batch(df_batch, table_name)

            # Apply null_rate / nullable nulls LAST — after correlations,
            # time-series, and rate curves, so the statistical passes see full
            # values and MNAR/MAR conditions are evaluated on final values.
            df_batch = self._apply_null_rates(df_batch, table_name)

            # Update context for future batches/tables
            self._update_context(table_name, df_batch)
            output_df = self._apply_configured_noise(df_batch.copy(), table_name, table)
            yield output_df

            rows_generated += batch_size

        # Gap C: propagate temporal density map transitively to this table
        # so that its children can weight FK sampling by the inherited density.
        self._propagate_density_map(table_name)

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
                    scaling_factors = np.ones(13)  # Index 1-12

                    x_known = np.array([p['month'] for p in points])
                    y_known = np.array([p['relative_value'] for p in points])

                    # Cyclic interpolation: wrap months outside declared range
                    # around the 12-month cycle instead of clamping to endpoints.
                    x_cyclic = np.concatenate([x_known - 12, x_known, x_known + 12])
                    y_cyclic = np.concatenate([y_known, y_known, y_known])

                    for m in range(1, 13):
                        scaling_factors[m] = np.interp(m, x_cyclic, y_cyclic)

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

                        # Normalize x_known to 0.0-1.0 relative to its own range so
                        # multi-year curves (e.g. month indices 1-36) work correctly.
                        x_range = max(x_known.max() - x_known.min(), 1.0)
                        x_known_norm = (x_known - x_known.min()) / x_range

                        row_factors = np.interp(t_norm, x_known_norm, y_known)

                # Apply!
                df[target_col] = df[target_col] * row_factors
                
            except Exception as e:
                warnings.warn(f"Failed to apply outcome curve for {table_name}: {e}")
                continue
                
        return df

    # ------------------------------------------------------------------
    # Gap 1 — RateCurve enforcement
    # ------------------------------------------------------------------

    def _apply_rate_curves(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Enforce exact per-period rate targets for boolean/categorical columns.

        Implements the Rate-Conformance (RCE) axis from the SpecBench paper
        (arXiv:2606.08736v1, §4).  For each ``RateCurve`` attached to this
        table, the method:

        1. Groups rows by period using the declared ``time_column``.
        2. Resolves the target rate for each observed period via optional linear
           interpolation between anchor points (``RateCurve.interpolate=True``).
        3. Flips exactly ``round(n_period × rate)`` rows to ``true_value`` using
           the Prop. 2 integer-rounding + remainder-correction algorithm that the
           FactEngine uses for aggregate targets — guaranteeing RCE = 0 per period.

        This is a **pure post-generation pass**: it changes *which* rows are
        classified as positive but never mutates any numeric aggregate column,
        so the FactEngine's AME = 0 guarantee is preserved.
        """
        rate_curves = getattr(self.config, "rate_curves", None)
        if not rate_curves:
            return df

        table_curves = [rc for rc in rate_curves if getattr(rc, "table", None) == table_name]
        if not table_curves:
            return df

        for rc in table_curves:
            if rc.column not in df.columns:
                warnings.warn(
                    f"RateCurve: column '{rc.column}' not found in '{table_name}'. "
                    "Skipping rate enforcement."
                )
                continue
            if rc.time_column not in df.columns:
                warnings.warn(
                    f"RateCurve: time_column '{rc.time_column}' not found in "
                    f"'{table_name}'. Skipping rate enforcement."
                )
                continue
            if not rc.rate_points:
                continue
            df = self._enforce_rate_curve(df, rc)

        return df

    def _enforce_rate_curve(self, df: pd.DataFrame, rc: Any) -> pd.DataFrame:
        """Enforce one ``RateCurve`` using the Prop. 2 remainder-corrected algorithm.

        For each observed monthly period, the target rate is resolved (with
        optional interpolation), then exactly ``round(n_period × rate)`` rows
        are randomly selected to carry ``rc.true_value``.

        Args:
            df: The table DataFrame to mutate (a copy is made internally).
            rc: A ``RateCurve`` Pydantic model instance.
        Returns:
            Modified copy of ``df`` with the rate constraint enforced.
        """
        timestamps = pd.to_datetime(df[rc.time_column], errors="coerce")
        if timestamps.isna().all():
            return df

        # ── Parse anchor points ──────────────────────────────────────────
        # rate_points: [{"period": "2024-01" | "01" | integer_month | "all", "rate": 0.03}]
        # Anchors are stored as (year, month) tuples for YYYY-MM formats, or as
        # bare 1-based month integers for the short forms.  We convert everything
        # to running-month indices AFTER we know the data's start_year/start_month
        # so that multi-year curves ("2025-01" → idx 1, "2026-01" → idx 13) are
        # handled correctly rather than silently colliding on the bare month number.
        ym_anchors: Dict[tuple, float] = {}   # (year, month) → rate  (YYYY-MM form)
        bare_anchors: Dict[int, float] = {}   # 1-based running index → rate (short form)
        all_period_rate: Optional[float] = None

        for point in rc.rate_points:
            period_str = str(point.get("period", "")).strip()
            rate = float(point.get("rate", 0.0))

            if period_str.lower() == "all":
                all_period_rate = rate
                continue
            # YYYY-MM — store with year so multi-year curves don't collide
            if len(period_str) == 7 and period_str[4] == "-":
                try:
                    y, m = int(period_str[:4]), int(period_str[5:])
                    ym_anchors[(y, m)] = rate
                    continue
                except ValueError:
                    pass
            # "01" … "12" → bare month integer (single-year shorthand)
            if period_str.isdigit() and 1 <= int(period_str) <= 12:
                bare_anchors[int(period_str)] = rate
                continue
            # bare integer > 12 → period index (1-based running month)
            try:
                bare_anchors[int(period_str)] = rate
            except ValueError:
                warnings.warn(f"RateCurve: unrecognised period format '{period_str}'. Skipping anchor.")

        if not ym_anchors and not bare_anchors and all_period_rate is None:
            return df

        # ── Compute 1-based running month index for every row ────────────
        valid_ts = timestamps.dropna()
        if valid_ts.empty:
            return df
        start_year = int(valid_ts.dt.year.min())
        start_month = int(valid_ts.dt.month.min())

        row_month_idx = (
            (timestamps.dt.year - start_year) * 12
            + (timestamps.dt.month - start_month)
            + 1
        ).fillna(-1).astype(int)

        # Convert YYYY-MM anchors to running indices now that we know the origin
        anchors: Dict[int, float] = dict(bare_anchors)
        for (y, m), rate in ym_anchors.items():
            running_idx = (y - start_year) * 12 + (m - start_month) + 1
            anchors[running_idx] = rate

        # ── Interpolate rates across all observed period indices ──────────
        observed_indices = sorted(idx for idx in row_month_idx.unique() if idx > 0)
        if not observed_indices:
            return df

        max_idx = max(observed_indices)
        interp_months = np.arange(1, max_idx + 1, dtype=float)

        # "all" sentinel: flat rate across every period — fill anchors for
        # all observed indices if no explicit anchors were provided, or if
        # there are observed months not covered by explicit anchors.
        if all_period_rate is not None:
            for obs_idx in observed_indices:
                anchors.setdefault(obs_idx, all_period_rate)

        anchor_months = np.array(sorted(anchors.keys()), dtype=float)
        anchor_rates = np.array([anchors[int(m)] for m in anchor_months], dtype=float)

        if rc.interpolate and len(anchor_months) >= 2:
            interp_rates = np.clip(
                np.interp(interp_months, anchor_months, anchor_rates), 0.0, 1.0
            )
        else:
            # Nearest-anchor (no interpolation): only declared periods are constrained
            interp_rates = np.full(len(interp_months), np.nan)
            for i, m in enumerate(interp_months):
                if int(m) in anchors:
                    interp_rates[i] = anchors[int(m)]

        month_to_rate = {
            int(m): float(r)
            for m, r in zip(interp_months, interp_rates)
            if not np.isnan(r)
        }

        # ── Prop. 2 enforcement per period ───────────────────────────────
        df = df.copy()
        true_val = rc.true_value

        # For a string categorical (true_value is one of several labels), the
        # negative class must be reassigned to a DIFFERENT label — otherwise the
        # base incidence of true_value leaks on top of the declared rate. Capture
        # the other labels from the originally-generated values, once.
        other_labels = None
        if not isinstance(true_val, bool) and isinstance(true_val, str):
            other_labels = [
                v for v in pd.unique(df[rc.column])
                if v != true_val and pd.notna(v)
            ]

        for month_idx, target_rate in month_to_rate.items():
            period_mask = row_month_idx == month_idx
            if not period_mask.any():
                continue

            period_indices = df.index[period_mask].to_numpy()
            n_period = len(period_indices)

            # Exact positive-class count: Prop. 2 binomial rounding
            target_count = int(round(n_period * target_rate))
            target_count = max(0, min(n_period, target_count))

            # Randomly choose which rows become the positive class
            chosen_pos = self.rng.choice(period_indices, size=target_count, replace=False)
            chosen_pos_set = set(chosen_pos.tolist())
            chosen_neg = period_indices[~np.isin(period_indices, chosen_pos)]

            df.loc[chosen_pos, rc.column] = true_val

            # Assign negative class
            if isinstance(true_val, bool):
                df.loc[chosen_neg, rc.column] = not true_val
            elif true_val is True:
                df.loc[chosen_neg, rc.column] = False
            elif true_val is False:
                df.loc[chosen_neg, rc.column] = True
            elif isinstance(true_val, (int, float)):
                # For numeric "flags" (0 vs true_val): set non-positives to 0
                df.loc[chosen_neg, rc.column] = 0
            elif other_labels:
                # String categorical: any negative row currently holding true_val
                # would leak above the target rate. Reassign those to another label
                # so the realised rate of true_val equals the declared rate exactly.
                neg_vals = df.loc[chosen_neg, rc.column].to_numpy()
                leak = chosen_neg[neg_vals == true_val]
                if len(leak) > 0:
                    df.loc[leak, rc.column] = self.rng.choice(other_labels, size=len(leak))
            # (no other labels available → degenerate single-category column, leave as-is)

        return df

    # ------------------------------------------------------------------
    # Gap B — Relative-curve cross-batch accumulation
    # ------------------------------------------------------------------

    def _rebalance_relative_batch(
        self,
        df: pd.DataFrame,
        table_name: str,
    ) -> pd.DataFrame:
        """Correct per-period sums so relative curves converge across batches.

        Context
        -------
        ``apply_outcome_curves`` applies relative multipliers independently per
        batch.  This is correct for shaping but doesn't guarantee any specific
        sum across the full table.  When the user supplies a relative curve with
        an avg_transaction_value and a row_count, we can derive an implied total
        target and correct toward it batch by batch.

        Algorithm (Prop. 2 analogue for floating-point)
        -----------------------------------------------
        For each period *p* with implied target *T_p*:
        1. Compute *B_p* = sum of the metric column for rows in this batch that
           fall in period *p*.
        2. Look up *R_p* = running total so far (before this batch).
        3. If *B_p* > 0 and *T_p* > *R_p*, apply a multiplicative correction:
               factor = (T_p - R_p) / B_p
           This scales the batch values so that after the batch the running total
           reaches exactly *T_p* (to floating-point precision).
        4. Update *R_p* += factor × *B_p*.

        Conservative guards
        -------------------
        * Only applies to relative-curve columns (NOT exact/absolute curves which
          go through FactEngine and need no correction).
        * Skips the batch if the implied target cannot be resolved.
        * Clamps the correction factor to [0.1, 10.0] to prevent extreme scaling.
        * The running total is per-simulator-instance so the correction is
          consistent across the streaming batch loop.
        """
        relative_curves = [
            c for c in getattr(self.config, "outcome_curves", [])
            if getattr(c, "table", None) == table_name
            and not self.fact_engine.curve_has_exact_targets(c)
        ]
        if not relative_curves:
            return df

        table = self.config.get_table(table_name)
        total_rows = self._planned_row_count(table_name, getattr(table, "row_count", len(df)))
        if total_rows <= 0:
            return df

        # Initialise the running-total dict for this table
        if table_name not in self._relative_curve_totals:
            self._relative_curve_totals[table_name] = {}

        df = df.copy()
        rt = self._relative_curve_totals[table_name]

        for curve in relative_curves:
            col = getattr(curve, "column", None)
            time_col = getattr(curve, "time_column", None)
            points = getattr(curve, "curve_points", []) or []
            avg_tx = getattr(curve, "avg_transaction_value", None)

            if not col or not time_col:
                continue
            if col not in df.columns or time_col not in df.columns:
                continue
            if not points or avg_tx is None or avg_tx <= 0:
                continue

            timestamps = pd.to_datetime(df[time_col], errors="coerce")

            # Build a per-month relative factor for ALL 12 months by linear interpolation
            # between control points (previously only control-point months were corrected,
            # which left interpolated months uncorrected and drifted the shape in multi-batch
            # streaming). Control points outside [1,12] are ignored.
            ctrl: Dict[int, float] = {}
            for point in points:
                if hasattr(point, "month"):
                    m = int(point.month); rv = float(getattr(point, "relative_value", 1.0))
                elif isinstance(point, dict):
                    m = int(point.get("month", 0))
                    rv = float(point.get("relative_value", point.get("target_value", 1.0)))
                else:
                    continue
                if 1 <= m <= 12:
                    ctrl[m] = rv
            if not ctrl:
                continue
            ctrl_months = sorted(ctrl)
            month_factor: Dict[int, float] = {}
            for m in range(1, 13):
                if m in ctrl:
                    month_factor[m] = ctrl[m]
                elif m <= ctrl_months[0]:
                    month_factor[m] = ctrl[ctrl_months[0]]
                elif m >= ctrl_months[-1]:
                    month_factor[m] = ctrl[ctrl_months[-1]]
                else:
                    lo = max(c for c in ctrl_months if c <= m)
                    hi = min(c for c in ctrl_months if c >= m)
                    frac = (m - lo) / (hi - lo)
                    month_factor[m] = ctrl[lo] + frac * (ctrl[hi] - ctrl[lo])

            # Implied per-row mean for a month = avg_tx * (month_factor / mean_factor), so the
            # overall table mean stays ~avg_tx and only the SHAPE follows the curve. The
            # per-month target is that mean times the month's ACTUAL accumulated row count
            # (tracked across batches), not a uniform total_rows/12 assumption.
            mean_factor = sum(month_factor.values()) / 12.0
            if mean_factor <= 0:
                continue

            count_key_prefix = f"{col}:cnt_month_"
            sum_key_prefix = f"{col}:sum_month_"

            for month_idx in range(1, 13):
                batch_month_mask = timestamps.dt.month == month_idx
                n_batch = int(batch_month_mask.sum())
                if n_batch == 0:
                    continue
                batch_sum = float(df.loc[batch_month_mask, col].sum())
                if batch_sum <= 0:
                    continue

                ckey = count_key_prefix + str(month_idx)
                skey = sum_key_prefix + str(month_idx)
                prev_count = rt.get(ckey, 0.0)
                prev_sum = rt.get(skey, 0.0)

                new_count = prev_count + n_batch
                per_row_target = avg_tx * (month_factor[month_idx] / mean_factor)
                cumulative_target = per_row_target * new_count

                remaining = cumulative_target - prev_sum
                correction = np.clip(remaining / batch_sum, 0.1, 10.0) if remaining > 0 else 1.0
                if abs(correction - 1.0) > 1e-9:
                    df.loc[batch_month_mask, col] = df.loc[batch_month_mask, col] * correction

                rt[ckey] = new_count
                rt[skey] = prev_sum + float(df.loc[batch_month_mask, col].sum())

        return df

    # ------------------------------------------------------------------
    # Gap C — Deep hierarchy temporal density propagation
    # ------------------------------------------------------------------

    def _propagate_density_map(self, table_name: str) -> None:
        """Transitively push temporal density from ancestors to ``table_name``.

        After every table is fully generated, this method checks whether any
        parent of ``table_name`` has a ``TemporalDensityMap``.  If so, and
        ``table_name`` doesn't already have its own map, we create a proxy
        map via ``TemporalDensityMap.from_parent_weights()`` so that
        *grandchild* tables can later do Level-1 FK weighting relative to
        ``table_name``'s density — which transitively reflects the grandparent's
        temporal curve.

        This enables full multi-level hierarchy temporal coherence without any
        user configuration::

            regions (curve) → stores (proxy) → sales (proxy)

        In this chain, ``sales.store_id`` will be weighted by ``stores``' proxy
        density, which reflects ``regions``' exact curve.
        """
        if table_name in self._parent_temporal_density:
            return  # Already has its own map (exact or previously propagated)

        # Find all parent tables of table_name via FK relationships
        for rel in self.config.relationships:
            if rel.child_table != table_name:
                continue
            parent_map = self._parent_temporal_density.get(rel.parent_table)
            if parent_map is None or not parent_map.buckets:
                continue

            # Resolve the best time column for this child table
            child_time_col = "date"
            child_cols = {c.name for c in self.config.get_columns(table_name)}
            for candidate in TemporalDensityMap._TIME_CANDIDATES:
                if candidate in child_cols:
                    child_time_col = candidate
                    break
            else:
                for col in self.config.get_columns(table_name):
                    if col.type == "date":
                        child_time_col = col.name
                        break

            self._parent_temporal_density[table_name] = TemporalDensityMap.from_parent_weights(
                child_table=table_name,
                child_time_column=child_time_col,
                parent_map=parent_map,
            )
            return  # Use the first parent that has a map

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
                random_state=int(self.rng.integers(0, 2**31)),
            ).reset_index(drop=True)
            sampled_series = pd.concat([sampled_series, extra], ignore_index=True)
        elif len(sampled_series) > len(clean_timestamps):
            sampled_series = sampled_series.iloc[:len(clean_timestamps)].reset_index(drop=True)

        return sampled_series.sample(frac=1.0, random_state=int(self.rng.integers(0, 2**31))).reset_index(drop=True)

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

        elif constraint.type == "inequality":
            # Row-level ordering rule: column_a OP column_b (e.g. end_date >= start_date).
            df = self._apply_inequality_constraint(df, constraint)

        elif constraint.type == "col_range":
            # Row-level bound: low_column <= column <= high_column (e.g. bid <= sale <= list).
            df = self._apply_col_range_constraint(df, constraint)

        return df

    # Comparison operators reachable from inequality/col_range constraints.
    _OPS = {
        ">":  lambda a, b: a > b,
        ">=": lambda a, b: a >= b,
        "<":  lambda a, b: a < b,
        "<=": lambda a, b: a <= b,
    }

    def _apply_inequality_constraint(self, df: pd.DataFrame, constraint: Any) -> pd.DataFrame:
        """Enforce ``column_a <op> column_b`` on every row.

        action="drop" removes violating rows; action="cap" snaps column_a onto
        column_b so the inequality holds (works for numeric and datetime columns).
        Rows where either side is null are left untouched — the rule only governs
        fully-populated pairs.
        """
        a, b, op = constraint.column_a, constraint.column_b, constraint.operator
        if not a or not b or op not in self._OPS:
            warnings.warn(f"Constraint '{constraint.name}': needs column_a, column_b and a valid operator. Skipping.")
            return df
        if a not in df.columns or b not in df.columns:
            warnings.warn(f"Constraint '{constraint.name}': column '{a}' or '{b}' not found. Skipping.")
            return df

        col_a, col_b = df[a], df[b]
        both_present = col_a.notna() & col_b.notna()
        satisfied = self._OPS[op](col_a, col_b)
        violating = both_present & ~satisfied
        if not violating.any():
            return df

        if constraint.action == "drop":
            return df.loc[~violating].reset_index(drop=True)

        # cap (default): set the violating column_a equal to column_b so the
        # boundary case satisfies >=/<=; for strict >/< this lands on the edge,
        # which is the closest feasible value without inventing a gap.
        df.loc[violating, a] = col_b[violating].values
        return df

    def _apply_col_range_constraint(self, df: pd.DataFrame, constraint: Any) -> pd.DataFrame:
        """Enforce ``low_column <= column <= high_column`` on every row.

        action="cap" (default) clips the middle column into the row's bounds;
        action="drop" removes rows that fall outside. Null bounds or values are
        left untouched.
        """
        col = constraint.column
        low, high = constraint.low_column, constraint.high_column
        if not col or not low or not high:
            warnings.warn(f"Constraint '{constraint.name}': needs column, low_column and high_column. Skipping.")
            return df
        for c in (col, low, high):
            if c not in df.columns:
                warnings.warn(f"Constraint '{constraint.name}': column '{c}' not found. Skipping.")
                return df

        mid, lo, hi = df[col], df[low], df[high]
        present = mid.notna() & lo.notna() & hi.notna()
        out_of_range = present & ((mid < lo) | (mid > hi))
        if not out_of_range.any():
            return df

        if constraint.action == "drop":
            return df.loc[~out_of_range].reset_index(drop=True)

        # cap (default): clip into [lo, hi] row-wise.
        df.loc[present, col] = mid[present].clip(lower=lo[present], upper=hi[present])
        return df

    def _domain_hour_weights(self) -> list:
        """Hour-of-day rhythm for human actions, by domain.

        - ecommerce/food: peaks lunch + evening
        - fintech/hr: business hours 9-5
        - gaming/social: evening + night heavy
        - default: mild daytime bias
        """
        domain = (self.config.domain or "").lower()

        if domain in ("ecommerce", "fooddelivery", "marketplace"):
            # Peaks: 11am-2pm lunch, 7pm-10pm evening
            return [1,1,1,1,1,1,2,3,5,7,9,12,13,12,10,8,7,10,14,15,12,8,4,2]
        if domain in ("fintech", "hr", "healthcare", "realestate"):
            # Business hours 8am-6pm
            return [1,1,1,1,1,2,4,8,14,16,16,15,13,15,16,14,12,8,5,3,2,2,1,1]
        if domain in ("gaming", "social"):
            # Evening/night heavy: 6pm-2am
            return [8,6,4,3,2,1,1,1,2,3,4,5,6,6,6,6,8,10,14,16,18,18,16,12]
        if domain in ("saas", "edtech"):
            # Workday with morning/afternoon bias
            return [1,1,1,1,1,2,4,9,14,16,15,13,12,14,15,13,11,8,5,4,3,2,2,1]
        # Generic mild daytime bias
        return [1,1,1,1,1,2,4,7,10,12,12,11,11,12,12,11,10,9,7,6,4,3,2,1]

    def _add_realistic_time(
        self,
        dates: pd.DatetimeIndex,
        table_name: str,
        size: int,  # noqa: ARG002 — kept for call-site compatibility
        column_name: str = "",
    ) -> pd.DatetimeIndex:
        """Shape datetimes with the temporal profile their semantics demand."""
        from misata.temporal_profiles import apply_temporal_profile, classify_temporal

        profile = classify_temporal(column_name, table_name)
        return apply_temporal_profile(
            dates, profile, self.rng, domain_hour_weights=self._domain_hour_weights()
        )

    def _apply_anomalies(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Inject statistical outliers into columns that declare ``anomaly_rate``.

        For numeric columns: injects values 3–6 standard deviations from the
        column mean, randomly positive or negative direction.
        For categorical columns: replaces values with an ``"__anomaly__"``
        sentinel that downstream systems can detect and handle.

        Usage in schema::

            Column(name="price", type="float", distribution_params={
                "distribution": "lognormal", "mu": 4.0, "sigma": 0.8,
                "anomaly_rate": 0.02,   # 2 % of rows get outlier values
            })
        """
        columns = self.config.columns.get(table_name, [])
        for col in columns:
            rate = col.distribution_params.get("anomaly_rate", 0.0)
            if rate <= 0 or col.name not in df.columns:
                continue
            n = len(df)
            mask = self.rng.random(n) < rate
            if not mask.any():
                continue
            series = df[col.name]
            if pd.api.types.is_numeric_dtype(series):
                mean = float(series.mean())
                std  = float(series.std()) or 1.0
                magnitude = self.rng.uniform(3.0, 6.0, size=mask.sum())
                direction = self.rng.choice([-1, 1], size=mask.sum())
                df.loc[mask, col.name] = mean + direction * magnitude * std
            else:
                df.loc[mask, col.name] = "__anomaly__"
        return df

    # ------------------------------------------------------------------
    # Feature 5: Hierarchical cluster / ICC effects
    # ------------------------------------------------------------------

    def _apply_cluster_effects(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Apply per-parent-entity random intercepts (hierarchical ICC model).

        Defined on the PARENT table via ``__cluster_effect__``:

            __cluster_effect__:
              affects_table: visits
              affects_columns:
                hba1c:
                  icc: 0.12          # intraclass correlation coefficient
                  sd_total: 1.5      # optional; used to derive sd_between if not given
                  sd_between: 0.52   # std-dev of entity-level random intercepts
                systolic_bp:
                  icc: 0.18
                  sd_total: 18.0

        For each declared column the method:
          1. Looks up the FK from ``table_name`` → parent.
          2. Draws one random intercept per parent entity from N(0, sd_between).
          3. Adds that intercept to every child row belonging to that entity.

        ICC relationship: sd_between = sqrt(icc) * sd_total.
        Provide either sd_between directly or both icc + sd_total.
        """
        for parent_table in self.config.tables:
            spec = parent_table.cluster_effect
            if not spec or spec.get("affects_table") != table_name:
                continue
            col_specs = spec.get("affects_columns") or {}
            # Find FK from child → parent
            rel = next(
                (r for r in self.config.relationships
                 if r.child_table == table_name and r.parent_table == parent_table.name),
                None,
            )
            if rel is None or rel.child_key not in df.columns:
                continue
            parent_df = self.context.get(parent_table.name)
            if parent_df is None:
                continue
            entity_ids = df[rel.child_key].unique()

            for col_name, col_spec in col_specs.items():
                if col_name not in df.columns:
                    continue
                col_numeric = pd.to_numeric(df[col_name], errors="coerce")
                if col_numeric.isna().all():
                    continue
                if "sd_between" in col_spec:
                    sd_between = float(col_spec["sd_between"])
                else:
                    icc = float(col_spec.get("icc", 0.10))
                    sd_total = float(col_spec.get("sd_total", col_numeric.std() or 1.0))
                    sd_between = np.sqrt(icc) * sd_total

                # One random intercept per parent entity
                intercepts = {
                    eid: float(self.rng.normal(0, sd_between))
                    for eid in entity_ids
                }
                entity_intercept = df[rel.child_key].map(intercepts)
                original_dtype = df[col_name].dtype
                shifted = (col_numeric + entity_intercept).values
                if pd.api.types.is_integer_dtype(original_dtype):
                    shifted = np.round(shifted).astype(original_dtype)
                df[col_name] = shifted

        return df

    def _apply_correlations(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Re-rank numeric columns to achieve declared Pearson correlations.

        Uses the Iman-Conover method: generate a correlated normal copula,
        then re-order each column's *existing* values to match the target
        rank structure.  This preserves marginal distributions exactly while
        imposing the requested correlation structure.

        Declared via ``Table.correlations``:
            correlations=[{"col_a": "age", "col_b": "salary", "r": 0.65}]
        """
        table_obj = next((t for t in self.config.tables if t.name == table_name), None)
        if table_obj is None or not table_obj.correlations:
            return df

        # Collect all unique numeric columns involved in correlation specs
        involved: set[str] = set()
        for spec in table_obj.correlations:
            involved.add(spec["col_a"])
            involved.add(spec["col_b"])
        involved = {c for c in involved if c in df.columns and pd.api.types.is_numeric_dtype(df[c])}
        if len(involved) < 2:
            return df

        # A column that is BOTH correlated and an outcome-curve target gets
        # blockwise Iman-Conover: values are re-ranked only WITHIN each time
        # period bucket, a sum-preserving permutation, so the exact per-period
        # curve targets survive while the declared correlation is approximated
        # globally (slightly attenuated by the between-period structure).
        curve_col_meta: Dict[str, tuple] = {
            oc.column: (
                getattr(oc, "time_column", "date"),
                getattr(oc, "time_unit", "month"),
            )
            for oc in (getattr(self.config, "outcome_curves", None) or [])
            if getattr(oc, "table", None) == table_name
        }

        cols = sorted(involved)
        n = len(df)

        # Build target correlation matrix
        idx = {c: i for i, c in enumerate(cols)}
        k = len(cols)
        target_corr = np.eye(k)
        for spec in table_obj.correlations:
            a, b, r = spec["col_a"], spec["col_b"], float(spec["r"])
            if a in idx and b in idx:
                i, j = idx[a], idx[b]
                target_corr[i, j] = r
                target_corr[j, i] = r

        # Cholesky decomposition of target correlation matrix.
        # If the matrix is not positive-definite (over-specified or conflicting
        # pairwise entries), attempt nearest-PD repair via eigenvalue clipping
        # before giving up so the user still gets approximate correlations.
        try:
            L = np.linalg.cholesky(target_corr)
        except np.linalg.LinAlgError:
            try:
                vals, vecs = np.linalg.eigh(target_corr)
                vals = np.clip(vals, 1e-8, None)   # clip negative eigenvalues
                target_corr_pd = vecs @ np.diag(vals) @ vecs.T
                # Re-normalise to a true correlation matrix (diag = 1)
                d = np.sqrt(np.diag(target_corr_pd))
                target_corr_pd = target_corr_pd / np.outer(d, d)
                L = np.linalg.cholesky(target_corr_pd)
                warnings.warn(
                    f"Table '{table_name}': correlation matrix was not positive-definite "
                    "(conflicting or over-specified pairwise targets). Applied nearest-PD "
                    "repair — realized correlations will be close but not exact.",
                    stacklevel=2,
                )
            except np.linalg.LinAlgError:
                warnings.warn(
                    f"Table '{table_name}': correlation matrix could not be repaired. "
                    "Correlations skipped for this table.",
                    stacklevel=2,
                )
                return df

        # Generate correlated standard normals
        Z = self.rng.standard_normal((k, n))
        correlated = (L @ Z).T  # shape (n, k)

        # Iman-Conover: re-order each column's values to match the rank of the correlated normals
        for i, col in enumerate(cols):
            # Curve-governed column: sum-preserving blockwise re-rank.
            meta = curve_col_meta.get(col)
            if meta is not None:
                time_col, time_unit = meta
                if time_col in df.columns:
                    freq = {"day": "D", "week": "W", "month": "M",
                            "quarter": "Q", "year": "Y"}.get(str(time_unit), "M")
                    try:
                        buckets = pd.to_datetime(df[time_col], errors="coerce").dt.to_period(freq)
                    except Exception:
                        buckets = None
                    if buckets is not None and buckets.notna().any():
                        col_vals = df[col].values.copy()
                        for _, bucket_idx in df.groupby(buckets, dropna=False).indices.items():
                            if len(bucket_idx) < 2:
                                continue
                            block_sorted = np.sort(col_vals[bucket_idx])
                            block_ranks = np.argsort(np.argsort(correlated[bucket_idx, i]))
                            col_vals[bucket_idx] = block_sorted[block_ranks]
                        df[col] = col_vals
                        continue
            original = df[col].values.copy()
            target_ranks = np.argsort(np.argsort(correlated[:, i]))
            sorted_original = np.sort(original)
            df[col] = sorted_original[target_ranks]

        return df

    # ------------------------------------------------------------------
    # Stratified profiles (#6)
    # ------------------------------------------------------------------

    def _generate_column_with_profiles(
        self,
        column: Column,
        profiles: list,
        base_params: dict,
        table_data: pd.DataFrame,
        size: int,
    ) -> np.ndarray:
        """Generate values from different distributions per subgroup.

        Each profile carries a ``when`` expression (evaluated with
        ``DataFrame.eval``) and any distribution params that override the
        column's top-level params for matching rows.  Rows that match no
        profile fall back to the base distribution.
        """
        result = np.empty(size, dtype=object)
        result[:] = np.nan
        remaining = np.ones(size, dtype=bool)

        for profile in profiles:
            when = profile.get("when", "")
            if when:
                try:
                    mask = table_data.eval(when).values.astype(bool)
                except Exception:
                    mask = np.zeros(size, dtype=bool)
            else:
                mask = np.ones(size, dtype=bool)

            mask = mask & remaining
            n = int(mask.sum())
            if n == 0:
                continue

            # Build a temporary column spec merging base params with profile overrides
            merged = {**base_params, **{k: v for k, v in profile.items() if k != "when"}}
            merged.pop("profiles", None)
            from misata.schema import Column as _Col
            temp_col = _Col(
                name=column.name,
                type=column.type,
                distribution_params=merged,
                unique=False,
            )
            vals = self.generate_column(column.name + "__profile__", temp_col, n, table_data[mask].reset_index(drop=True))
            result[mask] = vals
            remaining = remaining & ~mask

        # Fallback for unmatched rows
        n_rem = int(remaining.sum())
        if n_rem > 0:
            fallback_params = {k: v for k, v in base_params.items() if k != "profiles"}
            from misata.schema import Column as _Col
            fallback_col = _Col(
                name=column.name,
                type=column.type,
                distribution_params=fallback_params,
                unique=False,
            )
            vals = self.generate_column(column.name + "__fallback__", fallback_col, n_rem)
            result[remaining] = vals

        # Cast to a sensible dtype
        try:
            if column.type in ("int",):
                return result.astype(float).astype("Int64")
            elif column.type in ("float",):
                return result.astype(float)
            elif column.type == "boolean":
                return result.astype(bool)
        except Exception:
            pass
        return result

    # ------------------------------------------------------------------
    # null_rate / nullable — applied last so statistical passes see values
    # ------------------------------------------------------------------

    def _apply_null_rates(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Honour each column's explicit ``null_rate``.

        Nulls are only injected when a column declares an explicit ``null_rate``
        > 0. ``nullable: true`` alone never introduces nulls: it defaults to
        true for every dict-schema column, so treating it as "inject ~5%" would
        silently riddle every column with missing values. Set ``null_rate`` to
        control missingness explicitly (or use ``__noise__`` for table-wide
        rates).

        Primary-key, unique, and foreign-key columns are always skipped —
        nulling those would break referential integrity.
        """
        pk_cols = {
            c.name for c in self.config.get_columns(table_name)
            if c.name == "id" or getattr(c, "unique", False)
        }
        fk_cols = {
            r.child_key for r in self.config.relationships if r.child_table == table_name
        }
        protected = pk_cols | fk_cols

        for col in self.config.get_columns(table_name):
            if col.name not in df.columns or col.name in protected:
                continue
            params = col.distribution_params
            null_rate = params.get("null_rate")
            # Only apply explicit null_rate — nullable=True is the default for
            # all columns and should not silently introduce nulls unless the
            # user explicitly declares a rate.
            if null_rate is None:
                continue
            null_rate = float(null_rate)
            if null_rate <= 0:
                continue
            mask = pd.Series(self.rng.random(len(df)) < null_rate, index=df.index)
            _null_column(df, col.name, mask)
        return df

    # ------------------------------------------------------------------
    # Informative missingness (#3): MAR / conditional null
    # ------------------------------------------------------------------

    def _apply_informative_missingness(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Apply Missing-At-Random (MAR) and conditional null patterns.

        Column spec:
            missing_if:
              predictor: hba1c_baseline          # another column in the same row
              relationship: higher_increases_probability   # or lower_increases_probability
              base_rate: 0.05                    # null rate when predictor is at its median
              max_rate: 0.40                     # null rate at the extreme of the predictor
              mechanism: MAR                     # MAR (default) or MCAR

        The probability of a null scales linearly from ``base_rate`` at the
        predictor's 10th-percentile to ``max_rate`` at its 90th-percentile
        (or reversed for ``lower_increases_probability``).

        Also handles the simpler conditional form:
            null_when: "status == 'inactive'"   # pandas eval expression
        """
        columns = self.config.columns.get(table_name, [])
        for col in columns:
            params = col.distribution_params

            # --- null_when: simple boolean expression ---
            null_when = params.get("null_when")
            if null_when and col.name in df.columns:
                try:
                    mask = df.eval(null_when).values.astype(bool)
                    _null_column(df, col.name, pd.Series(mask, index=df.index))
                except Exception:
                    pass

            # --- missing_if: MAR ---
            spec = params.get("missing_if")
            if not spec or col.name not in df.columns:
                continue
            predictor = spec.get("predictor")
            if not predictor or predictor not in df.columns:
                continue

            mechanism = spec.get("mechanism", "MAR").upper()
            base_rate = float(spec.get("base_rate", 0.05))
            max_rate = float(spec.get("max_rate", 0.30))
            rel = spec.get("relationship", "higher_increases_probability")

            if mechanism == "MNAR":
                # Missing Not At Random: null probability tied to the column's
                # own (unobserved) value. Generate the values, scale null prob
                # against the column itself, then null the selected rows.
                own_vals = pd.to_numeric(df[col.name], errors="coerce")
                p10 = float(own_vals.quantile(0.10))
                p90 = float(own_vals.quantile(0.90))
                rng_width = p90 - p10 if p90 > p10 else 1.0
                normed = ((own_vals - p10) / rng_width).clip(0, 1)
                if rel == "lower_increases_probability":
                    normed = 1.0 - normed
                null_probs = base_rate + (max_rate - base_rate) * normed
                draw = pd.Series(self.rng.random(len(df)), index=df.index)
                _null_column(df, col.name, draw < null_probs)
                continue

            # MAR: null probability tied to an observed predictor column
            pred_vals = pd.to_numeric(df[predictor], errors="coerce")
            nan_pred_mask = pred_vals.isna()

            p10 = float(pred_vals.quantile(0.10))
            p90 = float(pred_vals.quantile(0.90))
            rng_width = p90 - p10 if p90 > p10 else 1.0

            normed = ((pred_vals - p10) / rng_width).clip(0, 1)
            if rel == "lower_increases_probability":
                normed = 1.0 - normed

            null_probs = base_rate + (max_rate - base_rate) * normed
            # Rows where predictor is NaN have no information → use base_rate
            null_probs[nan_pred_mask] = base_rate
            draw = pd.Series(self.rng.random(len(df)), index=df.index)
            _null_column(df, col.name, draw < null_probs)

        return df

    # ------------------------------------------------------------------
    # Exact incidence control (#4)
    # ------------------------------------------------------------------

    def _apply_exact_incidence(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Replace probabilistic boolean/categorical incidence with exact counts.

        Column spec (boolean example):
            is_adverse_event:
              type: boolean
              exact_incidence:
                mode: exact
                rate: 0.22                     # 22% of rows become True
                group_by: arm                  # optional: apply per group
                rates:                         # optional: per-group rates
                  placebo: 0.15
                  low_dose: 0.22
                  high_dose: 0.08

        Under ``mode: exact`` the engine computes ``floor(n * rate)`` True
        values and distributes them randomly within the group.  The remaining
        rows are always False.  This eliminates Bernoulli sampling noise so
        the generated dataset is auditable against its own spec.
        """
        columns = self.config.columns.get(table_name, [])
        for col in columns:
            spec = col.distribution_params.get("exact_incidence")
            if not spec or spec.get("mode", "probabilistic") != "exact":
                continue
            if col.name not in df.columns:
                continue

            group_by = spec.get("group_by")
            global_rate = float(spec.get("rate", 0.5))
            per_group_rates: dict = spec.get("rates", {})

            if group_by and group_by in df.columns and per_group_rates:
                values = np.zeros(len(df), dtype=bool)
                for grp, rate in per_group_rates.items():
                    idx = np.where(df[group_by].astype(str) == str(grp))[0]
                    n_true = int(round(len(idx) * float(rate)))
                    n_true = min(n_true, len(idx))
                    if n_true > 0:
                        chosen = self.rng.choice(len(idx), size=n_true, replace=False)
                        values[idx[chosen]] = True
                df[col.name] = values
            else:
                n = len(df)
                n_true = int(round(n * global_rate))
                values = np.zeros(n, dtype=bool)
                chosen = self.rng.choice(n, size=n_true, replace=False)
                values[chosen] = True
                df[col.name] = self.rng.permutation(values)

        return df

    # ------------------------------------------------------------------
    # Temporal / AR(1) time series (#1)
    # ------------------------------------------------------------------

    def _apply_time_series_columns(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Generate within-entity autocorrelated sequences for longitudinal data.

        Column spec:
            hba1c:
              type: float
              time_series:
                entity_id: patient_id          # groups rows into per-entity series
                order_by: visit_number         # sort key within each entity
                model: AR1                     # AR1 | linear_trend | random_walk | mean_reversion
                phi: 0.72                      # AR(1) autocorrelation coefficient
                noise_std: 0.30               # per-step noise std-dev
                anchor_column: hba1c_baseline  # starting value column (same table or @parent.col)
                trend:
                  slope_mean: -0.08            # mean slope per step
                  slope_std: 0.02              # per-entity slope variability

        The column must already exist in ``df`` (seeded from its base
        distribution).  This pass re-writes its values to follow the declared
        autocorrelation structure within each entity group.
        """
        columns = self.config.columns.get(table_name, [])
        for col in columns:
            spec = col.distribution_params.get("time_series")
            if not spec or col.name not in df.columns:
                continue

            entity_id = spec.get("entity_id")
            order_by = spec.get("order_by")
            model = spec.get("model", "AR1").upper()
            phi = float(spec.get("phi", 0.7))
            noise_std = float(spec.get("noise_std", 0.3))
            anchor_col = spec.get("anchor_column")
            trend_spec = spec.get("trend", {})
            slope_mean = float(trend_spec.get("slope_mean", 0.0))
            slope_std = float(trend_spec.get("slope_std", 0.0))

            if not entity_id or entity_id not in df.columns:
                continue

            result = df[col.name].astype(float).copy()

            for entity, grp_idx in df.groupby(entity_id).groups.items():
                grp = df.loc[grp_idx].copy()
                if order_by and order_by in grp.columns:
                    grp = grp.sort_values(order_by)
                    grp_idx = grp.index

                n = len(grp)
                if n == 0:
                    continue

                # Starting value: anchor column if present, else first generated value
                if anchor_col and anchor_col in grp.columns:
                    x0 = float(grp[anchor_col].iloc[0])
                else:
                    x0 = float(result.loc[grp_idx[0]])

                # Per-entity slope (for trend models)
                slope = float(self.rng.normal(slope_mean, slope_std)) if slope_std > 0 else slope_mean

                series = np.empty(n)
                series[0] = x0
                noise = self.rng.normal(0, noise_std, size=n)

                if model in ("AR1", "AUTOREGRESSIVE"):
                    for i in range(1, n):
                        series[i] = phi * series[i - 1] + (1 - phi) * x0 + slope * i + noise[i]
                elif model == "LINEAR_TREND":
                    for i in range(n):
                        series[i] = x0 + slope * i + noise[i]
                elif model == "RANDOM_WALK":
                    for i in range(1, n):
                        series[i] = series[i - 1] + noise[i]
                elif model == "MEAN_REVERSION":
                    mean_level = float(spec.get("mean_level", x0))
                    for i in range(1, n):
                        series[i] = series[i - 1] + phi * (mean_level - series[i - 1]) + noise[i]
                else:
                    series = result.loc[grp_idx].values

                result.loc[grp_idx] = series

            df[col.name] = result

        return df

    # ------------------------------------------------------------------
    # State machine (#9)
    # ------------------------------------------------------------------

    def _apply_state_machine(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Assign entity states via a Markov transition model.

        Table-level spec (via ``Table.state_machine`` or ``__state_machine__``
        in the dict schema, passed through as ``_state_machine`` in
        distribution_params of a sentinel column):

            __state_machine__:
              state_column: patient_status
              initial_state: enrolled
              transitions:
                enrolled:
                  on_treatment: 0.97
                  screen_failure: 0.03
                on_treatment:
                  completed: 0.77
                  dropout: 0.23

        The state machine assigns one terminal state to every row based on
        the declared transition probabilities. Chained transitions are
        followed until a terminal state (no outgoing transitions) is reached
        or the chain exceeds 20 hops.
        """
        table_obj = self.config.get_table(table_name)
        sm_spec = getattr(table_obj, "state_machine", None) or {}
        if not sm_spec:
            return df

        if isinstance(sm_spec, dict):
            state_col = sm_spec.get("state_column")
            initial = sm_spec.get("initial_state")
            transitions = sm_spec.get("transitions", {})
        else:
            return df

        if not state_col or not initial or not transitions:
            return df

        def _traverse(start: str) -> str:
            state = start
            for _ in range(20):
                nexts = transitions.get(state, {})
                if not nexts:
                    return state
                states = list(nexts.keys())
                probs = np.array([float(nexts[s]) for s in states], dtype=float)
                probs /= probs.sum()
                state = str(self.rng.choice(states, p=probs))
            return state

        df[state_col] = [_traverse(initial) for _ in range(len(df))]
        return df

    def _apply_null_if(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Set column to NaN/NaT where a sibling column matches a trigger value.

        Reads ``null_if`` from each column's distribution_params:
            null_if: {"column": "status", "values": ["cancelled", "refunded"]}
        or the shorthand single-value form:
            null_if: {"column": "status", "value": "cancelled"}
        """
        columns = self.config.columns.get(table_name, [])
        for col in columns:
            spec = col.distribution_params.get("null_if")
            if not spec:
                continue
            ref_col = spec.get("column")
            trigger_values = spec.get("values") or ([spec["value"]] if "value" in spec else [])
            if not ref_col or not trigger_values or ref_col not in df.columns or col.name not in df.columns:
                continue
            mask = df[ref_col].isin(trigger_values)
            _null_column(df, col.name, mask)
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

        # Merge context with the live local df so same-table column references
        # in formulas (e.g. profit = revenue - cost) resolve correctly.
        tables_for_engine = {**self.context, table_name: df}
        engine = FormulaEngine(tables_for_engine)

        # Authoritative FK mapping from the declared relationships: parent table →
        # the exact child FK column. This lets a cross-table formula
        # (@employees.hourly_rate) join on the real FK instead of guessing from
        # column names, which mis-joins when the parent PK is "id" and the child
        # FK is "employee_id".
        fk_mappings = {
            rel.parent_table: rel.child_key
            for rel in self.config.relationships
            if rel.child_table == table_name
        }

        for col in formula_cols:
            formula = col.distribution_params["formula"]
            try:
                result = engine.evaluate_with_lookups(df, formula, fk_mappings=fk_mappings)
                df[col.name] = result
            except (ValueError, ImportError) as e:
                warnings.warn(f"Formula column '{col.name}' skipped: {e}")

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

        Memory strategy
        ---------------
        Only tables that participate in a cascade event (as source or target)
        are buffered in memory.  All other tables stream directly to the caller
        one batch at a time, keeping memory usage proportional to cascade
        complexity rather than total dataset size.

        Yields:
            Tuple[str, pd.DataFrame]: (table_name, batch_df)
        """
        sorted_tables = self.topological_sort()
        cascade_events = [e for e in (self.config.events or []) if e.propagate_to]

        # Cross-table roll-ups: parent summary columns computed from child facts so the data
        # reconciles under a JOIN. Both the parent (target) and the child (source) must be
        # buffered together for the post-generation pass.
        from misata.rollups import (collect_declared_rollups, infer_rollups,
                                     apply_rollups)
        rollup_specs = collect_declared_rollups(self.config)
        try:
            rollup_specs = rollup_specs + infer_rollups(self.config)
        except Exception:
            pass  # inference is best-effort; never block generation
        rollup_tables: set = set()
        for s in rollup_specs:
            rollup_tables.add(s.parent_table)
            rollup_tables.add(s.from_table)

        # Identify which tables must be buffered (cascade resolution OR roll-ups)
        cascade_tables: set = set()
        for event in cascade_events:
            cascade_tables.add(event.table)
            cascade_tables.update(event.propagate_to.keys())
        buffer_tables = cascade_tables | rollup_tables

        buffered: Dict[str, pd.DataFrame] = {}
        streamed: list = []   # tables already yielded (order record for phase 3)

        # Phase 1 — generate in dependency order
        for table_name in sorted_tables:
            if table_name in buffer_tables:
                # Buffer: collect all batches for the post-generation passes
                batches = []
                for batch in self.generate_batches(table_name):
                    batches.append(batch)
                if batches:
                    buffered[table_name] = pd.concat(batches, ignore_index=True)
            else:
                # Stream immediately — no post-pass involvement
                for batch in self.generate_batches(table_name):
                    yield table_name, batch
                streamed.append(table_name)

        # Phase 2 — apply cascades, then roll-ups, to buffered tables
        for event in cascade_events:
            self.propagate_event_cascade(buffered, event)
        if rollup_specs:
            try:
                apply_rollups(buffered, rollup_specs)
            except Exception:
                pass  # a roll-up failure must never corrupt an otherwise-valid run

        # Phase 3 — yield buffered tables in original dependency order
        for table_name in sorted_tables:
            if table_name in buffered:
                yield table_name, buffered[table_name]

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
