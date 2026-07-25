"""
Manifest-driven dbt unit test generation.

dbt unit tests are the accepted way to prove a model's SQL logic is right, and
almost nobody writes them for one documented reason: the fixtures are authored
by hand and rot. dbt's own guidance is to hand-write seed files, and every
survey of the space notes that no tooling generates them.

The specific failure this module removes: hand-written fixtures do not agree
with each other. Someone writes ``customers`` with ids 1, 2, 3 and ``orders``
referencing ``customer_id`` 7, the join produces zero rows, and the test either
passes vacuously or fails for a reason that has nothing to do with the model.
Misata generates every input in one pass, so the foreign keys across the
fixtures resolve by construction.

What this reads
---------------
``target/manifest.json``, which is authoritative rather than guessed:

  - ``depends_on.nodes`` gives the exact upstream refs and sources, and dbt
    requires *every* one of them to be declared as an ``input`` or compilation
    fails.
  - each upstream node's ``columns`` gives real column names and warehouse
    data types (from the project's own schema.yml).
  - ``relationships`` test nodes give real foreign keys
    (``test_metadata.kwargs.to`` / ``.field`` plus ``attached_node``).
  - ``manifest['unit_tests']`` gives existing coverage, so we can report which
    models have none.

What this deliberately does NOT do
----------------------------------
It does not invent the ``expect`` rows. Knowing the expected output requires
knowing what the SQL does, and this module does not parse or execute SQL. It
emits the ``expect`` block with the model's real column names and leaves the
values for the author, clearly marked. A fixture that silently asserts the
wrong answer is worse than no fixture: it is the "noisy tests get ignored"
failure mode that keeps teams from adopting unit tests at all.

Usage::

    misata dbt-unit-test --select customer_orders
    misata dbt-unit-test --coverage
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# Warehouse data type → Misata column type. Ordered: first match wins, so the
# more specific patterns must come first (e.g. "timestamp" before "time").
_TYPE_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"bool", re.I), "boolean"),
    (re.compile(r"timestamp|datetime", re.I), "datetime"),
    (re.compile(r"^date$", re.I), "date"),
    (re.compile(r"^time$", re.I), "time"),
    (re.compile(r"int|serial|bigint|smallint", re.I), "integer"),
    (re.compile(r"numeric|decimal|float|double|real|money", re.I), "float"),
    (re.compile(r"char|text|string|varchar|uuid", re.I), "string"),
]

_DEFAULT_TYPE = "string"


def map_data_type(data_type: Optional[str]) -> str:
    """Map a warehouse data type to a Misata column type.

    Undocumented types fall back to string rather than raising: a fixture with
    a string column is still useful, and refusing to emit anything because one
    column lacks a ``data_type`` would make this useless on real projects,
    where documentation is patchy.
    """
    if not data_type:
        return _DEFAULT_TYPE
    for pattern, mapped in _TYPE_PATTERNS:
        if pattern.search(data_type):
            return mapped
    return _DEFAULT_TYPE


# --------------------------------------------------------------------------- #
# Manifest reading
# --------------------------------------------------------------------------- #


class ManifestError(RuntimeError):
    """The manifest is missing or unusable, with a fix in the message."""


def find_manifest(project_dir: Optional[Path] = None) -> Path:
    """Locate ``target/manifest.json``, walking upward from ``project_dir``."""
    start = (project_dir or Path.cwd()).resolve()
    for candidate in [start, *start.parents]:
        manifest = candidate / "target" / "manifest.json"
        if manifest.is_file():
            return manifest
        if (candidate / "dbt_project.yml").is_file():
            # Found the project root but no manifest: dbt has not run yet.
            raise ManifestError(
                f"Found a dbt project at {candidate} but no target/manifest.json. "
                "Run `dbt parse` (or any dbt command) first to produce it."
            )
    raise ManifestError(
        "No dbt project found (looked for dbt_project.yml walking upward). "
        "Run this from inside a dbt project, or pass --project-dir."
    )


def load_manifest(path: Path) -> Dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"Could not read {path}: {exc}") from exc
    if "nodes" not in manifest:
        raise ManifestError(
            f"{path} does not look like a dbt manifest (no 'nodes' key)."
        )
    return manifest


# --------------------------------------------------------------------------- #
# Model + input resolution
# --------------------------------------------------------------------------- #


@dataclass
class UnitTestInput:
    """One upstream dependency, resolved to a declarable dbt ``input``."""

    unique_id: str
    name: str
    kind: str                      # "model" | "source" | "seed" | "snapshot"
    ref_expr: str                  # ref('x') or source('a','b')
    columns: Dict[str, str]        # column name → Misata type
    rows: int
    fixture_name: str
    # (child column, parent input unique_id, parent column) for FKs on this input
    foreign_keys: List[Tuple[str, str, str]] = field(default_factory=list)

    @property
    def documented(self) -> bool:
        return bool(self.columns)


@dataclass
class UnitTestPlan:
    """Everything needed to emit one model's unit test, plus what we could not do."""

    model_name: str
    model_unique_id: str
    model_columns: List[str]
    inputs: List[UnitTestInput]
    warnings: List[str] = field(default_factory=list)
    skipped: Optional[str] = None
    has_existing_test: bool = False

    @property
    def usable(self) -> bool:
        return self.skipped is None and bool(self.inputs)


