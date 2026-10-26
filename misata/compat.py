"""
Schema import utilities for Misata.

Provides helpers for converting common schema formats into a native
``SchemaConfig``, so you can bring your existing schema definitions
into Misata without rewriting them.

Supported input formats:
- Generic dict-based schemas (column name → type + constraints)
- SQLAlchemy ORM models (via ``misata.schema_from_sqlalchemy``)
- YAML / JSON files (via ``misata.load_recipe``)

Example::

    import misata

    schemas = {
        "customers": {
            "id":     {"type": "integer", "primary_key": True},
            "name":   {"type": "string"},
            "email":  {"type": "email"},
            "status": {"type": "string", "enum": ["active", "inactive", "trial"]},
        },
        "orders": {
            "id":          {"type": "integer", "primary_key": True},
            "customer_id": {"type": "integer", "foreign_key": {"table": "customers", "column": "id"}},
            "amount":      {"type": "float",   "min": 1.0, "max": 5000.0},
            "placed_at":   {"type": "date",    "min_date": "2023-01-01", "max_date": "2025-12-31"},
        },
    }

    schema = misata.from_dict_schema(schemas, row_count=2000)
    tables = misata.generate_from_schema(schema)
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from misata.schema import (
    Degradation,
    SensorResponse,
    Column,
    Constraint,
    GroupShares,
    StockFlowIdentity,
    WaterfallIdentity,
    NoiseConfig,
    OutcomeCurve,
    RateCurve,
    RealismConfig,
    Relationship,
    SchemaConfig,
    Table,
)
from misata.exceptions import ConformanceWarning, warn


# Envelope keys hoisted into their dunder form by ``_normalise_envelope``.
# Every top-level key published by ``schema/misata.schema.json`` must appear
# here, or it would be accepted and then ignored, the worst outcome a
# declarative tool can produce. `tests/test_schema_contract.py` compares this
# list against the published schema and fails when they drift apart.
_ENVELOPE_KEYS: Tuple[Tuple[str, str], ...] = (
    ("outcome_curves", "__outcome_curves__"),
    ("rate_curves", "__rate_curves__"),
    ("group_shares", "__group_shares__"),
    ("waterfalls", "__waterfalls__"),
    ("stock_flows", "__stock_flows__"),
    ("degradations", "__degradations__"),
    ("lifecycles", "__lifecycles__"),
    ("retention", "__retention__"),
    ("missingness", "__missingness__"),
    ("late_arrivals", "__late_arrivals__"),
    ("time_grids", "__time_grids__"),
    ("duplicates", "__duplicates__"),
    ("event_logs", "__event_logs__"),
    ("outliers", "__outliers__"),
    ("typos", "__typos__"),
    ("bitemporal", "__bitemporal__"),
    ("dag_edges", "__dag_edges__"),
    ("graph_motifs", "__graph_motifs__"),
    ("joint_distributions", "__joint_distributions__"),
    ("closures", "__closures__"),
    ("processes", "__processes__"),
    ("preset", "__preset__"),
    ("noise", "__noise__"),
    ("realism", "__realism__"),
    ("events", "__events__"),
    ("vocabulary", "__vocabulary__"),
    ("vocabularies", "__vocabulary__"),
)

# Read directly rather than hoisted, so the contract test can account for them.
_DIRECT_TOP_LEVEL_KEYS: Tuple[str, ...] = (
    "tables", "name", "seed", "domain", "generation_mode",
    "relationships", "constraints", "locale", "rows",
)

#: Every top-level key ``from_dict_schema`` understands.
HANDLED_TOP_LEVEL_KEYS = frozenset(
    [k for k, _ in _ENVELOPE_KEYS] + list(_DIRECT_TOP_LEVEL_KEYS)
)

#: Declarations this parse could not build, collected rather than only warned
#: about. A malformed directive that is merely skipped lets generation run and
#: produce data in which the declared property is simply absent. Feasibility
#: turns each of these into a refusal, so a declaration is honoured or refused
#: and never merely ignored.
#:
#: A list rather than a raise, because from_dict_schema reports every problem at
#: once and fixing them one run at a time is miserable.
_DROPPED: List[Tuple[str, int, str]] = []

#: Published in the JSON Schema and deliberately not acted on here. Listed so
#: the contract test passes for a stated reason rather than by omission.
#: ``description`` is prose for the reader and changes no data.
UNHANDLED_TOP_LEVEL_KEYS = frozenset({"description"})


# ---------------------------------------------------------------------------
# Type normalisation
# ---------------------------------------------------------------------------

_TYPE_MAP: Dict[str, str] = {
    "integer": "int",
    "int": "int",
    "number": "int",
    "bigint": "int",
    "smallint": "int",
    "serial": "int",
    "float": "float",
    "decimal": "float",
    "double": "float",
    "numeric": "float",
    "real": "float",
    "money": "float",
    "string": "text",
    "text": "text",
    "varchar": "text",
    "char": "text",
    "uuid": "text",
    "email": "text",
    "phone": "text",
    "url": "text",
    "address": "text",
    "zipcode": "text",
    "date": "date",
    "datetime": "datetime",
    "timestamp": "datetime",
    "boolean": "boolean",
    "bool": "boolean",
    "foreign_key": "foreign_key",
    "list": "array",
    "jsonb": "json",
    "object": "json",
    "struct": "json",
    "map": "json",
}

#: The types `Column` itself accepts. `_TYPE_MAP` translates foreign spellings
#: (SQL, JSON Schema) into these, and does not contain them, so both sets are
#: needed to answer "is this a type Misata knows".
#: Distinguishes "caller passed no seed" from "caller passed 42".
_SEED_UNSET = object()

_NATIVE_TYPES = frozenset({
    "int", "float", "date", "time", "datetime",
    "categorical", "foreign_key", "text", "boolean", "json", "array",
})


def resolve_column_type(raw_type: str, *, where: str = "") -> str:
    """Translate a declared type, and refuse one nobody recognises.

    Falling back to text for an unrecognised type would let semantic inference
    fill the column from its name, so a column declared
    ``{"type": "category", "categories": ["US","UK","DE"]}`` could hold
    Australia, Brazil and Japan: plausible enough that nobody would look twice,
    and not what was declared.

    Substituting for a declaration is the worst of the three options. Honouring
    it is best, refusing it is honest, and quietly generating something else
    leaves the user holding data that does not match what they asked for behind
    a response that says it does.

    Raises:
        ValueError: naming the closest known spelling, because the mistake is
            almost always a near miss rather than an invention.
    """
    if not raw_type:
        return "text"
    key = str(raw_type).strip().lower()
    if key in _NATIVE_TYPES:
        return key
    if key in _TYPE_MAP:
        return _TYPE_MAP[key]

    import difflib
    known = sorted(_NATIVE_TYPES | set(_TYPE_MAP))
    close = difflib.get_close_matches(key, known, n=3, cutoff=0.6)
    hint = f" Did you mean {' or '.join(repr(c) for c in close)}?" if close else ""
    prefix = f"{where}: " if where else ""
    raise ValueError(
        f"{prefix}unknown column type {raw_type!r}.{hint} "
        f"Known types: {', '.join(known)}"
    )



_TEXT_TYPE_HINTS: Dict[str, str] = {
    # Identifiers — must come BEFORE "name" so substring scan stops here first.
    # Without these, columns like "anonymous_id" or "device_token" match "name"
    # or other substrings and get the wrong generator.
    "anonymous_id": "uuid",
    "anon_id": "uuid",
    "tracking_id": "uuid",
    "device_id": "uuid",
    "device_token": "uuid",
    "session_token": "uuid",
    "user_token": "uuid",
    "access_token": "uuid",
    "refresh_token": "uuid",
    "request_id": "uuid",
    "correlation_id": "uuid",
    "trace_id": "uuid",
    "guid": "uuid",
    # People — specific first (so exact match wins over "name" substring)
    "first_name": "first_name",
    "last_name": "last_name",
    "surname": "last_name",
    "family_name": "last_name",
    "full_name": "name",
    "display_name": "name",
    "customer_name": "name",
    "user_name": "name",
    "username": "username",
    "name": "name",
    # Contact
    "email": "email",
    "e_mail": "email",
    "mobile": "phone",
    "telephone": "phone",
    "phone": "phone",
    # Location
    "address": "address",
    "street": "address",
    "billing_address": "address",
    "shipping_address": "address",
    "city": "city",
    "town": "city",
    "country": "country",
    "postcode": "postcode",
    "postal_code": "postcode",
    "zip": "postcode",
    "zip_code": "postcode",
    # Business
    "organization": "company",
    "org_name": "company",
    "employer": "company",
    "company": "company",
    "job_title": "job",
    "position": "job",
    "job": "job",
    # Online
    "website": "url",
    "web_url": "url",
    "url": "url",
    "domain": "domain",
    # Entity catalog text — routed to the realistic catalog generators
    # (RealisticTextGenerator) so these get real product/menu/review values
    # instead of generic business sentences. Unambiguous column names only;
    # table-context-dependent cases (bare "name"/"title") are left alone.
    "product_name": "product_name",
    "product_title": "product_name",
    "item_name": "product_name",
    "sku_name": "product_name",
    "product_description": "product_description",
    "item_description": "product_description",
    "menu_item": "menu_item",
    "dish_name": "menu_item",
    "restaurant_name": "restaurant_name",
    "review_text": "review",
    "review_body": "review",
    "bio": "bio",
    "caption": "caption",
}

# ── Token-aware text_type inference ──────────────────────────────────────────
# Raw substring matching ("name" in "product_name") would turn entity columns
# into person names and "ip_address"/"mac_address" into street addresses, so
# the matcher below anchors on exact names, identifier suffixes, whole-word
# compound keys, and head tokens with explicit guards.

# Suffixes that mark an identifier/token rather than free text.
_ID_SUFFIXES = (
    "_id", "_uuid", "_guid", "_key", "_token", "_hash",
    "_sid", "_pid", "_fingerprint", "_secret",
)

# Multi-token hint keys, matched as a whole-word suffix ("billing_address",
# "first_name") so unrelated columns can't borrow a fragment.
_COMPOUND_HINT_KEYS = sorted(
    (k for k in _TEXT_TYPE_HINTS if "_" in k), key=len, reverse=True
)

# Head tokens that resolve regardless of qualifier.
_HEAD_TYPE: Dict[str, str] = {
    "city": "city", "town": "city",
    "country": "country",
    "postcode": "postcode", "zipcode": "postcode",
    "company": "company", "organization": "company", "employer": "company",
    "url": "url", "website": "url",
    "domain": "domain",
    "username": "username",
    "job": "job", "position": "job",
    "surname": "last_name",
}

# For an "*_name" column, the qualifier decides what kind of name it is.
_NAME_QUALIFIER_TYPE: Dict[str, str] = {
    "company": "company", "organization": "company", "org": "company",
    "employer": "company", "business": "company", "vendor": "company",
    "supplier": "company", "brand": "company",
    "first": "first_name", "given": "first_name",
    "last": "last_name", "family": "last_name",
    "full": "name", "display": "name", "customer": "name", "user": "name",
    "contact": "name", "account": "name", "holder": "name", "legal": "name",
    "domain": "domain",
}

# Qualifiers that make an "*_name" column NOT a person name (entity/technical).
_NON_PERSON_NAME = {
    "file", "host", "path", "code", "product", "category", "sub", "table",
    "column", "field", "event", "app", "application", "service", "tag", "role",
    "screen", "class", "feature", "node", "queue", "topic", "bucket", "index",
    "template", "theme", "font", "icon", "color", "currency", "language",
    "locale", "timezone", "region", "zone", "status", "type", "group",
    "channel", "segment", "plan", "tier", "sku", "model", "version", "build",
    "release", "project", "repo", "repository", "branch", "package", "module",
    "method", "function", "variable", "step", "stage", "device", "machine",
    "server", "cluster", "network", "site", "page", "menu", "item", "schema",
    "database", "param", "metric", "report", "dashboard", "widget", "section",
    "label", "store", "shop", "domain",
}

# Qualifiers that make an "*_address" column NOT a street address.
_NON_STREET_ADDRESS = {
    "ip", "mac", "wallet", "contract", "network", "memory", "bus", "return",
    "web", "url", "server", "host", "gateway", "broadcast", "subnet", "proxy",
    "peer", "node", "eth", "btc", "token", "device", "email",
}

# Tokens that, appearing anywhere, pin the whole column to one generator.
_PHONE_TOKENS = {"phone", "mobile", "telephone", "fax", "msisdn"}


def _infer_text_type(col_name: str) -> Optional[str]:
    """Infer a semantic ``text_type`` from a column name (token-aware).

    Returns ``None`` when nothing matches confidently, leaving the column as
    free text rather than guessing a wrong generator.
    """
    n = col_name.lower().strip().replace(" ", "_").replace("-", "_")
    if not n:
        return None
    # 1. Exact hint wins.
    if n in _TEXT_TYPE_HINTS:
        return _TEXT_TYPE_HINTS[n]
    # 2. Identifier-like suffix -> uuid (anonymous_id, request_id, device_token).
    if n.endswith(_ID_SUFFIXES) or n in ("uuid", "guid"):
        return "uuid"
    tokens = [t for t in re.split(r"[^a-z0-9]+", n) if t]
    if not tokens:
        return None
    head = tokens[-1]
    qualifier = tokens[-2] if len(tokens) >= 2 else ""
    # 3. Strong tokens anywhere.
    if "email" in tokens:
        return "email"
    if any(t in _PHONE_TOKENS for t in tokens):
        return "phone"
    # 4. Whole-word compound hint key as a suffix (billing_address, first_name).
    for key in _COMPOUND_HINT_KEYS:
        if n == key or n.endswith("_" + key):
            return _TEXT_TYPE_HINTS[key]
    # 5. "name" head — person name unless the qualifier marks an entity/tech name.
    if head == "name":
        if qualifier in _NAME_QUALIFIER_TYPE:
            return _NAME_QUALIFIER_TYPE[qualifier]
        if qualifier in _NON_PERSON_NAME:
            return None
        return "name"
    # 6. "address" head — street address unless a network/crypto address.
    if head == "address":
        if qualifier in _NON_STREET_ADDRESS:
            return None
        return "address"
    # 7. Unambiguous head tokens.
    return _HEAD_TYPE.get(head)


# Keys `_col_from_dict` interprets itself. Everything not in here is carried
# through to the engine verbatim, so a new generator feature works from a dict
# schema the day it lands rather than the day somebody remembers this list.
_CONSUMED_COLUMN_KEYS = frozenset({
    "type", "primary_key", "foreign_key", "unique", "nullable", "description",
    "enum", "choices", "probabilities", "weights",
    "min", "max", "decimals",
    "min_date", "max_date", "start", "end",
    "probability",
})


def _col_from_dict(
    col_name: str,
    col_def: Dict[str, Any],
    primary_key_col: Optional[str],
    row_count: Optional[int] = None,
) -> Optional[Column]:
    """Convert a single dict column definition to a Misata ``Column``."""
    raw_type = str(col_def.get("type", "string")).lower()

    # Primary keys → a surrogate key, bounded by how many rows there are.
    #
    # Real surrogate keys run 1..N, so a twenty row dimension has keys 1 to 20,
    # not values scattered up to two million. With `unique` set and a range of
    # exactly N, every value is used.
    if col_def.get("primary_key") and col_name == primary_key_col:
        upper = int(row_count) if isinstance(row_count, int) and row_count > 0 else 2_000_000
        return Column(
            name=col_name,
            type="int",
            distribution_params={"distribution": "uniform", "min": 1, "max": max(upper, 1)},
            nullable=False,
            unique=True,
        )

    # FK declared inline as a nested dict
    fk_ref = col_def.get("foreign_key")
    if fk_ref or raw_type == "foreign_key":
        return Column(
            name=col_name,
            type="foreign_key",
            distribution_params={},
            unique=bool(col_def.get("unique", False)),
            nullable=bool(col_def.get("nullable", False)),
        )

    misata_type = resolve_column_type(raw_type, where=f"column {col_name!r}")

    # Detect categorical from enum constraint
    enum = col_def.get("enum") or col_def.get("choices")
    if enum and isinstance(enum, list) and misata_type in ("text", "int", "float"):
        misata_type = "categorical"

    params: Dict[str, Any] = {}

    if misata_type == "categorical":
        choices = [str(c) for c in enum] if enum else ["Unknown"]
        params["choices"] = choices
        _probs = col_def.get("probabilities") or col_def.get("weights")
        if _probs is not None:
            params["probabilities"] = list(_probs)

    elif misata_type in ("int", "float"):
        if col_def.get("min") is not None:
            params["min"] = col_def["min"]
        if col_def.get("max") is not None:
            params["max"] = col_def["max"]
        if col_def.get("decimals") is not None:
            params["decimals"] = col_def["decimals"]

    elif misata_type == "text":
        # Token-aware inference: exact name, id-suffix, whole-word compound key,
        # then guarded head tokens — never a raw substring scan.
        # Only guess when the caller said nothing: an explicit `text_type` (or
        # `subtype`) from the dict schema is never overridden by a heuristic.
        _stated = col_def.get("text_type") or col_def.get("subtype")
        if _stated:
            params["text_type"] = _stated
            params.pop("_text_type_is_default", None)
        inferred = None if _stated else _infer_text_type(col_name)
        if inferred:
            params["text_type"] = inferred
            # This is a guess from the column name, not something the caller
            # asked for, and downstream has to be able to tell the difference.
            # A declared text_type beats domain inference, so without this
            # marker a column merely *called* `name` in a healthcare schema
            # would suppress the medical-department vocabulary it should get.
            params["_text_type_is_default"] = True
        # Explicit raw type in the dict schema always wins
        if raw_type in ("email", "phone", "url", "uuid"):
            params["text_type"] = raw_type
            params.pop("_text_type_is_default", None)

    elif misata_type in ("date", "datetime"):
        # "min"/"max" are what the MCP tool documents for date bounds and what
        # agents write, so they bound the window alongside "min_date"/"start";
        # the 2020-2024 default applies only when no bound is declared.
        params["start"] = col_def.get("min_date", col_def.get("start", col_def.get("min", "2020-01-01")))
        params["end"] = col_def.get("max_date", col_def.get("end", col_def.get("max", "2024-12-31")))

    elif misata_type == "boolean":
        if col_def.get("probability") is not None:
            params["probability"] = col_def["probability"]
        elif isinstance(col_def.get("enum"), list) and len(col_def["enum"]) == 1:
            # A single-value boolean enum (e.g. "enum": [False]) declares a
            # constant, same as it does for string/int/float columns above.
            # "enum" is a consumed key and the engine's boolean generator reads
            # only "probability", so the constant is expressed as a
            # probability of 1.0 or 0.0.
            params["probability"] = 1.0 if bool(col_def["enum"][0]) else 0.0

    # ── Everything else reaches the engine ───────────────────────────────────
    # Name the keys consumed above and pass the rest through. An allowlist
    # drops any declaration nobody remembered to add (a declared `template`
    # would produce generic filler instead).
    #
    # Passing through is also the safer direction. An unknown key carried into
    # distribution_params is ignored by the engine, while a known key dropped
    # here is a declaration that does nothing while the schema still reads as
    # though it means something.
    for key, value in col_def.items():
        if key not in _CONSUMED_COLUMN_KEYS and value is not None:
            params.setdefault(key, value)

    # The poisson generator reads "lambda"; accept the common "lam" alias too.
    if "lam" in params and "lambda" not in params:
        params["lambda"] = params["lam"]

    nullable = bool(col_def.get("nullable", True))
    unique = bool(col_def.get("unique", False))
    description = col_def.get("description") or None
    # A declared semantic type reaches the Column rather than being swallowed
    # into distribution_params, so the dict path can state a column's meaning
    # instead of leaving it to be guessed from the name.
    semantic = col_def.get("semantic") or None

    return Column(
        name=col_name,
        type=misata_type,
        distribution_params=params,
        nullable=nullable,
        unique=unique,
        semantic=semantic,
        description=description,
    )


def _auto_constraint_name(c_def: Dict[str, Any], index: int) -> str:
    """Build a descriptive constraint name from its shape.

    The ``Constraint`` model requires a ``name``, but it is purely cosmetic. Dict,
    YAML, and MCP-agent callers shouldn't have to invent one, so we synthesise a
    readable name from the constraint's columns and operator.
    """
    ctype = str(c_def.get("type", "constraint"))
    if c_def.get("column_a") and c_def.get("column_b"):
        op = c_def.get("operator", "?")
        return f"{ctype}_{c_def['column_a']}_{op}_{c_def['column_b']}"
    if c_def.get("low_column") and c_def.get("high_column"):
        return f"{ctype}_{c_def.get('column', 'col')}_in_{c_def['low_column']}_{c_def['high_column']}"
    if c_def.get("group_by"):
        return f"{ctype}_{'_'.join(map(str, c_def['group_by']))}"
    return f"{ctype}_{index}"


def _detect_pk(table_def: Dict[str, Any]) -> Optional[str]:
    for col_name, col_def in table_def.items():
        if isinstance(col_def, dict) and col_def.get("primary_key"):
            return col_name
    return "id" if "id" in table_def else None


def _column_defs_of(table_def: Any) -> Dict[str, Any]:
    """Extract the flat column-definitions dict from a table def, unwrapping
    the nested ``{"rows": N, "columns": {...}}`` form when present. Shared by
    the per-table PK detection below and by the FK-default-column lookup in
    ``from_dict_schema`` (a parent table can be in either shape regardless of
    which shape the child referencing it happens to use)."""
    if not isinstance(table_def, dict):
        return {}
    raw_columns = table_def.get("columns")
    if (
        isinstance(raw_columns, dict)
        and raw_columns
        and all(isinstance(v, dict) for v in raw_columns.values())
    ):
        return raw_columns
    return table_def


def _looks_like_table_def(value: Any) -> bool:
    """A table definition (vs a column definition) has a ``columns`` dict or a
    row-count key; a column definition has a ``type``/``enum``-shaped body."""
    if not isinstance(value, dict):
        return False
    if isinstance(value.get("columns"), dict):
        return True
    return any(k in value for k in ("rows", "row_count", "__rows__", "__row_count__"))


def _parse_relationship_entry(entry: Any) -> Optional[Relationship]:
    """Parse an envelope-level relationship: ``"users.user_id → orders.user_id"``
    (or ``->``), or a dict with parent/child keys."""
    if isinstance(entry, str):
        for arrow in ("→", "->"):
            if arrow in entry:
                left, right = (s.strip() for s in entry.split(arrow, 1))
                if "." in left and "." in right:
                    p_table, p_key = (s.strip() for s in left.rsplit(".", 1))
                    c_table, c_key = (s.strip() for s in right.rsplit(".", 1))
                    return Relationship(parent_table=p_table, child_table=c_table,
                                        parent_key=p_key, child_key=c_key)
        return None
    if isinstance(entry, dict):
        try:
            return Relationship(**entry)
        except (TypeError, ValueError):
            return None
    return None


def _unwrap_envelope(schemas: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize the YAML-style envelope format into the flat dict format.

    ``{"name": ..., "seed": ..., "tables": {...}, "relationships": [...]}``
    is what ``misata.yaml`` and several README examples use; callers frequently
    hand the same shape to :func:`from_dict_schema`. Unwrapping it keeps
    ``tables`` from being read as a table named "tables".
    """
    raw_tables = schemas.get("tables")
    if not isinstance(raw_tables, dict) or not raw_tables:
        return schemas
    if not all(_looks_like_table_def(v) for v in raw_tables.values()):
        # ``tables`` is (bizarrely) a real table of column defs — leave it alone.
        return schemas

    flat: Dict[str, Any] = {}
    # Hoist known envelope keys into their dunder forms.
    if schemas.get("name"):
        flat["__name__"] = schemas["name"]
    if schemas.get("seed") is not None:
        flat["__seed__"] = schemas["seed"]
    if schemas.get("domain"):
        flat["__domain__"] = schemas["domain"]
    if schemas.get("generation_mode"):
        flat["__generation_mode__"] = schemas["generation_mode"]
    if schemas.get("rows") is not None:
        flat["__rows__"] = schemas["rows"]
    for env_key, dunder in _ENVELOPE_KEYS:
        if schemas.get(env_key) is not None:
            flat[dunder] = schemas[env_key]

    # `locale` is published at the top level by our own JSON Schema, which
    # SchemaStore ships to every editor, so that is the spelling people are
    # autocompleted into. It lives on RealismConfig internally. Accept the
    # documented spelling and fold it in, so the declared locale is the one
    # the data uses.
    if schemas.get("locale"):
        realism_block = dict(flat.get("__realism__") or {})
        realism_block.setdefault("locale", schemas["locale"])
        flat["__realism__"] = realism_block
    # Preserve any dunder directives passed alongside the envelope.
    for k, v in schemas.items():
        if k.startswith("__"):
            flat[k] = v
    if schemas.get("relationships"):
        flat["__relationships__"] = schemas["relationships"]
    # Envelope-level constraints route to their table's __constraints__.
    for c_def in schemas.get("constraints") or []:
        if isinstance(c_def, dict) and c_def.get("table") in raw_tables:
            tdef = raw_tables[c_def["table"]]
            if isinstance(tdef, dict):
                tdef.setdefault("__constraints__", []).append(
                    {k: v for k, v in c_def.items() if k != "table"})
    flat.update(raw_tables)
    return flat


