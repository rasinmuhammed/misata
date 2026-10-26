"""
First-class YAML schema format for Misata.

Define your dataset as a plain YAML file, commit it to git, and regenerate
data with a single command.  More readable than Synth's JSON schemas, more
powerful than syda's YAML (no LLM required).

Quickstart::

    # 1. Scaffold a schema file
    misata init

    # 2. Edit misata.yaml to match your domain

    # 3. Generate data
    misata generate
    # → generates data/  with one CSV per table

Python API::

    import misata

    schema = misata.load_yaml_schema("misata.yaml")
    tables = misata.generate_from_schema(schema)

    # Round-trip: save any SchemaConfig back to YAML
    misata.save_yaml_schema(schema, "misata.yaml")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar, Union


import yaml

from misata.compat import resolve_column_type
from misata.schema import (
    Column,
    Constraint,
    Degradation,
    SensorResponse,
    GroupShares,
    SCD2Config,
    StockFlowIdentity,
    NoiseConfig,
    OutcomeCurve,
    RateCurve,
    RealismConfig,
    Relationship,
    ScenarioEvent,
    SchemaConfig,
    Table,
    WaterfallIdentity,
)
from misata.exceptions import ConformanceWarning, warn


# ---------------------------------------------------------------------------
# Template — written by `misata init` with no flags
# ---------------------------------------------------------------------------

MISATA_YAML_TEMPLATE = """\
# yaml-language-server: $schema=https://raw.githubusercontent.com/rasinmuhammed/misata/main/schema/misata.schema.json
# misata.yaml — synthetic data schema
# Run `misata generate` to produce data from this file.
# Commit this file to git so your whole team can regenerate the same dataset.
#
# Docs: https://github.com/rasinmuhammed/misata

name: My Dataset
domain: generic       # saas | ecommerce | fintech | healthcare | logistics | marketplace
seed: 42
rows: 1000            # default row count for every table (override per table)

# ── Tables ────────────────────────────────────────────────────────────────────
tables:
  users:
    rows: 1000
    description: "Registered users"
    columns:
      user_id:
        type: int
        unique: true
        min: 1
        max: 9999999
      email:
        type: text
        text_type: email    # email | name | company | phone | url | address | uuid
        unique: true
      full_name:
        type: text
        text_type: name
      country:
        type: categorical
        choices: [United States, United Kingdom, Canada, Germany, France]
        probabilities: [0.45, 0.20, 0.15, 0.12, 0.08]
      plan:
        type: categorical
        choices: [free, pro, enterprise]
        probabilities: [0.60, 0.30, 0.10]
      signup_date:
        type: date
        start: "2022-01-01"
        end: "2024-12-31"
      churned:
        type: boolean

  orders:
    rows: 5000
    description: "Purchase orders"
    columns:
      order_id:
        type: int
        unique: true
      user_id:
        type: foreign_key     # resolved via relationships below
      amount:
        type: float
        min: 5.0
        max: 500.0
        distribution: lognormal
      status:
        type: categorical
        choices: [pending, completed, cancelled, refunded]
        probabilities: [0.10, 0.75, 0.10, 0.05]
      placed_at:
        type: datetime
        start: "2022-01-01"
        end: "2024-12-31"

# ── Relationships (FK integrity) ──────────────────────────────────────────────
relationships:
  - "users.user_id → orders.user_id"

# ── Business-rule constraints ─────────────────────────────────────────────────
# constraints:
#   - name: unique_order_per_user_per_day
#     type: unique_combination
#     group_by: [user_id, placed_at]
#
#   - name: price_above_cost
#     type: inequality
#     column_a: price
#     operator: ">"
#     column_b: cost
#
#   - name: discount_in_bounds
#     type: col_range
#     column: discount
#     low_column: min_discount
#     high_column: max_discount

# ── Scenario events ───────────────────────────────────────────────────────────
# events:
#   - name: holiday_revenue_boost
#     table: orders
#     column: amount
#     condition: "placed_at >= '2024-11-01' and placed_at <= '2024-12-31'"
#     modifier_type: multiply
#     modifier_value: 1.5