def _model_nodes(manifest: Dict[str, Any]) -> Dict[str, Any]:
    return {
        uid: node
        for uid, node in manifest.get("nodes", {}).items()
        if node.get("resource_type") == "model"
    }


def resolve_model(manifest: Dict[str, Any], name: str) -> Tuple[str, Dict[str, Any]]:
    """Find a model by its name (not unique_id). Raises with candidates on miss."""
    models = _model_nodes(manifest)
    matches = [(uid, n) for uid, n in models.items() if n.get("name") == name]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        known = sorted(n["name"] for n in models.values())[:12]
        hint = ", ".join(known) if known else "none found"
        raise ManifestError(f"No model named '{name}'. Models in this project: {hint}")
    # Same model name in two packages: require the unique_id to disambiguate.
    ids = ", ".join(uid for uid, _ in matches)
    raise ManifestError(f"'{name}' is ambiguous across packages. Use one of: {ids}")


def extract_foreign_keys(
    manifest: Dict[str, Any],
) -> List[Tuple[str, str, str, str]]:
    """Pull real FKs out of the project's own ``relationships`` tests.

    Returns ``(child_unique_id, child_column, parent_unique_id, parent_column)``.

    This is the project's declared truth rather than a name-matching guess, so
    a fixture built from it produces joins that actually resolve.
    """
    out: List[Tuple[str, str, str, str]] = []
    nodes = manifest.get("nodes", {})
    # name → unique_id, so we can resolve the ref('x') inside the test kwargs.
    by_name = {
        n.get("name"): uid
        for uid, n in nodes.items()
        if n.get("resource_type") == "model"
    }
    for node in nodes.values():
        meta = node.get("test_metadata") or {}
        if meta.get("name") != "relationships":
            continue
        kwargs = meta.get("kwargs") or {}
        child_uid = node.get("attached_node")
        child_col = node.get("column_name") or kwargs.get("column_name")
        parent_col = kwargs.get("field")
        to_expr = str(kwargs.get("to") or "")
        if not (child_uid and child_col and parent_col):
            continue
        parent_uid: Optional[str] = None
        ref_match = re.search(r"ref\(\s*['\"]([^'\"]+)['\"]", to_expr)
        if ref_match:
            parent_uid = by_name.get(ref_match.group(1))
        else:
            src_match = re.search(
                r"source\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]", to_expr
            )
            if src_match:
                want = (src_match.group(1), src_match.group(2))
                for uid, s in manifest.get("sources", {}).items():
                    if (s.get("source_name"), s.get("name")) == want:
                        parent_uid = uid
                        break
        if parent_uid:
            out.append((child_uid, str(child_col), parent_uid, str(parent_col)))
    return out


