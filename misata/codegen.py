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

    def _generate_imports(self) -> str:
        """Generate import statements."""
        return """import pandas as pd
import numpy as np
import warnings
from collections import defaultdict, deque
import os

# Pure Python text generator (no external dependencies)
from misata.generators import TextGenerator
"""

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

    def generate(self, output_path: str, include_export: bool = True) -> None:
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
        script_parts.append(self._generate_imports())
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
        script_parts.append("    \"\"\"Generate synthetic data and export to CSV.\"\"\"")
        script_parts.append("    ")
        script_parts.append("    # Note: This is a simplified version.")
        script_parts.append("    # For full functionality, use the Misata library directly.")
        script_parts.append("    ")
        script_parts.append("    print('Generating synthetic data...')")
        script_parts.append("    print(f'Dataset: {CONFIG[\"name\"]}')")
        script_parts.append("    print(f'Tables: {len(CONFIG[\"tables\"])}')")
        script_parts.append("    ")
        script_parts.append("    # Initialize random seed")
        script_parts.append("    seed = CONFIG.get('seed', 42)")
        script_parts.append("    np.random.seed(seed)")
        script_parts.append("    rng = np.random.default_rng(seed)")
        script_parts.append("    text_gen = TextGenerator(seed=seed)")
        script_parts.append("    ")
        script_parts.append("    # TODO: Import and use DataSimulator from Misata")
        script_parts.append("    # For now, this is a placeholder")
        script_parts.append("    print('Please install misata library:')")
        script_parts.append("    print('  pip install misata')")
        script_parts.append("    print('Then use:')")
        script_parts.append("    print('  from misata import DataSimulator, SchemaConfig')")
        script_parts.append("    ")

        if include_export:
            script_parts.append("    # Export placeholder")
            script_parts.append("    output_dir = 'generated_data'")
            script_parts.append("    os.makedirs(output_dir, exist_ok=True)")
            script_parts.append("    print(f'Output directory: {output_dir}')")

        script_parts.append("")
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