# Envelope directives that are lists of dicts, each already carrying its own
# "table" field ({"table": "sales", "measure": "revenue", ...}) -- unlike
# __correlations__ and __constraints__, which are read only from inside a
# table's own dict, every one of these is read only from the schema's TOP
# level. Nesting __group_shares__ inside its table (the pattern
# __correlations__ uses) is a natural mistake, so these keys are hoisted from a
# table's dict to the top level rather than ignored, and the declared shares
# hold wherever they were written.
_TABLE_HOISTABLE_ENVELOPE_KEYS: Tuple[str, ...] = tuple(
    dunder for _attr, dunder in _ENVELOPE_KEYS
    if dunder not in ("__realism__", "__vocabulary__")
)


def _hoist_table_scoped_envelope_directives(schemas: Dict[str, Any]) -> Dict[str, Any]:
    """A directive nested inside the table it describes is accepted the same
    as one declared at the schema's top level -- merged in, "table" filled
    in from context when the entry omits it, never silently dropped."""
    if not isinstance(schemas, dict):
        return schemas
    hoisted: Dict[str, list] = {}
    patched: Dict[str, Any] = dict(schemas)
    for key, value in schemas.items():
        if key.startswith("__") or not isinstance(value, dict):
            continue
        misplaced = [k for k in _TABLE_HOISTABLE_ENVELOPE_KEYS if k in value]
        if not misplaced:
            continue
        table_def = dict(value)
        for dunder in misplaced:
            entries = table_def.pop(dunder) or []
            for entry in entries:
                if isinstance(entry, dict):
                    entry = {**entry}
                    entry.setdefault("table", key)
                hoisted.setdefault(dunder, []).append(entry)
        patched[key] = table_def
    for dunder, entries in hoisted.items():
        patched[dunder] = list(patched.get(dunder) or []) + entries
    return patched


