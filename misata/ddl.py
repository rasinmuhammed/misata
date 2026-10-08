"""
SQL DDL → SchemaConfig parser.

Converts CREATE TABLE statements into a Misata SchemaConfig that can be passed
directly to ``misata.generate_from_schema()``.

Supported SQL dialects: PostgreSQL, MySQL, SQLite, generic ANSI SQL.
"""

import re
import warnings
from typing import Dict, List, Optional, Tuple

from misata.schema import Column, Constraint, Relationship, SchemaConfig, Table


def _parent_key_for(parent: str, columns_map: Dict[str, List[Column]], fallback: str) -> str:
    """
    Pick the column an inferred foreign key should point at.

    The `_id` rule guesses a parent key called `id`, which is right for Rails
    and wrong for most hand-written SQL, where `categories` is keyed by
    `category_id`. Look at what the parent table actually has before pointing
    at a column that is not there.
    """
    names = [c.name for c in columns_map.get(parent, [])]
    if not names:
        return fallback
    lookup = {n.lower(): n for n in names}
    for candidate in (fallback, "id", f"{parent}_id"):
        if candidate and candidate.lower() in lookup:
            return lookup[candidate.lower()]
    for name in names:
        if name.lower().endswith("_id"):
            return name
    return names[0]


# SQL type → Misata type
_TYPE_MAP: List[Tuple[str, str]] = [
    (r"bool(?:ean)?",                                   "boolean"),
    (r"(?:big|small|tiny)?int(?:eger)?(?:\s*\(\d+\))?|serial|bigserial|smallserial", "int"),
    (r"(?:double\s+precision|float|real|decimal|numeric|money)(?:\s*\(\d+(?:,\s*\d+)?\))?", "float"),
    (r"(?:timestamp(?:tz)?|datetime)(?:\s+with(?:out)?\s+time\s+zone)?(?:\s*\(\d+\))?", "date"),
    (r"date",                                            "date"),
    (r"(?:var)?char(?:acter)?(?:\s+varying)?(?:\s*\(\d+\))?|text|string|clob|varchar2", "text"),
    (r"uuid",                                            "text"),
    (r"json(?:b)?",                                      "text"),
    (r"time(?:\s+with(?:out)?\s+time\s+zone)?(?:\s*\(\d+\))?", "text"),
]

_COMPILED: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"^" + p + r"$", re.IGNORECASE), t)
    for p, t in _TYPE_MAP
]


# Fixed-width code columns: CHAR(2) named country is an ISO 3166 code, not a
# country name that overflows it.
_ISO_COUNTRIES = ["US", "GB", "DE", "FR", "IN", "CA", "AU", "BR", "ES", "IT", "NL", "JP",
                  "MX", "SE", "PL", "IE", "SG", "AE", "ZA", "NG", "KR", "CH", "BE", "PT"]
_ISO_CURRENCIES = ["USD", "EUR", "GBP", "INR", "CAD", "AUD", "BRL", "JPY", "MXN", "SEK",
                   "PLN", "CHF", "SGD", "AED", "ZAR", "NGN", "KRW"]
_ISO_LANGUAGES = ["en", "es", "de", "fr", "pt", "it", "nl", "ja", "hi", "ar", "ko", "sv", "pl"]
_US_STATES = ["CA", "TX", "FL", "NY", "PA", "IL", "OH", "GA", "NC", "MI", "NJ", "VA",
              "WA", "AZ", "MA", "TN", "IN", "MO", "MD", "WI", "CO", "MN", "OR", "NV"]

_LEN_RE = re.compile(
    r"(?:var)?char(?:acter)?(?:\s+varying)?\s*\(\s*(\d+)\s*\)|varchar2\s*\(\s*(\d+)", re.I)
_FIXED_CHAR_RE = re.compile(r"^(?:char|character|nchar)\s*\(", re.I)


def _length_of(sql_type: str) -> Optional[int]:
    m = _LEN_RE.search(sql_type)
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def _code_choices(col_name: str, length: int) -> Optional[List[str]]:
    n = col_name.lower()
    if length == 2 and "country" in n:
        return _ISO_COUNTRIES
    if length == 3 and "currenc" in n:
        return _ISO_CURRENCIES
    if length == 2 and ("lang" in n or "locale" in n):
        return _ISO_LANGUAGES
    if length == 2 and "state" in n:
        return _US_STATES
    return None


