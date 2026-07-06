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
import warnings
from typing import Any, Dict, List, Optional

from misata.schema import (
    Column,
    Constraint,
    NoiseConfig,
    OutcomeCurve,
    RateCurve,
    Relationship,
    SchemaConfig,
    Table,
)


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
    "array": "text",
    "json": "text",
    "object": "text",
}

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
# Raw substring matching ("name" in "product_name") wrongly turned entity
# columns into person names and "ip_address"/"mac_address" into street
# addresses. The matcher below anchors on exact names, identifier suffixes,
# whole-word compound keys, and head tokens with explicit guards instead.

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


def _col_from_dict(
    col_name: str,
    col_def: Dict[str, Any],
    primary_key_col: Optional[str],
) -> Optional[Column]:
    """Convert a single dict column definition to a Misata ``Column``."""
    raw_type = str(col_def.get("type", "string")).lower()

    # Primary keys → sequential unique int (name must be "id" for Misata's auto-sequence)
    if col_def.get("primary_key") and col_name == primary_key_col:
        return Column(
            name=col_name,
            type="int",
            distribution_params={"distribution": "uniform", "min": 1, "max": 2_000_000},
            nullable=False,
            unique=True,
        )

    # FK declared inline as a nested dict
    fk_ref = col_def.get("foreign_key")
    if fk_ref or raw_type == "foreign_key":
        return Column(name=col_name, type="foreign_key", distribution_params={})

    misata_type = _TYPE_MAP.get(raw_type, "text")

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
        inferred = _infer_text_type(col_name)
        if inferred:
            params["text_type"] = inferred
        # Explicit raw type in the dict schema always wins
        if raw_type in ("email", "phone", "url", "uuid"):
            params["text_type"] = raw_type

    elif misata_type in ("date", "datetime"):
        params["start"] = col_def.get("min_date", col_def.get("start", "2020-01-01"))
        params["end"] = col_def.get("max_date", col_def.get("end", "2024-12-31"))

    elif misata_type == "boolean":
        if col_def.get("probability") is not None:
            params["probability"] = col_def["probability"]

    # ── Full generation-feature passthrough ──────────────────────────────────
    # Everything the engine supports must be reachable from a plain dict, not just
    # hand-built Column objects. Without this, an LLM or non-Python user silently loses
    # their distributions, exact percentages, formulas, and cross-table logic.
    if col_def.get("distribution") is not None:
        params["distribution"] = col_def["distribution"]
    # Distribution shape parameters (lognormal mu/sigma, normal mean/std, pareto alpha,
    # poisson lambda, binomial n/p, ...). These must reach the generator verbatim or
    # the declared distribution silently degrades to its default.
    for dist_key in ("mu", "sigma", "mean", "std", "alpha", "scale", "a", "b",
                     "lam", "lambda", "shape", "loc", "n", "p"):
        if col_def.get(dist_key) is not None:
            params[dist_key] = col_def[dist_key]
    # The poisson generator reads "lambda"; accept the common "lam" alias too.
    if "lam" in params and "lambda" not in params:
        params["lambda"] = params["lam"]
    # Data-quality knobs the generators honor per-column (were being dropped, so a
    # declared null_rate / outlier_rate produced clean data).
    for quality_key in ("null_rate", "outlier_rate"):
        if col_def.get(quality_key) is not None:
            params[quality_key] = col_def[quality_key]
    # Cross-column / cross-table logic
    for passthrough in ("formula", "depends_on", "mapping", "default", "zero_inflate", "rollup",
                        "inherits_curve_from", "references", "after_column", "relative_to",
                        "null_if", "min_gap_days", "sequence_start", "quantize",
                        "pattern", "pattern_weights", "text_type",
                        # 0.8.1 features
                        "profiles",       # stratified distributions per subgroup
                        "missing_if",     # MAR/MNAR informative missingness
                        "null_when",      # conditional null via eval expression
                        "exact_incidence", # exact count control for boolean/categorical
                        "time_series",    # within-entity AR1/trend/random-walk
                        ):
        if col_def.get(passthrough) is not None:
            params[passthrough] = col_def[passthrough]

    nullable = bool(col_def.get("nullable", True))
    unique = bool(col_def.get("unique", False))
    description = col_def.get("description") or None

    return Column(
        name=col_name,
        type=misata_type,
        distribution_params=params,
        nullable=nullable,
        unique=unique,
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
        except Exception:
            return None
    return None


def _unwrap_envelope(schemas: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize the YAML-style envelope format into the flat dict format.

    ``{"name": ..., "seed": ..., "tables": {...}, "relationships": [...]}``
    is what ``misata.yaml`` and several README examples use; callers frequently
    hand the same shape to :func:`from_dict_schema`. Without this unwrap the
    parser used to treat ``tables`` as a table named "tables" and silently
    generate garbage.
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
    for env_key, dunder in (("outcome_curves", "__outcome_curves__"),
                            ("rate_curves", "__rate_curves__"),
                            ("noise", "__noise__"),
                            ("vocabulary", "__vocabulary__"),
                            ("vocabularies", "__vocabulary__")):
        if schemas.get(env_key) is not None:
            flat[dunder] = schemas[env_key]
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


def from_dict_schema(
    schemas: Dict[str, Any],
    row_count: int = 1000,
    seed: Optional[int] = 42,
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

    Schema-level directives (top-level keys, siblings of the tables):

    - ``__outcome_curves__``: list of declared aggregate targets, e.g.
      ``[{"table": "orders", "column": "amount", "time_column": "order_date",
      "time_unit": "month", "value_mode": "absolute", "start_date": "2024-01-01",
      "curve_points": [{"month": 1, "target_value": 50000.0}, ...]}]`` —
      generated rows sum to each period's target exactly.
    - ``__rate_curves__``: list of per-period rate targets for boolean or
      categorical columns, e.g. ``[{"table": "transactions", "column":
      "is_fraud", "time_column": "transaction_date", "rate_points":
      [{"period": "2024-01", "rate": 0.03}, ...]}]``.
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
    schemas = _unwrap_envelope(schemas)

    tables: List[Table] = []
    columns_map: Dict[str, List[Column]] = {}
    relationships: List[Relationship] = []

    # Envelope metadata hoisted by _unwrap_envelope.
    schema_name = schemas.get("__name__") or "Imported schema"
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
            warnings.warn(f"Skipping unparseable relationships[{i}]: {rel_def!r}")

    # Top-level directives (not tables): declared outcome curves and rate
    # curves, the schema-level half of the engine contract. A single malformed
    # directive must NOT abort the whole generation — it is skipped with a
    # warning so the rest of the schema still produces data, mirroring the
    # resilience of the LLM-parser path. (A frontend or hand-written schema can
    # easily get one curve wrong; losing all output over it is the wrong failure.)
    outcome_curves: List[OutcomeCurve] = []
    for i, curve_def in enumerate(schemas.get("__outcome_curves__") or []):
        try:
            outcome_curves.append(OutcomeCurve(**curve_def))
        except Exception as e:
            warnings.warn(f"Skipping invalid __outcome_curves__[{i}]: {e}")
    rate_curves: List[RateCurve] = []
    for i, rate_def in enumerate(schemas.get("__rate_curves__") or []):
        try:
            rate_curves.append(RateCurve(**rate_def))
        except Exception as e:
            warnings.warn(f"Skipping invalid __rate_curves__[{i}]: {e}")

    # __noise__ injects declared data-quality defects (nulls, outliers, typos,
    # duplicates) at a known rate — so a data-cleaning / DQ pipeline can be
    # tested against ground truth, the same contract as the rate curves above.
    noise_config: Optional[NoiseConfig] = None
    raw_noise = schemas.get("__noise__")
    if raw_noise:
        try:
            noise_config = NoiseConfig(**raw_noise)
        except Exception as e:
            # Deliberately fail-loud (unlike the shaping curves): __noise__ is the
            # ground truth a data-quality pipeline is tested against. Silently
            # dropping a malformed spec would run the test on clean data without
            # the user knowing — a worse failure than aborting.
            raise ValueError(f"__noise__ is invalid: {e}") from e

    # __domain__ stores the domain name on the SchemaConfig for post-generation validation
    domain: Optional[str] = schemas.get("__domain__") or None

    # __vocabulary__ is the schema-embedded mini-capsule: column name → real
    # values, sampled by the engine for open-ended text columns.
    vocabularies: Optional[Dict[str, List[str]]] = None
    raw_vocab = schemas.get("__vocabulary__")
    if isinstance(raw_vocab, dict):
        cleaned = {
            str(k).strip().lower(): [str(x).strip() for x in v if str(x).strip()]
            for k, v in raw_vocab.items()
            if isinstance(v, (list, tuple))
        }
        vocabularies = {k: v for k, v in cleaned.items() if len(v) >= 2} or None
    # Per-table __vocabulary__ dunders (canvas round-trip) collect here and
    # merge below; explicit top-level entries win on key collisions.
    _table_vocabularies: Dict[str, List[str]] = {}

    for table_name, table_def in schemas.items():
        if table_name.startswith("__"):
            continue
        if not isinstance(table_def, dict):
            warnings.warn(f"Skipping non-dict entry for table '{table_name}'.")
            continue

        # Support both __table_description__ and __description__ as table-level metadata
        table_desc = (
            table_def.get("__table_description__")
            or table_def.get("__description__")
            or None
        )

        # Per-table row count: lets a 6-table schema say "4 regions, 50 sites, 5000 logs"
        # instead of forcing one global count on every table. Accept several spellings;
        # fall back to the global row_count when none is given.
        table_rows = row_count
        for rows_key in ("__rows__", "__row_count__", "rows", "row_count"):
            val = table_def.get(rows_key)
            # Honour an explicit 0 (empty table) — only a missing/negative/non-int
            # value falls back to the global default. `bool` is excluded since it
            # subclasses int.
            if isinstance(val, int) and not isinstance(val, bool) and val >= 0:
                table_rows = val
                break

        # Nested per-table format: {"rows": N, "columns": {...}} — read the
        # column defs from the sub-dict while table-level keys stay on the
        # outer def. (This is the misata.yaml shape handed to dict callers.)
        _raw_columns = table_def.get("columns")
        col_source = (
            _raw_columns
            if isinstance(_raw_columns, dict)
            and _raw_columns
            and all(isinstance(v, dict) for v in _raw_columns.values())
            else table_def
        )

        pk_col = _detect_pk(col_source)
        table_cols: List[Column] = []

        # Per-table constraints — e.g. inequality (end_date > start_date), col_range, etc.
        # Format: __constraints__: [{type: "inequality", column_a: "x", operator: ">", column_b: "y"}]
        # ``name`` is required by the Constraint model but is purely descriptive; auto-fill
        # it from the constraint's shape so dict/LLM/MCP callers don't have to invent one.
        table_constraints: List[Constraint] = []
        for i, c_def in enumerate(table_def.get("__constraints__") or []):
            if isinstance(c_def, dict) and not c_def.get("name"):
                c_def = {**c_def, "name": _auto_constraint_name(c_def, i)}
            try:
                table_constraints.append(Constraint(**c_def))
            except Exception as e:
                warnings.warn(f"Table '{table_name}' __constraints__[{i}] is invalid and was skipped: {e}")

        # Per-table Pearson correlations between numeric columns (applied post-generation).
        # Supports two formats:
        #
        # Pairwise list (simple):
        #   __correlations__: [{col_a: "bmi", col_b: "systolic_bp", r: 0.41}]
        #
        # Full matrix (complete):
        #   __correlations__:
        #     method: cholesky
        #     matrix:
        #       columns: [hba1c, glucose, bmi, systolic_bp]
        #       values:
        #         hba1c:   [1.00, 0.68, 0.31, 0.22]
        #         glucose: [0.68, 1.00, 0.35, 0.28]
        #         ...
        _raw_corr = table_def.get("__correlations__") or []
        if isinstance(_raw_corr, dict) and "matrix" in _raw_corr:
            # Expand full matrix into pairwise pairs
            mat_spec = _raw_corr["matrix"]
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
        else:
            table_correlations = list(_raw_corr)

        for col_name, col_def in col_source.items():
            if col_name.startswith("__") or not isinstance(col_def, dict):
                continue

            # Collect FK relationships — nested dict form or
            # ``references: "parent_table.parent_key"`` string form.
            fk_ref = col_def.get("foreign_key")
            if fk_ref and isinstance(fk_ref, dict):
                relationships.append(Relationship(
                    parent_table=fk_ref["table"],
                    child_table=table_name,
                    parent_key=fk_ref.get("column", "id"),
                    child_key=col_name,
                ))
            elif (
                isinstance(col_def.get("references"), str)
                and "." in col_def["references"]
                and (fk_ref or str(col_def.get("type", "")).lower() == "foreign_key")
            ):
                p_table, p_key = col_def["references"].rsplit(".", 1)
                relationships.append(Relationship(
                    parent_table=p_table.strip(),
                    child_table=table_name,
                    parent_key=p_key.strip(),
                    child_key=col_name,
                ))

            col = _col_from_dict(col_name, col_def, primary_key_col=pk_col)
            if col is not None:
                table_cols.append(col)

        state_machine = table_def.get("__state_machine__") or None
        cluster_effect = table_def.get("__cluster_effect__") or None

        # Table-level vocabulary rides the canvas round-trip as a dunder in
        # the table def; merge it up into the schema-level mini-capsule.
        table_vocab = table_def.get("__vocabulary__")
        if isinstance(table_vocab, dict):
            for k, v in table_vocab.items():
                if isinstance(v, (list, tuple)):
                    vals = [str(x).strip() for x in v if str(x).strip()]
                    if len(vals) >= 2:
                        _table_vocabularies[str(k).strip().lower()] = vals

        tables.append(Table(
            name=table_name,
            row_count=table_rows,
            description=table_desc,
            constraints=table_constraints,
            correlations=table_correlations,
            state_machine=state_machine,
            cluster_effect=cluster_effect,
        ))
        columns_map[table_name] = table_cols

    return SchemaConfig(
        name=schema_name,
        tables=tables,
        columns=columns_map,
        relationships=relationships,
        outcome_curves=outcome_curves,
        rate_curves=rate_curves,
        noise_config=noise_config,
        seed=seed,
        domain=domain,
        vocabularies=({**_table_vocabularies, **(vocabularies or {})} or None),
    )


# ---------------------------------------------------------------------------
# Post-generation referential integrity verification
# ---------------------------------------------------------------------------

class IntegrityReport:
    """Result of a referential integrity check across FK relationships."""

    def __init__(self, violations: List[Dict[str, Any]]):
        self.violations = violations
        self.ok = len(violations) == 0

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
    violations: List[Dict[str, Any]] = []

    for rel in schema.relationships:
        pname, cname = rel.parent_table, rel.child_table
        pkey, ckey = rel.parent_key, rel.child_key
        label = f"{cname}.{ckey} → {pname}.{pkey}"

        if pname not in tables:
            violations.append({"relationship": label,
                                "issue": f"Parent table '{pname}' not found.",
                                "orphan_count": -1})
            continue
        if cname not in tables:
            violations.append({"relationship": label,
                                "issue": f"Child table '{cname}' not found.",
                                "orphan_count": -1})
            continue

        parent_df = tables[pname]
        child_df = tables[cname]

        if pkey not in parent_df.columns:
            violations.append({"relationship": label,
                                "issue": f"Column '{pkey}' not in '{pname}'.",
                                "orphan_count": -1})
            continue
        if ckey not in child_df.columns:
            violations.append({"relationship": label,
                                "issue": f"Column '{ckey}' not in '{cname}'.",
                                "orphan_count": -1})
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

        if len(orphans) > 0:
            violations.append({
                "relationship": label,
                "issue": "Orphaned FK values detected.",
                "orphan_count": int(len(orphans)),
                "sample_orphans": orphans.unique()[:5].tolist(),
            })

    return IntegrityReport(violations=violations)
