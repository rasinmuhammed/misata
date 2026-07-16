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

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from misata.compat import _TYPE_MAP
from misata.schema import (
    Column,
    Constraint,
    GroupShares,
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
        probabilities: [0.40, 0.15, 0.12, 0.10, 0.08]
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
    # dict form
    return Relationship(
        parent_table=raw["parent"],
        parent_key=raw.get("parent_col", "id"),
        child_table=raw["child"],
        child_key=raw.get("child_col", raw["parent"] + "_id"),
        temporal_constraint=bool(raw.get("temporal", False)),
    )


def _parse_column(col_name: str, col_def: Dict[str, Any]) -> Column:
    """Map a YAML column definition to a Misata Column."""
    raw_type = str(col_def.get("type", "text")).lower()
    misata_type = _TYPE_MAP.get(raw_type, "text")

    # FK declared via relationships — column just needs type="foreign_key"
    if raw_type == "foreign_key" or misata_type == "foreign_key":
        return Column(name=col_name, type="foreign_key", distribution_params={})

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

    # Generation features that may appear on any column type (0.8.0.2): pass them through
    # so they survive load. These are validated at generation time, not here.
    for k in ("rollup", "zero_inflate", "depends_on", "mapping", "formula",
              "inherits_curve_from", "quantize"):
        if col_def.get(k) is not None:
            params[k] = col_def[k]

    return Column(
        name=col_name,
        type=misata_type,  # type: ignore[arg-type]
        distribution_params=params,
        nullable=bool(col_def.get("nullable", True)),
        unique=bool(col_def.get("unique", False)),
        description=col_def.get("description") or None,
    )


def _parse_constraint(raw: Dict[str, Any]) -> Constraint:
    return Constraint(
        name=raw.get("name", "unnamed"),
        type=raw["type"],
        group_by=list(raw.get("group_by", [])),
        column=raw.get("column"),
        value=raw.get("value"),
        action=raw.get("action", "cap"),
        column_a=raw.get("column_a"),
        operator=raw.get("operator"),
        column_b=raw.get("column_b"),
        low_column=raw.get("low_column"),
        high_column=raw.get("high_column"),
    )


def _parse_event(raw: Dict[str, Any]) -> ScenarioEvent:
    return ScenarioEvent(
        name=raw["name"],
        table=raw["table"],
        column=raw["column"],
        condition=raw["condition"],
        modifier_type=raw["modifier_type"],
        modifier_value=raw["modifier_value"],
        description=raw.get("description"),
    )


def _parse_curve(raw: Dict[str, Any]) -> OutcomeCurve:
    return OutcomeCurve(
        table=raw["table"],
        column=raw["column"],
        time_column=raw.get("time_column", "date"),
        time_unit=raw.get("time_unit", "month"),
        pattern_type=raw.get("pattern_type", "seasonal"),
        intra_period_pattern=raw.get("intra_period_pattern", "uniform"),
        avg_transaction_value=raw.get("avg_transaction_value"),
        concentration=float(raw.get("concentration", 2.0)),
        start_date=raw.get("start_date"),
        description=raw.get("description"),
        curve_points=list(raw.get("curve_points", [])),
    )


def _parse_rate_curve(raw: Dict[str, Any]) -> RateCurve:
    return RateCurve(
        table=raw["table"],
        column=raw["column"],
        time_column=raw.get("time_column", "date"),
        time_unit=raw.get("time_unit", "month"),
        true_value=raw.get("true_value", True),
        interpolate=bool(raw.get("interpolate", True)),
        description=raw.get("description"),
        rate_points=list(raw.get("rate_points", [])),
    )


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
    generation_mode = raw.get("generation_mode", "legacy")
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
        tables.append(Table(name=table_name, row_count=t_rows, description=t_desc))

        col_defs: Dict[str, Any] = tdef.get("columns", {})
        columns_map[table_name] = [
            _parse_column(col_name, (cdef or {}))
            for col_name, cdef in col_defs.items()
        ]

        # Per-table constraints declared inside the table block
        for c_raw in (tdef.get("constraints") or []):
            _table_constraints.setdefault(table_name, []).append(_parse_constraint(c_raw))

    # Relationships
    relationships = [
        _parse_relationship(r) for r in (raw.get("relationships") or [])
    ]

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

    # Exact group shares ("Electronics is 40% of revenue")
    group_shares = [GroupShares(**g) for g in (raw.get("group_shares") or [])]

    # Waterfall identities (declared per-period balances)
    waterfalls = [WaterfallIdentity(**w) for w in (raw.get("waterfalls") or [])]

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
        domain=domain,
        generation_mode=generation_mode,
        tables=tables,
        columns=columns_map,
        relationships=relationships,
        events=events,
        outcome_curves=outcome_curves,
        rate_curves=rate_curves,
        group_shares=group_shares,
        waterfalls=waterfalls,
        noise_config=noise_config,
        vocabularies=vocabularies,
        realism=realism,
        seed=file_seed,
    )



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
    if schema.domain:
        doc["domain"] = schema.domain
    if schema.seed is not None:
        doc["seed"] = schema.seed
    if getattr(schema, "generation_mode", "legacy") != "legacy":
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
        tables_doc[table.name] = entry
    doc["tables"] = tables_doc

    # Relationships — string shorthand
    if schema.relationships:
        doc["relationships"] = [
            f"{r.parent_table}.{r.parent_key} \u2192 {r.child_table}.{r.child_key}"
            for r in schema.relationships
        ]

    # Constraints — collect from all tables
    all_constraints: List[Dict[str, Any]] = []
    for table in schema.tables:
        for c in (table.constraints or []):
            all_constraints.append(_constraint_to_dict(c))
    if all_constraints:
        doc["constraints"] = all_constraints

    # Events
    if schema.events:
        doc["events"] = [
            {
                "name": e.name,
                "table": e.table,
                "column": e.column,
                "condition": e.condition,
                "modifier_type": e.modifier_type,
                "modifier_value": e.modifier_value,
            }
            for e in schema.events
        ]

    # Outcome curves
    if schema.outcome_curves:
        doc["outcome_curves"] = [
            {
                "table": c.table,
                "column": c.column,
                "time_column": c.time_column,
                "time_unit": c.time_unit,
                "pattern_type": c.pattern_type,
                **({"avg_transaction_value": c.avg_transaction_value}
                   if c.avg_transaction_value is not None else {}),
                **({"concentration": c.concentration}
                   if c.concentration != 2.0 else {}),
                **({"start_date": c.start_date}
                   if c.start_date is not None else {}),
                **({"intra_period_pattern": c.intra_period_pattern}
                   if c.intra_period_pattern not in (None, "uniform") else {}),
                "curve_points": c.curve_points,
            }
            for c in schema.outcome_curves
        ]

    # Rate curves
    if getattr(schema, "rate_curves", None):
        doc["rate_curves"] = [
            {
                "table": rc.table,
                "column": rc.column,
                "time_column": rc.time_column,
                "time_unit": rc.time_unit,
                **({"true_value": rc.true_value}
                   if rc.true_value is not True else {}),
                **({"interpolate": rc.interpolate}
                   if not rc.interpolate else {}),
                "rate_points": rc.rate_points,
            }
            for rc in schema.rate_curves
        ]

    # Exact group shares
    if getattr(schema, "group_shares", None):
        doc["group_shares"] = [
            {
                "table": g.table,
                "measure": g.measure,
                "group_column": g.group_column,
                "shares": g.shares,
                **({"description": g.description} if g.description else {}),
            }
            for g in schema.group_shares
        ]

    # Waterfall identities
    if getattr(schema, "waterfalls", None):
        doc["waterfalls"] = [
            {
                "table": w.table,
                **({"period_column": w.period_column}
                   if w.period_column != "period" else {}),
                **({"type_column": w.type_column}
                   if w.type_column != "movement_type" else {}),
                **({"amount_column": w.amount_column}
                   if w.amount_column != "amount" else {}),
                "starting_value": w.starting_value,
                "points": w.points,
                "inflow_shares": w.inflow_shares,
                "outflow_shares": w.outflow_shares,
                **({"outflow_rate": w.outflow_rate}
                   if w.outflow_rate != 0.03 else {}),
                **({"description": w.description} if w.description else {}),
            }
            for w in schema.waterfalls
        ]

    # Declared data-quality defects
    if getattr(schema, "noise_config", None):
        doc["noise"] = schema.noise_config.model_dump(exclude_none=True)

    # Schema-embedded vocabularies
    if getattr(schema, "vocabularies", None):
        doc["vocabularies"] = schema.vocabularies

    # Realism settings
    if getattr(schema, "realism", None):
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