def _balanced(text: str, start: int) -> Optional[str]:
    """The contents of the parenthesis opening at ``text[start]``."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
    return None


def _check_bodies(line: str) -> List[str]:
    out = []
    for m in re.finditer(r"\bCHECK\s*\(", line, re.I):
        body = _balanced(line, m.end() - 1)
        if body:
            out.append(body)
    return out


_NUM = r"(-?\d+(?:\.\d+)?)"


def _parse_check(body: str) -> Dict[str, Dict]:
    """Constraints a CHECK expresses that generation can honour, per column.

    Handles the shapes that cover most real schemas: ``col IN ('a', 'b')``,
    ``col BETWEEN x AND y``, comparisons joined by AND (``col >= 0 AND col <=
    100``) and ``length(col) <= n``. Anything else (OR, expressions over two
    columns, function calls) is left for the database to enforce: the import
    warns rather than guessing.
    """
    found: Dict[str, Dict] = {}

    def put(col: str, key: str, value) -> None:
        found.setdefault(col.strip('"').strip("`"), {})[key] = value

    if re.search(r"\bOR\b", body, re.I):
        return found
    for m in re.finditer(r"\"?(\w+)\"?\s+IN\s*\(([^)]*)\)", body, re.I):
        items = [v.strip().strip("'\"") for v in m.group(2).split(",") if v.strip()]
        if items:
            put(m.group(1), "choices", items)
    for m in re.finditer(r"\"?(\w+)\"?\s+BETWEEN\s+" + _NUM + r"\s+AND\s+" + _NUM, body, re.I):
        put(m.group(1), "min", float(m.group(2)))
        put(m.group(1), "max", float(m.group(3)))
    stripped = re.sub(r"\bBETWEEN\s+\S+\s+AND\s+\S+", " ", body, flags=re.I)
    for part in re.split(r"\bAND\b", stripped, flags=re.I):
        m = re.match(r"\s*(?:char_)?length\s*\(\s*\"?(\w+)\"?\s*\)\s*(<=|<)\s*(\d+)\s*$",
                     part, re.I)
        if m:
            n = int(m.group(3)) - (1 if m.group(2) == "<" else 0)
            put(m.group(1), "max_length", n)
            continue
        m = re.match(r"\s*\"?(\w+)\"?\s*(>=|>|<=|<)\s*" + _NUM + r"\s*$", part)
        if m:
            col, op, v = m.group(1), m.group(2), float(m.group(3))
            put(col, "min" if op in (">=", ">") else "max", v)
            put(col, "_strict_" + ("min" if op in (">=", ">") else "max"), op in (">", "<"))
    return found


_PAIR = re.compile(r"^\s*\"?([A-Za-z_]\w*)\"?\s*(>=|>|<=|<)\s*\"?([A-Za-z_]\w*)\"?\s*$")


def _column_pairs(body: str) -> List[Tuple[str, str, str]]:
    """``a > b`` comparisons between two columns, joined by AND."""
    if re.search(r"\bOR\b", body, re.I):
        return []
    out = []
    for part in re.split(r"\bAND\b", body, flags=re.I):
        m = _PAIR.match(part)
        if m and m.group(1).upper() not in ("NULL", "TRUE", "FALSE") and m.group(3).upper() not in ("NULL", "TRUE", "FALSE"):
            out.append((m.group(1), m.group(2), m.group(3)))
    return out


def _pair_duration(late: str, early: str) -> Tuple[int, int]:
    """Days between two dates a CHECK orders, from what the pair is called."""
    n = (late + " " + early).lower()
    if any(k in n for k in ("check_out", "checkout", "departure", "depart", "nights")):
        return 1, 14
    if any(k in n for k in ("ship", "deliver", "dispatch", "arriv")):
        return 1, 10
    if any(k in n for k in ("resolv", "closed", "complet", "respond", "answered")):
        return 0, 30
    if any(k in n for k in ("expir", "valid_to", "until", "renew", "end", "terminat", "cancel")):
        return 30, 730
    if any(k in n for k in ("due", "paid", "settle")):
        return 7, 60
    return 1, 365


def _apply_check(col: Column, rule: Dict) -> Column:
    """Fold parsed CHECK rules into a column's declaration."""
    params = dict(col.distribution_params or {})
    col_type = col.type
    if "choices" in rule:
        choices = rule["choices"]
        if col_type in ("int", "float"):
            try:
                choices = [int(c) if col_type == "int" else float(c) for c in choices]
            except ValueError:
                pass
        col_type = "categorical"
        params = {k: v for k, v in params.items() if k not in ("distribution", "min", "max")}
        params["choices"] = choices
    if "max_length" in rule:
        params["max_length"] = min(rule["max_length"], params.get("max_length", 10**9))
    if col_type in ("int", "float"):
        step = 1 if col_type == "int" else 0.01
        for side in ("min", "max"):
            if side in rule:
                v = rule[side]
                if rule.get("_strict_" + side):
                    v = v + step if side == "min" else v - step
                params[side] = int(v) if col_type == "int" else v
        if ("min" in rule or "max" in rule) and params.get("_distribution_is_default"):
            params = {k: v for k, v in params.items()
                      if k not in ("distribution", "_distribution_is_default")}
            params["distribution"] = "uniform" if "min" in params and "max" in params else "normal"
            if params["distribution"] == "normal":
                params.pop("_distribution_is_default", None)
    return Column(name=col.name, type=col_type, nullable=col.nullable, unique=col.unique,
                  distribution_params=params)


