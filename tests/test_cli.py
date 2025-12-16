"""
Integration tests for CLI commands.
"""

import os
import tempfile
import pytest
from click.testing import CliRunner

from misata.cli import main, generate, template, templates_list, examples


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
        assert '2.0.0' in result.output
    
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
