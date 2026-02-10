"""
Code generation module for creating standalone Python scripts.

Generates executable Python scripts from SchemaConfig that can be
run independently to produce synthetic data.
"""

import json
from pathlib import Path

from misata.schema import SchemaConfig


class ScriptGenerator:
    """
    Generates standalone Python scripts for data generation.

    The generated scripts are self-contained and can be executed
    without the Misata library installed.
    """

    def __init__(self, config: SchemaConfig):
        """
        Initialize the script generator.

        Args:
            config: Schema configuration to generate script from
        """
        self.config = config

    def _generate_imports(self, include_db: bool = False) -> str:
        """Generate import statements."""
        base = """import os
from misata import DataSimulator, SchemaConfig
"""
        if include_db:
            base += "from misata.db import seed_database\n"
        return base

    def _generate_config_dict(self) -> str:
        """Generate the configuration as a Python dictionary."""
        config_dict = self.config.model_dump()
        return f"CONFIG = {json.dumps(config_dict, indent=2)}"

    def _generate_simulator_class(self) -> str:
        """Generate the DataSimulator class code."""
        # Read the simulator.py file and extract the class
        simulator_path = Path(__file__).parent / "simulator.py"
        with open(simulator_path, "r") as f:
            content = f.read()

        # Extract just the class definition (simplified - in production use AST)
        # For now, include the entire simulator module
        return content.replace("from misata.schema import", "# from misata.schema import")

    def generate(
        self,
        output_path: str,
        include_export: bool = True,
        db_url: str | None = None,
        db_create: bool = False,
        db_truncate: bool = False,
        smart_mode: bool = False,
        use_llm: bool = True,
    ) -> None:
        """
        Generate a standalone Python script.

        Args:
            output_path: Path where the script should be saved
            include_export: Whether to include CSV export code at the end
        """
        script_parts = []

        # Header comment
        script_parts.append('"""')
        script_parts.append("Auto-generated synthetic data script by Misata")
        script_parts.append(f"Dataset: {self.config.name}")
        if self.config.description:
            script_parts.append(f"Description: {self.config.description}")
        script_parts.append('"""')
        script_parts.append("")

        # Imports
        script_parts.append(self._generate_imports(include_db=db_url is not None))
        script_parts.append("")

        # Configuration
        script_parts.append("# " + "=" * 70)
        script_parts.append("# CONFIGURATION")
        script_parts.append("# " + "=" * 70)
        script_parts.append(self._generate_config_dict())
        script_parts.append("")

        # Main execution
        script_parts.append("# " + "=" * 70)
        script_parts.append("# MAIN EXECUTION")
        script_parts.append("# " + "=" * 70)
        script_parts.append("")
        script_parts.append("def main():")
        script_parts.append("    \"\"\"Generate synthetic data and export or seed a database.\"\"\"")
        script_parts.append("    ")
        script_parts.append("    config = SchemaConfig(**CONFIG)")
        script_parts.append("    ")
        script_parts.append("    if DB_URL:")
        script_parts.append("        report = seed_database(")
        script_parts.append("            config,")
        script_parts.append("            DB_URL,")
        script_parts.append("            create=DB_CREATE,")
        script_parts.append("            truncate=DB_TRUNCATE,")
        script_parts.append("            smart_mode=SMART_MODE,")
        script_parts.append("            use_llm=USE_LLM,")
        script_parts.append("        )")
        script_parts.append("        print(f'Seeded {report.total_rows} rows into {report.dialect}')")
        script_parts.append("        return")
        script_parts.append("    ")
        script_parts.append("    simulator = DataSimulator(")
        script_parts.append("        config,")
        script_parts.append("        smart_mode=SMART_MODE,")
        script_parts.append("        use_llm=USE_LLM,")
        script_parts.append("    )")
        script_parts.append("    ")
        script_parts.append("    print('Generating synthetic data...')")

        if include_export:
            script_parts.append("    # Export placeholder")
            script_parts.append("    output_dir = 'generated_data'")
            script_parts.append("    os.makedirs(output_dir, exist_ok=True)")
            script_parts.append("    for table_name, batch_df in simulator.generate_all():")
            script_parts.append("        output_path = os.path.join(output_dir, f\"{table_name}.csv\")")
            script_parts.append("        mode = 'a' if os.path.exists(output_path) else 'w'")
            script_parts.append("        header = not os.path.exists(output_path)")
            script_parts.append("        batch_df.to_csv(output_path, mode=mode, header=header, index=False)")
            script_parts.append("    print(f'Output directory: {output_dir}')")

        script_parts.append("")
        script_parts.append(f"DB_URL = {json.dumps(db_url)}")
        script_parts.append(f"DB_CREATE = {json.dumps(db_create)}")
        script_parts.append(f"DB_TRUNCATE = {json.dumps(db_truncate)}")
        script_parts.append(f"SMART_MODE = {json.dumps(smart_mode)}")
        script_parts.append(f"USE_LLM = {json.dumps(use_llm)}")
        script_parts.append("")
        script_parts.append("if __name__ == '__main__':")
        script_parts.append("    main()")

        # Write to file
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        output_path_obj.write_text("\n".join(script_parts))

        print(f"Generated script saved to: {output_path}")

    def generate_yaml_config(self, output_path: str) -> None:
        """
        Generate a YAML configuration file.

        Args:
            output_path: Path where the YAML should be saved
        """
        import yaml

        config_dict = self.config.model_dump()

        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path_obj, "w") as f:
            yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)

        print(f"Generated YAML config saved to: {output_path}")