def _map_sql_type(raw: str) -> str:
    raw = raw.strip()
    for pattern, misata_type in _COMPILED:
        if pattern.match(raw):
            return misata_type
    return "text"


def _strip_comments(ddl: str) -> str:
    """Remove SQL line comments (--) and block comments (/* */)."""
    ddl = re.sub(r"/\*.*?\*/", " ", ddl, flags=re.DOTALL)
    ddl = re.sub(r"--[^\n]*", " ", ddl)
    return ddl


def _split_column_defs(body: str) -> List[str]:
    """Split the body of a CREATE TABLE into individual definitions, respecting parentheses."""
    parts: List[str] = []
    depth = 0
    current: List[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return [p for p in parts if p]


def from_ddl(
    ddl: str,
    *,
    infer_fks: bool = True,
    default_rows: int = 1000,
) -> SchemaConfig:
    """Parse SQL DDL CREATE TABLE statements into a :class:`SchemaConfig`.

    Supports PostgreSQL, MySQL, SQLite, and generic ANSI SQL. Inline
    ``REFERENCES`` clauses and standalone ``FOREIGN KEY`` constraints both
    produce :class:`Relationship` entries.

    Args:
        ddl:          One or more ``CREATE TABLE`` statements as a string.
        infer_fks:    If True (default), columns named ``<table>_id`` that
                      don't have an explicit ``REFERENCES`` clause are treated
                      as foreign keys to the table named by the prefix.
                      Set to False to only use explicit constraints.
        default_rows: Row count assigned to each generated table (default 1000).

    Returns:
        :class:`SchemaConfig` ready for :func:`misata.generate_from_schema`.

    Example::

        schema = misata.from_ddl(\"\"\"
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                created_at TIMESTAMP
            );
            CREATE TABLE orders (
                id SERIAL PRIMARY KEY,
                user_id INT REFERENCES users(id),
                amount DECIMAL(10, 2),
                placed_at TIMESTAMP
            );
        \"\"\")
        tables = misata.generate_from_schema(schema)
        print(tables["orders"].head())
    """
    ddl = _strip_comments(ddl)

    # Match CREATE TABLE headers and then walk character-by-character to find the
    # matching closing paren, which handles nested parens like DECIMAL(10,2) and
    # REFERENCES users(id) without the non-greedy .*? truncation bug.
    header_pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(?:\"?[\w]+\"?\.)?"       # optional schema prefix
        r"\"?([\w]+)\"?"            # table name (group 1)
        r"\s*\(",
        re.IGNORECASE,
    )

    def _extract_tables(ddl_text: str) -> List[Tuple[str, str]]:
        results = []
        for hdr in header_pattern.finditer(ddl_text):
            tname = hdr.group(1)
            depth = 1
            i = hdr.end()
            while i < len(ddl_text) and depth > 0:
                ch = ddl_text[i]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                i += 1
            results.append((tname, ddl_text[hdr.end(): i - 1]))
        return results

    def _singular(name: str) -> str:
        """
        Enough English to recognise a table's own key.

        Tables are usually plural and their key is usually singular, so
        `customers` has `customer_id`. Without this the key looks like a
        reference to a `customer` table that was never created. This only needs
        to catch the naming conventions people actually use in DDL, so it stays
        a handful of rules rather than a dependency.
        """
        lowered = name.lower()
        if lowered.endswith("ies") and len(name) > 3:
            return name[:-3] + "y"
        if lowered.endswith(("sses", "shes", "ches", "xes", "zes")):
            return name[:-2]
        if lowered.endswith("s") and not lowered.endswith("ss"):
            return name[:-1]
        return name

    fk_inline = re.compile(
        r"REFERENCES\s+(?:\"?[\w]+\"?\.)?"
        r"\"?([\w]+)\"?"
        r"\s*\(\s*\"?([\w]+)\"?\s*\)",
        re.IGNORECASE,
    )
    fk_constraint = re.compile(
        r"FOREIGN\s+KEY\s*\(\s*\"?([\w]+)\"?\s*\)"
        r"\s+REFERENCES\s+(?:\"?[\w]+\"?\.)?"
        r"\"?([\w]+)\"?"
        r"\s*\(\s*\"?([\w]+)\"?\s*\)",
        re.IGNORECASE,
    )
    skip_pattern = re.compile(
        r"^\s*(?:PRIMARY\s+KEY|UNIQUE|CHECK|CONSTRAINT\s+\w+\s+(?:PRIMARY|UNIQUE|CHECK)|INDEX)\b",
        re.IGNORECASE,
    )
    col_pattern = re.compile(r"^\"?([\w]+)\"?\s+([\w]+(?:\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))?)", re.IGNORECASE)
    pk_table_level = re.compile(
        r"^\s*(?:CONSTRAINT\s+\w+\s+)?PRIMARY\s+KEY\s*\(([^)]*)\)", re.IGNORECASE
    )

    tables: List[Table] = []
    columns_map: Dict[str, List[Column]] = {}
    relationships: List[Relationship] = []
    all_table_names: List[str] = []
    inferred_fks: set = set()  # (child_table, child_col) that came from the _id rule

    for table_name, body in _extract_tables(ddl):
        all_table_names.append(table_name)
        cols: List[Column] = []
        fk_specs: List[Tuple[str, str, str]] = []  # (child_col, parent_table, parent_col)
        explicit_fk_cols: set = set()
        pk_cols: set = set()
        unique_cols: set = set()
        checks: Dict[str, Dict] = {}
        unparsed_checks = 0
        pair_checks: List[Tuple[str, str, str]] = []
        unique_sets: List[List[str]] = []

        for line in _split_column_defs(body):
            # CHECK constraints, inline or table-level: fold what generation
            # can honour into the column, count the rest.
            for chk in _check_bodies(line):
                parsed = _parse_check(chk)
                pairs = _column_pairs(chk)
                pair_checks.extend(pairs)
                if parsed:
                    for cname, rule in parsed.items():
                        checks.setdefault(cname, {}).update(rule)
                elif not pairs:
                    unparsed_checks += 1
            table_unique = re.match(
                r"^\s*(?:CONSTRAINT\s+\"?\w+\"?\s+)?UNIQUE\s*\(([^)]*)\)", line, re.I)
            if table_unique:
                ucols = [c.strip().strip('"') for c in table_unique.group(1).split(",")]
                if len(ucols) == 1:
                    unique_cols.add(ucols[0])
                elif ucols:
                    unique_sets.append(ucols)

            # Standalone FOREIGN KEY constraint
            fk_match = fk_constraint.search(line)
            if fk_match:
                child_col, parent_table, parent_col = fk_match.groups()
                fk_specs.append((child_col, parent_table, parent_col))
                explicit_fk_cols.add(child_col)
                continue

            # Table-level PRIMARY KEY (a, b). Recorded before the constraint is
            # skipped, because a table's own key must never be inferred as a
            # foreign key pointing somewhere else.
            pk_constraint = pk_table_level.search(line)
            if pk_constraint:
                pk_cols.update(
                    c.strip().strip('"') for c in pk_constraint.group(1).split(",")
                )

            # Skip other table-level constraints
            if skip_pattern.match(line):
                continue

            # Column definition
            col_match = col_pattern.match(line)
            if not col_match:
                continue

            col_name = col_match.group(1)
            sql_type = col_match.group(2)
            misata_type = _map_sql_type(sql_type)
            # Ignore keywords inside CHECK bodies and string literals.
            bare = re.sub(r"'[^']*'", "''", line)
            for chk in _check_bodies(bare):
                bare = bare.replace(chk, "")
            upper = bare.upper()
            nullable = "NOT NULL" not in upper and "PRIMARY KEY" not in upper
            if "PRIMARY KEY" in upper:
                pk_cols.add(col_name)
            if re.search(r"\bUNIQUE\b", upper):
                unique_cols.add(col_name)
            length = _length_of(sql_type) if misata_type == "text" else None

            # Inline REFERENCES
            inline = fk_inline.search(line)
            if inline:
                parent_table, parent_col = inline.group(1), inline.group(2)
                fk_specs.append((col_name, parent_table, parent_col))
                explicit_fk_cols.add(col_name)
                misata_type = "foreign_key"
                distribution_params: Dict = {"references": f"{parent_table}.{parent_col}"}
            else:
                distribution_params = {}
                scale = re.search(r"(?:decimal|numeric)\s*\(\s*\d+\s*,\s*(\d+)\s*\)",
                                  sql_type, re.I)
                if scale and misata_type == "float":
                    distribution_params["decimals"] = int(scale.group(1))
                if length:
                    distribution_params["max_length"] = length
                    codes = (_code_choices(col_name, length)
                             if _FIXED_CHAR_RE.match(sql_type) or length <= 3 else None)
                    if codes:
                        misata_type = "categorical"
                        distribution_params = {"choices": codes}

            cols.append(Column(name=col_name, type=misata_type, nullable=nullable,
                               distribution_params=distribution_params))

        # Keys and declared uniqueness: a single-column primary key is unique,
        # as is any column under an inline or single-column UNIQUE.
        if len(pk_cols) == 1:
            unique_cols |= pk_cols
        final_cols = []
        for col in cols:
            if col.name in checks and col.type != "foreign_key":
                col = _apply_check(col, checks[col.name])
            if col.name in unique_cols and not col.unique:
                params = dict(col.distribution_params or {})
                if col.type == "text" and col.name in pk_cols and "pattern" not in params:
                    # A text primary key is a code, not a sentence: prose
                    # keys collide, overflow their width, and read as fake.
                    width = params.get("max_length")
                    if width is None or width >= 36:
                        params["text_type"] = "uuid"
                    else:
                        digits = max(1, min(width - 4, 12)) if width > 4 else width
                        prefix = (re.sub(r"[^A-Z]", "", _singular(table_name).upper())[:3]
                                  if width > 4 else "")
                        params["pattern"] = (f"{prefix}-" if prefix else "") + "#" * digits
                col = Column(name=col.name, type=col.type, nullable=col.nullable,
                             unique=True, distribution_params=params)
            final_cols.append(col)
        cols = final_cols
        if unparsed_checks:
            warnings.warn(
                f"{table_name}: {unparsed_checks} CHECK constraint(s) are beyond what "
                f"the importer can translate (OR, multi-column or function "
                f"expressions); the database will still enforce them, so seeding may "
                f"fail on rows that violate them.",
                UserWarning, stacklevel=2,
            )

        # FK inference from _id suffix
        if infer_fks:
            own_key_names = {"id", f"{table_name}_id", f"{_singular(table_name)}_id"}
            for col in cols:
                if (col.name.endswith("_id") and col.name not in explicit_fk_cols
                        and col.name not in own_key_names
                        and col.name not in pk_cols):
                    guessed_parent = col.name[:-3]
                    fk_specs.append((col.name, guessed_parent, "id"))
                    explicit_fk_cols.add(col.name)
                    inferred_fks.add((table_name, col.name))

        # Promote inferred FK columns to foreign_key type
        explicit_fk_set = {c for c, _, _ in fk_specs}
        new_cols = []
        for col in cols:
            if col.name in explicit_fk_set and col.type not in ("foreign_key",):
                new_cols.append(Column(
                    name=col.name,
                    type="foreign_key",
                    nullable=col.nullable,
                    distribution_params=col.distribution_params,
                ))
            else:
                new_cols.append(col)
        cols = new_cols

        # A later date checked against an earlier one (check_out > check_in)
        # is drawn as the earlier date plus a duration that fits the pair,
        # not as an unrelated date repaired afterwards.
        by_name = {c.name: c for c in cols}
        for a_col, op, b_col in pair_checks:
            late, early = (a_col, b_col) if ">" in op else (b_col, a_col)
            lc, ec = by_name.get(late), by_name.get(early)
            if lc is not None and ec is not None and lc.type == "date" and ec.type in ("date", "datetime"):
                lo_days, hi_days = _pair_duration(late, early)
                params = dict(lc.distribution_params or {})
                params.update(after_column=early, max_delta_days=hi_days,
                              min_delta_days=max(lo_days, 1 if op in (">", "<") else 0))
                if hi_days <= 30:
                    params["delta_shape"] = "skewed"
                by_name[late] = Column(name=lc.name, type=lc.type, nullable=lc.nullable,
                                       unique=lc.unique, distribution_params=params)
        cols = [by_name[c.name] for c in cols]

        # Rules across columns: CHECK (a > b) and composite keys.
        col_names = {c.name for c in cols}
        table_constraints: List[Constraint] = []
        for a, op, b in pair_checks:
            if a in col_names and b in col_names:
                table_constraints.append(Constraint(
                    name=f"{table_name}_{a}_{'gt' if '>' in op else 'lt'}_{b}", type="inequality",
                    column_a=a, operator=op, column_b=b, action="cap"))
        if len(pk_cols) > 1:
            unique_sets.append(sorted(pk_cols, key=[c.name for c in cols].index)
                               if all(c in col_names for c in pk_cols) else sorted(pk_cols))
        for us in unique_sets:
            if all(c in col_names for c in us):
                table_constraints.append(Constraint(
                    name=f"{table_name}_unique_{'_'.join(us)}", type="unique_combination",
                    group_by=list(us), action="drop"))
        tables.append(Table(name=table_name, row_count=default_rows, constraints=table_constraints))
        columns_map[table_name] = cols

        for child_col, parent_table, parent_col in fk_specs:
            relationships.append(Relationship(
                parent_table=parent_table,
                child_table=table_name,
                parent_key=parent_col,
                child_key=child_col,
            ))

    if not tables:
        raise ValueError(
            "No CREATE TABLE statements found in DDL. "
            "Make sure each statement follows the standard syntax: "
            "CREATE TABLE name (col_definitions);"
        )

    # Drop relationships referencing unknown tables, which avoids SchemaConfig
    # validation errors
    known = set(all_table_names)

    # `category_id` guesses a parent called `category`, but the table is almost
    # always `categories`. Resolve the plural before giving up, and only for
    # names we guessed: an explicit REFERENCES naming a missing table is the
    # author's error, not ours to reinterpret.
    by_lower = {t.lower(): t for t in all_table_names}

    def _resolve_parent(guess: str) -> Optional[str]:
        for candidate in (guess, guess + "s", guess + "es",
                          (guess[:-1] + "ies") if guess.endswith("y") else guess):
            match = by_lower.get(candidate.lower())
            if match:
                return match
        return None

    resolved: List[Relationship] = []
    for rel in relationships:
        if rel.parent_table not in known and (rel.child_table, rel.child_key) in inferred_fks:
            parent = _resolve_parent(rel.parent_table)
            if parent:
                rel = Relationship(
                    parent_table=parent,
                    child_table=rel.child_table,
                    parent_key=_parent_key_for(parent, columns_map, rel.parent_key),
                    child_key=rel.child_key,
                )
        resolved.append(rel)
    relationships = resolved

    valid_rels = [r for r in relationships if r.parent_table in known]
    dropped = len(relationships) - len(valid_rels)
    if dropped:
        warnings.warn(
            f"{dropped} inferred FK relationship(s) dropped because the referenced "
            "table was not found in the DDL. Pass infer_fks=False to suppress.",
            UserWarning,
            stacklevel=2,
        )

    # A column left typed foreign_key after its relationship was dropped is an
    # invalid schema, and the error it raises names a fix the caller cannot
    # apply because the parent table does not exist. Demote it instead.
    surviving = {(r.child_table, r.child_key) for r in valid_rels}
    for tname, tcols in columns_map.items():
        for index, col in enumerate(tcols):
            if col.type == "foreign_key" and (tname, col.name) not in surviving:
                tcols[index] = Column(
                    name=col.name,
                    type="int",
                    nullable=col.nullable,
                    distribution_params={},
                )

    return SchemaConfig(
        name="from_ddl",
        tables=tables,
        columns=columns_map,
        relationships=valid_rels,
    )
