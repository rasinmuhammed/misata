
<h1 align="center">Misata</h1>
<p align="center">
  <strong>AI-Powered Synthetic Data Engine</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/misata/"><img src="https://img.shields.io/pypi/v/misata?color=blue" alt="PyPI version"></a>
  <a href="https://pypi.org/project/misata/"><img src="https://img.shields.io/pypi/pyversions/misata" alt="Python versions"></a>
  <a href="https://github.com/rasinmuhammed/misata/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
  <a href="https://github.com/rasinmuhammed/misata/stargazers"><img src="https://img.shields.io/github/stars/rasinmuhammed/misata?style=social" alt="GitHub stars"></a>
  <a href="https://pepy.tech/projects/misata"><img src="https://static.pepy.tech/personalized-badge/misata?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=Downloads" alt="PyPI Downloads"></a>
</p>

<p align="center">
  Generate realistic, multi-table synthetic datasets from natural language descriptions.<br>
  Perfect for testing, development, ML training, and demos.
</p>

---

## 🚀 MisataStudio - Coming Soon!

<img width="1300" height="753" alt="Screenshot 2026-01-10 at 11 12 04 PM" src="https://github.com/user-attachments/assets/9336d3db-0ec1-40d4-affd-7fd9a8ce10e2" />


<p align="center">
  <strong>The next evolution of synthetic data generation</strong>
</p>

**MisataStudio** is our upcoming visual IDE for synthetic data engineering, featuring:

| Feature | Description |
|---------|-------------|
| 🎨 **Visual Schema Builder** | Drag-and-drop table design with live preview |
| 🤖 **Multi-Agent Pipeline** | AI agents for schema, domain, and validation |
| ✅ **100% Constraint Compliance** | Guaranteed business rule enforcement |
| 📈 **Outcome Curve Targeting** | Generate data that hits specific metrics |
| 🔀 **Causal "What-If" Queries** | Interventional scenario simulation |

**Stay tuned for early access!**

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🗣️ **Natural Language → Schema** | Describe your data needs in plain English |
| 🤖 **LLM-Powered Intelligence** | Uses Groq/OpenAI for smart schema generation |
| 🔗 **Multi-Table Relationships** | Automatic foreign key handling with referential integrity |
| 📊 **Statistical Distributions** | Normal, uniform, Poisson, exponential, and more |
| 🎯 **Business Constraints** | Sum limits, ratios, temporal ordering |
| ⚡ **Blazing Fast** | 250,000 rows/second with vectorized NumPy |
| 🧠 **Smart Value Generation** | Domain-aware realistic values (medical, HR, retail) |
| 📈 **Reverse Engineering** | Describe a chart, get matching data |

## 🚀 Quick Start

### Installation

```bash
pip install misata
```

### Set up your LLM API key

```bash
# Option 1: Environment variable
export GROQ_API_KEY=your_key_here

# Option 2: .env file
echo "GROQ_API_KEY=your_key_here" > .env
```