def _column_to_dict(col: Column) -> Dict[str, Any]:
    """Serialize a Column to YAML-schema dict (omit defaults to keep it clean)."""
    # Reverse-map Misata type to YAML type
    _REVERSE_TYPE = {
        "int": "int", "float": "float", "text": "text",
        "date": "date", "datetime": "datetime", "boolean": "boolean",
        "categorical": "categorical", "foreign_key": "foreign_key",
    }
    d: Dict[str, Any] = {"type": _REVERSE_TYPE.get(col.type, col.type)}
    if col.unique:
        d["unique"] = True
    if not col.nullable:
        d["nullable"] = False
    if col.description:
        d["description"] = col.description

    p = col.distribution_params or {}
    for k in ("min", "max", "decimals", "distribution", "text_type", "start", "end",
              # 0.8.0.2 generation features must survive the YAML round-trip
              "rollup", "zero_inflate", "depends_on", "mapping", "formula",
              "inherits_curve_from", "quantize"):
        if k in p:
            d[k] = p[k]
    if "choices" in p:
        d["choices"] = p["choices"]
    if "probabilities" in p:
        d["probabilities"] = p["probabilities"]
    return d


def _constraint_to_dict(c: Constraint) -> Dict[str, Any]:
    d: Dict[str, Any] = {"name": c.name, "type": c.type}
    if c.group_by:
        d["group_by"] = c.group_by
    if c.column:
        d["column"] = c.column
    if c.value is not None:
        d["value"] = c.value
    if c.action and c.action != "cap":
        d["action"] = c.action
    if c.column_a:
        d["column_a"] = c.column_a
    if c.operator:
        d["operator"] = c.operator
    if c.column_b:
        d["column_b"] = c.column_b
    if c.low_column:
        d["low_column"] = c.low_column
    if c.high_column:
        d["high_column"] = c.high_column
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
            return _json.load(fh)
    except Exception:
        pass

    # Fall back to the repo copy for editable installs
    repo_path = Path(__file__).parent.parent / "schema" / "misata.schema.json"
    if repo_path.exists():
        return _json.loads(repo_path.read_text(encoding="utf-8"))

    raise FileNotFoundError(
        "misata.schema.json not found. Reinstall misata or fetch it from "
        f"{JSON_SCHEMA_URL}"
    )
