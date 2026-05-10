"""Misata MCP server.

Thin protocol shim that exposes Misata's public API to AI agents over
the Model Context Protocol. The server runs over stdio and registers
five tools — ``list_domains``, ``preview_story``, ``inspect_schema``,
``generate_dataset``, ``validate_yaml`` — that map onto the existing
:mod:`misata` functions.

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


mcp = FastMCP("misata")


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
