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
from misata.codegen import ScriptGenerator
from misata.db import load_tables_from_db, seed_database
from misata.quality import check_quality
from misata.recipes import RecipeSpec, RunManifest, load_recipe, save_recipe, utc_now
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

    # Validate inputs
    if not story and not config and not sqlalchemy and not db_url:
        console.print("[red]Error: Must provide --story, --config, --sqlalchemy, or --db-url[/red]")
        sys.exit(1)

    if sum(1 for x in [story, config, sqlalchemy] if x) > 1:
        console.print("[yellow]Warning: Multiple schema sources provided. Using priority: config > sqlalchemy > story.[/yellow]")

    if config:
        console.print(f"📄 Loading configuration from: [cyan]{config}[/cyan]")
        config_dict = _load_yaml_or_json(config)
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

    import uvicorn
    from misata.api import app
    uvicorn.run(app, host=host, port=port)


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


if __name__ == "__main__":
    main()
