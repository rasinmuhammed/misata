# Misata - Quick Start Guide

## Installation

```bash
cd /Users/muhammedrasin/Misata
pip install -e .
```

```bash
# Optional: Postgres seeding support
pip install "misata[db]"
```

```bash
# Optional: SQLAlchemy schema introspection
pip install "misata[orm]"
```

## Setup Groq API Key

1. Get your free key at: https://console.groq.com
2. Create a `.env` file:

```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

Or set the environment variable directly:
```bash
export GROQ_API_KEY=your_key_here
```

## Instant Examples

### 1. Generate SaaS Data (Rule-based)
```bash
misata generate \
  --story "SaaS company with 10K users, 20% churn in Q3 2023" \
  --output-dir ./saas_data \
  --seed 42
```

### 2. Generate with LLM (Intelligent)
```bash
misata generate \
  --story "Mobile fitness app with workout tracking, seasonal patterns" \
  --use-llm \
  --output-dir ./fitness_data
```

### 3. Graph Reverse Engineering
```bash
misata graph "Revenue from $100K to $1M over 2 years with Q2 dips" \
  --output-dir ./revenue_data
```

### 4. Start Web UI
```bash
# Terminal 1: API server
misata serve --port 8000

# Terminal 2: Web frontend
cd web && npm run dev
```

Open http://localhost:3000 🎉

### 5. Seed a Database
```bash
# SQLite
misata generate --story "SaaS company with users and subscriptions" \
  --db-url sqlite:///./misata.db --db-create --db-truncate

# Postgres (requires misata[db])
misata generate --story "E-commerce with products and orders" \
  --db-url postgresql://user:pass@localhost:5432/misata --db-create

# Generate from SQLAlchemy models
misata generate --sqlalchemy myapp.models:Base --db-url sqlite:///./app.db --db-create

# Export a portable seed script
misata generate --story "SaaS with users" \
  --db-url sqlite:///./misata.db --db-create --export-script ./seed.py
```

### 6. Generate Schema from an Existing DB
```bash
misata schema --db-url sqlite:///./misata.db --output schema.yaml
```

### 7. Generate Schema from SQLAlchemy (requires misata[orm])
```bash
misata schema --sqlalchemy myapp.models:Base --output schema.yaml
```

### 8. Scenarios, Validation, and Quality
```bash
# Apply scenario overrides
misata generate --story "SaaS with churn events" --scenario ./scenarios/churn.yaml

# Validate a database directly
misata validate --db-url sqlite:///./misata.db --config schema.yaml

# Run quality checks
misata quality --db-url sqlite:///./misata.db --config schema.yaml
```

## Python API

```python
from misata import DataSimulator, SchemaConfig
from misata.story_parser import StoryParser

# Rule-based parsing
parser = StoryParser()
config = parser.parse("SaaS with 50K users")

# Or with LLM
from misata.llm_parser import LLMSchemaGenerator
llm = LLMSchemaGenerator()  # Reads GROQ_API_KEY from .env
config = llm.generate_from_story("Fitness app with seasonal patterns")

# Generate data
simulator = DataSimulator(config, seed=42)
data = simulator.generate_all()

# Export
simulator.export_to_csv("./output")
```

## Project Structure

```
Misata/
├── misata/               # Python package
│   ├── schema.py         # Pydantic models
│   ├── simulator.py      # Core engine
│   ├── llm_parser.py     # Groq LLM integration
│   ├── api.py            # FastAPI backend
│   └── cli.py            # CLI interface
├── web/                  # Next.js web UI
├── examples/             # Demo scripts
├── .env.example          # Environment template
└── pyproject.toml        # Dependencies
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `misata generate` | Generate data from story |
| `misata graph` | Reverse engineer from chart description |
| `misata parse` | Output config file for review |
| `misata schema` | Introspect schema from DB/SQLAlchemy |
| `misata serve` | Start API server |
| `misata examples` | Show usage examples |
| `misata validate` | Validate CSV or DB data |
| `misata quality` | Run data quality checks |

## Troubleshooting

### "Command not found: misata"
```bash
cd /Users/muhammedrasin/Misata
pip install -e .
```

### "Groq API key required"
```bash
# Option 1: Environment variable
export GROQ_API_KEY=your_key

# Option 2: .env file
cp .env.example .env
# Edit .env with your key
```

### Using without LLM
Just omit the `--use-llm` flag for rule-based parsing:
```bash
misata generate --story "SaaS 10K users"
```

## Performance

| Rows | Time | Speed |
|------|------|-------|
| 10K | 0.04s | 250K rows/sec |
| 100K | 0.4s | 250K rows/sec |
| 1M | 4s | 250K rows/sec |

---

**Misata** - AI-Powered Synthetic Data Engine 🧠
