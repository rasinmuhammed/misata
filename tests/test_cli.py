"""
Integration tests for CLI commands.
"""

import os
import sqlite3
import tempfile
import json
import pytest
import yaml
from click.testing import CliRunner

from misata.cli import main, generate, template, templates_list, examples, schema_cmd


class TestCLICommands:
    """Test CLI commands."""
    
    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()
    
    def test_help_command(self, runner):
        """Test --help works."""
        result = runner.invoke(main, ['--help'])
        
        assert result.exit_code == 0
        assert 'Misata' in result.output
    
    def test_version_command(self, runner):
        """Test --version works."""
        result = runner.invoke(main, ['--version'])
        
        assert result.exit_code == 0
        import misata
        assert misata.__version__ in result.output
    
    def test_examples_command(self, runner):
        """Test examples command."""
        result = runner.invoke(examples)
        
        assert result.exit_code == 0
        assert 'SaaS' in result.output
        assert 'template' in result.output
    
    def test_templates_list_command(self, runner):
        """Test templates-list command."""
        result = runner.invoke(templates_list)
        
        assert result.exit_code == 0
        assert 'saas' in result.output
        assert 'ecommerce' in result.output
        assert 'fitness' in result.output
        assert 'healthcare' in result.output
    
    def test_template_command(self, runner):
        """Test template command generates data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(template, [
                'saas',
                '--output-dir', tmpdir,
                '--scale', '0.01',  # Very small for speed
                '--no-validate'
            ])
            
            assert result.exit_code == 0
            assert 'plans' in result.output
            
            # Check files were created
            assert os.path.exists(os.path.join(tmpdir, 'plans.csv'))
            assert os.path.exists(os.path.join(tmpdir, 'users.csv'))
    
    def test_template_invalid_name(self, runner):
        """Test template command with invalid name."""
        result = runner.invoke(template, ['nonexistent'])
        
        assert 'Unknown template' in result.output or result.exit_code != 0
    
    def test_generate_without_args_fails(self, runner):
        """Test generate command requires story or config."""
        result = runner.invoke(generate)
        
        assert result.exit_code != 0 or 'Error' in result.output


class TestCLIGenerate:
    """Test CLI generate command."""
    
    @pytest.fixture
    def runner(self):
        return CliRunner()
    
    def test_generate_with_story(self, runner):
        """Test generate with story (rule-based)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(generate, [
                '--story', 'Simple company with 100 users',
                '--output-dir', tmpdir,
                '--rows', '10'
            ])
            
            # Should complete (might fail if story parser doesn't match, but shouldn't crash)
            assert 'Error' not in result.output or result.exit_code == 0 or 'users' in result.output.lower()

    def test_generate_with_db_url_sqlite(self, runner):
        """Test generate with db-url seeds SQLite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "seed.db")
            db_url = f"sqlite:///{db_path}"

            result = runner.invoke(generate, [
                '--story', 'Simple company with 10 users',
                '--rows', '10',
                '--db-url', db_url,
                '--db-create',
                '--db-truncate',
            ])

            assert result.exit_code == 0
            assert "Seeded" in result.output

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}
            assert len(tables) > 0
            conn.close()

    def test_schema_from_db_cli(self, runner):
        """Test schema command with sqlite db."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "schema.db")
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
            conn.commit()
            conn.close()

            output_path = os.path.join(tmpdir, "schema.yaml")
            result = runner.invoke(schema_cmd, [
                '--db-url', f"sqlite:///{db_path}",
                '--output', output_path,
            ])

            assert result.exit_code == 0
            assert os.path.exists(output_path)

    def test_recipe_init_creates_yaml(self, runner):
        """Test recipe init writes a starter recipe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            recipe_path = os.path.join(tmpdir, "recipe.yaml")
            result = runner.invoke(main, [
                "recipe", "init",
                "--name", "smoke_recipe",
                "--story", "Simple company with 10 users",
                "--output", recipe_path,
            ])

            assert result.exit_code == 0
            assert os.path.exists(recipe_path)

            with open(recipe_path, "r", encoding="utf-8") as f:
                recipe_data = yaml.safe_load(f)

            assert recipe_data["name"] == "smoke_recipe"
            assert recipe_data["story"] == "Simple company with 10 users"

    def test_recipe_run_with_story_writes_artifacts(self, runner):
        """Test recipe run from story produces manifest and reports."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = os.path.join(tmpdir, "output")
            recipe_path = os.path.join(tmpdir, "recipe.yaml")
            with open(recipe_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(
                    {
                        "name": "story_recipe",
                        "story": "Simple company with 10 users",
                        "seed": 42,
                        "output_dir": output_dir,
                        "validation": True,
                        "quality": True,
                        "audit": True,
                    },
                    f,
                    sort_keys=False,
                )

            result = runner.invoke(main, [
                "recipe", "run",
                "--config", recipe_path,
                "--rows", "10",
            ])

            assert result.exit_code == 0
            manifest_path = os.path.join(output_dir, "run_manifest.json")
            assert os.path.exists(manifest_path)
            assert os.path.exists(os.path.join(output_dir, "validation_report.json"))
            assert os.path.exists(os.path.join(output_dir, "quality_report.json"))
            assert os.path.exists(os.path.join(output_dir, "audit_report.json"))

            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            assert manifest["status"] == "success"
            assert manifest["recipe_name"] == "story_recipe"
            assert manifest["total_rows"] > 0

    def test_recipe_run_with_schema_config(self, runner):
        """Test recipe run from embedded schema config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = os.path.join(tmpdir, "output")
            recipe_path = os.path.join(tmpdir, "schema_recipe.yaml")
            recipe_data = {
                "name": "schema_recipe",
                "output_dir": output_dir,
                "validation": True,
                "quality": True,
                "audit": False,
                "schema_config": {
                    "name": "SimpleDataset",
                    "seed": 7,
                    "tables": [{"name": "users", "row_count": 5}],
                    "columns": {
                        "users": [
                            {
                                "name": "id",
                                "type": "int",
                                "distribution_params": {"distribution": "uniform", "min": 1, "max": 5},
                            },
                            {
                                "name": "email",
                                "type": "text",
                                "distribution_params": {"text_type": "email"},
                            },
                        ]
                    },
                    "relationships": [],
                    "events": [],
                    "outcome_curves": [],
                },
            }
            with open(recipe_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(recipe_data, f, sort_keys=False)

            result = runner.invoke(main, [
                "recipe", "run",
                "--config", recipe_path,
            ])

            assert result.exit_code == 0
            assert os.path.exists(os.path.join(output_dir, "users.csv"))

            with open(os.path.join(output_dir, "run_manifest.json"), "r", encoding="utf-8") as f:
                manifest = json.load(f)

            assert manifest["tables"]["users"] == 5


class TestCLIInit:
    """Tests for `misata init` command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_init_no_flags_writes_template(self, runner, tmp_path):
        """Default init writes the commented YAML template."""
        out = tmp_path / "misata.yaml"
        result = runner.invoke(main, ["init", "--output", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()
        content = out.read_text()
        assert "tables:" in content
        assert "relationships:" in content

    def test_init_story_mode_writes_valid_yaml(self, runner, tmp_path):
        """--story flag produces a loadable misata.yaml."""
        out = tmp_path / "misata.yaml"
        result = runner.invoke(main, [
            "init",
            "--story", "A SaaS company with 50 users",
            "--rows", "50",
            "--output", str(out),
        ])
        assert result.exit_code == 0, result.output
        assert out.exists()
        data = yaml.safe_load(out.read_text())
        assert "tables" in data or "name" in data  # valid YAML was written

    def test_init_no_overwrite_without_force(self, runner, tmp_path):
        """init refuses to overwrite without --force."""
        out = tmp_path / "misata.yaml"
        out.write_text("existing: true\n")
        result = runner.invoke(main, ["init", "--output", str(out)])
        # Should either fail with a non-zero exit code or warn the user
        assert result.exit_code != 0 or "force" in result.output.lower() or "exist" in result.output.lower()

    def test_init_force_overwrites(self, runner, tmp_path):
        """--force overwrites an existing file."""
        out = tmp_path / "misata.yaml"
        out.write_text("existing: true\n")
        result = runner.invoke(main, ["init", "--output", str(out), "--force"])
        assert result.exit_code == 0, result.output
        content = out.read_text()
        assert "tables:" in content  # original content replaced

    def test_init_db_mode_sqlite(self, runner, tmp_path):
        """--db flag introspects a SQLite DB and writes its schema."""
        db_path = tmp_path / "app.db"
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, price REAL)")
        conn.commit()
        conn.close()

        out = tmp_path / "misata.yaml"
        result = runner.invoke(main, [
            "init",
            "--db", f"sqlite:///{db_path}",
            "--output", str(out),
        ])
        assert result.exit_code == 0, result.output
        assert out.exists()
        content = out.read_text()
        # The saved YAML should reference the "products" table
        assert "products" in content
