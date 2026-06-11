"""
Command-line interface for Misata.

Provides easy-to-use commands for generating synthetic data from stories
or configuration files, now with LLM-powered schema generation.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import click
import numpy as np
import pandas as pd
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table as RichTable

from misata import DataSimulator, SchemaConfig, __version__
from misata.audit import AuditLogger
from misata.yaml_schema import MISATA_YAML_TEMPLATE, load_yaml_schema, save_yaml_schema
from misata.codegen import ScriptGenerator
from misata.db import load_tables_from_db, seed_database
from misata.quality import check_quality
from misata.recipes import RecipeSpec, RunManifest, load_recipe, save_recipe, utc_now
from misata.reporting import build_oracle_report
from misata.schema import ScenarioEvent
from misata.story_parser import StoryParser
from misata.validation import validate_data

console = Console()


def _apply_scenario_file(schema_config: SchemaConfig, scenario_path: str) -> None:
    with open(scenario_path, "r") as f:
        content = f.read()

    try:
        data = yaml.safe_load(content)
    except Exception:
        data = json.loads(content)

    if isinstance(data, dict) and "events" in data:
        events = data["events"]
    else:
        events = data

    if not isinstance(events, list):
        raise ValueError("Scenario file must be a list of events or contain 'events' list.")

    for event in events:
        schema_config.events.append(ScenarioEvent(**event))


def _load_yaml_or_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        data = yaml.safe_load(content)
    except Exception:
        data = json.loads(content)

    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {path}")
    return data


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    def _default(value: Any) -> Any:
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, Path):
            return str(value)
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    path.write_text(json.dumps(payload, indent=2, default=_default), encoding="utf-8")


def _serialize_quality_report(report: Any) -> Dict[str, Any]:
    return {
        "score": report.score,
        "passed": report.passed,
        "summary": report.summary(),
        "stats": report.stats,
        "issues": [
            {
                "severity": issue.severity,
                "category": issue.category,
                "table": issue.table,
                "column": issue.column,
                "message": issue.message,
                "details": issue.details,
            }
            for issue in report.issues
        ],
    }


def _serialize_validation_report(report: Any) -> Dict[str, Any]:
    return {
        "is_clean": report.is_clean,
        "has_errors": report.has_errors,
        "has_warnings": report.has_warnings,
        "tables_checked": report.tables_checked,
        "columns_checked": report.columns_checked,
        "total_rows": report.total_rows,
        "summary": report.summary(),
        "issues": [
            {
                "severity": issue.severity.value,
                "table": issue.table,
                "column": issue.column,
                "message": issue.message,
                "affected_rows": issue.affected_rows,
                "sample_values": issue.sample_values,
            }
            for issue in report.issues
        ],
    }


def _generate_tables_to_csv(
    schema_config: SchemaConfig,
    output_dir: str,
    *,
    smart: bool,
    smart_no_llm: bool,
    batch_size: int,
) -> Dict[str, int]:
    console.print("\n⚙️  Initializing simulator...")
    simulator = DataSimulator(
        schema_config,
        batch_size=batch_size,
        smart_mode=smart,
        use_llm=not smart_no_llm,
    )

    console.print(f"\n🔧 Generating {len(schema_config.tables)} table(s)...\n")

    os.makedirs(output_dir, exist_ok=True)
    files_created = set()
    table_rows: Dict[str, int] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TextColumn("{task.completed:,} rows"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating data...", total=None)

        for table_name, batch_df in simulator.generate_all():
            output_path = os.path.join(output_dir, f"{table_name}.csv")
            mode = "a" if table_name in files_created else "w"
            header = table_name not in files_created

            batch_df.to_csv(output_path, mode=mode, header=header, index=False)
            files_created.add(table_name)

            generated_rows = len(batch_df)
            table_rows[table_name] = table_rows.get(table_name, 0) + generated_rows
            progress.update(task, advance=generated_rows, description=f"Generating {table_name}...")

    console.print("\n" + "=" * 70)
    console.print(simulator.get_summary())
    console.print("=" * 70)
    return table_rows


def _resolve_recipe_schema(recipe: RecipeSpec, rows: int) -> SchemaConfig:
    if recipe.schema_config is not None:
        schema_config = recipe.to_schema_config()
        if schema_config is None:
            raise ValueError("Recipe schema_config could not be parsed.")
        return schema_config

    parser = StoryParser()
    return parser.parse(recipe.story, default_rows=rows)


def print_banner():
    """Print the Misata banner."""
    console.print(Panel.fit(
        "[bold purple]🧠 Misata[/bold purple] [dim]- AI-Powered Synthetic Data Engine[/dim]",
        border_style="purple"
    ))


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """
    Misata - AI-Powered Synthetic Data Engine

    Generate industry-realistic data from natural language stories.
    """
    pass


@main.command("init")
@click.option("--db", type=str, default=None,
              help="Database URL to introspect (e.g., postgresql://localhost/myapp)")
@click.option("--story", "-s", type=str, default=None,
              help='Natural language description (e.g., "A SaaS company with users")')
@click.option("--output", "-o", type=click.Path(), default="misata.yaml",
              help="Output file path (default: misata.yaml)")
@click.option("--rows", "-n", type=int, default=1000,
              help="Default row count per table (default: 1000)")
@click.option("--seed", type=int, default=42, help="Random seed (default: 42)")
@click.option("--force", is_flag=True, default=False,
              help="Overwrite existing file without prompting")
def init(db: Optional[str], story: Optional[str], output: str,
         rows: int, seed: int, force: bool) -> None:
    """Scaffold a misata.yaml schema file in the current directory.

    \b
    Examples:
        misata init                                    # commented template
        misata init --story "A SaaS company"          # from natural language
        misata init --db postgresql://localhost/myapp  # from existing database
        git commit misata.yaml
        misata generate                                # teammates regenerate data
    """
    out_path = Path(output)
    if out_path.exists() and not force:
        console.print(f"[yellow]{output} already exists. Use --force to overwrite.[/yellow]")
        sys.exit(1)

    if db:
        try:
            from misata.introspect import schema_from_db
            console.print(f"Introspecting schema from [cyan]{db}[/cyan] ...")
            schema = schema_from_db(db, default_rows=rows)
            schema.seed = seed
            save_yaml_schema(schema, out_path)
            console.print(f"[green]Detected {len(schema.tables)} table(s) → {output}[/green]")
        except Exception as exc:
            console.print(f"[red]DB introspection failed: {exc}[/red]")
            sys.exit(1)
    elif story:
        try:
            schema = StoryParser().parse(story, default_rows=rows)
            schema.seed = seed
            save_yaml_schema(schema, out_path)
            console.print(f"[green]Parsed {len(schema.tables)} table(s) → {output}[/green]")
        except Exception as exc:
            console.print(f"[red]Story parsing failed: {exc}[/red]")
            sys.exit(1)
    else:
        out_path.write_text(MISATA_YAML_TEMPLATE, encoding="utf-8")
        console.print(f"[green]Template written → {output}[/green]")

    console.print(f"\n  Edit [cyan]{output}[/cyan], then run:")
    console.print("    [bold cyan]misata generate[/bold cyan]")


@main.command()
@click.option(
    "--story",
    "-s",
    type=str,
    help="Natural language description of the data to generate",
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    help="Path to YAML configuration file",
)
@click.option(
    "--sqlalchemy",
    type=str,
    default=None,
    help="SQLAlchemy target for schema (module:Base or module:metadata)",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(),
    default="./generated_data",
    help="Output directory for CSV files (default: ./generated_data)",
)
@click.option(
    "--rows",
    "-n",
    type=int,
    default=10000,
    help="Default number of rows (if not specified in story/config)",
)
@click.option(
    "--seed",
    type=int,
    default=None,
    help="Random seed for reproducibility",
)
@click.option(
    "--use-llm",
    is_flag=True,
    default=False,
    help="Use LLM for intelligent schema generation",
)
@click.option(
    "--provider",
    "-p",
    type=click.Choice(["groq", "openai", "ollama"]),
    default=None,
    help="LLM provider (groq, openai, ollama). Default: MISATA_PROVIDER env or groq",
)
@click.option(
    "--model",
    "-m",
    type=str,
    default=None,
    help="LLM model name (e.g., llama3, gpt-4o-mini)",
)
@click.option(
    "--export-script",
    type=click.Path(),
    default=None,
    help="Export a standalone Python script instead of generating data",
)
@click.option(
    "--scenario",
    type=click.Path(exists=True),
    default=None,
    help="Path to scenario YAML/JSON file to apply",
)
@click.option(
    "--db-url",
    type=str,
    default=None,
    help="Database URL to seed directly (e.g., sqlite:///tmp.db, postgresql://...)",
)
@click.option(
    "--db-create/--no-db-create",
    default=False,
    help="Create tables in the database if missing",
)
@click.option(
    "--db-truncate/--no-db-truncate",
    default=False,
    help="Truncate tables before inserting new data",
)
@click.option(
    "--db-batch-size",
    type=int,
    default=None,
    help="Batch size for DB seeding (defaults to generator batch size)",
)
@click.option(
    "--smart/--no-smart",
    default=False,
    help="Enable smart, domain-aware value generation",
)
@click.option(
    "--smart-no-llm",
    is_flag=True,
    default=False,
    help="Disable LLM for smart value generation (use curated pools only)",
)
@click.option(
    "--locale",
    type=str,
    default=None,
    help=(
        "Locale for names, addresses, phone formats, and salary distributions "
        "(e.g. de_DE, pt_BR, ja_JP, hi_IN). Auto-detected from story when not set."
    ),
)
@click.option(
    "--oracle/--no-oracle",
    default=True,
    help="Write a proof-oriented oracle_report.json with validation, quality, locale, privacy, and fidelity checks.",
)
@click.option(
    "--capsule",
    type=click.Path(exists=True),
    default=None,
    help="Capsule JSON whose vocabularies override built-in pools (see `misata capsule`).",
)
def generate(
    story: Optional[str],
    config: Optional[str],
    sqlalchemy: Optional[str],
    output_dir: str,
    rows: int,
    seed: Optional[int],
    use_llm: bool,
    provider: Optional[str],
    model: Optional[str],
    export_script: Optional[str],
    scenario: Optional[str],
    db_url: Optional[str],
    db_create: bool,
    db_truncate: bool,
    db_batch_size: Optional[int],
    smart: bool,
    smart_no_llm: bool,
    locale: Optional[str],
    oracle: bool,
    capsule: Optional[str],
) -> None:
    """
    Generate synthetic data from a story or configuration file.

    Examples:

        # From natural language story (rule-based)
        misata generate --story "A SaaS company with 50K users, 20% churn in Q3"

        # From story with LLM (requires GROQ_API_KEY)
        misata generate --story "SaaS company with churn" --use-llm

        # From configuration file
        misata generate --config config.yaml --output-dir ./data
    """
    print_banner()

    # Auto-detect misata.yaml when no source is given
    if not story and not config and not sqlalchemy and not db_url:
        if Path("misata.yaml").exists():
            config = "misata.yaml"
            console.print("[dim]Auto-detected misata.yaml in current directory.[/dim]")
        else:
            console.print("[red]Error: Must provide --story, --config, --sqlalchemy, or --db-url[/red]")
            console.print("[dim]Tip: run `misata init` to scaffold a misata.yaml file.[/dim]")
            sys.exit(1)

    if sum(1 for x in [story, config, sqlalchemy] if x) > 1:
        console.print("[yellow]Warning: Multiple schema sources provided. Using priority: config > sqlalchemy > story.[/yellow]")

    if config:
        console.print(f"Loading schema from: [cyan]{config}[/cyan]")
        config_dict = _load_yaml_or_json(config)
        # Route to yaml_schema loader when the file uses the misata.yaml format
        # (has a "tables" dict, not the Pydantic-serialised SchemaConfig list format)
        if isinstance(config_dict.get("tables"), dict):
            schema_config = load_yaml_schema(config, rows=rows, seed=seed)
        else:
            schema_config = SchemaConfig(**config_dict)
    elif sqlalchemy:
        from misata.introspect import load_sqlalchemy_target, schema_from_sqlalchemy

        console.print(f"🔍 Loading SQLAlchemy schema from: [cyan]{sqlalchemy}[/cyan]")
        target = load_sqlalchemy_target(sqlalchemy)
        schema_config = schema_from_sqlalchemy(target, default_rows=rows)
    elif db_url and not story:
        # Auto-introspect schema from database
        from misata.introspect import schema_from_db

        console.print(f"🔍 Introspecting schema from: [cyan]{db_url}[/cyan]")
        schema_config = schema_from_db(db_url, default_rows=rows)
        console.print(f"✅ Found {len(schema_config.tables)} table(s)")
    else:
        console.print(f"📖 Parsing story: [italic]{story}[/italic]\n")

        if use_llm:
            try:
                from misata.llm_parser import LLMSchemaGenerator

                # Determine provider for display
                display_provider = provider or os.environ.get("MISATA_PROVIDER", "groq")
                display_model = model or LLMSchemaGenerator.PROVIDERS.get(display_provider, {}).get("default_model", "")

                console.print(f"🧠 [purple]Using {display_provider.title()} ({display_model}) for intelligent parsing...[/purple]")

                with console.status("[purple]Generating schema with AI...[/purple]"):
                    llm = LLMSchemaGenerator(provider=provider, model=model)
                    schema_config = llm.generate_from_story(story, default_rows=rows)

                console.print("✅ [green]LLM schema generated successfully![/green]")
            except ImportError as e:
                console.print(f"\n[red]❌ {e}[/red]")
                console.print("   Install LLM support with: [cyan]pip install \"misata[llm]\"[/cyan]")
                sys.exit(1)
            except ValueError as e:
                error_msg = str(e)
                if "API key required" in error_msg:
                    console.print(f"\n[red]❌ {error_msg}[/red]")
                    console.print("\n   Options:")
                    console.print("   • [yellow]export GROQ_API_KEY=xxx[/yellow] (free: https://console.groq.com)")
                    console.print("   • [yellow]export OPENAI_API_KEY=xxx[/yellow]")
                    console.print("   • [yellow]--provider ollama[/yellow] (local, no key needed)")
                    sys.exit(1)
                raise
        else:
            # Rule-based parsing (original)
            parser = StoryParser()
            schema_config = parser.parse(story, default_rows=rows)

            if parser.detected_domain:
                console.print(f"✓ Detected domain: [green]{parser.detected_domain}[/green]")
            if parser.scale_params:
                console.print(f"✓ Detected scale: [green]{parser.scale_params}[/green]")
            if parser.temporal_events:
                console.print(f"✓ Detected events: [green]{len(parser.temporal_events)}[/green]")

    # LLM Schema Enrichment: enrich existing schemas with AI intelligence
    if use_llm and (config or sqlalchemy or (db_url and not story)):
        try:
            from misata.llm_parser import LLMSchemaGenerator

            display_provider = provider or os.environ.get("MISATA_PROVIDER", "groq")
            display_model = model or LLMSchemaGenerator.PROVIDERS.get(display_provider, {}).get("default_model", "")

            console.print(f"\n🧠 [purple]Enriching schema with {display_provider.title()} ({display_model})...[/purple]")
            console.print("   Inferring domain, distributions, correlations, and business rules...")

            with console.status("[purple]AI is analyzing your schema...[/purple]"):
                llm = LLMSchemaGenerator(provider=provider, model=model)
                schema_config = llm.enrich_schema(schema_config)

            # Count enrichments
            ref_count = sum(1 for t in schema_config.tables if t.is_reference and t.inline_data)
            constraint_count = sum(len(t.constraints) for t in schema_config.tables)
            console.print(f"✅ [green]Schema enriched![/green]")
            if ref_count:
                console.print(f"   📚 Reference tables with real data: {ref_count}")
            if constraint_count:
                console.print(f"   📏 Business rules inferred: {constraint_count}")
        except ImportError as e:
            console.print(f"\n[red]❌ {e}[/red]")
            console.print("   Install LLM support with: [cyan]pip install \"misata[llm]\"[/cyan]")
            sys.exit(1)
        except ValueError as e:
            error_msg = str(e)
            if "API key required" in error_msg:
                console.print(f"\n[red]❌ {error_msg}[/red]")
                console.print("\n   Options:")
                console.print("   • [yellow]export GROQ_API_KEY=xxx[/yellow] (free: https://console.groq.com)")
                console.print("   • [yellow]export OPENAI_API_KEY=xxx[/yellow]")
                console.print("   • [yellow]--provider ollama[/yellow] (local, no key needed)")
                sys.exit(1)
            raise

    # Apply scenario file if provided
    if scenario:
        _apply_scenario_file(schema_config, scenario)

    # Set seed if provided
    if seed is not None:
        schema_config.seed = seed

    # Attach capsule file: its vocabularies beat built-in pools
    if capsule:
        from misata import _attach_capsule
        _attach_capsule(schema_config, capsule)
        console.print(f"💊 Using capsule: [cyan]{capsule}[/cyan]")

    # Inject locale: --locale flag overrides auto-detected locale from story parser
    _effective_locale = locale
    if not _effective_locale:
        _effective_locale = getattr(
            getattr(schema_config, "realism", None), "locale", None
        )
    if _effective_locale:
        from misata.schema import RealismConfig
        if schema_config.realism is None:
            object.__setattr__(schema_config, "realism", RealismConfig())
        object.__setattr__(schema_config.realism, "locale", _effective_locale)
        console.print(f"   Locale: [cyan]{_effective_locale}[/cyan]")

    # Display schema info
    console.print(f"\n📋 Schema: [bold]{schema_config.name}[/bold]")
    console.print(f"   Tables: {len(schema_config.tables)}")
    console.print(f"   Relationships: {len(schema_config.relationships)}")
    console.print(f"   Events: {len(schema_config.events)}")

    # Export script or generate data
    if export_script:
        console.print("\n📝 Generating standalone script...")
        generator = ScriptGenerator(schema_config)
        generator.generate(
            export_script,
            include_export=db_url is None,
            db_url=db_url,
            db_create=db_create,
            db_truncate=db_truncate,
            smart_mode=smart,
            use_llm=not smart_no_llm,
        )
        console.print(f"[green]✓ Script saved to: {export_script}[/green]")
        return

    if db_url:
        batch_size = db_batch_size if db_batch_size is not None else 10_000
        console.print("\n🗄️  Seeding database...")
        report = seed_database(
            schema_config,
            db_url,
            create=db_create,
            truncate=db_truncate,
            batch_size=batch_size,
            smart_mode=smart,
            use_llm=not smart_no_llm,
        )
        console.print(f"[green]✓ Seeded {report.total_rows:,} rows into {report.dialect}[/green]")
        console.print(f"⏱️  Time: [cyan]{report.duration_seconds:.2f} seconds[/cyan]")
        if oracle:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            tables = load_tables_from_db(db_url, tables=list(report.table_rows.keys()))
            oracle_payload = build_oracle_report(
                tables,
                schema_config,
                seed=schema_config.seed,
                row_counts=report.table_rows,
            )
            oracle_path = output_path / "oracle_report.json"
            _write_json(oracle_path, oracle_payload)
            console.print(f"🔮 Oracle report: [cyan]{oracle_path}[/cyan]")
        return

    # Generate data
    batch_size = db_batch_size if db_batch_size is not None else 10_000
    start_time = time.time()
    table_rows = _generate_tables_to_csv(
        schema_config,
        output_dir,
        smart=smart,
        smart_no_llm=smart_no_llm,
        batch_size=batch_size,
    )

    elapsed = time.time() - start_time

    # Display summary
    console.print(f"\n⏱️  Generation time: [cyan]{elapsed:.2f} seconds[/cyan]")

    # Calculate performance metrics
    total_rows = sum(table_rows.values())
    rows_per_sec = total_rows / elapsed if elapsed > 0 else 0
    console.print(f"🚀 Performance: [green]{rows_per_sec:,.0f} rows/second[/green]")

    console.print(f"\n💾 Data saved to: [cyan]{output_dir}[/cyan]")

    if oracle:
        output_path = Path(output_dir)
        tables = {
            table_name: pd.read_csv(output_path / f"{table_name}.csv")
            for table_name in table_rows
        }
        oracle_payload = build_oracle_report(
            tables,
            schema_config,
            seed=schema_config.seed,
            row_counts=table_rows,
        )
        oracle_path = output_path / "oracle_report.json"
        _write_json(oracle_path, oracle_payload)
        console.print(f"🔮 Oracle report: [cyan]{oracle_path}[/cyan]")

    console.print("\n[bold green]✓ Done![/bold green]")


@main.group()
def recipe() -> None:
    """Create and run reusable Misata recipes."""
    pass


@recipe.command("init")
@click.option("--name", type=str, default="my_recipe", help="Recipe name")
@click.option("--story", type=str, default=None, help="Natural language description for the dataset")
@click.option(
    "--schema-config",
    type=click.Path(exists=True),
    default=None,
    help="Existing schema configuration file to embed",
)
@click.option("--seed", type=int, default=None, help="Random seed for reproducibility")
@click.option(
    "--output-dir",
    type=click.Path(),
    default="./generated_data",
    help="Output directory for generated data and reports",
)
@click.option("--db-url", type=str, default=None, help="Optional database URL to seed on recipe runs")
@click.option("--validation/--no-validation", default=True, help="Run validation checks after generation")
@click.option("--quality/--no-quality", default=True, help="Run quality checks after generation")
@click.option("--audit/--no-audit", default=False, help="Capture audit trail for recipe runs")
@click.option(
    "--output",
    type=click.Path(),
    default="recipe.yaml",
    help="Recipe file to create",
)
def recipe_init(
    name: str,
    story: Optional[str],
    schema_config: Optional[str],
    seed: Optional[int],
    output_dir: str,
    db_url: Optional[str],
    validation: bool,
    quality: bool,
    audit: bool,
    output: str,
) -> None:
    """Create a starter YAML recipe."""
    print_banner()

    schema_payload = _load_yaml_or_json(schema_config) if schema_config else None
    recipe_story = story if story or schema_payload is None else None
    if recipe_story is None and schema_payload is None:
        recipe_story = "Describe your dataset here"

    recipe_spec = RecipeSpec(
        name=name,
        story=recipe_story,
        schema_config=schema_payload,
        seed=seed,
        output_dir=output_dir,
        db_url=db_url,
        validation=validation,
        quality=quality,
        audit=audit,
    )
    recipe_path = save_recipe(recipe_spec, output)

    console.print(f"[green]✓ Recipe saved to: {recipe_path}[/green]")
    console.print(f"   Run it with: [cyan]misata recipe run --config {recipe_path}[/cyan]")


@recipe.command("run")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True),
    required=True,
    help="Path to the YAML recipe file",
)
@click.option(
    "--rows",
    type=int,
    default=10000,
    help="Default rows when the recipe uses story-based parsing",
)
@click.option(
    "--db-create/--no-db-create",
    default=False,
    help="Create tables in the database if missing",
)
@click.option(
    "--db-truncate/--no-db-truncate",
    default=False,
    help="Truncate tables before inserting new data",
)
@click.option(
    "--db-batch-size",
    type=int,
    default=10_000,
    help="Batch size for generation and DB seeding",
)
@click.option(
    "--smart/--no-smart",
    default=False,
    help="Enable smart, domain-aware value generation",
)
@click.option(
    "--smart-no-llm",
    is_flag=True,
    default=False,
    help="Disable LLM for smart value generation (use curated pools only)",
)
def recipe_run(
    config_path: str,
    rows: int,
    db_create: bool,
    db_truncate: bool,
    db_batch_size: int,
    smart: bool,
    smart_no_llm: bool,
) -> None:
    """Run a recipe and write report artifacts."""
    print_banner()

    recipe_spec = load_recipe(config_path)
    output_dir = Path(recipe_spec.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = RunManifest(
        recipe_name=recipe_spec.name,
        misata_version=__version__,
        status="running",
        started_at=utc_now(),
        seed=recipe_spec.seed,
        output_dir=str(output_dir),
        db_url=recipe_spec.db_url,
    )
    manifest_path = output_dir / "run_manifest.json"

    audit_logger: Optional[AuditLogger] = None
    audit_session_id: Optional[str] = None
    started = time.time()
    audit_closed = False

    try:
        schema_config = _resolve_recipe_schema(recipe_spec, rows)
        if recipe_spec.seed is not None:
            schema_config.seed = recipe_spec.seed

        console.print(f"📦 Recipe: [bold]{recipe_spec.name}[/bold]")
        console.print(f"📁 Output: [cyan]{output_dir}[/cyan]")

        if recipe_spec.audit:
            audit_logger = AuditLogger(db_path=str(output_dir / "audit.db"))
            audit_session_id = audit_logger.start_session()
            audit_logger.log(
                "recipe_loaded",
                {
                    "recipe_name": recipe_spec.name,
                    "config_path": str(Path(config_path).resolve()),
                },
            )

        if recipe_spec.db_url:
            console.print("\n🗄️  Seeding database from recipe...")
            report = seed_database(
                schema_config,
                recipe_spec.db_url,
                create=db_create,
                truncate=db_truncate,
                batch_size=db_batch_size,
                smart_mode=smart,
                use_llm=not smart_no_llm,
            )
            table_rows = report.table_rows
            tables = load_tables_from_db(recipe_spec.db_url, tables=list(table_rows.keys()))
            if audit_logger is not None:
                audit_logger.log_data_generation(table_rows, report.total_rows, int(report.duration_seconds * 1000))
        else:
            table_rows = _generate_tables_to_csv(
                schema_config,
                str(output_dir),
                smart=smart,
                smart_no_llm=smart_no_llm,
                batch_size=db_batch_size,
            )
            tables = {
                table_name: pd.read_csv(output_dir / f"{table_name}.csv")
                for table_name in table_rows
            }
            if audit_logger is not None:
                audit_logger.log_data_generation(table_rows, sum(table_rows.values()), int((time.time() - started) * 1000))

        manifest.tables = table_rows
        manifest.total_rows = sum(table_rows.values())

        if recipe_spec.validation:
            validation_report = validate_data(tables, schema_config)
            validation_path = output_dir / "validation_report.json"
            _write_json(validation_path, _serialize_validation_report(validation_report))
            manifest.artifacts["validation_report"] = str(validation_path)
            if audit_logger is not None:
                audit_logger.log_validation(
                    passed=not validation_report.has_errors,
                    score=100.0 if validation_report.is_clean else 75.0,
                    issues_count=len(validation_report.issues),
                )

        if recipe_spec.quality:
            quality_report = check_quality(tables, relationships=schema_config.relationships, schema=schema_config)
            quality_path = output_dir / "quality_report.json"
            _write_json(quality_path, _serialize_quality_report(quality_report))
            manifest.artifacts["quality_report"] = str(quality_path)

        oracle_payload = build_oracle_report(
            tables,
            schema_config,
            seed=schema_config.seed,
            row_counts=table_rows,
            validation_report=validation_report if recipe_spec.validation else None,
            quality_report=quality_report if recipe_spec.quality else None,
        )
        oracle_path = output_dir / "oracle_report.json"
        _write_json(oracle_path, oracle_payload)
        manifest.artifacts["oracle_report"] = str(oracle_path)

        if audit_logger is not None and audit_session_id is not None:
            audit_logger.end_session(audit_session_id)
            audit_closed = True
            audit_summary = audit_logger.get_session_summary(audit_session_id)
            audit_path = output_dir / "audit_report.json"
            _write_json(audit_path, audit_summary)
            manifest.artifacts["audit_report"] = str(audit_path)
            manifest.artifacts["audit_db"] = str(output_dir / "audit.db")

        manifest.status = "success"
        manifest.completed_at = utc_now()
        manifest.artifacts["run_manifest"] = str(manifest_path)
        _write_json(manifest_path, manifest.model_dump())

        console.print(f"[green]✓ Recipe run completed in {time.time() - started:.2f}s[/green]")
        console.print(f"   Manifest: [cyan]{manifest_path}[/cyan]")
        for artifact_name, artifact_path in manifest.artifacts.items():
            if artifact_name == "run_manifest":
                continue
            console.print(f"   {artifact_name}: [cyan]{artifact_path}[/cyan]")

    except Exception as exc:
        manifest.status = "failed"
        manifest.completed_at = utc_now()
        manifest.error = str(exc)
        manifest.artifacts["run_manifest"] = str(manifest_path)
        _write_json(manifest_path, manifest.model_dump())
        raise
    finally:
        if audit_logger is not None and audit_session_id is not None and not audit_closed:
            audit_logger.end_session(audit_session_id)


@main.command()
@click.argument("description")
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(),
    default="./generated_data",
    help="Output directory for CSV files",
)
def graph(description: str, output_dir: str) -> None:
    """
    REVERSE ENGINEERING: Generate data from a chart description.

    Describe your desired chart pattern and get matching data.

    Example:

        misata graph "Monthly revenue from $100K to $1M over 2 years, with Q2 dips"
    """
    print_banner()

    try:
        from misata.llm_parser import LLMSchemaGenerator

        console.print(f"📊 Graph description: [italic]{description}[/italic]")
        console.print("\n🧠 [purple]Using LLM to reverse-engineer schema...[/purple]")

        with console.status("[purple]Generating schema from chart description...[/purple]"):
            llm = LLMSchemaGenerator()
            schema_config = llm.generate_from_graph(description)

        console.print("✅ [green]Schema generated![/green]")
        console.print(f"\n📋 Schema: [bold]{schema_config.name}[/bold]")

        # Generate data
        simulator = DataSimulator(schema_config)
        console.print("\n🔧 Generating data...")

        start_time = time.time()

        import os
        os.makedirs(output_dir, exist_ok=True)
        files_created = set()
        total_rows = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Generating...", total=None)
            for table_name, batch_df in simulator.generate_all():
                output_path = os.path.join(output_dir, f"{table_name}.csv")
                mode = 'a' if table_name in files_created else 'w'
                header = table_name not in files_created
                batch_df.to_csv(output_path, mode=mode, header=header, index=False)
                files_created.add(table_name)

                total_rows += len(batch_df)
                progress.update(task, advance=len(batch_df))

        elapsed = time.time() - start_time

        console.print(simulator.get_summary())
        console.print(f"\n⏱️  Generation time: [cyan]{elapsed:.2f}s[/cyan]")
        console.print(f"\n[bold green]✓ Data exported to {output_dir}[/bold green]")

    except ValueError as e:
        if "GROQ_API_KEY" in str(e):
            console.print("\n[red]❌ Groq API key required for graph mode.[/red]")
            console.print("   Set your API key: [yellow]export GROQ_API_KEY=your_key[/yellow]")
            console.print("   Get a free key: [cyan]https://console.groq.com[/cyan]")
            sys.exit(1)
        raise


@main.command()
@click.argument("story")
@click.option(
    "--rows",
    "-n",
    type=int,
    default=10000,
    help="Default number of rows",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="config.yaml",
    help="Output YAML configuration file",
)
@click.option(
    "--use-llm",
    is_flag=True,
    default=False,
    help="Use LLM for intelligent parsing",
)
def parse(story: str, rows: int, output: str, use_llm: bool) -> None:
    """
    Parse a story and output the generated configuration.

    Useful for reviewing and editing the configuration before generation.

    Example:

        misata parse "SaaS company with 50K users" --output saas_config.yaml
    """
    print_banner()
    console.print(f"Story: [italic]{story}[/italic]\n")

    if use_llm:
        try:
            from misata.llm_parser import LLMSchemaGenerator

            console.print("🧠 [purple]Using LLM for parsing...[/purple]")
            with console.status("[purple]Generating with AI...[/purple]"):
                llm = LLMSchemaGenerator()
                schema_config = llm.generate_from_story(story, default_rows=rows)
        except ImportError as e:
            console.print(f"\n[red]❌ {e}[/red]")
            console.print("   Falling back to rule-based parsing.")
            console.print("   Install LLM support with: [cyan]pip install \"misata[llm]\"[/cyan]")
            parser = StoryParser()
            schema_config = parser.parse(story, default_rows=rows)
        except ValueError as e:
            if "GROQ_API_KEY" in str(e):
                console.print("\n[red]❌ Groq API key required.[/red]")
                console.print("   Falling back to rule-based parsing...")
                parser = StoryParser()
                schema_config = parser.parse(story, default_rows=rows)
            else:
                raise
    else:
        parser = StoryParser()
        schema_config = parser.parse(story, default_rows=rows)

    # Display summary
    console.print("[bold]Generated Configuration:[/bold]")
    console.print(f"  Name: {schema_config.name}")
    console.print(f"  Tables: {len(schema_config.tables)}")
    console.print(f"  Relationships: {len(schema_config.relationships)}")
    console.print(f"  Events: {len(schema_config.events)}")

    # Export to YAML
    generator = ScriptGenerator(schema_config)
    generator.generate_yaml_config(output)

    console.print(f"\n[green]✓ Configuration saved to: {output}[/green]")
    console.print("  Review and edit as needed, then run:")
    console.print(f"    [cyan]misata generate --config {output}[/cyan]")


@main.command()
@click.option("--port", "-p", type=int, default=8000, help="Port to run the API server")
@click.option("--host", "-h", type=str, default="0.0.0.0", help="Host to bind to")
def serve(port: int, host: str) -> None:
    """
    Start the Misata API server for the web UI.

    Example:

        misata serve --port 8000
    """
    print_banner()
    console.print("\n🌐 Starting Misata API server...")
    console.print(f"   Host: [cyan]{host}[/cyan]")
    console.print(f"   Port: [cyan]{port}[/cyan]")
    console.print(f"\n📝 API Docs: [cyan]http://localhost:{port}/docs[/cyan]")
    console.print("🎨 Web UI: [cyan]http://localhost:3000[/cyan] (run 'npm run dev' in /web)")
    console.print("\nPress [bold]Ctrl+C[/bold] to stop.\n")

    try:
        import uvicorn
        from misata.api import app
    except ImportError as e:
        console.print(f"[red]❌ {e}[/red]")
        console.print("Install API support with: [cyan]pip install \"misata[api]\"[/cyan]")
        sys.exit(1)
    uvicorn.run(app, host=host, port=port)


@main.command()
@click.argument("source", type=click.Path(exists=True))
@click.option("--rows", "-n", type=int, default=None,
              help="Rows to generate (default: same as source file)")
@click.option("--output", "-o", type=click.Path(), default="./synthetic",
              help="Output directory for CSV files (default: ./synthetic)")
@click.option("--seed", type=int, default=None, help="Random seed")
def mimic(source: str, rows: Optional[int], output: str, seed: Optional[int]) -> None:
    """
    Generate a privacy-safe synthetic twin of a CSV file.

    Misata profiles every column's distribution, cardinality, and semantic
    type, then produces a fresh dataset that matches the structure without
    reusing any real values.

    \b
    Examples:

        misata mimic customers.csv
        misata mimic orders.csv --rows 100000 --output ./synthetic
        misata mimic data.csv --seed 42
    """
    print_banner()
    from misata.profiler import mimic as _mimic

    console.print(f"\n[bold]Profiling:[/bold] [cyan]{source}[/cyan]")
    import pandas as pd
    df = pd.read_csv(source)
    console.print(f"   Source: {len(df):,} rows × {len(df.columns)} columns")

    with console.status("Fitting distributions and generating synthetic twin..."):
        from pathlib import Path as _Path
        table_name = _Path(source).stem
        tables = _mimic(df, rows=rows, seed=seed, table_name=table_name)

    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, tdf in tables.items():
        out_path = out_dir / f"{name}.csv"
        tdf.to_csv(out_path, index=False)
        console.print(f"   [green]✓[/green] {name}: {len(tdf):,} rows → {out_path}")

    console.print(f"\n[green]Done.[/green] Synthetic data written to [cyan]{output}[/cyan]")


@main.command()
def examples() -> None:
    """
    Show example stories and usage patterns.
    """
    print_banner()

    examples_table = RichTable(show_header=True, header_style="bold purple")
    examples_table.add_column("Scenario", style="cyan", width=30)
    examples_table.add_column("Command", style="green", width=50)

    examples_table.add_row(
        "SaaS with churn (rule-based)",
        'misata generate -s "SaaS with 50K users, 20% churn in Q3"',
    )
    examples_table.add_row(
        "SaaS with LLM",
        'misata generate -s "SaaS with churn patterns" --use-llm',
    )
    examples_table.add_row(
        "E-commerce (LLM)",
        'misata generate -s "E-commerce with 100K orders" --use-llm',
    )
    examples_table.add_row(
        "Pharma services",
        'misata generate -s "Pharma with 500 projects, 50K timesheets"',
    )
    examples_table.add_row(
        "Graph reverse engineering",
        'misata graph "Revenue from $100K to $1M over 2 years"',
    )
    examples_table.add_row(
        "Quick template",
        'misata template saas --users 10000',
    )
    examples_table.add_row(
        "Start web UI",
        'misata serve --port 8000',
    )

    console.print(examples_table)

    console.print("\n[bold]Story Syntax Tips:[/bold]")
    console.print("  • Mention numbers: '50K users', '1M transactions'")
    console.print("  • Specify domain: 'SaaS', 'e-commerce', 'pharma'")
    console.print("  • Add events: 'growth', 'churn', 'crash in Q3'")
    console.print("  • Be specific: '20% churn in Q3 2023'")

    console.print("\n[bold]LLM Mode (--use-llm):[/bold]")
    console.print("  Requires GROQ_API_KEY environment variable")
    console.print("  Get free key: [cyan]https://console.groq.com[/cyan]")

    console.print("\n[bold]Industry Templates:[/bold]")
    console.print("  Available: saas, ecommerce, fitness, healthcare")
    console.print("  Example: [cyan]misata template <name> [OPTIONS][/cyan]")


@main.command()
@click.argument("template_name")
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(),
    default="./generated_data",
    help="Output directory for CSV files",
)
@click.option(
    "--scale",
    "-s",
    type=float,
    default=1.0,
    help="Row count multiplier (e.g., 0.1 for 10%, 2.0 for 2x)",
)
@click.option(
    "--validate/--no-validate",
    default=True,
    help="Run post-generation validation",
)
def template(template_name: str, output_dir: str, scale: float, validate: bool) -> None:
    """
    Generate data from an industry template.

    Available templates: saas, ecommerce, fitness, healthcare

    Examples:

        misata template saas
        misata template ecommerce --scale 0.5
        misata template fitness --output-dir ./fitness_data
    """
    print_banner()

    try:
        from misata.templates import template_to_schema, list_templates

        available = list_templates()
        if template_name not in available:
            console.print(f"[red]Error: Unknown template '{template_name}'[/red]")
            console.print(f"Available templates: [cyan]{', '.join(available)}[/cyan]")
            return

        console.print(f"📋 Loading template: [bold purple]{template_name}[/bold purple]")
        if scale != 1.0:
            console.print(f"   Scale: {scale}x")

        schema_config = template_to_schema(template_name, row_multiplier=scale)

        console.print(f"\n📊 Schema: [bold]{schema_config.name}[/bold]")
        console.print(f"   Tables: {len(schema_config.tables)}")
        console.print(f"   Relationships: {len(schema_config.relationships)}")

        # Count reference vs transactional tables
        ref_tables = sum(1 for t in schema_config.tables if t.is_reference)
        trans_tables = len(schema_config.tables) - ref_tables
        console.print(f"   Reference tables: {ref_tables}")
        console.print(f"   Transactional tables: {trans_tables}")

        # Generate data
        console.print("\n⚙️  Generating data...")
        simulator = DataSimulator(schema_config)

        start_time = time.time()

        import os
        os.makedirs(output_dir, exist_ok=True)
        files_created = set()
        total_rows = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TextColumn("{task.completed:,} rows"),
            console=console,
        ) as progress:
            task = progress.add_task("Generating...", total=None)

            for table_name, batch_df in simulator.generate_all():
                output_path = os.path.join(output_dir, f"{table_name}.csv")
                mode = 'a' if table_name in files_created else 'w'
                header = table_name not in files_created

                batch_df.to_csv(output_path, mode=mode, header=header, index=False)
                files_created.add(table_name)

                total_rows += len(batch_df)
                progress.update(task, advance=len(batch_df), description=f"Generating {table_name}...")

        elapsed = time.time() - start_time

        console.print(simulator.get_summary())
        console.print(f"\n⏱️  Generation time: [cyan]{elapsed:.2f}s[/cyan]")
        console.print(f"\n[bold green]✓ Data exported to {output_dir}[/bold green]")

        # Run validation if enabled
        if validate:
            console.print("\n🔍 Running validation on exported files...")
            try:
                # Validate by reading back files (or sample)
                # For now, let's read the full files, assuming they fit in memory for small template demos
                # In production, validation should support streaming or sampling
                import pandas as pd
                from pathlib import Path
                from misata.validation import validate_data

                tables = {}
                data_path = Path(output_dir)
                for csv_file in data_path.glob("*.csv"):
                    # Basic check if it's one of ours
                    if csv_file.stem in [t.name for t in schema_config.tables]:
                         # Warning: reading potentially large files
                         # TODO: implement scalable validation
                         tables[csv_file.stem] = pd.read_csv(csv_file)

                report = validate_data(tables, schema_config)

                if report.is_clean:
                    console.print("[green]✅ All validations passed![/green]")
                else:
                    console.print(report.summary())
            except Exception as e:
                console.print(f"[yellow]⚠️ Validation failed (memory issue or other): {e}[/yellow]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@main.command()
@click.option(
    "--data-dir",
    "-d",
    type=click.Path(exists=True),
    required=False,
    help="Directory containing CSV files to validate",
)
@click.option(
    "--db-url",
    type=str,
    default=None,
    help="Database URL to validate directly",
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    required=False,
    help="Optional schema config for relationship validation",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Optional per-table row limit when validating a database",
)
def validate_cmd(data_dir: Optional[str], db_url: Optional[str], config: Optional[str], limit: Optional[int]) -> None:
    """
    Validate existing CSV data files.

    Example:

        misata validate --data-dir ./generated_data
        misata validate --db-url sqlite:///./misata.db --config schema.yaml
    """
    print_banner()

    import pandas as pd
    from misata.validation import validate_data

    if not data_dir and not db_url:
        console.print("[red]Error: Provide --data-dir or --db-url[/red]")
        return

    schema_config = None
    if config:
        import yaml
        with open(config, "r") as f:
            config_dict = yaml.safe_load(f)
        schema_config = SchemaConfig(**config_dict)

    # Load all CSVs
    tables = {}
    if data_dir:
        console.print(f"🔍 Validating data in: [cyan]{data_dir}[/cyan]\\n")
        data_path = Path(data_dir)
        for csv_file in data_path.glob("*.csv"):
            table_name = csv_file.stem
            tables[table_name] = pd.read_csv(csv_file)
            console.print(f"  Loaded {table_name}: {len(tables[table_name]):,} rows")
    else:
        from misata.db import load_tables_from_db
        console.print(f"🔍 Validating data in: [cyan]{db_url}[/cyan]\\n")
        tables = load_tables_from_db(db_url, limit=limit)
        for name, df in tables.items():
            console.print(f"  Loaded {name}: {len(df):,} rows")

    if not tables:
        console.print("[yellow]No CSV files found in directory.[/yellow]")
        return

    console.print()
    report = validate_data(tables, schema_config)
    console.print(report.summary())


@main.command("schema")
@click.option("--db-url", type=str, default=None, help="Database URL to introspect")
@click.option("--sqlalchemy", type=str, default=None, help="SQLAlchemy target module:object")
@click.option("--output", "-o", type=click.Path(), required=True, help="Output YAML file")
@click.option("--rows", "-n", type=int, default=1000, help="Default row count per table")
def schema_cmd(db_url: Optional[str], sqlalchemy: Optional[str], output: str, rows: int) -> None:
    """
    Generate a Misata schema from a database or SQLAlchemy models.
    """
    print_banner()

    if not db_url and not sqlalchemy:
        console.print("[red]Error: Provide --db-url or --sqlalchemy[/red]")
        return

    if db_url and sqlalchemy:
        console.print("[yellow]Warning: Both provided. Using --db-url.[/yellow]")

    if db_url:
        from misata.introspect import schema_from_db
        schema_config = schema_from_db(db_url, default_rows=rows)
    else:
        from misata.introspect import load_sqlalchemy_target, schema_from_sqlalchemy
        target = load_sqlalchemy_target(sqlalchemy)
        schema_config = schema_from_sqlalchemy(target, default_rows=rows)

    generator = ScriptGenerator(schema_config)
    generator.generate_yaml_config(output)
    console.print(f"[green]✓ Schema saved to: {output}[/green]")


@main.command("quality")
@click.option(
    "--data-dir",
    "-d",
    type=click.Path(exists=True),
    required=False,
    help="Directory containing CSV files to analyze",
)
@click.option(
    "--db-url",
    type=str,
    default=None,
    help="Database URL to analyze directly",
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    required=False,
    help="Optional schema config for relationship checks",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Optional per-table row limit when analyzing a database",
)
def quality_cmd(data_dir: Optional[str], db_url: Optional[str], config: Optional[str], limit: Optional[int]) -> None:
    """
    Run data quality checks on CSV files or a database.
    """
    print_banner()

    if not data_dir and not db_url:
        console.print("[red]Error: Provide --data-dir or --db-url[/red]")
        return

    schema_config = None
    if config:
        import yaml
        with open(config, "r") as f:
            config_dict = yaml.safe_load(f)
        schema_config = SchemaConfig(**config_dict)

    import pandas as pd
    from misata.quality import DataQualityChecker

    if data_dir:
        tables = {}
        data_path = Path(data_dir)
        for csv_file in data_path.glob("*.csv"):
            table_name = csv_file.stem
            tables[table_name] = pd.read_csv(csv_file)
            console.print(f"  Loaded {table_name}: {len(tables[table_name]):,} rows")
    else:
        from misata.db import load_tables_from_db
        tables = load_tables_from_db(db_url, limit=limit)
        for name, df in tables.items():
            console.print(f"  Loaded {name}: {len(df):,} rows")

    checker = DataQualityChecker()
    report = checker.check_all(tables, schema_config.relationships if schema_config else [])
    console.print(report.summary())


@main.command()
def templates_list() -> None:
    """
    List available industry templates.
    """
    print_banner()

    from misata.templates import TEMPLATES

    console.print("[bold]Available Industry Templates:[/bold]\\n")

    template_table = RichTable(show_header=True, header_style="bold purple")
    template_table.add_column("Template", style="cyan")
    template_table.add_column("Description")
    template_table.add_column("Tables", justify="right")

    for name, template in TEMPLATES.items():
        table_count = len(template["tables"])
        template_table.add_row(name, template["description"], str(table_count))

    console.print(template_table)
    console.print("\\nUsage: [cyan]misata template <name> [OPTIONS][/cyan]")


@main.command()
@click.option("--port", "-p", type=int, default=8501, help="Port to run Studio on")
@click.option("--host", "-h", type=str, default="localhost", help="Host to bind to")
@click.option("--no-browser", is_flag=True, help="Don't open browser automatically")
def studio(port: int, host: str, no_browser: bool) -> None:
    """
    Launch Misata Studio - the visual schema designer.

    Features:
    - Upload CSV to reverse-engineer schema
    - Visual distribution curve editor (Reverse Graph)
    - Generate millions of matching rows

    Example:

        misata studio
        misata studio --port 8080
    """
    print_banner()
    console.print("\n🎨 [bold purple]Launching Misata Studio...[/bold purple]")
    console.print(f"   URL: [cyan]http://{host}:{port}[/cyan]")
    console.print("\nPress [bold]Ctrl+C[/bold] to stop.\n")

    try:
        from misata.studio import launch
        launch(port=port, host=host, open_browser=not no_browser)
    except ImportError:
        console.print("[red]Error: Misata Studio requires additional dependencies.[/red]")
        console.print("Install with: [cyan]pip install misata[studio][/cyan]")


@main.command("validate")
@click.argument("csv_file", type=click.Path(exists=True))
@click.option("--schema",  "-s", type=click.Path(exists=True), default=None,
              help="misata.yaml (or JSON) schema to check conformance against.")
@click.option("--story",   type=str, default=None,
              help="Plain-English story — parsed to a schema for conformance checking.")
@click.option("--table",   type=str, default=None,
              help="Table name to look up in the schema (defaults to filename stem).")
def validate_cmd(csv_file: str, schema: Optional[str], story: Optional[str], table: Optional[str]) -> None:
    """Profile a CSV file and optionally check it against a schema.

    Examples:

        misata validate customers.csv

        misata validate orders.csv --schema misata.yaml

        misata validate orders.csv --story "A SaaS company with orders table"
    """
    print_banner()
    from pathlib import Path
    from misata.validation import validate_csv

    console.print(f"[bold]Validating:[/bold] [cyan]{csv_file}[/cyan]")

    schema_config = None
    if schema:
        try:
            schema_config = load_yaml_schema(schema)
            console.print(f"[dim]Schema loaded from {schema}[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning: could not load schema: {e}[/yellow]")

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as progress:
        progress.add_task("Profiling …", total=None)
        report = validate_csv(csv_file, schema=schema_config, story=story, table_name=table)

    # Print rich table
    tbl = RichTable(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
    tbl.add_column("Column",        style="bold", min_width=20)
    tbl.add_column("Type",          style="dim")
    tbl.add_column("Nulls",         justify="right")
    tbl.add_column("Range / Values")
    tbl.add_column("Notes",         style="dim")

    for c in report.columns:
        tbl.add_row(c["name"], c["type"], c["nulls"], c["range"], c["notes"])

    console.print()
    console.print(tbl)
    console.print()

    colour = "green" if report.score >= 90 else "yellow" if report.score >= 70 else "red"
    console.print(f"  Quality score: [{colour}]{report.score}/100[/{colour}]")

    if report.issues:
        console.print(f"  [yellow]{len(report.issues)} issue(s):[/yellow]")
        for issue in report.issues:
            console.print(f"    [yellow]·[/yellow] {issue}")
    else:
        console.print("  [green]No issues found.[/green]")
    console.print()


@main.command("dbt-seed")
@click.option("--story", "-s", type=str, default=None,
              help="Plain-English story to generate data from.")
@click.option("--config", "-c", type=click.Path(exists=True), default=None,
              help="misata.yaml schema file.")
@click.option("--seeds-dir", type=click.Path(), default="seeds",
              help="dbt seeds directory (default: seeds/).")
@click.option("--rows", "-n", type=int, default=1000,
              help="Row count for the primary table (default: 1000).")
@click.option("--seed", type=int, default=42,
              help="Random seed for reproducibility (default: 42).")
@click.option("--force", is_flag=True, default=False,
              help="Overwrite existing seed CSV files.")
def dbt_seed_cmd(
    story: Optional[str],
    config: Optional[str],
    seeds_dir: str,
    rows: int,
    seed: int,
    force: bool,
) -> None:
    """Generate synthetic data and write CSV files into a dbt seeds directory.

    Generates one CSV per table and writes them to the specified seeds directory.
    Run `dbt seed` afterwards to load them into your data warehouse.

    Examples:

        misata dbt-seed --story "A SaaS company with 1k users" --seeds-dir seeds/

        misata dbt-seed --config misata.yaml --rows 5000 --seeds-dir dbt/seeds/

        misata dbt-seed -s "A fintech with fraud data" -n 2000 --force
    """
    print_banner()
    from pathlib import Path

    seeds_path = Path(seeds_dir)
    seeds_path.mkdir(parents=True, exist_ok=True)

    # Build schema
    if config:
        schema_config = load_yaml_schema(config, rows=rows, seed=seed)
        console.print(f"[dim]Schema loaded from {config}[/dim]")
    elif story:
        from misata.story_parser import StoryParser
        schema_config = StoryParser().parse(story, default_rows=rows)
        schema_config.seed = seed
        console.print(f"[dim]Parsed domain:[/dim] [cyan]{schema_config.domain or 'generic'}[/cyan]")
    else:
        console.print("[red]Error:[/red] provide --story or --config")
        raise SystemExit(1)

    # Generate
    from misata.simulator import DataSimulator
    import pandas as pd

    sim = DataSimulator(schema_config)
    tables: dict = {}
    for name, batch in sim.generate_all():
        if name in tables:
            tables[name] = pd.concat([tables[name], batch], ignore_index=True)
        else:
            tables[name] = batch

    # Write CSVs
    written = []
    skipped = []
    for table_name, df in tables.items():
        dest = seeds_path / f"{table_name}.csv"
        if dest.exists() and not force:
            skipped.append(table_name)
            continue
        df.to_csv(dest, index=False)
        written.append((table_name, len(df), str(dest)))

    for table_name, row_count, path in written:
        console.print(
            f"[green]✓[/green] [bold]{table_name}[/bold] — "
            f"{row_count:,} rows → [cyan]{path}[/cyan]"
        )
    for table_name in skipped:
        console.print(
            f"[yellow]⚠[/yellow] [bold]{table_name}[/bold] — "
            f"skipped (file exists, use --force to overwrite)"
        )

    if written:
        console.print(
            f"\n[dim]Run [bold]dbt seed[/bold] to load {len(written)} table(s) "
            f"into your warehouse.[/dim]"
        )


@main.group("capsule")
def capsule_group() -> None:
    """Create, inspect, and use domain vocabulary capsules.

    A capsule is one shareable JSON file of domain vocabularies. Mine one
    from example CSVs (no LLM needed), or generate one with an LLM once and
    use it deterministically forever:

        misata capsule create --domain veterinary --from-csv ./samples/
        misata generate --story "a vet clinic..." --capsule veterinary.capsule.json
    """


@capsule_group.command("create")
@click.option("--domain", required=True, help="Domain name for the capsule (e.g. veterinary).")
@click.option("--from-csv", "csv_path", type=click.Path(exists=True), default=None,
              help="CSV file or directory of CSVs to mine vocabularies from (no LLM).")
@click.option("--vocab", "vocab_names", multiple=True,
              help="Vocabulary names to generate via LLM/curated pools (repeatable).")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output path (default: <domain>.capsule.json).")
def capsule_create(domain: str, csv_path: str, vocab_names: tuple, output: str) -> None:
    """Create a capsule from example CSVs and/or named vocabularies."""
    from misata.capsules import (
        capsule_from_dataframes,
        capsule_from_llm,
        merge_into,
        save_capsule,
    )
    from misata.domain_capsule import DomainCapsule

    capsule = DomainCapsule(domain=domain)
    if csv_path:
        path = Path(csv_path)
        files = sorted(path.glob("*.csv")) if path.is_dir() else [path]
        frames = {f.stem: pd.read_csv(f) for f in files}
        capsule = merge_into(capsule, capsule_from_dataframes(domain, frames))
    if vocab_names:
        capsule = merge_into(capsule, capsule_from_llm(domain, list(vocab_names)))
    if not capsule.vocabularies:
        console.print("[red]No vocabularies produced — pass --from-csv and/or --vocab.[/red]")
        sys.exit(1)

    out = Path(output) if output else Path(f"{domain}.capsule.json")
    save_capsule(capsule, out)
    console.print(f"[green]✓[/green] Capsule written to [cyan]{out}[/cyan]")
    for name, values in sorted(capsule.vocabularies.items()):
        console.print(f"  [bold]{name}[/bold]: {len(values)} values")


@capsule_group.command("show")
@click.argument("capsule_path", type=click.Path(exists=True))
def capsule_show(capsule_path: str) -> None:
    """Summarise a capsule file: vocabularies, sizes, provenance."""
    from misata.capsules import load_capsule

    capsule = load_capsule(capsule_path)
    console.print(f"[bold]Domain:[/bold] {capsule.domain}   [bold]Locale:[/bold] {capsule.locale}")
    for name, values in sorted(capsule.vocabularies.items()):
        provs = capsule.provenance.get(name, [])
        source = provs[0].source_name if provs else "unknown"
        preview = ", ".join(map(str, values[:4]))
        console.print(f"  [bold]{name}[/bold] ({len(values)} values, from {source}): {preview}…")


if __name__ == "__main__":
    main()
