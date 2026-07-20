"""Deterministic parsing for structured spec prompts.

Some "stories" are not stories: they are schemas written in prose, with exact
table lists, exact row counts, column lists, FK rules, and enumerations
("Table 1: customers / Rows: exactly 500 / Columns: ... / customer_id must
match values from customers table"). Sending a spec like that through an LLM
and hoping it obeys is fragile, and truncation on token-capped providers makes
it worse. So both story paths check here first: when a prompt looks like a
spec, it is parsed deterministically, and "exactly 500" means exactly 500.

Rules the parser cannot translate are collected in the report and surfaced as
warnings, never guessed at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

_TABLE_HEADER_RE = re.compile(r"(?im)^\s*table\s*\d*\s*[:\-]\s*([A-Za-z_][\w]*)\s*$")
_ROWS_RE = re.compile(r"(?i)\brows?\b\s*[:\-]?\s*(?:exactly\s*)?([\d][\d,]*)")
_COLUMNS_MARK_RE = re.compile(r"(?i)^\s*columns?\s*[:\-]?\s*$")
_IDENT_LINE_RE = re.compile(r"^\s*([a-z][a-z0-9_]*)\s*$")
_ARROW_FK_RE = re.compile(r"([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*(?:→|->)\s*([A-Za-z_]\w*)\.([A-Za-z_]\w*)")
_MATCH_FK_RE = re.compile(r"(?i)\b([a-z_]\w*)\b\s+must match values? from\s+(?:the\s+)?([a-z_]\w*)\s+table")
_RANGE_RE = re.compile(r"(?i)\b([a-z_]\w*?)s?\b\s+must be\s+(-?\d+)\s+(?:to|-|through)\s+(-?\d+)")
_ENUM_HEAD_RE = re.compile(r"(?i)^\s*(.+?)\s+(?:must (?:only )?be|types?)\s*:\s*$")
_VAR_POOL_RE = re.compile(r"(?m)^\s*([a-z_]\w*)\s*:\s*(.+,.+)$")
_ENUM_ITEM_RE = re.compile(r"^\s*([A-Z][A-Za-z0-9 /&\-]{0,38})\s*$")

_BOOLEAN_NAMES = {"verified_purchase", "follow_up_required", "is_active", "paid", "churned"}
_SENTIMENT_CHOICES = ["positive", "neutral", "negative"]


def looks_like_spec(text: str) -> bool:
    """A prompt is a spec when it declares tables with explicit structure."""
    if not text or len(text) < 200:
        return False
    headers = _TABLE_HEADER_RE.findall(text)
    if len(headers) >= 2:
        return True
    return bool(headers) and bool(_ROWS_RE.search(text)) and "column" in text.lower()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

@dataclass
class SpecReport:
    tables: int = 0
    relationships: int = 0
    enums: int = 0
    ranges: int = 0
    templates: int = 0
    refined: int = 0
    untranslated: List[str] = field(default_factory=list)
    # Columns whose values are contractual (FKs, PKs, declared enums, declared
    # ranges, realized templates). An LLM refinement pass may add a coupling
    # to them but can never change their pools or bounds.
    locked: Dict[str, List[str]] = field(default_factory=dict)

    def lock(self, table: str, column: str) -> None:
        self.locked.setdefault(table, []).append(column)

    def summary(self) -> str:
        line = (
            f"Structured spec parsed deterministically: {self.tables} table(s), "
            f"{self.relationships} foreign key(s), {self.enums} enumeration(s), "
            f"{self.ranges} range rule(s), {self.templates} text template(s)."
        )
        if self.refined:
            line += f" LLM refined {self.refined} column(s) within the locked contract."
        if self.untranslated:
            line += " Rules not translated (listed, not guessed): " + "; ".join(
                self.untranslated[:6]
            )
        return line


@dataclass
class _TableSpec:
    name: str
    rows: int
    columns: List[str] = field(default_factory=list)
    body: str = ""


def _split_tables(text: str, default_rows: int) -> List[_TableSpec]:
    matches = list(_TABLE_HEADER_RE.finditer(text))
    specs: List[_TableSpec] = []
    for i, m in enumerate(matches):
        name = m.group(1)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() : end]
        rows_m = _ROWS_RE.search(body)
        rows = int(rows_m.group(1).replace(",", "")) if rows_m else default_rows

        columns: List[str] = []
        lines = body.split("\n")
        j = 0
        while j < len(lines):
            if _COLUMNS_MARK_RE.match(lines[j]):
                j += 1
                while j < len(lines):
                    line = lines[j].strip()
                    if not line:
                        # allow a single blank inside the column list
                        if j + 1 < len(lines) and _IDENT_LINE_RE.match(lines[j + 1]):
                            j += 1
                            continue
                        break
                    ident = _IDENT_LINE_RE.match(line)
                    if not ident:
                        break
                    columns.append(ident.group(1))
                    j += 1
                break
            j += 1
        specs.append(_TableSpec(name=name, rows=rows, columns=columns, body=body))
    # A repeated later mention ("Row counts must be exactly: customers: 500")
    # never overrides the block declaration; blocks are the source of truth.
    return specs


def _singular(word: str) -> str:
    w = word.lower()
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _find_column(table: _TableSpec, phrase: str) -> Optional[str]:
    """Match an enum heading like 'Ticket categories' or 'Interaction types'
    to a column of the table. Score every column by token overlap (an exact
    token match outweighs a substring hit) so 'category' beats 'ticket_id'
    and 'interaction_type' beats 'interaction_id'."""
    tokens = [_singular(t) for t in re.findall(r"[A-Za-z_]+", phrase)]
    best: Optional[str] = None
    best_score = 0
    for col in table.columns:
        base = col.lower()
        score = 0
        for t in tokens:
            if not t:
                continue
            if t == base:
                score += 3
            elif t in base or base in t:
                score += 1
        if score > best_score or (score == best_score and score and best and len(col) < len(best)):
            best, best_score = col, score
    return best


def _collect_enum_items(lines: List[str], start: int) -> Tuple[List[str], int]:
    items: List[str] = []
    j = start
    while j < len(lines):
        line = lines[j].strip()
        if not line:
            if items:
                break
            j += 1
            continue
        m = _ENUM_ITEM_RE.match(line)
        if not m or line.endswith(":"):
            break
        items.append(m.group(1).strip())
        j += 1
    return items, j


def _parse_templates(
    body: str, table: _TableSpec, report: SpecReport
) -> Dict[str, Dict[str, Any]]:
    """'Generate <col> using template' + variable pools + an example sentence
    becomes native template params: each pool value found in the example is
    replaced by its {slot}, and the engine fills slots per row. If the spec
    already writes {placeholder} syntax, it is taken as-is."""
    out: Dict[str, Dict[str, Any]] = {}
    tmpl_m = re.search(r"(?i)generate\s+([a-z_]\w*)\s+using\s+template", body)
    if not tmpl_m:
        return out
    col = tmpl_m.group(1)
    if col not in table.columns:
        return out

    pools: Dict[str, List[str]] = {}
    for pm in _VAR_POOL_RE.finditer(body):
        values = [v.strip() for v in pm.group(2).split(",") if v.strip()]
        if len(values) >= 2:
            pools[pm.group(1)] = values

    ex_m = re.search(r'(?i)example[^\n]*:\s*\n\s*"([^"]+)"', body)
    if not ex_m or not pools:
        report.untranslated.append(f"template for '{col}' lacked an example or pools")
        return out
    template = ex_m.group(1)

    if "{" not in template:
        # A concrete example sentence: slot it by swapping each pool value
        # found in it for its {pool_name} placeholder.
        slotted = False
        for pool_name, values in pools.items():
            hit = next((v for v in values if v.lower() in template.lower()), None)
            if hit:
                template = re.sub(
                    re.escape(hit), "{" + pool_name + "}", template,
                    count=1, flags=re.IGNORECASE,
                )
                slotted = True
        if not slotted:
            report.untranslated.append(
                f"template example for '{col}' matched no variable pools"
            )
            return out

    out[col] = {"templates": [template], "variables": pools}
    report.templates += 1
    return out


def parse_spec(text: str, default_rows: int = 1000) -> Tuple["SchemaConfig", SpecReport]:
    from misata.schema import Column, Relationship, SchemaConfig, Table
    from misata.semantic import SemanticInference

    report = SpecReport()
    specs = _split_tables(text, default_rows)
    if not specs:
        raise ValueError("No table blocks found in the spec.")
    report.tables = len(specs)
    by_name = {t.name: t for t in specs}
    inference = SemanticInference()

    # Foreign keys, both syntaxes, from the WHOLE text (rules often live in a
    # final validation section). (child_table, child_col, parent_table, parent_col)
    fks: Dict[Tuple[str, str], Tuple[str, str]] = {}

    for t in specs:
        for m in _MATCH_FK_RE.finditer(t.body):
            col, parent = m.group(1), m.group(2)
            if parent in by_name and col in t.columns and parent != t.name:
                parent_key = col if col in by_name[parent].columns else (
                    by_name[parent].columns[0] if by_name[parent].columns else col
                )
                fks[(t.name, col)] = (parent, parent_key)

    for m in _ARROW_FK_RE.finditer(text):
        lt, lc, rt, rc = m.groups()
        if lt not in by_name or rt not in by_name or lt == rt:
            continue
        # The side whose column is its own primary key is the parent.
        def _is_pk(tbl: str, col: str) -> bool:
            cols = by_name[tbl].columns
            return bool(cols) and cols[0] == col
        if _is_pk(lt, lc) and not _is_pk(rt, rc):
            parent, pk, child, ck = lt, lc, rt, rc
        elif _is_pk(rt, rc) and not _is_pk(lt, lc):
            parent, pk, child, ck = rt, rc, lt, lc
        else:
            parent, pk, child, ck = lt, lc, rt, rc
        if ck in by_name[child].columns:
            fks[(child, ck)] = (parent, pk)

    # Enumerations and ranges per table block
    enums: Dict[Tuple[str, str], List[str]] = {}
    ranges: Dict[Tuple[str, str], Tuple[int, int]] = {}
    template_choices: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for t in specs:
        lines = t.body.split("\n")
        for j, line in enumerate(lines):
            em = _ENUM_HEAD_RE.match(line.strip())
            if em:
                # Match on the whole heading ("Interaction types") so words the
                # head pattern consumed, like "types", still count as tokens.
                phrase = re.sub(r"(?i)\b(must|only|be)\b", " ", line)
                col = _find_column(t, phrase)
                items, _ = _collect_enum_items(lines, j + 1)
                if col and len(items) >= 2:
                    enums[(t.name, col)] = items
                    report.enums += 1
                elif items:
                    report.untranslated.append(
                        f"{t.name}: enumeration '{em.group(1)}' matched no column"
                    )
        for rm in _RANGE_RE.finditer(t.body):
            col = _find_column(t, rm.group(1))
            if col:
                ranges[(t.name, col)] = (int(rm.group(2)), int(rm.group(3)))
                report.ranges += 1
        for col, variants in _parse_templates(t.body, t, report).items():
            template_choices[(t.name, col)] = variants

    # Known prose rules we deliberately do not fake
    if re.search(r"(?i)sentiment must match rating", text):
        report.untranslated.append(
            "'sentiment must match rating' coupling (columns generated independently)"
        )

    # Build the SchemaConfig
    tables: List[Table] = []
    columns: Dict[str, List[Column]] = {}
    relationships: List[Relationship] = []

    for t in specs:
        cols: List[Column] = []
        for i, name in enumerate(t.columns):
            key = (t.name, name)
            if key in fks:
                parent, pk = fks[key]
                relationships.append(Relationship(
                    parent_table=parent, child_table=t.name,
                    parent_key=pk, child_key=name,
                ))
                report.relationships += 1
                report.lock(t.name, name)
                cols.append(Column(name=name, type="foreign_key", nullable=False))
                continue
            if key in template_choices:
                report.lock(t.name, name)
                cols.append(Column(
                    name=name, type="text",
                    distribution_params=dict(template_choices[key]),
                ))
                continue
            if key in enums:
                report.lock(t.name, name)
                cols.append(Column(
                    name=name, type="categorical",
                    distribution_params={"choices": enums[key]},
                ))
                continue
            if key in ranges:
                lo, hi = ranges[key]
                report.lock(t.name, name)
                cols.append(Column(
                    name=name, type="int",
                    distribution_params={"min": lo, "max": hi},
                ))
                continue
            if name == "sentiment" or name.endswith("_sentiment"):
                cols.append(Column(
                    name=name, type="categorical",
                    distribution_params={"choices": list(_SENTIMENT_CHOICES)},
                ))
                continue
            if name in _BOOLEAN_NAMES or name.startswith(("is_", "has_")):
                cols.append(Column(name=name, type="boolean"))
                continue
            if i == 0 and (name == "id" or name.endswith("_id")):
                report.lock(t.name, name)
                cols.append(Column(
                    name=name, type="int", unique=True,
                    distribution_params={"min": 1, "max": max(t.rows * 10, 1000)},
                ))
                continue

            inferred = inference.infer_column(name)
            if inferred is not None:
                itype, iparams = inferred
                cols.append(Column(name=name, type=itype, distribution_params=iparams))
            elif name.endswith(("_date", "_at")) or name == "date":
                cols.append(Column(
                    name=name, type="date",
                    distribution_params={"start": "2024-01-01", "end": "2025-12-31"},
                ))
            elif name.endswith(("_score", "_votes", "_minutes", "quantity", "_count")):
                cols.append(Column(
                    name=name, type="int", distribution_params={"min": 1, "max": 100},
                ))
            elif name.endswith(("amount", "revenue", "price")):
                cols.append(Column(
                    name=name, type="float",
                    distribution_params={"min": 10, "max": 10_000, "decimals": 2},
                ))
            else:
                cols.append(Column(name=name, type="text"))

        if not cols:
            report.untranslated.append(f"{t.name}: no columns found; skipped")
            continue
        tables.append(Table(name=t.name, row_count=t.rows, columns=[c.name for c in cols]))
        columns[t.name] = cols

    built = {t.name for t in tables}
    relationships = [
        r for r in relationships if r.parent_table in built and r.child_table in built
    ]

    return SchemaConfig(
        name="spec prompt",
        description="Parsed deterministically from a structured spec prompt",
        tables=tables, columns=columns, relationships=relationships, seed=42,
    ), report


# ---------------------------------------------------------------------------
# LLM refinement of a parsed spec (the hybrid path)
# ---------------------------------------------------------------------------
# The parser owns the contract; the model owns the semantics. After parsing,
# an LLM may be asked to refine UNLOCKED columns (realistic distributions,
# better text types) and to translate open prose rules into conditional
# mappings ("sentiment must match rating" -> depends_on + mapping). Its
# answer is merged here under hard enforcement: structure, row counts, FKs,
# and locked pools/bounds can never change, whatever the model returns.

_SAFE_TYPES = {"int", "float", "text", "categorical", "date", "boolean"}
_SAFE_PARAMS = {
    "distribution", "mean", "std", "mu", "sigma", "min", "max", "decimals",
    "choices", "probabilities", "text_type", "start", "end",
    "depends_on", "mapping", "templates", "template", "variables",
}


def spec_skeleton(schema: "SchemaConfig", report: SpecReport) -> str:
    """Compact one-line-per-table skeleton for the refinement prompt. Small on
    purpose: it replaces the full spec text, which is what blows token caps."""
    locked = {t: set(cs) for t, cs in report.locked.items()}
    lines = []
    for t in schema.tables:
        parts = []
        for c in schema.columns[t.name]:
            tag = c.type
            if c.name in locked.get(t.name, set()):
                tag += ",LOCKED"
            parts.append(f"{c.name}({tag})")
        lines.append(f"{t.name} [{t.row_count} rows]: " + ", ".join(parts))
    return "\n".join(lines)


def _as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else [v]


def merge_refinements(
    schema: "SchemaConfig", report: SpecReport, overrides: Dict[str, Any]
) -> int:
    """Apply LLM overrides to a parsed spec schema, enforcing the contract.

    Accepted shape: {table: {column: {"type": ..., "distribution_params": {...}}}}
    (flat params on the column dict are tolerated). Rules:
      - unknown tables/columns are ignored; row counts and FKs are untouchable
      - locked columns accept ONLY a depends_on+mapping coupling whose mapped
        values stay inside the declared pool
      - unlocked columns accept safe types and whitelisted params
    Returns the number of columns changed (also recorded on the report).
    """
    if not isinstance(overrides, dict):
        return 0
    locked = {t: set(cs) for t, cs in report.locked.items()}
    applied = 0
    for tname, col_overrides in overrides.items():
        if tname not in schema.columns or not isinstance(col_overrides, dict):
            continue
        col_map = {c.name: c for c in schema.columns[tname]}
        for cname, spec in col_overrides.items():
            col = col_map.get(cname)
            if col is None or not isinstance(spec, dict):
                continue
            if col.type == "foreign_key" or col.unique:
                continue
            params = dict(spec.get("distribution_params") or {})
            for k in _SAFE_PARAMS:
                if k in spec and k not in params:
                    params[k] = spec[k]

            dep = params.get("depends_on")
            mapping = params.get("mapping")
            has_coupling = (
                isinstance(dep, str) and dep in col_map and dep != cname
                and isinstance(mapping, dict) and mapping
            )

            if cname in locked.get(tname, set()):
                # Contractual column: a coupling is the only accepted change,
                # and every mapped value must stay inside the declared pool.
                declared = (col.distribution_params or {}).get("choices")
                if not has_coupling or declared is None:
                    continue
                allowed = {str(v) for v in declared}
                mapped = {str(v) for vs in mapping.values() for v in _as_list(vs)}
                if not mapped.issubset(allowed):
                    continue
                col.distribution_params.update({
                    "depends_on": dep,
                    "mapping": {str(k): _as_list(v) for k, v in mapping.items()},
                    # Unmapped parent values fall back inside the vocabulary.
                    "default": list(declared),
                })
                applied += 1
                continue

            changed = False
            ntype = spec.get("type")
            if ntype in _SAFE_TYPES and ntype != col.type:
                col.type = ntype
                changed = True
            safe = {k: v for k, v in params.items() if k in _SAFE_PARAMS}
            if not has_coupling:
                safe.pop("depends_on", None)
                safe.pop("mapping", None)
            elif isinstance(safe.get("mapping"), dict):
                safe["mapping"] = {str(k): v for k, v in safe["mapping"].items()}
            if safe:
                col.distribution_params.update(safe)
                changed = True
            if changed:
                applied += 1
    report.refined += applied
    return applied
