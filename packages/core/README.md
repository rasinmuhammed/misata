# 🧠 Misata

**Generate realistic multi-table datasets from natural language.**

No schema writing. No training data. Just describe what you need.

[![Version](https://img.shields.io/badge/version-0.2.0--beta-purple.svg)]()
[![License](https://img.shields.io/badge/license-MIT-blue.svg)]()
[![Python](https://img.shields.io/badge/python-3.10+-green.svg)]()

## ✨ What Makes Misata Different

| Feature | Faker | SDV | **Misata** |
|---------|-------|-----|------------|
| Natural language input | ❌ | ❌ | ✅ |
| Auto schema generation | ❌ | ❌ | ✅ |
| Relational integrity | ❌ | ✅ | ✅ |
| Business constraints | ❌ | ❌ | ✅ |
| No training data needed | ✅ | ❌ | ✅ |
| Streaming (10M+ rows) | ❌ | ❌ | ✅ |

## 🚀 Quick Start

```bash
pip install misata
```

### With Groq (Free, Fast)

```bash
export GROQ_API_KEY=your_key  # Get free: https://console.groq.com
misata generate --story "A SaaS with 50K users, subscriptions, and payments" --use-llm
```

### With OpenAI

```bash
export OPENAI_API_KEY=your_key
misata generate --story "E-commerce with products and orders" --use-llm --provider openai
```

### With Ollama (Local, Free, Private)

```bash
ollama run llama3  # Start Ollama first
misata generate --story "Fitness app with workouts" --use-llm --provider ollama
```

## 📊 Example Output

```
$ misata generate --story "A fitness app with 50K users" --use-llm

🧠 Using Groq (llama-3.3-70b-versatile) for intelligent parsing...
✅ LLM schema generated successfully!

📋 Schema: FitnessApp
   Tables: 5
   Relationships: 4

🔧 Generating 5 table(s)...

   ✓ exercises     (10 rows)
   ✓ plans         (5 rows)
   ✓ users         (50,000 rows)
   ✓ subscriptions (45,000 rows)
   ✓ workouts      (500,000 rows)

⏱️  Generation time: 2.34 seconds
🚀 Performance: 213,675 rows/second
💾 Data saved to: ./generated_data
```

## 💻 Python API

```python
from misata import DataSimulator, SchemaConfig
from misata.llm_parser import LLMSchemaGenerator

# Generate schema from story
llm = LLMSchemaGenerator(provider="groq")  # or "openai", "ollama"
config = llm.generate_from_story(
    "A mobile fitness app with 50K users, workout tracking, "
    "premium subscriptions, and January signup spikes"
)

# Generate data
for table_name, batch in DataSimulator(config).generate_all():
    print(f"Generated {len(batch)} rows for {table_name}")
```

## 🔧 CLI Reference

```bash
# Basic generation (rule-based, no API key needed)
misata generate --story "SaaS company with users and subscriptions"

# LLM-powered generation
misata generate --story "..." --use-llm

# Specify provider and model
misata generate --story "..." --use-llm --provider ollama --model llama3

# Custom output directory
misata generate --story "..." --use-llm --output-dir ./my_data

# Set row count
misata generate --story "..." --use-llm --rows 100000

# Reproducible with seed
misata generate --story "..." --use-llm --seed 42
```

## 🎯 Business Rule Constraints

Define rules like "employees can't log >8 hours/day":

```python
from misata import Constraint, Table

timesheets = Table(
    name="timesheets",
    row_count=10000,
    constraints=[
        Constraint(
            name="max_daily_hours",
            type="sum_limit",
            group_by=["employee_id", "date"],
            column="hours",
            value=8.0,
            action="redistribute"
        )
    ]
)
```

## 🔑 LLM Providers

| Provider | Env Variable | Free Tier | Notes |
|----------|--------------|-----------|-------|
| **Groq** | `GROQ_API_KEY` | ✅ 30 req/min | Fastest, recommended |
| **OpenAI** | `OPENAI_API_KEY` | ❌ | Best quality |
| **Ollama** | None | ✅ Local | Private, no internet |

## 📈 Extending Data Pools

```python
from misata import TextGenerator

# Add custom names
TextGenerator.extend_pool("first_names", ["Arjun", "Priya", "Rahul"])

# Load from file
TextGenerator.load_pools_from_file("custom_pools.json")

# Save for reuse
TextGenerator.save_pools_to_file("expanded_pools.json")
```

## 🤖 ML Training Data

Make your synthetic data **indistinguishable from real-world data** with noise injection:

```python
from misata import add_noise, NoiseInjector

# Quick noise injection
noisy_df = add_noise(df,
    null_rate=0.05,      # 5% missing values
    outlier_rate=0.02,   # 2% statistical outliers
    typo_rate=0.01,      # 1% typos in text
    duplicate_rate=0.03, # 3% duplicate rows
    seed=42
)

# Advanced: Temporal distribution drift
injector = NoiseInjector(seed=42)
df = injector.apply_temporal_drift(df, 
    date_column="created_at",
    value_column="revenue", 
    drift_rate=0.15,      # 15% increase over time
    drift_direction="up"
)
```

### Attribute Customization

```python
from misata import Customizer, ColumnOverride
import numpy as np

customizer = Customizer(seed=42)

# Custom age distribution (realistic, not uniform)
customizer.add_override("users", ColumnOverride(
    name="age",
    generator=lambda n: np.random.normal(35, 12, n).clip(18, 80).astype(int)
))

# Conditional values based on other columns
customizer.add_conditional("orders", "shipping_cost", {
    "country": {"US": 5.99, "UK": 9.99, "DE": 7.99}
})

# Apply to generated data
df = customizer.apply(df, "users")
```

## ⚡ Performance

| Rows | Time | Speed |
|------|------|-------|
| 10K | 0.03s | 333K rows/sec |
| 100K | 0.26s | 385K rows/sec |
| 1M | 2.6s | 390K rows/sec |
| 10M | 26s | 390K rows/sec (streaming) |

## � Try It Now

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/rasinmuhammed/misata/blob/main/examples/getting_started.ipynb)

Try Misata in your browser without installing anything!

## 💼 Enterprise & Consulting

**Need help with complex scenarios?**

- 🏢 Custom enterprise data schemas (10M+ rows)
- 🔧 Integration with your existing pipelines
- 📊 Industry-specific realistic data generation
- 🎓 Training and onboarding for your team

📧 **Contact: rasinbinabdulla@gmail.com**

## �📄 License

MIT License

## 👤 Author

Built by **Muhammed Rasin**

---

**Misata** - From story to synthetic database in one command.


