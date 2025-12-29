# Contributing to Misata

Thank you for your interest in contributing to Misata! This document provides guidelines and instructions for contributing.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)

## 📜 Code of Conduct

Please be respectful and constructive in all interactions. We're all here to make Misata better together.

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Git
- A Groq API key (free at [console.groq.com](https://console.groq.com))

### Development Setup

```bash
# Fork and clone the repository
git clone https://github.com/YOUR_USERNAME/misata.git
cd misata

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with dev dependencies
cd packages/core
pip install -e ".[dev]"

# Set up environment variables
cp .env.example .env
# Edit .env with your GROQ_API_KEY

# Run tests to verify setup
pytest tests/
```

## 🔧 Making Changes

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation updates
- `refactor/description` - Code refactoring
- `test/description` - Test additions

### Commit Messages

Follow conventional commits:

```
type(scope): description

[optional body]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Examples:
```
feat(generators): add beta distribution generator
fix(simulator): handle empty foreign key lookup
docs(readme): add installation instructions
```

## 📤 Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make your changes**
   - Write code
   - Add tests
   - Update documentation

3. **Run quality checks**
   ```bash
   # Format code
   black .
   
   # Lint
   ruff check .
   
   # Type check
   mypy misata/
   
   # Run tests
   pytest tests/ -v
   ```

4. **Push and create PR**
   ```bash
   git push origin feature/my-feature
   ```
   
   Then open a PR on GitHub.

5. **PR Description**
   - Describe what changes you made
   - Reference any related issues
   - Include screenshots for UI changes

## 📏 Coding Standards

### Python

- **Formatter**: Black (line length 100)
- **Linter**: Ruff
- **Type hints**: Required for all functions
- **Docstrings**: Google style

```python
def generate_column(
    self,
    table_name: str,
    column: Column,
    size: int,
) -> np.ndarray:
    """Generate values for a single column.
    
    Args:
        table_name: Name of the table being generated
        column: Column definition
        size: Number of values to generate
        
    Returns:
        Array of generated values
        
    Raises:
        ColumnGenerationError: If generation fails
    """
    pass
```

### File Organization

```
misata/
├── __init__.py          # Public exports
├── schema.py            # Pydantic models
├── simulator.py         # Core engine
├── generators/          # Generator implementations
│   ├── __init__.py
│   └── base.py
├── exceptions.py        # Custom exceptions
└── ...
```

## 🧪 Testing

### Running Tests

```bash
# All tests
pytest tests/

# Specific test file
pytest tests/test_simulator.py

# With coverage
pytest tests/ --cov=misata --cov-report=html

# Verbose output
pytest tests/ -v
```

### Writing Tests

```python
import pytest
from misata import DataSimulator, SchemaConfig

class TestDataSimulator:
    def test_generate_basic_table(self):
        """Test basic table generation."""
        config = SchemaConfig(...)
        simulator = DataSimulator(config)
        
        for table_name, df in simulator.generate_all():
            assert len(df) > 0
    
    @pytest.mark.parametrize("distribution", ["uniform", "normal", "poisson"])
    def test_integer_distributions(self, distribution):
        """Test various integer distributions."""
        pass
```

### Test Categories

- **Unit tests**: `tests/unit/` - Fast, isolated tests
- **Integration tests**: `tests/integration/` - API + Core interaction
- **Performance tests**: `tests/performance/` - Benchmarks

## 📚 Documentation

### Docstrings

All public functions and classes need docstrings:

```python
class DataSimulator:
    """High-performance synthetic data simulator.
    
    Generates synthetic datasets based on SchemaConfig definitions,
    using vectorized operations for maximum performance.
    
    Attributes:
        config: Schema configuration
        seed: Random seed for reproducibility
        
    Example:
        >>> sim = DataSimulator(config, seed=42)
        >>> for table_name, df in sim.generate_all():
        ...     df.to_csv(f"{table_name}.csv")
    """
```

### README Updates

When adding features, update:
- Feature list in README.md
- CLI commands if applicable
- API examples

## 🎯 Areas for Contribution

### Good First Issues

- Add more statistical distributions
- Improve error messages
- Add more templates
- Documentation improvements

### Larger Projects

- New generator types
- Performance optimizations
- New output formats
- Enhanced LLM prompts

## ❓ Questions?

- Open a [GitHub Issue](https://github.com/rasinmuhammed/misata/issues)
- Start a [Discussion](https://github.com/rasinmuhammed/misata/discussions)

---

Thank you for contributing! 🙏
