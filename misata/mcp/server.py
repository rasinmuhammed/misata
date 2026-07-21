"""Misata MCP server.

Thin protocol shim that exposes Misata's public API to AI agents over
the Model Context Protocol. The server runs over stdio and registers
six tools — ``generate_from_schema`` (primary: the agent designs the
schema, Misata guarantees the math), ``generate_dataset``,
``list_domains``, ``preview_story``, ``inspect_schema``,
``validate_yaml`` — that map onto the existing :mod:`misata` functions.

This module is part of Misata itself (not a separate package) because
the server is a *protocol adapter*, not a new product. It calls the
library directly with no HTTP boundary, so version skew is impossible.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - import-time guard
    raise ImportError(
        "The MCP extra is not installed. Install with: pip install \"misata[mcp]\""
    ) from exc

import misata
from misata.story_parser import StoryParser


mcp = FastMCP(
    "misata",
    instructions=(
        "Misata generates realistic, referentially-intact multi-table synthetic data — "
        "no real data, no ML model, fully seeded. Use it whenever a user needs test data, "
        "a seeded database, demo data, fixtures, or a relational dataset shaped to "
        "specific outcomes (a revenue curve, a fraud rate, exact monthly aggregates). "
        "Division of labour: YOU are good at designing schemas; Misata is good at "
        "guaranteeing the math (FK integrity, exact aggregates, distributions, "
        "reproducibility). So when you know — or can design — the tables and columns the "
        "user needs, call generate_from_schema with a schema dict: that is the primary "
        "tool, and it returns a per-relationship integrity verification you can show the "
        "user. Use generate_dataset(story) only for quick one-sentence requests where "
        "Misata's own parser should design the schema (18 curated domains + structural "
        "composition for unknown ones; preview_story shows the interpretation first). "
        "To fill a real development database, use seed_database with a connection "
        "string: it reads the schema from the database itself, inserts parents before "
        "children, and verifies every foreign key against the database afterwards. It "
        "PLANS BY DEFAULT — show the user the plan, and only re-call with apply=true "
        "once they agree; never pass apply=true on a first call, and never choose "
        "truncate (which destroys data) on the user's behalf."
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _domain_catalogue() -> List[Dict[str, Any]]:
    """Build the public list of domains, with one canonical sample story each."""
    samples = {
        "saas": "A SaaS company with 5k users and 20% churn",
        "ecommerce": "An ecommerce store with 10k orders and seasonal peaks",
        "fintech": "A fintech with 5k customers and 50k payments",
        "healthcare": "A healthcare clinic with 1k patients and doctors",
        "marketplace": "A freelance marketplace with sellers and buyers",
        "logistics": "A logistics fleet with drivers, vehicles, and shipments",
        "hr": "An HR system with 500 employees and payroll",
        "social": "A social media app with creators, posts, and reels",
        "realestate": "A real estate platform with property listings and agents",
        "pharma": "A pharma research company with clinical trials",
        "fooddelivery": "A food delivery app with restaurants, couriers, and orders",
        "edtech": "An edtech platform with courses, students, and quizzes",
        "gaming": "A gaming platform with players, matches, and achievements",
        "crm": "A CRM with companies, contacts, and a deals pipeline",
        "crypto": "A crypto exchange with wallets and blockchain transactions",
        "insurance": "An insurance company with policies and claims",
        "travel": "A travel booking platform with hotels and flights",
        "streaming": "A Netflix-like streaming service with subscribers",
    }
    return [
        {
            "domain": domain,
            "keywords": list(keywords),
            "sample_story": samples.get(domain, ""),
        }
        for domain, keywords in StoryParser.DOMAIN_KEYWORDS.items()
    ]


def _df_preview(df, n: int = 5) -> List[Dict[str, Any]]:
    """Return up to N rows as JSON-safe dicts."""
    return json.loads(df.head(n).to_json(orient="records", date_format="iso", default_handler=str))


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def _tool_error(exc: Exception, suggestion: str) -> Dict[str, Any]:
    """Return a structured error payload instead of raising — keeps agents recoverable."""
    return {
        "ok": False,
        "error": type(exc).__name__,
        "message": str(exc),
        "suggestion": suggestion,
    }


@mcp.tool()
def list_domains() -> Dict[str, Any]:
    """List the 18 built-in business domains Misata can generate from natural language.

    Each domain has trigger keywords and a sample story you can pass to
    ``preview_story`` or ``generate_dataset``. Use this when the user asks
    "what kinds of data can you generate?" or to suggest a story format.
    """
    try:
        return {
            "ok": True,
            "count": len(StoryParser.DOMAIN_KEYWORDS),
            "domains": _domain_catalogue(),
        }
    except Exception as exc:
        return _tool_error(exc, "This should never fail — please report a bug at https://github.com/rasinmuhammed/misata/issues")


@mcp.tool()
def preview_story(story: str, rows: int = 1000) -> Dict[str, Any]:
    """Inspect what Misata would generate from a story — without generating any rows.

    Returns the detected domain, confidence, near-misses, locale, scale,
    and a preview of the tables that would be produced. Use this to
    confirm interpretation before committing to a (potentially large)
    generation.

    Args:
        story: Plain-English description of the dataset.
        rows:  Default row count for the primary table (affects preview only).
    """
    try:
        report = misata.preview(story, rows=rows)
        return {
            "ok": True,
            "domain": report.domain,
            "domain_confidence": report.domain_confidence,
            "matched_keywords": report.matched_keywords,
            "near_misses": report.near_misses,
            "locale": report.locale,
            "scale": report.scale_params,
            "events": report.temporal_events,
            "tables": report.table_preview,
            "total_rows": report.total_rows,
            "warnings": report.warnings,
            "summary": report.summary(),
        }
    except Exception as exc:
        return _tool_error(
            exc,
            "Check that the story is a non-empty string. "
            "Try calling list_domains() first to see which domain keywords are supported.",
        )


@mcp.tool()
def inspect_schema(story: str, rows: int = 1000) -> Dict[str, Any]:
    """Return the full schema (tables, columns, relationships) for a story without
    generating data.

    Heavier than ``preview_story`` — includes every column with its type and
    distribution params. Use when the user wants to see the structure they'll
    get, or to author a ``misata.yaml`` file from a natural-language seed.

    Args:
        story: Plain-English description of the dataset.
        rows:  Default row count for the primary table.
    """
    try:
        schema = misata.parse(story, rows=rows)
    except Exception as exc:
        return _tool_error(
            exc,
            "Try preview_story() first to see how Misata interprets your description. "
            "Adding a domain keyword (e.g. 'saas', 'fintech', 'ecommerce') often resolves parsing issues.",
        )

    tables_out = []
    for tbl in schema.tables:
        cols = schema.get_columns(tbl.name)
        tables_out.append({
            "name": tbl.name,
            "row_count": tbl.row_count,
            "description": tbl.description,
            "columns": [
                {
                    "name": c.name,
                    "type": c.type,
                    "unique": c.unique,
                    "nullable": c.nullable,
                    "params": dict(c.distribution_params or {}),
                }
                for c in cols
            ],
        })

    relationships_out = [
        {
            "parent_table": r.parent_table,
            "parent_key": r.parent_key,
            "child_table": r.child_table,
            "child_key": r.child_key,
        }
        for r in schema.relationships
    ]

    outcome_curves_out = [
        {
            "table": c.table,
            "column": c.column,
            "time_column": c.time_column,
            "time_unit": c.time_unit,
            "pattern_type": c.pattern_type,
            "value_mode": c.value_mode,
            "curve_points": c.curve_points,
        }
        for c in schema.outcome_curves
    ]

    return {
        "ok": True,
        "name": schema.name,
        "domain": schema.domain,
        "tables": tables_out,
        "relationships": relationships_out,
        "outcome_curves": outcome_curves_out,
        "summary": schema.summary(),
    }


@mcp.tool()
def generate_dataset(
    story: str,
    rows: int = 1000,
    seed: Optional[int] = None,
    output_dir: Optional[str] = None,
    sample_rows: int = 5,
) -> Dict[str, Any]:
    """Generate a synthetic dataset from a story and write it to disk as CSV files.

    Returns the output directory, file paths, row counts per table, and a
    small sample of rows for each table so the agent can show the user what
    was produced without loading every row into context.

    Args:
        story:        Plain-English description of the dataset.
        rows:         Default row count for the primary table.
        seed:         Optional random seed (same seed → byte-identical output).
        output_dir:   Where to write CSVs. Defaults to a fresh temp dir.
        sample_rows:  Number of rows from each table to include in the response (max 50).
    """
    sample_rows = max(0, min(sample_rows, 50))

    if output_dir:
        out_path = Path(output_dir).expanduser().resolve()
        try:
            out_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return _tool_error(
                exc,
                f"Could not create output directory '{output_dir}'. "
                "Check that the path is writable, or omit output_dir to use a temp directory.",
            )
    else:
        out_path = Path(tempfile.mkdtemp(prefix="misata-mcp-"))

    try:
        tables = misata.generate(story, rows=rows, seed=seed)
    except Exception as exc:
        return _tool_error(
            exc,
            "Try preview_story() first to verify Misata understands the story. "
            "If rows is very large (>1 000 000), reduce it. "
            "Adding a domain keyword such as 'saas', 'fintech', or 'ecommerce' "
            "ensures a richer, more reliable schema.",
        )

    files: List[Dict[str, Any]] = []
    for name, df in tables.items():
        csv_path = out_path / f"{name}.csv"
        df.to_csv(csv_path, index=False)
        files.append({
            "table": name,
            "path": str(csv_path),
            "rows": len(df),
            "columns": list(df.columns),
            "sample": _df_preview(df, sample_rows) if sample_rows else [],
        })

    total_rows = sum(f["rows"] for f in files)

    return {
        "ok": True,
        "output_dir": str(out_path),
        "files": files,
        "total_rows": total_rows,
        "table_count": len(files),
        "seed": seed,
    }


@mcp.tool()
def generate_from_schema(
    schema: Dict[str, Any],
    rows: int = 1000,
    seed: Optional[int] = 42,
    output_dir: Optional[str] = None,
    sample_rows: int = 5,
) -> Dict[str, Any]:
    """Generate a dataset from a schema you design. This is the primary Misata tool.

    DIVISION OF LABOUR
    You (the agent) design what the data should look like — the tables,
    columns, business rules, and declared targets. Misata handles the hard
    guarantees: every FK resolves, every rollup reconciles to the cent, every
    declared outcome curve is hit exactly, every seed produces byte-identical
    output. The response includes a per-relationship integrity proof.

    SCHEMA FORMAT  {table_name: {column_name: spec, ...}, ...}

    TABLE-LEVEL KEYS (inside a table dict)
      "__rows__": 5000          Per-table row count; overrides the global rows arg.
                                Always set this — one global count rarely fits all tables.
      "__constraints__"         List of row-level business rules (see CONSTRAINTS below).
      "__correlations__"        List of pairwise Pearson targets (see CORRELATIONS below).
      "__state_machine__"       Markov terminal-state assignment (see STATE MACHINE below).

    COLUMN TYPES
      integer, float, decimal   Numeric.
      string                    Short categorical or free text.
      text                      Long free text (descriptions, notes).
      email, phone, url, uuid   Semantic strings; always valid format.
      date, datetime            Temporal; realistic granularity applied automatically.
      boolean                   True/False with declared probability.

    COLUMN SPEC KEYS (inside a column dict)
      primary_key: true         Auto-incremented PK; column excluded from CSV output.
      foreign_key: {table, column}  Child FK; referential integrity guaranteed + verified.
      min / max                 Numeric or date bounds.
      decimals: 2               Decimal places for float output.
      unique: true              All values in the column are distinct.
      nullable: true            Allow nulls (default true).
      enum: [...]               Categorical choices. Add probabilities: [...] for weights;
                                omit for realistic Zipf-shaped rank frequencies.
      probabilities: [...]      Weights for enum choices; must sum to 1.0.

    DISTRIBUTIONS  (float / integer columns)
      distribution: normal      Also: lognormal, uniform, exponential, beta,
                                poisson, power_law, gamma.
      mean / std                Normal params. Can be a scalar OR a per-row
                                parent-entity lookup:
                                  mean: {formula: "@patients.hba1c_baseline"}
                                The FK is resolved per-row so each child row's
                                distribution is anchored to its parent's value.
                                Use this for longitudinal data where within-entity
                                variation should be modelled separately from
                                between-entity variation.
      mu / sigma                Lognormal params (mu and sigma are of log(x)).
      min / max                 Hard clamps applied after sampling.
      Use lognormal for money, file sizes, session durations — anything
      right-skewed and strictly positive. Use normal for measurements.

    DERIVED COLUMNS
      formula: "quantity * unit_price"       Row-level arithmetic; pandas eval syntax.
      formula: "hours * @employees.rate"     Cross-table via FK: @parent_table.column.
      rollup: {from_table, fk, agg, column}  Parent column that EXACTLY reconciles with
                                              child rows under JOIN. agg: sum/count/mean/
                                              max/min. Add where: {col: val} to filter.
      RULE: use rollup (not formula) for any parent column that summarises child rows.
      Rollups are closed-form exact; formulas cannot cross the FK boundary correctly.

    CODE-STYLE STRINGS
      pattern: "SKU-\\d{5}"              Single pattern expanded per row.
      pattern: ["A/\\d{5}", "\\d{6}"]   List: one shape drawn per row.
      pattern_weights: [0.7, 0.3]        Weights for pattern list (optional).
      Supported tokens: \\d (digit), [A-Z] (uppercase letter), [a-z] (lowercase),
      literal chars, {n} repeat count. Example: "[A-Z]{2}-\\d{4}" → "AB-3721".

    TEXT SEMANTICS
      text_type: person_name    Always beats column-name inference. Options:
                                person_name, email, company, city, country,
                                postal_code, phone, url, description, username,
                                product_name, review_text, address, job_title.
      Dates: appointment times snap to 15-min business-hours grids; signups
      follow waking-hour rhythms; machine events keep sub-second precision.
      Names, genders, and emails are generated jointly and always agree.

    STRATIFIED DISTRIBUTIONS (profiles)
      Use when different subgroups need different distributions for the same column.
      profiles: [
        {when: "arm == 'placebo'",  distribution: normal, mean: -0.35, std: 0.50},
        {when: "arm == 'high_dose'", distribution: normal, mean: -1.25, std: 0.55},
      ]
      Rows that match no profile get the column's top-level distribution.
      The when expression is a pandas eval string; reference any already-generated
      column in the same table. Always list profiles after the columns they reference.

    INFORMATIVE MISSINGNESS (MAR)
      null_when: "dropout == False"        Null this column when expression is true.
      missing_if:                          Missing-At-Random tied to a predictor column.
        predictor: hba1c_baseline
        relationship: higher_increases_probability   # or lower_increases_probability
        base_rate: 0.05                    # null probability at predictor median
        max_rate: 0.40                     # null probability at predictor extreme
      Use null_when for status-conditional nulls (dropout_visit is null when not dropped
      out). Use missing_if when missingness is correlated with an observed variable.

    EXACT INCIDENCE CONTROL
      exact_incidence:                     Hit the declared count exactly (not approximately).
        mode: exact
        rate: 0.22                         # exactly floor(n * 0.22) rows become True
        group_by: arm                      # optional: apply per group
        rates: {placebo: 0.15, high_dose: 0.55}  # per-group exact rates
      Use exact_incidence instead of probability on boolean columns when the user states
      a precise rate that must hold in the data, not just on average.

    WITHIN-ENTITY TIME SERIES (longitudinal autocorrelation)
      time_series:                         Re-writes a column to have AR1 autocorrelation
        entity_id: patient_id              within each entity group.
        order_by: visit_number
        model: AR1                         # AR1 | linear_trend | random_walk | mean_reversion
        phi: 0.72                          # autocorrelation coefficient (AR1 only)
        noise_std: 0.30
        anchor_column: hba1c_baseline      # starting value (column in the same table)
        trend:
          slope_mean: -0.08               # mean drift per step
          slope_std: 0.02                 # per-entity slope variability
      Required for any longitudinal dataset (clinical visits, IoT sensors, user sessions).
      Without it every row is independent and the data fails any time-series test.

    CONSTRAINTS  (table-level __constraints__ list)
      {"type": "inequality", "column_a": "visit_date", "operator": ">=",
       "column_b": "enroll_date", "action": "cap"}
         Enforces column_a OP column_b. action: "cap" (snap column_a to column_b)
         or "drop" (remove violating rows). Works on dates and numerics.
      {"type": "col_range", "low_column": "min_price", "column": "price",
       "high_column": "max_price", "action": "cap"}
         Keeps low_column <= column <= high_column.
      {"type": "max_per_group", "group_by": "user_id", "max_count": 3}
         Limits rows per group value.
      {"type": "unique_combination", "columns": ["user_id", "product_id"]}
         No duplicate (col_a, col_b) pairs.
      Use constraints for any business rule that must hold on every row:
      visit_date >= enrollment_date, price > cost, resolution_day > onset_day.

    CORRELATIONS  (table-level __correlations__ list)
      [{"col_a": "bmi", "col_b": "systolic_bp", "r": 0.41}]
      Enforced via Iman-Conover (rank reordering): preserves each column's
      marginal distribution while hitting the declared Pearson r exactly.
      Declare correlations for any pair of measurements that co-vary in the
      real domain (bmi/bp, income/spending, tenure/salary).
      Also supports full matrix syntax:
        __correlations__:
          matrix:
            columns: [hba1c, glucose, bmi]
            values:
              hba1c:   [1.00, 0.65, 0.28]
              glucose: [0.65, 1.00, 0.22]
              bmi:     [0.28, 0.22, 1.00]

    ICC CLUSTER EFFECTS  (parent table __cluster_effect__)
      __cluster_effect__:
        affects_table: visits
        affects_columns:
          hba1c:
            icc: 0.18          # intraclass correlation coefficient
            sd_total: 1.5      # total standard deviation; sd_between = sqrt(icc)*sd_total
          systolic_bp:
            sd_between: 8.0    # supply sd_between directly if preferred
      Applies per-parent-entity random intercepts to the named child columns.
      Required for multi-site or multi-centre designs — without it all sites
      look identical and any ICC statistical test will detect the synthetic origin.
      icc: 0.10-0.30 is typical for clinical measurements across sites.

    STATE MACHINE  (table-level __state_machine__)
      __state_machine__:
        state_column: patient_status
        initial_state: enrolled
        transitions:
          enrolled: {on_treatment: 0.97, screen_failure: 0.03}
          on_treatment: {completed: 0.77, dropout: 0.23}
      Assigns one terminal state to every row by following the Markov chain.
      States with no outgoing transitions are terminal. Use for any process
      with defined states: clinical trial statuses, customer lifecycle,
      order fulfilment stages, support ticket resolution.

    SCHEMA-LEVEL DIRECTIVES  (top-level keys, siblings of the tables)

    __outcome_curves__  Declare aggregate targets the engine hits EXACTLY.
      [{"table": "orders", "column": "amount", "time_column": "order_date",
        "time_unit": "month", "value_mode": "absolute",
        "start_date": "2024-01-01", "avg_transaction_value": 120.0,
        "curve_points": [
          {"month": 1, "target_value": 50000.0},
          {"month": 6, "target_value": 110000.0},
          {"month": 12, "target_value": 200000.0}
        ]}]
      ALWAYS use this when the user states what a number should sum to per
      period: "revenue grows from $50k to $200k", "Q4 spike", "10x growth".
      avg_transaction_value drives row count per period; set it to roughly
      the median row value for that column.

    __rate_curves__  Per-period rate targets for boolean/categorical columns.
      [{"table": "transactions", "column": "is_fraud",
        "time_column": "transaction_date",
        "rate_points": [
          {"period": "2024-01", "rate": 0.02},
          {"period": "2024-Q4", "rate": 0.05}
        ]}]
      Use when fraud rate, churn rate, or conversion rate changes over time.

    __domain__  Domain hint for post-generation validation.
      "__domain__": "clinical_trial"   # or "clinical", "financial", "fintech"
      After generating, call misata.validate_domain(tables, domain="clinical_trial")
      to surface any physiologically or financially impossible values.
      Built-in ranges: HbA1c 4-14 %, BMI 10-80, systolic BP 60-260, age 0-130,
      glucose 2-40, cholesterol 1-20, hemoglobin 3-25 for clinical;
      price ≥ 0, discount 0-1, rate -1 to 100 for financial.


    DESIGN RULES — follow these to get the best result in one pass

    1. Always set __rows__ per table. A fintech schema with customers=2000,
       accounts=4000, transactions=50000 is far better than 1000 everywhere.

    2. Every child table needs a FK column pointing to its parent PK. Without
       it orphan rows are generated and the integrity proof will fail.

    3. Use lognormal for money, file sizes, response times (right-skewed,
       strictly positive). Use normal for measurements (height, score, temp).

    4. Declare correlations for any pair that co-varies in the real domain.
       Generated data with an identity correlation matrix is the clearest
       synthetic-data tell there is.

    5. Use exact_incidence instead of probability when the user states a
       precise rate. "3% fraud" with probability: 0.03 gives ~3% on average;
       exact_incidence gives exactly 3%.

    6. Use rollup (not formula) for any parent column that must reconcile with
       child rows. customers.total_spent generated independently of orders will
       never match; a rollup makes it exact.

    7. Use __outcome_curves__ any time the user mentions a revenue shape, a
       growth trajectory, a seasonal pattern, or a specific period total. It
       is the single feature most likely to be forgotten and most visible when
       absent.

    8. Use profiles when two groups need different distributions. A clinical
       trial where all arms share one HbA1c distribution is statistically wrong
       and the difference will be caught by any summary table.

    9. For longitudinal data (visits, sessions, sensor readings), add
       time_series to the key measurement columns. Independent rows fail every
       autocorrelation test and are visually obvious when plotted.

    10. Add __state_machine__ to any entity that moves through a process. An
        order table with no status progression is not realistic order data.

    Args:
        schema:      Dict of table defs plus optional schema-level directives.
        rows:        Default row count for tables without __rows__.
        seed:        Random seed (same seed → byte-identical output on any machine).
        output_dir:  Where to write CSVs. Omit to use a fresh temp dir.
        sample_rows: Rows per table to include in the JSON response (max 50).
    """
    sample_rows = max(0, min(sample_rows, 50))

    if output_dir:
        out_path = Path(output_dir).expanduser().resolve()
        try:
            out_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return _tool_error(
                exc,
                f"Could not create output directory '{output_dir}'. "
                "Check that the path is writable, or omit output_dir to use a temp directory.",
            )
    else:
        out_path = Path(tempfile.mkdtemp(prefix="misata-mcp-"))

    try:
        config = misata.from_dict_schema(schema, row_count=rows, seed=seed)
        tables = misata.generate_from_schema(config)
    except Exception as exc:
        return _tool_error(
            exc,
            "Check the schema dict format in this tool's description: each table maps "
            "column names to specs like {\"type\": \"integer\", \"primary_key\": true} or "
            "{\"type\": \"float\", \"min\": 1, \"max\": 100}. Foreign keys are "
            "{\"foreign_key\": {\"table\": \"users\", \"column\": \"id\"}}.",
        )

    files: List[Dict[str, Any]] = []
    for name, df in tables.items():
        csv_path = out_path / f"{name}.csv"
        df.to_csv(csv_path, index=False)
        files.append({
            "table": name,
            "path": str(csv_path),
            "rows": len(df),
            "columns": list(df.columns),
            "sample": _df_preview(df, sample_rows) if sample_rows else [],
        })

    # Integrity verification: prove every declared relationship holds, so the
    # agent can report "verified" instead of "should be fine".
    verification: List[Dict[str, Any]] = []
    for rel in config.relationships:
        parent_df = tables.get(rel.parent_table)
        child_df = tables.get(rel.child_table)
        if parent_df is None or child_df is None:
            continue
        if rel.parent_key not in parent_df.columns or rel.child_key not in child_df.columns:
            continue
        child_vals = child_df[rel.child_key].dropna()
        orphans = int((~child_vals.isin(set(parent_df[rel.parent_key]))).sum())
        verification.append({
            "relationship": f"{rel.child_table}.{rel.child_key} → {rel.parent_table}.{rel.parent_key}",
            "intact": orphans == 0,
            "orphans": orphans,
        })

    return {
        "ok": True,
        "output_dir": str(out_path),
        "files": files,
        "total_rows": sum(f["rows"] for f in files),
        "table_count": len(files),
        "seed": seed,
        "integrity": {
            "verified": all(v["intact"] for v in verification) if verification else True,
            "relationships": verification,
        },
    }


@mcp.tool()
def seed_database(
    db_url: str,
    rows: int = 500,
    apply: bool = False,
    truncate: bool = False,
    append: bool = False,
    tables: Optional[List[str]] = None,
    skip_tables: Optional[List[str]] = None,
    seed: int = 42,
) -> Dict[str, Any]:
    """Fill a live Postgres or SQLite database with realistic, connected data,
    read from the database's own schema.

    Reads the tables, columns, and foreign keys directly from the target
    database, generates data that respects them, inserts parents before
    children, then queries the database back to confirm every foreign key
    resolves. No schema file and no ORM are needed: a connection string is
    enough.

    SAFETY — this is the only Misata tool that writes to a user's database:
      * It **plans by default**. With ``apply=False`` (the default) nothing is
        written; you get the table list, insert order, existing row counts,
        and what would be inserted. Show that plan to the user.
      * Only call again with ``apply=True`` after the user has seen the plan
        and agreed. Never pass ``apply=True`` on a first call.
      * If any target table already has rows, the write is refused unless the
        user chooses ``truncate=True`` (wipe and reseed) or ``append=True``
        (keep existing rows, seed only empty tables, and draw foreign keys
        from the rows already there). Never guess between these.
      * ``truncate=True`` DESTROYS existing data. Only use it on a throwaway
        development database and only when the user explicitly asks.

    Args:
        db_url: Connection string, e.g. ``postgresql://localhost/myapp_dev``
            or ``sqlite:///dev.db``.
        rows: Base row count; reference and transaction tables scale from it.
        apply: False (default) plans only. True performs the write.
        truncate: Wipe target tables (children first) before seeding.
        append: Keep populated tables and seed only the empty ones.
        tables: Optional allow-list of table names to seed.
        skip_tables: Tables to leave untouched (migrations, auth, etc.).
        seed: Random seed; the same seed reproduces the same data.

    Returns:
        A plan (``applied: false``) or a result with per-table row counts and
        a per-relationship integrity proof (``integrity.verified``).
    """
    try:
        from misata.db import (
            seed_database as _seed_db,
            table_row_counts,
            verify_referential_integrity,
            _topological_sort,
        )
        from misata.introspect import schema_from_db
    except ImportError as exc:
        return _tool_error(
            exc, 'Install database support with: pip install "misata[db]"'
        )

    if truncate and append:
        return {
            "ok": False,
            "error": "ConflictingOptions",
            "message": "truncate and append are mutually exclusive.",
            "suggestion": "Pick one: truncate wipes and reseeds, append keeps existing rows.",
        }

    try:
        config = schema_from_db(db_url, default_rows=rows, include_tables=tables)
    except Exception as exc:
        return _tool_error(
            exc,
            "Check the connection string and that the database is reachable. "
            'Postgres needs: pip install "misata[db]"',
        )

    if not config.tables:
        return {"ok": False, "error": "NoTables",
                "message": "No tables found in that database.",
                "suggestion": "Create the schema first (run your migrations), then seed."}

    if skip_tables:
        from misata.cli import _prune_config_for_skip
        config, effective_skip = _prune_config_for_skip(config, set(skip_tables))
        cascaded = sorted(effective_skip - set(skip_tables))
        if not config.tables:
            return {"ok": False, "error": "NothingToSeed",
                    "message": "Every table was excluded by skip_tables.",
                    "suggestion": "Skip fewer tables, or use append to reference existing rows."}
    else:
        cascaded = []

    order = _topological_sort(config)
    existing = table_row_counts(db_url, order)
    nonempty = [t for t in order if existing.get(t, 0) > 0]
    row_plan = {t.name: t.row_count for t in config.tables}

    plan = {
        "database": db_url.split("@")[-1],  # never echo credentials back
        "insert_order": order,
        "foreign_keys": len(config.relationships),
        "tables": [
            {
                "name": t,
                "existing_rows": existing.get(t, 0),
                "will_insert": ("keep" if (append and t in nonempty)
                                else row_plan.get(t, 0)),
            }
            for t in order
        ],
        "tables_with_existing_data": nonempty,
        "also_skipped_because_their_parent_was_skipped": cascaded,
    }

    if not apply:
        plan.update({
            "ok": True,
            "applied": False,
            "note": (
                "Plan only, nothing was written. Show this to the user. To "
                "write, call again with apply=true"
                + (
                    f" plus either truncate=true (DESTROYS the {len(nonempty)} "
                    "table(s) that already have rows) or append=true (keeps them)."
                    if nonempty else "."
                )
            ),
        })
        return plan

    if nonempty and not (truncate or append):
        return {
            "ok": False,
            "error": "TablesNotEmpty",
            "message": f"These tables already contain data: {', '.join(nonempty)}.",
            "suggestion": (
                "Ask the user which they want: truncate=true wipes and reseeds "
                "them (destructive), append=true keeps them and seeds only the "
                "empty tables, or skip_tables leaves them alone."
            ),
            "plan": plan,
        }

    config.seed = seed
    try:
        report = _seed_db(
            config, db_url, create=False, truncate=truncate, append=append,
            smart_mode=False, use_llm=False,
        )
        integrity = verify_referential_integrity(config, db_url)
    except Exception as exc:
        return _tool_error(
            exc,
            "The schema was read but the write failed. Check that the "
            "connection has INSERT permission and that column types are supported.",
        )

    return {
        "ok": True,
        "applied": True,
        "mode": "truncate" if truncate else ("append" if append else "fresh"),
        "total_rows": report.total_rows,
        "table_rows": report.table_rows,
        "duration_seconds": round(report.duration_seconds, 3),
        "insert_order": order,
        "integrity": {
            "verified": integrity.verified,
            "total_orphans": integrity.total_orphans,
            "relationships": [
                {"relationship": r.label, "orphans": r.orphans, "intact": r.intact}
                for r in integrity.relationships
            ],
        },
        "note": (
            "Every foreign key was checked against the database itself, not "
            "just in memory."
        ),
    }


@mcp.tool()
def validate_yaml(yaml_text: str) -> Dict[str, Any]:
    """Validate a ``misata.yaml`` document at two levels.

    Runs both checks in sequence:
      1. **Structural** — the published JSON Schema (correct field types,
         required fields, enum values). Catches typos and shape errors.
      2. **Semantic** — ``misata.validate_schema`` (probabilities sum to 1.0,
         every foreign_key has a matching Relationship, no cycles, outcome
         curves reference real columns, etc.). These are the rules that
         would crash generation; the error messages include suggested fixes.

    Use this when an agent has authored or edited a misata.yaml on the
    user's behalf and wants to confirm it parses *and* will actually
    generate before invoking ``generate_dataset``.

    Args:
        yaml_text: The full contents of a misata.yaml file as a string.

    Returns:
        ``{"valid": true}`` if both checks pass; otherwise
        ``{"valid": false, "errors": [...], "stage": "structural"|"semantic"}``
        with the layer that failed first.
    """
    try:
        import yaml
    except ImportError:
        return {"valid": False, "errors": ["PyYAML is not available in this environment"], "stage": "import"}

    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return {
            "valid": False,
            "errors": [
                "jsonschema is not installed. Install with: pip install \"misata[mcp]\""
            ],
            "stage": "import",
        }

    # Stage 0 — YAML parse
    try:
        document = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        return {"valid": False, "errors": [f"YAML parse error: {exc}"], "stage": "yaml"}

    if not isinstance(document, dict):
        return {
            "valid": False,
            "errors": ["Root of misata.yaml must be a mapping"],
            "stage": "yaml",
        }

    # Stage 1 — structural (JSON Schema)
    json_schema = misata.json_schema()
    structural = sorted(
        Draft202012Validator(json_schema).iter_errors(document),
        key=lambda e: list(e.absolute_path),
    )
    if structural:
        return {
            "valid": False,
            "stage": "structural",
            "errors": [
                {"path": list(e.absolute_path), "message": e.message}
                for e in structural[:25]
            ],
            "error_count": len(structural),
        }

    # Stage 2 — semantic (sum-to-1, FK integrity, cycles, …) via load + validate
    # Use a tempfile because load_yaml_schema reads from disk.
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(yaml_text)
            tmp_path = Path(fh.name)
        schema = misata.load_yaml_schema(tmp_path)
        misata.validate_schema(schema)
    except misata.SchemaValidationError as exc:
        return {
            "valid": False,
            "stage": "semantic",
            "errors": [{"message": issue} for issue in exc.issues],
            "error_count": len(exc.issues),
        }
    except Exception as exc:  # noqa: BLE001 - any load error counts as semantic failure
        return {
            "valid": False,
            "stage": "semantic",
            "errors": [{"message": f"{type(exc).__name__}: {exc}"}],
            "error_count": 1,
        }
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    return {"ok": True, "valid": True, "errors": [], "stage": "ok"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the Misata MCP server over stdio.

    Invoked by the ``misata-mcp`` console script. Most users won't call this
    directly — they configure their MCP client (Claude Desktop, Cursor,
    Windsurf, etc.) to launch ``misata-mcp`` and the client manages the process.
    """
    # FastMCP.run() handles signal management, transport setup, and request loop.
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