def _dedupe_relationships(rels: List[Relationship]) -> List[Relationship]:
    """One relationship per edge, keeping the one that says the most.

    A schema can describe the same edge twice: inline on the column
    (`foreign_key: {...}`) and explicitly in `__relationships__`. Only the
    explicit form can carry `partition_by`, `min_children`, temporal
    eligibility or filters, and the FK generator takes the FIRST relationship
    matching a column — so whichever landed first won, and a declaration could
    be silently shadowed by an inferred duplicate of itself.

    Merging rather than dropping: the richer entry wins field by field, so an
    inline FK plus an explicit `partition_by` produces one edge carrying both.
    """
    merged: Dict[tuple, Relationship] = {}
    order: List[tuple] = []
    for rel in rels:
        key = (rel.parent_table, rel.child_table, rel.parent_key, rel.child_key)
        prior = merged.get(key)
        if prior is None:
            merged[key] = rel
            order.append(key)
            continue
        # Keep every non-default the pair carries between them.
        data = prior.model_dump()
        for field, value in rel.model_dump().items():
            if value in (None, [], {}, 0, False):
                continue
            if data.get(field) in (None, [], {}, 0, False):
                data[field] = value
        merged[key] = Relationship(**data)
    return [merged[k] for k in order]


def _build_entries(key: str, entries: Any, build: Callable[[Any], Any]) -> List[Any]:
    """Build each entry of a ``__key__`` directive, skipping malformed ones.

    One malformed directive does not abort the whole schema: it is skipped
    with a warning so the rest still produces data, and recorded in
    ``_DROPPED`` so feasibility can refuse it by name.
    """
    out: List[Any] = []
    for i, raw in enumerate(entries or []):
        try:
            out.append(build(raw))
        except Exception as e:  # noqa: BLE001 - any malformed entry is skipped and recorded
            warn(f"Skipping invalid __{key}__[{i}]: {e}", ConformanceWarning)
            _DROPPED.append((key, i, str(e)))
    return out