Get a free API key at [console.groq.com](https://console.groq.com)

### Generate Your First Dataset

```bash
# From natural language
misata generate --story "SaaS company with 10K users, 20% churn in Q3" --output-dir ./data

# With LLM intelligence
misata generate --story "Hospital with patients and doctors" --use-llm --output-dir ./hospital

# From industry template
misata template saas --output-dir ./saas_data
```

### Python API

```python
from misata import DataSimulator, SchemaConfig
from misata.llm_parser import LLMSchemaGenerator

# With LLM (recommended)
llm = LLMSchemaGenerator()
config = llm.generate_from_story("Fitness app with 50K users, workout tracking")

# Generate data
simulator = DataSimulator(config, seed=42)
simulator.export_to_csv("./fitness_data")

# Or iterate over batches
for table_name, batch_df in simulator.generate_all():
    print(f"Generated {len(batch_df)} rows for {table_name}")
```

## 📊 Example Output

```
# Generated from: "Hospital with patients and doctors"

patients.csv (10,000 rows)
├── id, name, date_of_birth, blood_type, doctor_id
├── Referential integrity with doctors table ✓
└── Realistic column distributions ✓

doctors.csv (100 rows)
├── id, name, specialty, department, hire_date
└── LLM-generated realistic specialties ✓

appointments.csv (25,000 rows)
├── id, patient_id, doctor_id, date, diagnosis
├── Foreign keys to both tables ✓
└── Temporal constraints (appointment after hire) ✓
```

## 🎯 Use Cases

| Use Case | How Misata Helps |
|----------|------------------|
| **Unit Testing** | Generate consistent test fixtures |
| **Load Testing** | Create millions of rows quickly |
| **ML Training** | Synthetic training data with realistic patterns |
| **Demo Data** | Beautiful, realistic data for demos |
| **Development** | No more waiting for production data |
| **Privacy** | No PII in synthetic data |

## 📖 Documentation

- [Quick Start Guide](./QUICKSTART.md)
- [CLI Reference](#cli-commands)
- [Python API](#python-api)
- [Schema DSL](#schema-configuration)
- [Templates](#templates)

## 💻 CLI Commands

| Command | Description |
|---------|-------------|
| `misata generate` | Generate data from story or config |
| `misata template` | Use an industry template |
| `misata graph` | Reverse-engineer from chart description |
| `misata parse` | Preview generated schema config |
| `misata serve` | Start API server for web UI |
| `misata templates` | List available templates |

### Examples

```bash
# Generate with specific row count
misata generate --story "E-commerce with orders" --rows 100000

# Use different LLM provider
misata generate --story "..." --use-llm --provider openai

# Export as Parquet
misata generate --story "..." --format parquet

# With seed for reproducibility
misata generate --story "..." --seed 42
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Natural Language                  │
│         "SaaS company with 50K users..."            │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────┐
│              LLMSchemaGenerator                      │
│  • Groq (Llama 3.3) / OpenAI (GPT-4) / Ollama       │
│  • Generates SchemaConfig with relationships        │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────┐
│                  DataSimulator                       │
│  • Topological sort for dependencies                │
│  • Vectorized NumPy generation                      │
│  • Batch processing for large datasets              │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────┐
│                CSV / Parquet / JSON                  │
│         users.csv, orders.csv, events.csv           │
└─────────────────────────────────────────────────────┘
```

## 📋 Schema Configuration

```python
from misata import SchemaConfig, Table, Column, Relationship

config = SchemaConfig(
    name="My Schema",
    tables=[
        Table(name="users", row_count=10000),
        Table(name="orders", row_count=50000),
    ],
    columns={
        "users": [
            Column(name="id", type="int", distribution_params={"distribution": "sequence"}),
            Column(name="name", type="text", distribution_params={"text_type": "name"}),
            Column(name="email", type="text", distribution_params={"text_type": "email"}),
            Column(name="age", type="int", distribution_params={"distribution": "normal", "mean": 35, "std": 10}),
        ],
        "orders": [
            Column(name="id", type="int", distribution_params={"distribution": "sequence"}),
            Column(name="user_id", type="foreign_key"),
            Column(name="amount", type="float", distribution_params={"min": 10, "max": 500}),
            Column(name="status", type="categorical", distribution_params={"choices": ["pending", "shipped", "delivered"]}),
        ],
    },
    relationships=[
        Relationship(parent_table="users", child_table="orders", parent_key="id", child_key="user_id"),
    ],
)
```

## 🏭 Templates

Pre-built schemas for common use cases:

| Template | Tables | Description |
|----------|--------|-------------|
| `saas` | users, subscriptions, events | SaaS company with churn |
| `ecommerce` | customers, products, orders | Online retail |
| `fitness` | users, exercises, workouts | Fitness app |
| `healthcare` | patients, doctors, appointments | Hospital system |

```bash
misata template ecommerce --scale 2.0 --output-dir ./data
```

## ⚡ Performance

| Dataset Size | Time | Speed |
|--------------|------|-------|
| 10,000 rows | 0.04s | 250K rows/sec |
| 100,000 rows | 0.4s | 250K rows/sec |
| 1,000,000 rows | 4s | 250K rows/sec |

Vectorized NumPy operations ensure consistent performance regardless of scale.

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

```bash
# Clone the repo
git clone https://github.com/rasinmuhammed/misata.git
cd misata

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest tests/
```

## 📄 License

MIT License - see [LICENSE](./LICENSE) for details.

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/rasinmuhammed">Muhammed Rasin</a>
</p>