# ── Outcome curves (hit exact aggregate targets) ────────────────────────────
# outcome_curves:
#   - table: orders
#     column: amount
#     time_column: order_date
#     time_unit: month           # day | week | month | quarter
#     pattern_type: growth       # growth | seasonal | decline | flat
#     avg_transaction_value: 75  # used to plan row counts (paper §3.1)
#     concentration: 2.0         # Dirichlet α — controls per-row dispersion (§3.2)
#     start_date: "2024-01-01"   # override start date inferred from time_column
#     intra_period_pattern: uniform   # uniform | weekday_heavy | weekend_heavy
#     curve_points:
#       - {period: "2024-01", value: 10000}   # exact monthly aggregate target
#       - {period: "2024-06", value: 45000}
#       - {period: "2024-12", value: 120000}
#
# ── Rate curves (hit exact per-period rate targets) ──────────────────────────
# rate_curves:
#   - table: transactions
#     column: is_fraud
#     time_column: transaction_date
#     time_unit: quarter         # day | week | month | quarter
#     true_value: true           # value counted as the positive class
#     interpolate: true          # linearly interpolate rates between anchors
#     rate_points:
#       - {period: "2024-01", rate: 0.02}   # 2% fraud rate in January
#       - {period: "2024-06", rate: 0.04}   # 4% by June
#       - {period: "2024-12", rate: 0.05}   # 5% by December
"""


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

# Keys the column parser consumes itself. Everything else a user writes on a
# column is carried into `distribution_params` for the engine to read.
_STRUCTURAL_COLUMN_KEYS = frozenset({
    "type", "unique", "nullable", "description", "primary_key",
    "choices", "probabilities", "start", "end", "text_type", "distribution",
})


def _parse_relationship(raw: Union[str, Dict[str, Any]]) -> Relationship:
    """Accept both shorthand string and dict form."""
    if isinstance(raw, str):
        # "parent_table.parent_col → child_table.child_col"
        # also handle ASCII arrow "->"
        arrow = "→" if "→" in raw else "->"
        parts = raw.split(arrow)
        if len(parts) != 2:
            raise ValueError(
                f"Relationship string must be 'parent.col → child.col', got: {raw!r}"
            )
        lhs, rhs = parts[0].strip(), parts[1].strip()
        p_table, p_col = lhs.rsplit(".", 1)
        c_table, c_col = rhs.rsplit(".", 1)
        return Relationship(
            parent_table=p_table.strip(),
            parent_key=p_col.strip(),
            child_table=c_table.strip(),
            child_key=c_col.strip(),
        )
    # Dict form, in either spelling: the short `parent`/`child_col` names or
    # the model's own `parent_table`/`child_key`.
    parent = raw.get("parent") or raw.get("parent_table")
    child = raw.get("child") or raw.get("child_table")
    if not parent or not child:
        raise ValueError(
            "Relationship needs a parent and a child table. Use "
            "{parent_table: orders, child_table: order_items, "
            "parent_key: order_id, child_key: order_id}; got: "
            f"{sorted(raw)}"
        )
    aliases = {"parent", "child", "parent_col", "child_col", "temporal"}
    fields = {k: v for k, v in raw.items()
              if k in Relationship.model_fields and v is not None}
    unknown = sorted(set(raw) - set(Relationship.model_fields) - aliases)
    if unknown:
        raise ValueError(f"relationship {parent} -> {child} has unknown field(s) {unknown}")
    # `parent: orders.order_id` names the key the way the arrow shorthand does.
    parent, _, parent_col = str(parent).partition(".")
    child, _, child_col = str(child).partition(".")
    fields.update(
        parent_table=parent,
        parent_key=raw.get("parent_col") or raw.get("parent_key") or parent_col or "id",
        child_table=child,
        child_key=(raw.get("child_col") or raw.get("child_key") or child_col
                   or f"{parent}_id"),
    )
    if "temporal" in raw:
        fields["temporal_constraint"] = bool(raw["temporal"])
    return Relationship(**fields)


def _parse_column(col_name: str, col_def: Dict[str, Any],
                  row_count: Optional[int] = None) -> Column:
    """Map a YAML column definition to a Misata Column."""
    raw_type = str(col_def.get("type", "text")).lower()
    misata_type = resolve_column_type(raw_type, where=f"column {col_name!r}")

    # FK declared via relationships — column just needs type="foreign_key"
    if raw_type == "foreign_key" or misata_type == "foreign_key":
        # Keep everything written next to the foreign key, not just its name.
        # `unique: true` matters most: it says the relationship is one-to-one,
        # so the key is drawn without replacement and the database's own unique
        # index accepts the insert. `references` and `nullable` carry through
        # the same way.
        fk_params = {k: v for k, v in col_def.items()
                     if k not in _STRUCTURAL_COLUMN_KEYS and v is not None}
        return Column(
            name=col_name,
            type="foreign_key",
            distribution_params=fk_params,
            nullable=bool(col_def.get("nullable", True)),
            unique=bool(col_def.get("unique", False)),
            description=col_def.get("description") or None,
        )

    # Categorical from choices
    choices = col_def.get("choices")
    if choices and isinstance(choices, list) and misata_type in ("text", "int", "float"):
        misata_type = "categorical"

    params: Dict[str, Any] = {}

    if misata_type == "categorical":
        params["choices"] = [str(c) for c in (choices or ["Unknown"])]
        probs = col_def.get("probabilities")
        if probs:
            params["probabilities"] = list(probs)

    elif misata_type in ("int", "float"):
        for k in ("min", "max", "decimals"):
            if col_def.get(k) is not None:
                params[k] = col_def[k]
        if col_def.get("distribution"):
            params["distribution"] = col_def["distribution"]

    elif misata_type == "text":
        if col_def.get("text_type"):
            params["text_type"] = col_def["text_type"]

    elif misata_type in ("date", "datetime"):
        params["start"] = col_def.get("start", "2020-01-01")
        params["end"] = col_def.get("end", "2024-12-31")

    # Generation features that may appear on any column type: pass them through
    # so they survive load. These are validated at generation time, not here.
    #
    # The engine reads more than fifty parameters from `distribution_params`
    # (`null_rate`, `pattern`, `templates`, `null_when`, `quantiles` and the
    # rest), so this names the keys consumed above and passes everything else
    # through rather than enumerating what to keep.
    #
    # Passing through is also the safer direction. An unknown key carried into
    # distribution_params is ignored by the engine; a known key dropped here is
    # a declaration that does nothing while the file still looks authoritative.
    for k, v in col_def.items():
        if k not in _STRUCTURAL_COLUMN_KEYS and v is not None:
            params.setdefault(k, v)

    # A primary key is unique, and it is drawn from a range wide enough to stay
    # that way. This was doing neither: `primary_key` was not a structural key,
    # so it fell through into distribution_params, the column kept the default
    # normal distribution, and a declared key produced 142 distinct values
    # across 2,000 rows. The dict path had always honoured it, so the same
    # document behaved differently depending on which door it came through,
    # which is the failure this project keeps finding.
    #
    # Nothing catches it downstream either: an orphan check asks whether a
    # child's value exists in the parent, never whether the parent's key is
    # unique, so integrity still reported clean.
    is_pk = bool(col_def.get("primary_key", False))
    if is_pk:
        params.pop("primary_key", None)
        # Unless the author asked for a specific shape, a key is drawn
        # uniformly from a range wide enough that uniqueness is not a fight.
        # The default normal distribution over a narrow range made the engine
        # widen it and warn on every run.
        if "distribution" not in col_def:
            params.pop("_distribution_is_default", None)
            params["distribution"] = "uniform"
            params.setdefault("min", 1)
            # Bounded by the table, so a twenty row dimension gets keys 1..20
            # rather than a surrogate key of 1,660,996. The dict path does the
            # same, and a parity test holds the two doors together.
            upper = int(row_count) if isinstance(row_count, int) and row_count > 0 else 2_000_000
            params.setdefault("max", max(upper, 1))

    return Column(
        name=col_name,
        type=misata_type,  # type: ignore[arg-type]
        distribution_params=params,
        nullable=False if is_pk else bool(col_def.get("nullable", True)),
        unique=is_pk or bool(col_def.get("unique", False)),
        description=col_def.get("description") or None,
    )


def _parse_constraint(raw: Dict[str, Any]) -> Constraint:
    """A constraint with every field its model defines.

    ``table`` is accepted as routing for top-level constraints. Any other key
    the model does not define is refused, so a misspelt field fails loudly
    instead of loading as None.
    """
    known = set(Constraint.model_fields)
    # `table` is routing, consumed by the caller to decide which table the
    # constraint attaches to, and is not a field of the constraint itself.
    routing = {"table"}
    unknown = sorted(set(raw) - known - routing)
    if unknown:
        raise ValueError(
            f"constraint {raw.get('name', '<unnamed>')!r} has unknown field(s) "
            f"{unknown}. Valid fields: {sorted(known)}")

    fields = {k: v for k, v in raw.items() if k in known}
    fields.setdefault("name", "unnamed")
    fields.setdefault("action", "cap")
    if "group_by" in fields:
        fields["group_by"] = list(fields["group_by"] or [])
    return Constraint(**fields)


_Model = TypeVar("_Model")


def _model_from(model: Type[_Model], raw: Dict[str, Any], what: str) -> _Model:
    """``model(**raw)``, refusing keys the model does not define.

    Every field the model has is read, so a declaration written to YAML loads
    back whole; an unknown key is a typo the author needs to hear about.
    """
    fields = set(getattr(model, "model_fields"))
    unknown = sorted(set(raw) - fields)
    if unknown:
        raise ValueError(f"{what} has unknown field(s) {unknown}. "
                         f"Valid fields: {sorted(fields)}")
    return model(**raw)


def _parse_event(raw: Dict[str, Any]) -> ScenarioEvent:
    return _model_from(ScenarioEvent, raw, f"event {raw.get('name', '<unnamed>')!r}")


def _parse_curve(raw: Dict[str, Any]) -> OutcomeCurve:
    return _model_from(OutcomeCurve, raw,
                       f"outcome curve on {raw.get('table')}.{raw.get('column')}")


def _parse_rate_curve(raw: Dict[str, Any]) -> RateCurve:
    return _model_from(RateCurve, raw,
                       f"rate curve on {raw.get('table')}.{raw.get('column')}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_yaml_schema(
    path: Union[str, Path],
    rows: int = 1000,
    seed: Optional[int] = 42,
) -> SchemaConfig:
    """Load a ``misata.yaml`` schema file into a :class:`~misata.schema.SchemaConfig`.

    Args:
        path: Path to the YAML file.
        rows: Default row count when the file omits it.
        seed: Default seed when the file omits it.

    Returns:
        :class:`~misata.schema.SchemaConfig` ready for
        :func:`~misata.generate_from_schema`.

    Example::

        schema = misata.load_yaml_schema("misata.yaml")
        tables = misata.generate_from_schema(schema)
    """
    path = Path(path).expanduser()
    raw: Dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    name = raw.get("name", path.stem)
    generation_mode = raw.get("generation_mode", "anchored")
    domain = raw.get("domain")
    file_seed = raw.get("seed", seed)
    default_rows = int(raw.get("rows", rows))

    # Tables + columns
    tables_raw: Dict[str, Any] = raw.get("tables", {})
    tables: List[Table] = []
    columns_map: Dict[str, List[Column]] = {}

    # Collect per-table constraints from inline table blocks
    _table_constraints: Dict[str, List[Constraint]] = {}

    for table_name, tdef in tables_raw.items():
        tdef = tdef or {}
        t_rows = int(tdef.get("rows", default_rows))
        t_desc = tdef.get("description")
        t_scd2 = SCD2Config(**tdef["scd2"]) if isinstance(tdef.get("scd2"), dict) else None
        tables.append(Table(name=table_name, row_count=t_rows,
                            description=t_desc, scd2=t_scd2))

        col_defs: Dict[str, Any] = tdef.get("columns", {})
        columns_map[table_name] = [
            _parse_column(col_name, (cdef or {}), row_count=t_rows)
            for col_name, cdef in col_defs.items()
        ]

        # Per-table constraints declared inside the table block
        for c_raw in (tdef.get("constraints") or []):
            _table_constraints.setdefault(table_name, []).append(_parse_constraint(c_raw))

    # Relationships
    relationships = [
        _parse_relationship(r) for r in (raw.get("relationships") or [])
    ]
    # A foreign key column that names what it references
    # (`references: customers.customer_id`) declares its relationship.
    declared = {(r.child_table, r.child_key) for r in relationships}
    for t_name, cols in columns_map.items():
        for col in cols:
            ref = (col.distribution_params or {}).get("references") \
                if col.type == "foreign_key" else None
            if (isinstance(ref, str) and "." in ref
                    and (t_name, col.name) not in declared):
                parent, key = ref.split(".", 1)
                relationships.append(Relationship(
                    parent_table=parent, child_table=t_name,
                    parent_key=key, child_key=col.name))

    # Top-level constraints — must have an explicit `table:` field, or we attach
    # to the first table as a last-resort fallback.
    for c_raw in (raw.get("constraints") or []):
        c_obj = _parse_constraint(c_raw)
        target = c_raw.get("table") or (tables[0].name if tables else "unknown")
        _table_constraints.setdefault(target, []).append(c_obj)

    # Apply accumulated constraints to Table objects
    for table in tables:
        if table.name in _table_constraints:
            table.constraints = _table_constraints[table.name]

    # Events
    events = [_parse_event(e) for e in (raw.get("events") or [])]

    # Outcome curves
    outcome_curves = [_parse_curve(c) for c in (raw.get("outcome_curves") or [])]

    # Rate curves
    rate_curves = [_parse_rate_curve(c) for c in (raw.get("rate_curves") or [])]

    # Units that wear out. The failure time is declared; damage and remaining
    # useful life follow from it, so the label is exact rather than annotated.
    degradations = []
    for spec_raw in (raw.get("degradations") or []):
        spec_raw = dict(spec_raw)
        spec_raw["responses"] = [
            SensorResponse(**r) for r in (spec_raw.get("responses") or [])
        ]
        degradations.append(Degradation(**spec_raw))

    # Exact group shares ("Electronics is 40% of revenue")
    group_shares = [GroupShares(**g) for g in (raw.get("group_shares") or [])]

    # Waterfall identities (declared per-period balances)
    waterfalls = [WaterfallIdentity(**w) for w in (raw.get("waterfalls") or [])]

    # Stock-flow identities
    stock_flows = [StockFlowIdentity(**s) for s in (raw.get("stock_flows") or [])]

    # The schema-level declarations. This loader handles the documented
    # `tables: {name: {...}}` YAML form and is a separate path from
    # `compat.from_dict_schema`, so both must read every declaration. One table,
    # so the next declaration is one line rather than another branch.
    from misata.schema import (Bitemporal, CohortRetention, DagEdges,
                               Duplicates, EventLog, GraphMotifs,
                               JointDistribution, LateArrival, Lifecycle,
                               Missingness, Outliers, Process, TimeGrid,
                               TransitiveClosure, Typos)
    _declared: Dict[str, List[Any]] = {}
    for key, model in (("lifecycles", Lifecycle),
                       ("retention", CohortRetention),
                       ("missingness", Missingness),
                       ("late_arrivals", LateArrival),
                       ("time_grids", TimeGrid),
                       ("duplicates", Duplicates),
                       ("event_logs", EventLog),
                       ("outliers", Outliers),
                       ("typos", Typos),
                       ("bitemporal", Bitemporal),
                       ("dag_edges", DagEdges),
                       ("closures", TransitiveClosure),
                       ("processes", Process),
                       ("graph_motifs", GraphMotifs),
                       ("joint_distributions", JointDistribution)):
        parsed: List[Any] = []
        for i, item in enumerate(raw.get(key) or []):
            try:
                parsed.append(model(**item))
            except Exception as e:
                warn(f"Skipping invalid {key}[{i}] in {path.name}: {e}", ConformanceWarning)
        _declared[key] = parsed

    # Declared data-quality defects
    noise_raw = raw.get("noise")
    noise_config = NoiseConfig(**noise_raw) if noise_raw else None

    # Schema-embedded vocabularies (column name -> real values)
    vocab_raw = raw.get("vocabularies")
    vocabularies = (
        {str(k): [str(v) for v in vals] for k, vals in vocab_raw.items() if vals}
        if isinstance(vocab_raw, dict) else None
    ) or None

    # Realism settings (locale, capsule file). The documented top-level
    # `locale:` shorthand folds into the realism block.
    realism_raw = dict(raw.get("realism") or {})
    if raw.get("locale") and "locale" not in realism_raw:
        realism_raw["locale"] = raw["locale"]
    realism = RealismConfig(**realism_raw) if realism_raw else None

    return SchemaConfig(
        name=name,
        description=raw.get("description"),
        domain=domain,
        generation_mode=generation_mode,
        tables=tables,
        columns=columns_map,
        relationships=relationships,
        events=events,
        outcome_curves=outcome_curves,
        rate_curves=rate_curves,
        group_shares=group_shares,
        degradations=degradations,
        waterfalls=waterfalls,
        stock_flows=stock_flows,
        lifecycles=_declared["lifecycles"],
        retention=_declared["retention"],
        missingness=_declared["missingness"],
        late_arrivals=_declared["late_arrivals"],
        time_grids=_declared["time_grids"],
        duplicates=_declared["duplicates"],
        event_logs=_declared["event_logs"],
        outliers=_declared["outliers"],
        typos=_declared["typos"],
        bitemporal=_declared["bitemporal"],
        dag_edges=_declared["dag_edges"],
        closures=_declared["closures"],
        processes=_declared["processes"],
        graph_motifs=_declared["graph_motifs"],
        joint_distributions=_declared["joint_distributions"],
        preset=raw.get("preset"),
        noise_config=noise_config,
        vocabularies=vocabularies,
        realism=realism,
        seed=file_seed,
    )



def load_schema_file(
    path: Union[str, Path],
    *,
    seed: Optional[int] = None,
    rows: Optional[int] = None,
) -> SchemaConfig:
    """A schema from any file form Misata writes or reads.

    Accepts ``misata.yaml`` (tables as a mapping), a ``SchemaConfig`` dump
    such as ``schema.solved.json`` (tables as a list), the dict schema form,
    and SQL DDL in a ``.sql`` file. JSON is read as YAML, which it is a
    subset of.

    Args:
        path: The schema file.
        seed: Overrides the file's seed.
        rows: Row count for tables that do not state one.

    Raises:
        ValueError: the file does not hold a mapping or CREATE TABLE statements.
    """
    path = Path(path).expanduser()
    if path.suffix.lower() == ".sql":
        from misata.ddl import from_ddl

        schema = from_ddl(path.read_text(encoding="utf-8"), default_rows=rows or 1000)
        if not schema.tables:
            raise ValueError(f"no CREATE TABLE statements in {path}")
        schema.name = path.stem
        if seed is not None:
            schema.seed = seed
        return schema
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected a mapping in {path}")
    tables = raw.get("tables")
    if isinstance(tables, dict):
        return load_yaml_schema(path, seed=seed) if rows is None else load_yaml_schema(
            path, rows=rows, seed=seed)
    if isinstance(tables, list):
        schema = SchemaConfig(**raw)
    else:
        from misata.compat import from_dict_schema

        schema = from_dict_schema(raw, row_count=rows)
    if seed is not None:
        schema.seed = seed
    return schema


def save_yaml_schema(
    schema: SchemaConfig,
    path: Union[str, Path],
) -> Path:
    """Serialize a :class:`~misata.schema.SchemaConfig` to a ``misata.yaml`` file.

    The output is human-readable and can be edited, committed to git, and
    reloaded with :func:`load_yaml_schema`.

    Args:
        schema: The schema to serialize.
        path:   Destination file path.

    Returns:
        ``Path`` of the written file.

    Example::

        schema = misata.parse("A SaaS company with 5k users")
        misata.save_yaml_schema(schema, "misata.yaml")
    """
    path = Path(path).expanduser()

    doc: Dict[str, Any] = {"name": schema.name}
    if getattr(schema, "description", None):
        doc["description"] = schema.description
    if schema.domain:
        doc["domain"] = schema.domain
    if schema.seed is not None:
        doc["seed"] = schema.seed
    # Serialize the mode only when it deviates from the default ("anchored"),
    # so a legacy schema records generation_mode: legacy explicitly.
    if getattr(schema, "generation_mode", "anchored") != "anchored":
        doc["generation_mode"] = schema.generation_mode

    # Tables
    tables_doc: Dict[str, Any] = {}
    for table in schema.tables:
        cols = schema.get_columns(table.name)
        col_doc: Dict[str, Any] = {}
        for col in cols:
            col_doc[col.name] = _column_to_dict(col)
        entry: Dict[str, Any] = {"rows": table.row_count, "columns": col_doc}
        if table.description:
            entry["description"] = table.description
        if table.scd2 is not None:
            entry["scd2"] = table.scd2.model_dump(exclude_none=True)
        if table.constraints:
            entry["constraints"] = [_dump(c) for c in table.constraints]
        tables_doc[table.name] = entry
    doc["tables"] = tables_doc

    if schema.relationships:
        doc["relationships"] = [_relationship_to_yaml(r) for r in schema.relationships]

    # Every other declaration is written through its own model, so a field the
    # model gains is written and read back without this function changing.
    for key in _DECLARATION_KEYS:
        items = getattr(schema, key, None) or []
        if items:
            doc[key] = [_dump(item) for item in items]

    if schema.preset:
        doc["preset"] = schema.preset

    # Declared data-quality defects
    if schema.noise_config is not None:
        doc["noise"] = schema.noise_config.model_dump(exclude_none=True)

    # Schema-embedded vocabularies
    if schema.vocabularies:
        doc["vocabularies"] = schema.vocabularies

    # Realism settings
    if schema.realism is not None:
        realism_doc = schema.realism.model_dump(exclude_none=True)
        if realism_doc:
            doc["realism"] = realism_doc

    # The header line gives yaml-language-server users (VS Code and friends)
    # autocomplete and inline validation against the published JSON Schema.
    header = (
        "# yaml-language-server: $schema="
        "https://raw.githubusercontent.com/rasinmuhammed/misata/"
        "main/schema/misata.schema.json\n"
    )
    path.write_text(
        header + yaml.dump(doc, allow_unicode=True, default_flow_style=False,
                           sort_keys=False),
        encoding="utf-8",
    )
    return path


#: Schema-level declarations, each a list of models under its own YAML key.
_DECLARATION_KEYS = (
    "events", "outcome_curves", "rate_curves", "group_shares", "waterfalls",
    "stock_flows", "degradations", "lifecycles", "retention", "missingness",
    "late_arrivals", "time_grids", "duplicates", "event_logs", "outliers", "typos",
    "bitemporal", "dag_edges", "closures", "processes", "graph_motifs",
    "joint_distributions",
)

#: The four fields the ``parent.key -> child.key`` shorthand carries.
_SHORTHAND_FIELDS = {"parent_table", "parent_key", "child_table", "child_key"}


def _dump(model: Any) -> Dict[str, Any]:
    """A declaration as YAML-ready data, leaving out every field at its default."""
    return dict(model.model_dump(mode="json", exclude_defaults=True))


def _relationship_to_yaml(r: Relationship) -> Union[str, Dict[str, Any]]:
    """The arrow shorthand, or the full form when the relationship says more."""
    fields = _dump(r)
    if set(fields) <= _SHORTHAND_FIELDS:
        return f"{r.parent_table}.{r.parent_key} \u2192 {r.child_table}.{r.child_key}"
    return {"parent_table": r.parent_table, "parent_key": r.parent_key,
            "child_table": r.child_table, "child_key": r.child_key, **fields}


def _column_to_dict(col: Column) -> Dict[str, Any]:
    """A column as ``misata.yaml`` writes it: its type, flags and every parameter.

    A distribution the column never declared is left out, so the loader
    defaults it again instead of recording the default as a choice.
    """
    d: Dict[str, Any] = {"type": col.type}
    if col.unique:
        d["unique"] = True
    if not col.nullable and "nullable" in col.model_fields_set:
        d["nullable"] = False
    if col.description:
        d["description"] = col.description
    params = dict(col.distribution_params or {})
    if params.pop("_distribution_is_default", False):
        params.pop("distribution", None)
    d.update(params)
    return d


# ---------------------------------------------------------------------------
# JSON Schema (for IDE autocomplete + inline validation of misata.yaml)
# ---------------------------------------------------------------------------

JSON_SCHEMA_URL = (
    "https://raw.githubusercontent.com/rasinmuhammed/misata/"
    "main/schema/misata.schema.json"
)


def json_schema() -> Dict[str, Any]:
    """Return the JSON Schema for ``misata.yaml`` as a Python dict.

    Use this to wire IDE autocomplete in editors that don't read the
    inline ``# yaml-language-server`` comment, or to embed the schema in
    custom tooling.

    Example::

        import json, misata
        print(json.dumps(misata.json_schema(), indent=2))
    """
    import json as _json

    # Prefer the packaged copy (works from a wheel install)
    try:
        from importlib import resources

        with resources.files("misata._schemas").joinpath(
            "misata.schema.json"
        ).open("r", encoding="utf-8") as fh:
            return dict(_json.load(fh))
    except Exception:
        pass

    # Fall back to the repo copy for editable installs
    repo_path = Path(__file__).parent.parent / "schema" / "misata.schema.json"
    if repo_path.exists():
        return dict(_json.loads(repo_path.read_text(encoding="utf-8")))

    raise FileNotFoundError(
        "misata.schema.json not found. Reinstall misata or fetch it from "
        f"{JSON_SCHEMA_URL}"
    )