def _build_rate_curve(rate_def: Any) -> RateCurve:
    """A rate curve, accepting ``curve_points`` or ``points`` for ``rate_points``.

    ``curve_points`` is the outcome curves' key and is often carried over, so
    it is read as the rate points rather than ignored.
    """
    if isinstance(rate_def, dict) and not rate_def.get("rate_points"):
        rate_def = {**{k: v for k, v in rate_def.items() if k not in ("curve_points", "points")},
                    "rate_points": rate_def.get("curve_points") or rate_def.get("points") or []}
        if not rate_def["rate_points"]:
            raise ValueError("no rate_points: give [{'period': 'YYYY-MM', 'rate': 0.03}, ...]")
    return RateCurve(**rate_def)


def _build_degradation(d_def: Any) -> "Degradation":
    d_def = dict(d_def)
    d_def["responses"] = [SensorResponse(**r) for r in (d_def.get("responses") or [])]
    return Degradation(**d_def)


def _declared_directives(schemas: Dict[str, Any]) -> Dict[str, List[Any]]:
    """Every schema-level declaration list, keyed by its SchemaConfig field.

    Every SchemaConfig declaration is reachable from the dict and YAML forms,
    so ``misata lint`` accepts the files the docs show. One table, so the next
    declaration is one line rather than a new branch.
    """
    from misata.schema import (Bitemporal, CohortRetention, DagEdges,
                               Duplicates, EventLog, GraphMotifs,
                               JointDistribution, LateArrival, Lifecycle,
                               Missingness, Outliers, Process, ScenarioEvent,
                               TimeGrid, TransitiveClosure, Typos)

    builders: Tuple[Tuple[str, Callable[[Any], Any]], ...] = (
        ("outcome_curves", lambda raw: OutcomeCurve(**raw)),
        ("rate_curves", _build_rate_curve),
        ("group_shares", lambda raw: GroupShares(**raw)),
        ("waterfalls", lambda raw: WaterfallIdentity(**raw)),
        # Units that wear out: registering the envelope key is not the same
        # as building the object, so each entry is built or recorded dropped.
        ("degradations", _build_degradation),
        ("stock_flows", lambda raw: StockFlowIdentity(**raw)),
        ("events", lambda raw: ScenarioEvent(**raw)),
        ("lifecycles", lambda raw: Lifecycle(**raw)),
        ("retention", lambda raw: CohortRetention(**raw)),
        ("missingness", lambda raw: Missingness(**raw)),
        ("late_arrivals", lambda raw: LateArrival(**raw)),
        ("time_grids", lambda raw: TimeGrid(**raw)),
        ("duplicates", lambda raw: Duplicates(**raw)),
        ("event_logs", lambda raw: EventLog(**raw)),
        ("outliers", lambda raw: Outliers(**raw)),
        ("typos", lambda raw: Typos(**raw)),
        ("bitemporal", lambda raw: Bitemporal(**raw)),
        ("dag_edges", lambda raw: DagEdges(**raw)),
        ("graph_motifs", lambda raw: GraphMotifs(**raw)),
        ("joint_distributions", lambda raw: JointDistribution(**raw)),
        ("closures", lambda raw: TransitiveClosure(**raw)),
        ("processes", lambda raw: Process(**raw)),
    )
    return {key: _build_entries(key, schemas.get(f"__{key}__"), build)
            for key, build in builders}


