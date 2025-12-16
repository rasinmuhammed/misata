"""
Command-line interface for Misata.

Provides easy-to-use commands for generating synthetic data from stories
or configuration files, now with LLM-powered schema generation.
"""

import os
import sys
import time
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table as RichTable

from misata import DataSimulator, SchemaConfig
from misata.codegen import ScriptGenerator
from misata.story_parser import StoryParser

console = Console()


def print_banner():
    """Print the Misata banner."""
    console.print(Panel.fit(
        "[bold purple]🧠 Misata[/bold purple] [dim]- AI-Powered Synthetic Data Engine[/dim]",
        border_style="purple"
    ))


@click.group()
@click.version_option(version="2.0.0")
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
def generate(
    story: Optional[str],
    config: Optional[str],
    output_dir: str,
    rows: int,
    seed: Optional[int],
    use_llm: bool,
    provider: Optional[str],
    model: Optional[str],
    export_script: Optional[str],
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
    if not story and not config:
        console.print("[red]Error: Must provide either --story or --config[/red]")
        sys.exit(1)

    if story and config:
        console.print("[yellow]Warning: Both story and config provided. Using config.[/yellow]")

    if config:
        console.print(f"📄 Loading configuration from: [cyan]{config}[/cyan]")
        import yaml
        with open(config, "r") as f:
            config_dict = yaml.safe_load(f)
        schema_config = SchemaConfig(**config_dict)
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
        generator.generate(export_script)
        console.print(f"[green]✓ Script saved to: {export_script}[/green]")
        return

    # Generate data
    console.print("\n⚙️  Initializing simulator...")
    # Default batch size is 10k, good for CLI
    simulator = DataSimulator(schema_config)

    console.print(f"\n🔧 Generating {len(schema_config.tables)} table(s)...\n")

    start_time = time.time()
    total_rows = 0

    # Prepare export
    import os
    os.makedirs(output_dir, exist_ok=True)
    files_created = set()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TextColumn("{task.completed:,} rows"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating data...", total=None)

        for table_name, batch_df in simulator.generate_all():
            # Write to disk immediately
            output_path = os.path.join(output_dir, f"{table_name}.csv")
            mode = 'a' if table_name in files_created else 'w'
            header = table_name not in files_created

            batch_df.to_csv(output_path, mode=mode, header=header, index=False)
            files_created.add(table_name)

            batch_size = len(batch_df)
            total_rows += batch_size
            progress.update(task, advance=batch_size, description=f"Generating {table_name}...")

    elapsed = time.time() - start_time

    # Display summary
    console.print("\n" + "="*70)
    console.print(simulator.get_summary())
    console.print("="*70)
    console.print(f"\n⏱️  Generation time: [cyan]{elapsed:.2f} seconds[/cyan]")

    # Calculate performance metrics
    rows_per_sec = total_rows / elapsed if elapsed > 0 else 0
    console.print(f"🚀 Performance: [green]{rows_per_sec:,.0f} rows/second[/green]")

    console.print(f"\n💾 Data saved to: [cyan]{output_dir}[/cyan]")
    console.print("\n[bold green]✓ Done![/bold green]")


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
    required=True,
    help="Directory containing CSV files to validate",
)
def validate_cmd(data_dir: str) -> None:
    """
    Validate existing CSV data files.

    Example:

        misata validate --data-dir ./generated_data
    """
    print_banner()

    import pandas as pd
    from misata.validation import validate_data

    console.print(f"🔍 Validating data in: [cyan]{data_dir}[/cyan]\\n")

    # Load all CSVs
    tables = {}
    data_path = Path(data_dir)
    for csv_file in data_path.glob("*.csv"):
        table_name = csv_file.stem
        tables[table_name] = pd.read_csv(csv_file)
        console.print(f"  Loaded {table_name}: {len(tables[table_name]):,} rows")

    if not tables:
        console.print("[yellow]No CSV files found in directory.[/yellow]")
        return

    console.print()
    report = validate_data(tables)
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


if __name__ == "__main__":
    main()