def _columns_of(node: Dict[str, Any]) -> Dict[str, str]:
    """Documented columns of a node, mapped to Misata types."""
    return {
        col_name: map_data_type((col or {}).get("data_type"))
        for col_name, col in (node.get("columns") or {}).items()
    }


def _ref_expression(unique_id: str, node: Dict[str, Any]) -> str:
    """The dbt expression that declares this node as an input."""
    if unique_id.startswith("source."):
        return f"source('{node.get('source_name')}', '{node.get('name')}')"
    return f"ref('{node.get('name')}')"


def _models_with_unit_tests(manifest: Dict[str, Any]) -> set:
    """unique_ids of models that already have at least one unit test."""
    covered = set()
    for ut in (manifest.get("unit_tests") or {}).values():
        # dbt records the tested model both by name and (in recent versions)
        # in depends_on; use whatever is present.
        for uid in (ut.get("depends_on") or {}).get("nodes", []):
            if uid.startswith("model."):
                covered.add(uid)
        name = ut.get("model")
        if name:
            for uid, node in _model_nodes(manifest).items():
                if node.get("name") == name:
                    covered.add(uid)
    return covered


def build_plan(
    manifest: Dict[str, Any],
    model_name: str,
    *,
    rows: int = 5,
) -> UnitTestPlan:
    """Resolve one model into a complete, emittable unit test plan."""
    model_uid, model = resolve_model(manifest, model_name)
    plan = UnitTestPlan(
        model_name=model_name,
        model_unique_id=model_uid,
        model_columns=list((model.get("columns") or {}).keys()),
        inputs=[],
        has_existing_test=model_uid in _models_with_unit_tests(manifest),
    )

    # dbt's own documented limits on unit tests. Refuse rather than emit
    # something that cannot run.
    if model.get("language") != "sql":
        plan.skipped = (
            f"dbt unit tests support SQL models only; '{model_name}' is "
            f"{model.get('language')}."
        )
        return plan
    materialized = (model.get("config") or {}).get("materialized")
    if materialized == "materialized_view":
        plan.skipped = (
            f"dbt does not support unit tests on materialized views "
            f"('{model_name}' is {materialized})."
        )
        return plan

    all_fks = extract_foreign_keys(manifest)
    upstream = (model.get("depends_on") or {}).get("nodes", [])
    if not upstream:
        plan.skipped = (
            f"'{model_name}' has no upstream refs or sources, so there is "
            "nothing to mock. Unit tests need at least one input."
        )
        return plan

    nodes = manifest.get("nodes", {})
    sources = manifest.get("sources", {})

    for uid in upstream:
        node = nodes.get(uid) or sources.get(uid)
        if node is None:
            plan.warnings.append(f"Upstream {uid} is not in the manifest; skipped.")
            continue
        kind = uid.split(".", 1)[0]
        columns = _columns_of(node)
        inp = UnitTestInput(
            unique_id=uid,
            name=str(node.get("name")),
            kind=kind,
            ref_expr=_ref_expression(uid, node),
            columns=columns,
            rows=rows,
            fixture_name=f"{model_name}__{node.get('name')}",
        )
        if not columns:
            plan.warnings.append(
                f"'{inp.name}' has no documented columns in the manifest, so its "
                "fixture cannot be generated. Add columns to its schema.yml, "
                "then re-run."
            )
        plan.inputs.append(inp)

    # Attach FKs, but only where BOTH sides are inputs of this test. A foreign
    # key pointing outside the mocked set cannot be honoured in a fixture.
    input_ids = {i.unique_id for i in plan.inputs}
    by_uid = {i.unique_id: i for i in plan.inputs}
    for child_uid, child_col, parent_uid, parent_col in all_fks:
        if child_uid in input_ids and parent_uid in input_ids:
            child = by_uid[child_uid]
            if child_col in child.columns:
                child.foreign_keys.append((child_col, parent_uid, parent_col))

    if not any(i.documented for i in plan.inputs):
        plan.skipped = (
            f"None of the inputs to '{model_name}' have documented columns. "
            "Misata will not guess column names; document them in schema.yml first."
        )
    return plan


