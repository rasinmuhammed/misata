"""
Schema introspection utilities for Misata.

Supports database URLs and SQLAlchemy metadata.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from misata.schema import Column, Constraint, Relationship, SchemaConfig, Table


def schema_from_db(
    db_url: str,
    *,
    default_rows: int = 1000,
    include_tables: Optional[List[str]] = None,
) -> SchemaConfig:
    from misata.db import _connect  # type: ignore

    dialect, conn = _connect(db_url)
    try:
        if dialect == "sqlite":
            tables = _sqlite_list_tables(conn, include_tables)
            columns_map, relationships, constraints = _sqlite_introspect(conn, tables)
            external = {}
        else:
            tables = _postgres_list_tables(conn, include_tables)
            columns_map, relationships, external, constraints = _postgres_introspect(
                conn, tables)
    finally:
        conn.close()

    table_defs = [Table(name=t, row_count=default_rows,
                        constraints=constraints.get(t, []))
                  for t in tables]

    # A foreign key can point out of `public` at a table somebody else owns.
    # Supabase is the common case: every project's `public.profiles.id`
    # references `auth.users.id`, and auth rows are created by the auth service,
    # not by us. Carry such a parent in the config so the relationship resolves,
    # with row_count 0 so nothing is generated for it. The seeder reads its real
    # keys and draws children from those.
    external_counts = {}
    for name, (schema_name, key_col, existing) in external.items():
        if name in tables:
            continue
        external_counts[name] = existing
        table_defs.append(
            Table(
                name=name,
                row_count=0,
                external_schema=schema_name,
                description=(f"Read-only: owned by the {schema_name} schema, "
                             f"{existing:,} existing row(s)."),
            )
        )
        columns_map.setdefault(
            name,
            [Column(name=key_col, type="text", distribution_params={}, unique=True)],
        )

    config = SchemaConfig(
        name="IntrospectedSchema",
        tables=table_defs,
        columns=columns_map,
        relationships=relationships,
    )

    # Auto-assign proportional row counts based on FK graph
    assign_proportional_row_counts(config, default_rows, external_counts)

    # Auto-enrich with realistic column constraints
    enrich_introspected_schema(config)
    return config


def assign_proportional_row_counts(
    config: SchemaConfig,
    base_rows: int,
    external_counts: Optional[Dict[str, int]] = None,
) -> None:
    """
    Assign realistic, proportional row counts to tables based on the FK graph
    and table name semantics.

    Instead of flat N rows per table, this analyzes the relational structure
    to determine each table's tier:

    Tier 0 — Reference tables (categories, types, statuses): base × 0.15
    Tier 1 — Entity tables (users, customers, products):     base × 1.0
    Tier 2 — Transaction tables (orders, bookings):           base × 2.5
    Tier 3 — Line-item tables (order_items, line_items):      base × 5.0
    Tier 4 — Activity tables (reviews, logs, events):         base × 1.5

    The result: categories=15, users=100, products=100, orders=250,
    order_items=500, reviews=150 (for base_rows=100).
    """
    # Build the FK graph: parent → [children]
    parent_to_children: dict = {}
    child_to_parents: dict = {}
    for rel in config.relationships:
        parent_to_children.setdefault(rel.parent_table, []).append(rel.child_table)
        child_to_parents.setdefault(rel.child_table, []).append(rel.parent_table)

    table_names = {t.name for t in config.tables}

    # ─── Classify each table into a tier ───
    # Reference tables: have children but no parents, and match reference-like names
    REFERENCE_PATTERNS = {
        "categor", "type", "status", "tag", "role", "permission",
        "department", "region", "currency", "language", "country",
        "brand", "color", "size", "material", "genre", "topic",
    }

    # Line-item patterns: the "many" side of many-to-many or order→items
    LINE_ITEM_PATTERNS = {
        "item", "line", "detail", "entry", "cart_item", "basket_item",
        "order_item", "order_line", "invoice_item", "invoice_line",
    }

    # Activity/feedback patterns: things users do, fewer than transactions
    ACTIVITY_PATTERNS = {
        "review", "comment", "feedback", "rating", "log", "event",
        "notification", "message", "audit", "history", "note",
    }

    # Transaction patterns: the core business events
    TRANSACTION_PATTERNS = {
        "order", "booking", "payment", "invoice", "transaction",
        "purchase", "sale", "subscription", "shipment", "return",
    }

    tier_map: dict = {}

    for table in config.tables:
        name = table.name.lower()
        parents = child_to_parents.get(table.name, [])
        children = parent_to_children.get(table.name, [])

        # Check name patterns
        is_reference = any(pat in name for pat in REFERENCE_PATTERNS)
        is_line_item = any(pat in name for pat in LINE_ITEM_PATTERNS)
        is_activity = any(pat in name for pat in ACTIVITY_PATTERNS)
        is_transaction = any(pat in name for pat in TRANSACTION_PATTERNS)

        if is_line_item:
            tier_map[table.name] = 3  # Line items: most rows
        elif is_activity:
            tier_map[table.name] = 4  # Activity: moderate
        elif is_reference and not parents:
            tier_map[table.name] = 0  # Reference: fewest rows
        elif is_reference:
            tier_map[table.name] = 0  # Still reference even with parents
        elif is_transaction:
            tier_map[table.name] = 2  # Transactions
        elif not parents and children:
            # Root entity (no parents, has children) — like users, products
            tier_map[table.name] = 1
        elif parents and children:
            # Bridge/Transaction (has both parents and children)
            tier_map[table.name] = 2
        elif parents and not children:
            # Leaf (only parents, no children) — could be line item or activity
            num_parents = len(parents)
            if num_parents >= 2:
                tier_map[table.name] = 3  # Many FKs → line item
            else:
                tier_map[table.name] = 4  # Single FK → activity
        else:
            tier_map[table.name] = 1  # Default: entity

    # ─── Assign row counts based on tier ───
    TIER_MULTIPLIERS = {
        0: 0.15,   # Reference: 15% of base  (100 → 15 categories)
        1: 1.0,    # Entity: 100% of base    (100 → 100 users)
        2: 2.5,    # Transaction: 250%       (100 → 250 orders)
        3: 5.0,    # Line item: 500%         (100 → 500 order_items)
        4: 1.5,    # Activity: 150%          (100 → 150 reviews)
    }

    for table in config.tables:
        if table.external_schema:
            # Somebody else's table. We read it, we never fill it.
            table.row_count = 0
            continue
        tier = tier_map.get(table.name, 1)
        multiplier = TIER_MULTIPLIERS[tier]
        row_count = max(5, int(base_rows * multiplier))  # Minimum 5 rows
        table.row_count = row_count

    # A child whose foreign key is also its own primary key is one-to-one with
    # its parent, so it cannot have more rows than the parent has. Supabase's
    # `profiles.id -> auth.users.id` is exactly this, and asking for 2,500
    # profiles against 25 auth users is not a shortfall to be filled in later,
    # it is arithmetic that cannot hold.
    by_name = {t.name: t for t in config.tables}
    unique_cols = {
        (t, c.name) for t, cols in config.columns.items() for c in cols if c.unique
    }
    for rel in config.relationships:
        child, parent = by_name.get(rel.child_table), by_name.get(rel.parent_table)
        if not child or not parent or child.row_count == 0:
            continue
        if (rel.child_table, rel.child_key) not in unique_cols:
            continue
        # An external parent's ceiling is the rows it already has, not the
        # zero we will generate for it.
        ceiling = (external_counts or {}).get(rel.parent_table, parent.row_count)
        if ceiling:
            child.row_count = min(child.row_count, ceiling)


def enrich_introspected_schema(config: SchemaConfig) -> None:
    """
    Auto-detect column semantics from names and set proper distribution_params.

    This transforms generic introspected columns into well-parameterized ones
    that produce realistic data. Fixes: wrong domains, bad ranges, missing enums,
    unrealistic FK values, etc.
    """
    # Collect all table names for FK range inference
    table_names = {t.name for t in config.tables}

    for table in config.tables:
        table_lower = table.name.lower()
        columns = config.columns.get(table.name, [])

        for col in columns:
            name_lower = col.name.lower()
            params = col.distribution_params

            # Skip FK columns — they're handled by the simulator's FK logic
            if col.type == "foreign_key":
                continue

            # ── TEXT COLUMNS: Infer text_type and domain_hint ──
            if col.type == "text":
                # Email
                if "email" in name_lower:
                    params["text_type"] = "email"
                    continue
                # Phone
                elif "phone" in name_lower or "mobile" in name_lower or "tel" in name_lower:
                    col.type = "categorical"
                    params["choices"] = [
                        "+1 (212) 555-0101", "+1 (310) 555-0142", "+1 (415) 555-0198",
                        "+1 (312) 555-0167", "+1 (713) 555-0134", "+1 (602) 555-0156",
                        "+1 (206) 555-0189", "+1 (305) 555-0112", "+1 (404) 555-0178",
                        "+1 (617) 555-0145", "+1 (512) 555-0123", "+1 (303) 555-0191",
                        "+1 (503) 555-0167", "+1 (919) 555-0134", "+1 (703) 555-0156",
                        "+1 (469) 555-0189", "+1 (704) 555-0112", "+1 (858) 555-0178",
                        "+1 (952) 555-0145", "+1 (480) 555-0198",
                    ]
                    continue
                # Address / street
                elif name_lower in ("street", "address", "address_line", "street_address"):
                    params["text_type"] = "address"
                    continue
                # City
                elif name_lower == "city":
                    col.type = "categorical"
                    params["choices"] = [
                        "New York", "Los Angeles", "Chicago", "Houston", "Phoenix",
                        "Philadelphia", "San Antonio", "San Diego", "Dallas", "Austin",
                        "San Francisco", "Seattle", "Denver", "Boston", "Nashville",
                        "Portland", "Las Vegas", "Atlanta", "Miami", "Minneapolis",
                    ]
                    continue
                # State
                elif name_lower in ("state", "province", "region"):
                    col.type = "categorical"
                    params["choices"] = [
                        "California", "Texas", "Florida", "New York", "Pennsylvania",
                        "Illinois", "Ohio", "Georgia", "North Carolina", "Michigan",
                        "New Jersey", "Virginia", "Washington", "Arizona", "Massachusetts",
                        "Tennessee", "Indiana", "Missouri", "Maryland", "Colorado",
                    ]
                    continue
                # Zip / postal code
                elif name_lower in ("zip_code", "postal_code", "zip", "zipcode"):
                    col.type = "categorical"
                    params["choices"] = [
                        "10001", "10013", "10016", "10019", "10022",
                        "90001", "90012", "90036", "90045", "90210",
                        "60601", "60614", "60657", "77001", "77024",
                        "94102", "94110", "94133", "98101", "98109",
                        "33101", "33139", "30301", "30308", "02101",
                    ]
                    continue
                # Country
                elif name_lower == "country":
                    col.type = "categorical"
                    params["choices"] = [
                        "United States", "United Kingdom", "Canada", "Germany", "France",
                        "Australia", "Japan", "India", "Brazil", "Netherlands",
                        "Spain", "Italy", "Sweden", "Switzerland", "Singapore",
                    ]
                    params["probabilities"] = [
                        0.40, 0.10, 0.08, 0.06, 0.05,
                        0.04, 0.04, 0.04, 0.03, 0.03,
                        0.03, 0.03, 0.02, 0.02, 0.03,
                    ]
                    continue
                # First name
                elif name_lower in ("first_name", "firstname", "given_name"):
                    params["text_type"] = "name"
                    continue
                # Last name
                elif name_lower in ("last_name", "lastname", "surname", "family_name"):
                    params["text_type"] = "name"
                    continue
                # SKU
                elif name_lower == "sku":
                    params["smart_generate"] = True
                    params["domain_hint"] = "sku"
                    continue
                # Product name / category name — use domain-aware smart gen
                elif name_lower == "name":
                    # Use table context for domain detection
                    if "product" in table_lower:
                        params["smart_generate"] = True
                        params["domain_hint"] = "product"
                    elif "categor" in table_lower:
                        col.type = "categorical"
                        params["choices"] = [
                            "Electronics", "Clothing & Apparel", "Home & Garden",
                            "Sports & Outdoors", "Beauty & Personal Care", "Books & Media",
                            "Toys & Games", "Food & Grocery", "Health & Wellness",
                            "Automotive", "Office Supplies", "Jewelry & Watches",
                            "Baby & Kids", "Pet Supplies", "Arts & Crafts",
                            "Shoes & Footwear", "Kitchen & Dining", "Tools & Hardware",
                            "Furniture", "Travel & Luggage",
                        ]
                    elif "user" in table_lower or "customer" in table_lower or "person" in table_lower:
                        params["text_type"] = "name"
                    else:
                        params["smart_generate"] = True
                    continue
                # Description / body — long text
                elif name_lower in ("description", "body", "content", "details", "bio", "summary"):
                    if "review" in table_lower:
                        params["smart_generate"] = True
                        params["domain_hint"] = "review_text"
                    elif "product" in table_lower or "categor" in table_lower:
                        col.type = "categorical"
                        params["choices"] = [
                            "Premium quality with durable construction and modern design.",
                            "Versatile and reliable, perfect for everyday use.",
                            "High-performance solution designed for demanding users.",
                            "Eco-friendly materials with excellent craftsmanship.",
                            "Compact and lightweight with advanced features.",
                            "Best-in-class warranty and customer support included.",
                            "Innovative design combining style and functionality.",
                            "Professional-grade quality at an affordable price point.",
                            "Top-rated by customers for reliability and value.",
                            "Engineered for maximum efficiency and long-lasting use.",
                            "Sleek modern aesthetic with intuitive controls.",
                            "Essential everyday item with premium materials.",
                        ]
                    else:
                        params["smart_generate"] = True
                        params["domain_hint"] = "description"
                    continue
                # Title
                elif name_lower == "title":
                    if "review" in table_lower:
                        params["smart_generate"] = True
                        params["domain_hint"] = "review_title"
                    else:
                        params["smart_generate"] = True
                        params["domain_hint"] = "title"
                    continue
                # Slug
                elif name_lower == "slug":
                    params["text_type"] = "word"
                    continue
                # Status (convert to categorical with proper enum)
                elif name_lower == "status":
                    col.type = "categorical"
                    if "order" in table_lower:
                        params["choices"] = ["pending", "processing", "shipped", "delivered", "cancelled"]
                        params["probabilities"] = [0.15, 0.10, 0.15, 0.45, 0.15]
                    elif "user" in table_lower or "account" in table_lower:
                        params["choices"] = ["active", "inactive", "suspended"]
                        params["probabilities"] = [0.80, 0.15, 0.05]
                    else:
                        params["choices"] = ["active", "inactive", "pending"]
                        params["probabilities"] = [0.60, 0.25, 0.15]
                    continue
                # Tier / plan
                elif name_lower in ("tier", "plan", "subscription_plan"):
                    col.type = "categorical"
                    params["choices"] = ["free", "premium", "enterprise"]
                    params["probabilities"] = [0.60, 0.30, 0.10]
                    continue
                # Generic — let smart_values handle it, but pass table context
                else:
                    params["smart_generate"] = True
                    continue

            # ── INT COLUMNS: Set realistic ranges ──
            # Note: rng.integers(low, high) is EXCLUSIVE on high, so use max+1
            elif col.type == "int":
                if name_lower == "rating":
                    col.type = "categorical"
                    params["choices"] = [1, 2, 3, 4, 5]
                    params["probabilities"] = [0.05, 0.08, 0.15, 0.35, 0.37]
                    continue
                elif name_lower == "quantity" or name_lower == "qty":
                    params["distribution"] = "uniform"
                    params["min"] = 1
                    params["max"] = 11  # exclusive → gives 1-10
                    continue
                elif name_lower in ("helpful_votes", "upvotes", "likes"):
                    params["distribution"] = "uniform"
                    params["min"] = 0
                    params["max"] = 51  # exclusive → gives 0-50
                    continue
                elif name_lower == "stock_qty" or name_lower == "inventory":
                    params["distribution"] = "uniform"
                    params["min"] = 0
                    params["max"] = 501  # exclusive → gives 0-500
                    continue

            # ── FLOAT COLUMNS: Set realistic ranges ──
            elif col.type == "float":
                if name_lower in ("price", "unit_price"):
                    params["distribution"] = "uniform"
                    params["min"] = 4.99
                    params["max"] = 999.99
                    params["decimals"] = 2
                    continue
                elif name_lower == "cost":
                    params["distribution"] = "uniform"
                    params["min"] = 2.00
                    params["max"] = 500.00
                    params["decimals"] = 2
                    continue
                elif name_lower in ("subtotal", "total", "line_total"):
                    params["distribution"] = "uniform"
                    params["min"] = 9.99
                    params["max"] = 2500.00
                    params["decimals"] = 2
                    continue
                elif name_lower in ("tax", "shipping_cost", "fee"):
                    params["distribution"] = "uniform"
                    params["min"] = 0.00
                    params["max"] = 50.00
                    params["decimals"] = 2
                    continue
                elif name_lower == "discount":
                    params["distribution"] = "uniform"
                    params["min"] = 0.00
                    params["max"] = 25.00
                    params["decimals"] = 2
                    continue
                elif "weight" in name_lower:
                    params["distribution"] = "uniform"
                    params["min"] = 0.1
                    params["max"] = 30.0
                    params["decimals"] = 2
                    continue

            # ── BOOLEAN COLUMNS: Set realistic probabilities ──
            elif col.type == "boolean":
                if name_lower in ("is_active", "active", "enabled"):
                    params["probability"] = 0.85
                elif name_lower in ("is_default",):
                    params["probability"] = 0.20
                elif name_lower in ("verified_purchase", "verified"):
                    params["probability"] = 0.75


def schema_from_sqlalchemy(
    sqlalchemy_obj,
    *,
    default_rows: int = 1000,
) -> SchemaConfig:
    try:
        from sqlalchemy import MetaData  # type: ignore
    except Exception as exc:
        raise ImportError("SQLAlchemy is required. Install misata[orm].") from exc

    metadata = _extract_metadata(sqlalchemy_obj)
    if metadata is None:
        raise ValueError("Could not extract SQLAlchemy MetaData from object.")

    tables = []
    columns_map: Dict[str, List[Column]] = {}
    relationships: List[Relationship] = []

    for table in metadata.sorted_tables:
        tables.append(Table(name=table.name, row_count=default_rows))
        cols: List[Column] = []
        for col in table.columns:
            has_fk = bool(col.foreign_keys)
            col_type = "foreign_key" if has_fk else _map_sqlalchemy_type(col.type)
            params = {}
            cols.append(
                Column(
                    name=col.name,
                    type=col_type,
                    distribution_params=params,
                    nullable=col.nullable,
                    unique=bool(col.unique),
                )
            )

            for fk in col.foreign_keys:
                parent_table = fk.column.table.name
                parent_key = fk.column.name
                relationships.append(
                    Relationship(
                        parent_table=parent_table,
                        child_table=table.name,
                        parent_key=parent_key,
                        child_key=col.name,
                    )
                )
        columns_map[table.name] = cols

    return SchemaConfig(
        name="SQLAlchemySchema",
        tables=tables,
        columns=columns_map,
        relationships=relationships,
    )


def load_sqlalchemy_target(import_path: str):
    import importlib

    if ":" not in import_path:
        raise ValueError("SQLAlchemy target must be in form module:object")

    module_path, attr = import_path.split(":", 1)
    module = importlib.import_module(module_path)
    target = getattr(module, attr, None)
    if target is None:
        raise ValueError(f"Could not import '{attr}' from '{module_path}'")
    return target


def _extract_metadata(obj):
    try:
        from sqlalchemy import MetaData  # type: ignore
        if isinstance(obj, MetaData):
            return obj
    except ImportError:
        pass
    if hasattr(obj, "metadata"):
        return obj.metadata
    return None


def _sqlite_list_tables(conn, include_tables: Optional[List[str]]) -> List[str]:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    tables = [row[0] for row in cur.fetchall()]
    if include_tables:
        tables = [t for t in tables if t in include_tables]
    return tables


def _sqlite_introspect(conn, tables: List[str]):
    columns_map: Dict[str, List[Column]] = {}
    relationships: List[Relationship] = []
    constraints_map: Dict[str, List[Constraint]] = {}

    for table in tables:
        # `PRAGMA table_info` reports the primary key and nothing about UNIQUE.
        # A column declared `name TEXT UNIQUE` therefore looked ordinary, the
        # generator drew it from a finite pool, and the insert was rejected.
        # Unique indexes carry that information; single-column ones only,
        # because a unique index over (a, b) constrains the pair.
        unique_cols: set = set()
        composite: list = []
        for idx in conn.execute(f'PRAGMA index_list("{table}")').fetchall():
            idx_name, is_unique = idx[1], idx[2]
            if not is_unique:
                continue
            members = conn.execute(f'PRAGMA index_info("{idx_name}")').fetchall()
            if len(members) == 1:
                unique_cols.add(members[0][2])
            elif len(members) > 1:
                # UNIQUE (a, b) constrains the pair, not either column. Marking
                # both individually unique would be a stricter schema than the
                # database declares; the engine already has a constraint type
                # for this, it had simply never been emitted from introspection.
                composite.append([m[2] for m in sorted(members)])

        cur = conn.execute(f'PRAGMA table_info("{table}")')
        cols: List[Column] = []
        for row in cur.fetchall():
            name = row[1]
            sql_type = row[2] or ""
            nullable = row[3] == 0
            is_pk = row[5] == 1 or name in unique_cols
            col_type = _map_sql_type(sql_type)
            cols.append(
                Column(
                    name=name,
                    type=col_type,
                    distribution_params={},
                    nullable=nullable,
                    unique=bool(is_pk),
                )
            )
        columns_map[table] = cols
        for combo in composite:
            constraints_map.setdefault(table, []).append(Constraint(
                name=f"{table}_unique_{'_'.join(combo)}",
                type="unique_combination", group_by=list(combo), action="drop"))

        fk_cur = conn.execute(f'PRAGMA foreign_key_list("{table}")')
        for fk in fk_cur.fetchall():
            _mark_fk_column(columns_map[table], fk[3])
            relationships.append(
                Relationship(
                    parent_table=fk[2],
                    child_table=table,
                    parent_key=fk[4],
                    child_key=fk[3],
                )
            )

    return columns_map, relationships, constraints_map


def _postgres_list_tables(conn, include_tables: Optional[List[str]]) -> List[str]:
    sql = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        tables = [row[0] for row in cur.fetchall()]
    if include_tables:
        tables = [t for t in tables if t in include_tables]
    return tables


def _postgres_introspect(conn, tables: List[str]):
    columns_map: Dict[str, List[Column]] = {}
    relationships: List[Relationship] = []
    constraints_map: Dict[str, List[Constraint]] = {}
    # parent table name -> (schema, referenced column) for FKs that leave `public`
    external: Dict[str, Tuple[str, str]] = {}

    col_sql = """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
    """
    pk_sql = """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_schema = 'public'
          AND tc.table_name = %s
          AND tc.constraint_type = 'PRIMARY KEY'
    """
    # A UNIQUE constraint is not a PRIMARY KEY, and only primary keys were read.
    # So `tags.name varchar UNIQUE` came back as an ordinary column, the
    # generator drew it from a finite pool, and Postgres rejected the insert on
    # `tags_name_key`. Every Rails, Laravel and Django schema is full of these
    # (email, slug, name), which made seeding fail on most real applications.
    #
    # Single-column constraints only: a UNIQUE over (a, b) constrains the pair,
    # and marking a and b individually unique would be a stricter schema than
    # the database declares.
    unique_sql = """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_schema = 'public'
          AND tc.table_name = %s
          AND tc.constraint_type = 'UNIQUE'
          AND (SELECT COUNT(*) FROM information_schema.key_column_usage k2
               WHERE k2.constraint_name = tc.constraint_name) = 1
    """
    # The multi-column ones become a `unique_combination` constraint, which the
    # engine has always supported and introspection had never emitted.
    composite_sql = """
        SELECT tc.constraint_name, kcu.column_name, kcu.ordinal_position
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_schema = 'public'
          AND tc.table_name = %s
          AND tc.constraint_type = 'UNIQUE'
          AND (SELECT COUNT(*) FROM information_schema.key_column_usage k2
               WHERE k2.constraint_name = tc.constraint_name) > 1
        ORDER BY tc.constraint_name, kcu.ordinal_position
    """
    fk_sql = """
        SELECT
            tc.table_name AS child_table,
            kcu.column_name AS child_column,
            ccu.table_name AS parent_table,
            ccu.column_name AS parent_column,
            ccu.table_schema AS parent_schema
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
          AND tc.table_name = %s
    """

    with conn.cursor() as cur:
        for table in tables:
            cur.execute(pk_sql, (table,))
            pk_cols = {row[0] for row in cur.fetchall()}

            cur.execute(unique_sql, (table,))
            pk_cols |= {row[0] for row in cur.fetchall()}

            cur.execute(composite_sql, (table,))
            combos: Dict[str, List[str]] = {}
            for cname, col, _pos in cur.fetchall():
                combos.setdefault(cname, []).append(col)
            for cname, cols_in_combo in combos.items():
                constraints_map.setdefault(table, []).append(Constraint(
                    name=cname, type="unique_combination",
                    group_by=cols_in_combo, action="drop"))

            cur.execute(col_sql, (table,))
            cols: List[Column] = []
            for name, data_type, is_nullable in cur.fetchall():
                col_type = _map_sql_type(data_type)
                cols.append(
                    Column(
                        name=name,
                        type=col_type,
                        distribution_params={},
                        nullable=is_nullable == "YES",
                        unique=name in pk_cols,
                    )
                )
            columns_map[table] = cols

            cur.execute(fk_sql, (table,))
            for row in cur.fetchall():
                child_table, child_col, parent_table, parent_col, parent_schema = row
                _mark_fk_column(columns_map[child_table], child_col)
                if parent_schema != "public":
                    # Owned by another schema (Supabase keeps accounts in
                    # `auth.users`). Record it so the caller can read its real
                    # rows; we must never generate or insert into it. The count
                    # is taken now, while the connection is open: it is the
                    # ceiling on any child keyed one-to-one off this table.
                    if parent_table not in external:
                        with conn.cursor() as ccur:
                            ccur.execute(
                                f'SELECT COUNT(*) FROM "{parent_schema}"."{parent_table}"')
                            n = int(ccur.fetchone()[0])
                        external[parent_table] = (parent_schema, parent_col, n)
                relationships.append(
                    Relationship(
                        parent_table=parent_table,
                        child_table=child_table,
                        parent_key=parent_col,
                        child_key=child_col,
                    )
                )

    return columns_map, relationships, external, constraints_map


def _map_sql_type(sql_type: str) -> str:
    t = sql_type.lower()
    if "int" in t:
        return "int"
    if any(x in t for x in ["numeric", "decimal", "real", "double", "float"]):
        return "float"
    if "bool" in t:
        return "boolean"
    if "timestamp" in t or "datetime" in t:
        return "datetime"
    if t == "date":
        return "date"
    if t == "time":
        return "time"
    return "text"


def _map_sqlalchemy_type(sql_type) -> str:
    t = str(sql_type).lower()
    return _map_sql_type(t)


def _mark_fk_column(columns: List[Column], name: str) -> None:
    for col in columns:
        if col.name == name:
            col.type = "foreign_key"
            break