def _default_row_count(schemas: Dict[str, Any], row_count: Optional[int]) -> int:
    """The row count for tables that do not state one.

    An explicit ``row_count`` argument wins, since that is the caller
    overriding the document; then the schema's own top-level ``rows``, which
    the published JSON Schema offers; then 1000.
    """
    if row_count is not None:
        return row_count
    declared_rows = schemas.get("__rows__")
    if declared_rows is None:
        declared_rows = schemas.get("rows")
    if isinstance(declared_rows, int) and not isinstance(declared_rows, bool) and declared_rows >= 0:
        return declared_rows
    return 1000


def _schema_vocabularies(schemas: Dict[str, Any]) -> Optional[Dict[str, List[str]]]:
    """``__vocabulary__``: the schema-embedded mini-capsule of column name to
    real values, sampled by the engine for open-ended text columns."""
    raw_vocab = schemas.get("__vocabulary__")
    if not isinstance(raw_vocab, dict):
        return None
    cleaned = {
        str(k).strip().lower(): [str(x).strip() for x in v if str(x).strip()]
        for k, v in raw_vocab.items()
        if isinstance(v, (list, tuple))
    }
    return {k: v for k, v in cleaned.items() if len(v) >= 2} or None


def _table_row_count(table_def: Dict[str, Any], default: int) -> int:
    """A table's own row count, so a 6-table schema can say "4 regions, 50
    sites, 5000 logs". An explicit 0 (empty table) is honoured; a missing,
    negative or non-int value (``bool`` included) falls back to ``default``."""
    for rows_key in ("__rows__", "__row_count__", "rows", "row_count"):
        val = table_def.get(rows_key)
        if isinstance(val, int) and not isinstance(val, bool) and val >= 0:
            return val
    return default