# --------------------------------------------------------------------------- #
# Fixture generation
# --------------------------------------------------------------------------- #


def generate_fixtures(
    plan: UnitTestPlan, *, seed: int = 42
) -> Dict[str, "pd.DataFrame"]:
    """Generate one DataFrame per documented input, with FKs resolving.

    All inputs are generated in a single Misata run so foreign keys agree
    across fixtures. That is the property hand-written fixtures almost always
    get wrong, and it is why the resulting joins actually produce rows.
    """
    import misata

    documented = [i for i in plan.inputs if i.documented]
    if not documented:
        return {}

    # Parents must be generated before children, so order inputs so that any
    # FK target appears first. The engine also topologically sorts, but naming
    # the relationships correctly is what matters here.
    name_for = {i.unique_id: i.name for i in documented}

    tables: Dict[str, Any] = {}
    for inp in documented:
        fk_cols = {c for c, _, _ in inp.foreign_keys}
        cols: Dict[str, Any] = {}
        for col_name, misata_type in inp.columns.items():
            if col_name in fk_cols:
                # Resolved below, after all parents are known.
                continue
            spec: Dict[str, Any] = {"type": misata_type}
            # An id-looking integer column is the natural primary key: make it
            # unique so children have distinct parents to point at.
            if misata_type == "integer" and (
                col_name == "id" or col_name.endswith("_id")
            ):
                spec.update({"unique": True, "min": 1, "max": 9999})
            cols[col_name] = spec
        for child_col, parent_uid, parent_col in inp.foreign_keys:
            parent_name = name_for.get(parent_uid)
            if parent_name is None:
                continue
            cols[child_col] = {
                "type": "foreign_key",
                "foreign_key": {"table": parent_name, "column": parent_col},
            }
        tables[inp.name] = {"rows": inp.rows, "columns": cols}

    schema = {
        "name": f"{plan.model_name}_unit_test",
        "seed": seed,
        "tables": tables,
    }
    generated = misata.generate_from_schema(misata.from_dict_schema(schema))

    # Return keyed by fixture name, with columns in the manifest's declared
    # order so the CSV header matches what a reader expects.
    out: Dict[str, "pd.DataFrame"] = {}
    for inp in documented:
        df = generated.get(inp.name)
        if df is None:
            continue
        ordered = [c for c in inp.columns if c in df.columns]
        out[inp.fixture_name] = df[ordered].head(inp.rows).reset_index(drop=True)
    return out


# --------------------------------------------------------------------------- #
# YAML rendering
# --------------------------------------------------------------------------- #


def render_unit_test_yaml(plan: UnitTestPlan) -> str:
    """Render a valid dbt ``unit_tests`` block for this plan.

    Every upstream is declared as an input, because dbt fails compilation if a
    ref used by the model is missing from ``given``.
    """
    lines: List[str] = [
        "# Generated by `misata dbt-unit-test`.",
        "#",
        "# This file belongs in your models/ directory (dbt requires unit test",
        "# definitions there, not in tests/). The CSV fixtures it references",
        "# live in tests/fixtures/.",
        "#",
        "# PREREQUISITE: the upstream models must already exist in the warehouse.",
        "# dbt introspects each input relation to type a CSV fixture's columns, so",
        "# on a cold project `dbt test` fails with \"the relation doesn't exist\".",
        "# Run `dbt build` (or `dbt run`) once first, then the unit test works.",
        "#",
        "# The `given` inputs are complete and ready to run: every ref the model",
        "# uses is declared, and the foreign keys across the fixtures resolve.",
        "#",
        "# The `expect` rows are NOT filled in. Determining the correct output",
        "# requires knowing what the SQL should produce, which is your call, not",
        "# a guess Misata should make. The column names below are real, taken",
        "# from the model's own documentation.",
        "",
        "unit_tests:",
        f"  - name: test_{plan.model_name}",
        f"    description: >",
        f"      Unit test for {plan.model_name}, with Misata-generated inputs.",
        f"    model: {plan.model_name}",
        "    given:",
    ]

    for inp in plan.inputs:
        lines.append(f"      - input: {inp.ref_expr}")
        if inp.documented:
            lines.append("        format: csv")
            lines.append(f"        fixture: {inp.fixture_name}")
        else:
            # Still declared (dbt requires it), but with an empty inline row set
            # so the test compiles and the gap is obvious.
            lines.append("        format: csv")
            lines.append("        rows: |")
            lines.append("          # TODO: no documented columns for "
                         f"{inp.name}; add them to schema.yml and re-run misata")
        if inp.foreign_keys:
            for child_col, _, parent_col in inp.foreign_keys:
                lines.append(
                    f"        # {inp.name}.{child_col} resolves to {parent_col}"
                )

    lines.append("    expect:")
    lines.append("      format: csv")
    lines.append("      rows: |")
    if plan.model_columns:
        lines.append("        " + ",".join(plan.model_columns))
        lines.append("        # TODO: one row per expected output row")
    else:
        lines.append("        # TODO: document this model's columns in "
                     "schema.yml so Misata can emit the header")
    lines.append("")
    return "\n".join(lines)