def _table_constraints(table_name: str, table_def: Dict[str, Any]) -> List[Constraint]:
    """Per-table constraints, e.g. inequality (end_date > start_date) or col_range.

    Format: ``__constraints__: [{type: "inequality", column_a: "x", operator:
    ">", column_b: "y"}]``. ``name`` is required by the Constraint model but is
    purely descriptive, so it is filled in from the constraint's shape when
    omitted. A malformed constraint is skipped with a warning.
    """
    table_constraints: List[Constraint] = []
    for i, c_def in enumerate(table_def.get("__constraints__") or []):
        if isinstance(c_def, dict) and not c_def.get("name"):
            c_def = {**c_def, "name": _auto_constraint_name(c_def, i)}
        try:
            table_constraints.append(Constraint(**c_def))
        except Exception as e:  # noqa: BLE001 - a malformed constraint is skipped with a warning
            warn(f"Table '{table_name}' __constraints__[{i}] is invalid and was skipped: {e}", ConformanceWarning)
    return table_constraints


def _table_correlations(table_def: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pearson correlations between numeric columns, applied after generation.

    Two formats are accepted. A pairwise list::

        __correlations__: [{col_a: "bmi", col_b: "systolic_bp", r: 0.41}]

    or a full matrix, expanded here into pairs above the diagonal::

        __correlations__:
          method: cholesky
          matrix:
            columns: [hba1c, glucose, bmi, systolic_bp]
            values:
              hba1c:   [1.00, 0.68, 0.31, 0.22]
              glucose: [0.68, 1.00, 0.35, 0.28]
              ...
    """
    raw_corr = table_def.get("__correlations__") or []
    if not (isinstance(raw_corr, dict) and "matrix" in raw_corr):
        return list(raw_corr)
    mat_spec = raw_corr["matrix"]
    cols_order = mat_spec.get("columns", [])
    values_map = mat_spec.get("values", {})
    table_correlations: List[Dict[str, Any]] = []
    for i, col_a in enumerate(cols_order):
        row_vals = values_map.get(col_a, [])
        if isinstance(row_vals, (list, tuple)):
            for j, col_b in enumerate(cols_order):
                if j > i and j < len(row_vals):
                    r = float(row_vals[j])
                    if abs(r) > 0.001:
                        table_correlations.append({"col_a": col_a, "col_b": col_b, "r": r})
    return table_correlations


def _column_relationship(schemas: Dict[str, Any], table_name: str, col_name: str,
                         col_def: Dict[str, Any]) -> Optional[Relationship]:
    """The relationship a column declares inline, if any.

    Accepted forms: a nested ``foreign_key: {"table": ..., "column": ...}``
    dict, the ``foreign_key: "parent_table.parent_key"`` shorthand, or
    ``references: "parent_table.parent_key"`` on a foreign-key column.
    """
    fk_ref = col_def.get("foreign_key")
    if fk_ref and isinstance(fk_ref, dict):
        # ``{"table": "parent"}`` with no explicit ``column`` points at the
        # parent's actual primary key, resolved the way _detect_pk does, so a
        # parent keyed by something other than "id" still gets a relationship
        # to a column that exists. "id" is the fallback only when the parent
        # is not declared in this dict.
        parent_def = schemas.get(fk_ref["table"])
        resolved_pk = (
            _detect_pk(_column_defs_of(parent_def)) if parent_def is not None else None
        )
        return Relationship(
            parent_table=fk_ref["table"],
            child_table=table_name,
            parent_key=fk_ref.get("column") or resolved_pk or "id",
            child_key=col_name,
            # Every parent gets at least this many children (an order with a
            # line), declared inline as well as in __relationships__.
            **({"min_children": int(fk_ref["min_children"])} if fk_ref.get("min_children") else {}),
        )
    if isinstance(fk_ref, str) and "." in fk_ref:
        p_table, p_key = fk_ref.rsplit(".", 1)
    elif (
        isinstance(col_def.get("references"), str)
        and "." in col_def["references"]
        and (fk_ref or str(col_def.get("type", "")).lower() == "foreign_key")
    ):
        p_table, p_key = col_def["references"].rsplit(".", 1)
    else:
        return None
    return Relationship(
        parent_table=p_table.strip(),
        child_table=table_name,
        parent_key=p_key.strip(),
        child_key=col_name,
    )


def _table_vocabulary(table_def: Dict[str, Any]) -> Dict[str, List[str]]:
    """Table-level ``__vocabulary__`` (the canvas round-trip form), merged up
    into the schema-level mini-capsule by the caller."""
    vocab: Dict[str, List[str]] = {}
    table_vocab = table_def.get("__vocabulary__")
    if isinstance(table_vocab, dict):
        for k, v in table_vocab.items():
            if isinstance(v, (list, tuple)):
                vals = [str(x).strip() for x in v if str(x).strip()]
                if len(vals) >= 2:
                    vocab[str(k).strip().lower()] = vals
    return vocab


def _inline_rows(table_def: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Reference rows given verbatim, or None.

    A date dimension is a calendar, not a sample: its months, quarters and
    years are facts that agree with each other, so they are taken as written
    rather than generated column by column.
    """
    for key in ("__inline_data__", "__rows_data__", "inline_data"):
        candidate = table_def.get(key)
        if isinstance(candidate, list) and candidate and all(
                isinstance(r, dict) for r in candidate):
            return candidate
    return None


def _table_from_def(
    schemas: Dict[str, Any], table_name: str, table_def: Dict[str, Any],
    default_rows: int, relationships: List[Relationship],
) -> Tuple[Table, List[Column]]:
    """One table and its columns; inline relationships go into ``relationships``."""
    # Support both __table_description__ and __description__ as table-level metadata
    table_desc = (
        table_def.get("__table_description__")
        or table_def.get("__description__")
        or None
    )
    table_rows = _table_row_count(table_def, default_rows)

    # A table whose rows are given verbatim must not have its key range
    # synthesised: a date_key of 20240101 does not fit in 1..730.
    has_inline_rows = any(
        isinstance(table_def.get(k), list) and table_def.get(k)
        for k in ("__inline_data__", "__rows_data__", "inline_data"))

    # Nested per-table format: {"rows": N, "columns": {...}}. Column defs come
    # from the sub-dict while table-level keys stay on the outer def. (This is
    # the misata.yaml shape handed to dict callers.)
    col_source = _column_defs_of(table_def)
    pk_col = _detect_pk(col_source)
    table_constraints = _table_constraints(table_name, table_def)
    table_correlations = _table_correlations(table_def)

    table_cols: List[Column] = []
    for col_name, col_def in col_source.items():
        if col_name.startswith("__") or not isinstance(col_def, dict):
            continue
        rel = _column_relationship(schemas, table_name, col_name, col_def)
        if rel is not None:
            relationships.append(rel)
        col = _col_from_dict(col_name, col_def, primary_key_col=pk_col,
                             row_count=(None if has_inline_rows else table_rows))
        if col is not None:
            table_cols.append(col)

    inline_rows = _inline_rows(table_def)
    table = Table(
        name=table_name,
        row_count=len(inline_rows) if inline_rows else table_rows,
        description=table_desc,
        constraints=table_constraints,
        correlations=table_correlations,
        state_machine=table_def.get("__state_machine__") or None,
        cluster_effect=table_def.get("__cluster_effect__") or None,
        is_reference=bool(inline_rows),
        inline_data=inline_rows,
    )
    return table, table_cols


def from_dict_schema(
    schemas: Dict[str, Any],
    row_count: Optional[int] = None,
    seed: Any = _SEED_UNSET,
) -> SchemaConfig:
    """Convert a plain dict schema definition to a Misata ``SchemaConfig``.

    This accepts a flexible format where each table is a dict of column
    definitions.  Supported column definition keys:

    - ``type``: data type (see full list below)
    - ``primary_key``: ``True`` to mark as PK (auto-generated, excluded from output)
    - ``foreign_key``: ``{"table": "...", "column": "..."}`` to declare a FK
    - ``min`` / ``max``: numeric range
    - ``min_date`` / ``max_date``: date range
    - ``enum`` / ``choices``: list of allowed values (becomes categorical)
    - ``decimals``: decimal places for floats
    - ``nullable``: whether ``None`` values are allowed (default ``True``)
    - ``unique``: whether values must be unique

    Supported types: ``integer``, ``float``, ``decimal``, ``string``, ``text``,
    ``email``, ``phone``, ``url``, ``uuid``, ``date``, ``datetime``,
    ``timestamp``, ``boolean``, ``foreign_key``.

    Schema-level directives (top-level keys, siblings of the tables). Every
    one below may ALSO be nested inside the table dict it describes (the
    ``__correlations__``/``__constraints__`` placement) — each entry's own
    ``"table"`` field is filled in from that nesting when omitted, and
    either placement reaches the same declaration:

    - ``__outcome_curves__``: list of declared aggregate targets, e.g.
      ``[{"table": "orders", "column": "amount", "time_column": "order_date",
      "time_unit": "month", "value_mode": "absolute", "start_date": "2024-01-01",
      "curve_points": [{"month": 1, "target_value": 50000.0}, ...]}]`` —
      generated rows sum to each period's target exactly.
    - ``__rate_curves__``: list of per-period rate targets for boolean or
      categorical columns, e.g. ``[{"table": "transactions", "column":
      "is_fraud", "time_column": "transaction_date", "rate_points":
      [{"period": "2024-01", "rate": 0.03}, ...]}]``.
    - ``__group_shares__``: exact shares of a measure across a categorical
      column, e.g. ``[{"table": "orders", "measure": "revenue",
      "group_column": "category", "shares": {"Electronics": 0.4,
      "Home": 0.25, "Toys": 0.2, "Grocery": 0.15}}]``. Paired with an
      outcome curve on the same table and measure, the shares hold exactly
      inside every declared period; otherwise over the table total.
    - ``__noise__``: declared data-quality defects injected at a known rate, so
      a cleaning / DQ pipeline can be tested against ground truth, e.g.
      ``{"mode": "custom", "duplicate_rate": 0.03, "null_rate": 0.02,
      "outlier_rate": 0.01, "typo_rate": 0.01}``. Use ``mode:
      "analytics_safe"`` to mutate only non-key columns and never duplicate
      rows (keeps PK/FK integrity and declared aggregates intact).

    Args:
        schemas:   Dict mapping table name → column definitions dict.
        row_count: Default row count for every table.
        seed:      Random seed for reproducibility.

    Returns:
        :class:`~misata.schema.SchemaConfig` ready for
        :func:`~misata.generate_from_schema`.

    Example::

        schema = misata.from_dict_schema({
            "products": {
                "id":       {"type": "integer", "primary_key": True},
                "name":     {"type": "string"},
                "price":    {"type": "float", "min": 1.0, "max": 999.0},
                "category": {"type": "string", "enum": ["Electronics", "Clothing", "Books"]},
            },
            "orders": {
                "id":         {"type": "integer", "primary_key": True},
                "product_id": {"type": "integer",
                               "foreign_key": {"table": "products", "column": "id"}},
                "quantity":   {"type": "integer", "min": 1, "max": 10},
                "placed_at":  {"type": "date"},
            },
        }, row_count=5000)

        tables = misata.generate_from_schema(schema)
    """
    _DROPPED.clear()
    schemas = _unwrap_envelope(schemas)
    schemas = _hoist_table_scoped_envelope_directives(schemas)

    # `locale` is published at the top level by the JSON Schema and lives on
    # RealismConfig internally. _unwrap_envelope folds it in for the envelope
    # form; the flat form is folded in here, so either spelling reaches the
    # generator.
    if isinstance(schemas.get("locale"), str):
        realism_block = dict(schemas.get("__realism__") or {})
        realism_block.setdefault("locale", schemas["locale"])
        schemas = {**schemas, "__realism__": realism_block}

    tables: List[Table] = []
    columns_map: Dict[str, List[Column]] = {}
    relationships: List[Relationship] = []

    # Envelope metadata hoisted by _unwrap_envelope.
    # Both spellings. `__name__` is this path's own dialect; `name` is what the
    # published JSON Schema documents and what the YAML loader honours, so the
    # same document gets the same name through either entry point.
    # Only when it is metadata. A schema may contain a table literally called
    # `name`, in which case the value is a mapping of columns and taking it as
    # the dataset's title fails validation.
    _declared_name = schemas.get("name")
    schema_name = (schemas.get("__name__")
                   or (_declared_name if isinstance(_declared_name, str) else None)
                   or "Imported schema")
    if schemas.get("__seed__") is not None:
        try:
            seed = int(schemas["__seed__"])
        except (TypeError, ValueError):
            pass
    for i, rel_def in enumerate(schemas.get("__relationships__") or []):
        rel = _parse_relationship_entry(rel_def)
        if rel is not None:
            relationships.append(rel)
        else:
            warn(f"Skipping unparseable relationships[{i}]: {rel_def!r}", ConformanceWarning)

    # Top-level directives (not tables): the schema-level half of the engine
    # contract. A malformed entry is skipped with a warning rather than
    # aborting generation, mirroring the resilience of the LLM-parser path.
    declared = _declared_directives(schemas)

    # __noise__ injects declared data-quality defects (nulls, outliers, typos,
    # duplicates) at a known rate, so a data-cleaning pipeline can be tested
    # against ground truth. Unlike the shaping directives it fails loudly: a
    # malformed spec silently dropped would run that test on clean data.
    noise_config: Optional[NoiseConfig] = None
    raw_noise = schemas.get("__noise__")
    if raw_noise:
        try:
            noise_config = NoiseConfig(**raw_noise)
        except Exception as e:
            raise ValueError(f"__noise__ is invalid: {e}") from e

    effective_row_count = _default_row_count(schemas, row_count)

    # __realism__ carries locale and the realism switches. It fails loudly for
    # the same reason as __noise__: an ignored realism block hands back data
    # that looks fine and is not what was asked for.
    realism_config: Optional[RealismConfig] = None
    raw_realism = schemas.get("__realism__")
    if raw_realism:
        try:
            realism_config = RealismConfig(**raw_realism)
        except Exception as e:
            raise ValueError(f"realism is invalid: {e}") from e

    # __domain__ stores the domain name on the SchemaConfig for post-generation validation
    domain: Optional[str] = schemas.get("__domain__") or None
    vocabularies = _schema_vocabularies(schemas)
    # Per-table __vocabulary__ entries collect here and merge below; explicit
    # top-level entries win on key collisions.
    table_vocabularies: Dict[str, List[str]] = {}

    for table_name, table_def in schemas.items():
        if table_name.startswith("__"):
            continue
        if table_name == "generation_mode" and isinstance(table_def, str):
            continue  # flat-form directive, read below
        if not isinstance(table_def, dict):
            # A recognised top-level key carrying metadata is not a malformed
            # table: the documented `name` and `seed` pass without a warning.
            #
            # The test is the VALUE, not the key: `name: "sales"` is metadata,
            # while `name: {...columns...}` is a table that happens to be
            # called name, and a schema is allowed to have one.
            if (table_name in HANDLED_TOP_LEVEL_KEYS
                    or table_name in UNHANDLED_TOP_LEVEL_KEYS):
                continue
            warn(
                f"Skipping {table_name!r}: a table must be a mapping of column "
                f"names to definitions, and this is a "
                f"{type(table_def).__name__}.",
                ConformanceWarning,)
            continue

        table, table_cols = _table_from_def(
            schemas, table_name, table_def, effective_row_count, relationships)
        table_vocabularies.update(_table_vocabulary(table_def))
        tables.append(table)
        columns_map[table_name] = table_cols

    config = SchemaConfig(
        name=schema_name,
        tables=tables,
        columns=columns_map,
        relationships=_dedupe_relationships(relationships),
        **declared,
        preset=schemas.get("__preset__"),
        generation_mode=(schemas.get("__generation_mode__")
                         or schemas.get("generation_mode") or "anchored"),
        noise_config=noise_config,
        realism=realism_config,
        # An explicit argument wins; otherwise honour the `seed` written in the
        # document, which the JSON Schema publishes and the YAML loader reads.
        # The same document must produce the same bytes through both loaders,
        # which is the one thing a seed exists to guarantee.
        seed=(seed if seed is not _SEED_UNSET
              else (schemas["seed"] if isinstance(schemas.get("seed"), int)
                    else 42)),
        domain=domain,
        vocabularies=({**table_vocabularies, **(vocabularies or {})} or None),
    )
    # Carry what this parse could not build, so feasibility can refuse it by
    # name instead of the schema quietly arriving one declaration short.
    object.__setattr__(config, "_dropped_declarations", tuple(_DROPPED))
    return config


# ---------------------------------------------------------------------------
# Post-generation referential integrity verification
# ---------------------------------------------------------------------------

class IntegrityReport:
    """Result of a referential integrity check across FK relationships.

    ``relationships`` holds one entry per declared relationship — intact ones
    included (``{"relationship": ..., "intact": True, "orphans": 0}``) — so
    the report is a positive proof, not just an absence of complaints.
    """

    def __init__(
        self,
        violations: List[Dict[str, Any]],
        relationships: Optional[List[Dict[str, Any]]] = None,
    ):
        self.violations = violations
        self.relationships = relationships or []
        self.ok = len(violations) == 0

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serialisable form: ``{"ok", "relationships", "violations"}``."""
        return {
            "ok": self.ok,
            "relationships": self.relationships,
            "violations": self.violations,
        }

    def __repr__(self) -> str:
        if self.ok:
            return "IntegrityReport(ok=True, violations=0)"
        lines = [f"IntegrityReport(ok=False, violations={len(self.violations)}):"]
        for v in self.violations:
            count = v["orphan_count"]
            count_str = f"{count:,} orphans" if count >= 0 else "table missing"
            lines.append(f"  {v['relationship']}: {count_str} — {v['issue']}")
            if "sample_orphans" in v:
                lines.append(f"    sample values: {v['sample_orphans']}")
        return "\n".join(lines)

    def raise_if_invalid(self) -> None:
        """Raise ``ValueError`` if any violations were found."""
        if not self.ok:
            raise ValueError(str(self))


def verify_integrity(
    tables: Dict[str, Any],
    schema: SchemaConfig,
) -> IntegrityReport:
    """Verify referential integrity across all FK relationships.

    Misata guarantees zero orphans during generation. Use this after manual
    edits, data merges, or multi-step pipelines to catch regressions.

    Args:
        tables: Dict mapping table name → ``pd.DataFrame``.
        schema: The ``SchemaConfig`` that describes the relationships.

    Returns:
        :class:`IntegrityReport` — check ``.ok`` for pass/fail, or call
        ``.raise_if_invalid()`` to turn failures into exceptions.

    Example::

        tables = misata.generate("An ecommerce store with 5k orders", seed=42)
        report = misata.verify_integrity(tables, schema)
        print(report)  # IntegrityReport(ok=True, violations=0)
    """
    import pandas as pd

    violations: List[Dict[str, Any]] = []
    relationships: List[Dict[str, Any]] = []

    def _broken(label: str, issue: str) -> None:
        violations.append({"relationship": label, "issue": issue,
                           "orphan_count": -1})
        relationships.append({"relationship": label, "intact": False,
                              "orphans": -1, "issue": issue})

    for rel in schema.relationships:
        pname, cname = rel.parent_table, rel.child_table
        pkey, ckey = rel.parent_key, rel.child_key
        label = f"{cname}.{ckey} → {pname}.{pkey}"

        if pname not in tables:
            _broken(label, f"Parent table '{pname}' not found.")
            continue
        if cname not in tables:
            _broken(label, f"Child table '{cname}' not found.")
            continue

        parent_df = tables[pname]
        child_df = tables[cname]

        if pkey not in parent_df.columns:
            _broken(label, f"Column '{pkey}' not in '{pname}'.")
            continue
        if ckey not in child_df.columns:
            _broken(label, f"Column '{ckey}' not in '{cname}'.")
            continue

        # Normalise numeric types before membership test: an int PK and a
        # float64 FK column (widened by NaN assignment) would never match
        # without this coercion, producing false orphan reports.
        parent_ids = parent_df[pkey].dropna()
        child_vals = child_df[ckey].dropna()
        if pd.api.types.is_numeric_dtype(parent_ids) and pd.api.types.is_numeric_dtype(child_vals):
            parent_ids = parent_ids.astype(float)
            child_vals = child_vals.astype(float)
        valid_ids = set(parent_ids.unique())
        orphans = child_vals[~child_vals.isin(valid_ids)]

        relationships.append({"relationship": label,
                              "intact": len(orphans) == 0,
                              "orphans": int(len(orphans))})
        if len(orphans) > 0:
            violations.append({
                "relationship": label,
                "issue": "Orphaned FK values detected.",
                "orphan_count": int(len(orphans)),
                "sample_orphans": orphans.unique()[:5].tolist(),
            })

    return IntegrityReport(violations=violations, relationships=relationships)