def coerce_to_declared_types(
    df: "pd.DataFrame", columns: Dict[str, str]
) -> "pd.DataFrame":
    """Render each value the way its *declared* type requires.

    This matters more than it looks. The engine's ``date`` type yields a
    timestamp (``2022-11-05 12:21:29``), so writing it straight into a fixture
    for a column the warehouse declares as ``date`` puts a time component into
    a date column. Depending on the adapter that either fails to cast or, worse,
    silently succeeds and quietly changes what a date comparison in the model
    means — a test that misleads is the thing this module exists to avoid.

    So the fixture is formatted against the type the project declared, not the
    type the generator happened to produce.
    """
    out = df.copy()
    for col, misata_type in columns.items():
        if col not in out.columns:
            continue
        series = out[col]
        if misata_type == "date":
            out[col] = pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%d")
        elif misata_type == "time":
            out[col] = pd.to_datetime(series, errors="coerce").dt.strftime("%H:%M:%S")
        elif misata_type == "datetime":
            # Seconds precision: nanoseconds are noise in a fixture and make
            # an expected-vs-actual comparison needlessly brittle.
            out[col] = pd.to_datetime(series, errors="coerce").dt.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        elif misata_type == "integer":
            # Never let an integer column serialise as 1.0.
            out[col] = pd.to_numeric(series, errors="coerce").astype("Int64")
        elif misata_type == "boolean":
            out[col] = series.map(
                lambda v: "" if pd.isna(v) else ("true" if bool(v) else "false")
            )
    return out


def fixture_csv(df: "pd.DataFrame", columns: Optional[Dict[str, str]] = None) -> str:
    """Serialise a fixture to the CSV dbt expects: header row, no index.

    Pass ``columns`` (name → Misata type) to render values against their
    declared types; see :func:`coerce_to_declared_types`.
    """
    if columns:
        df = coerce_to_declared_types(df, columns)
    return df.to_csv(index=False, lineterminator="\n")


# --------------------------------------------------------------------------- #
# Coverage
# --------------------------------------------------------------------------- #


@dataclass
class CoverageRow:
    name: str
    unique_id: str
    has_unit_test: bool
    upstream_count: int
    documented: bool


def coverage(manifest: Dict[str, Any]) -> List[CoverageRow]:
    """Which models have a unit test, and which are ready for one.

    Sorted so the most useful targets come first: undocumented models cannot
    be generated for, so they sink to the bottom.
    """
    covered = _models_with_unit_tests(manifest)
    rows: List[CoverageRow] = []
    for uid, node in _model_nodes(manifest).items():
        upstream = (node.get("depends_on") or {}).get("nodes", [])
        rows.append(
            CoverageRow(
                name=str(node.get("name")),
                unique_id=uid,
                has_unit_test=uid in covered,
                upstream_count=len(upstream),
                documented=bool(node.get("columns")),
            )
        )
    rows.sort(key=lambda r: (r.has_unit_test, not r.documented, -r.upstream_count, r.name))
    return rows
