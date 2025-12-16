# 🧠 Misata

**AI-Powered Synthetic Data Engine**

Generate industry-realistic data that's indistinguishable from the real thing. Powered by Groq Llama 3.3 for intelligent schema generation.

[![Version](https://img.shields.io/badge/version-2.0.0-purple.svg)]()
[![License](https://img.shields.io/badge/license-MIT-blue.svg)]()
[![Python](https://img.shields.io/badge/python-3.10+-green.svg)]()

## ✨ Features

🧠 **AI-Powered Schema Generation** - Describe your data in plain English  
📊 **Graph Reverse Engineering** - Describe a chart, get matching data  
⚡ **Blazing Fast** - 250K+ rows/second with vectorized operations  
🔗 **Referential Integrity** - Automatic parent-child relationship enforcement  
📈 **Statistical Control** - Apply growth, seasonality, crashes, trends  
🎨 **Beautiful Web UI** - Visual studio for data generation  

## 🚀 Quick Start

### Installation

```bash
cd /Users/muhammedrasin/Misata
pip install -e .
```

### Set Groq API Key (for LLM features)

```bash
# Get your free key: https://console.groq.com
export GROQ_API_KEY=your_key_here
```

### Generate Data

```bash
# Rule-based generation (fast, no API needed)
misata generate --story "SaaS company with 50K users, 20% churn in Q3"

# LLM-powered generation (intelligent, realistic)
misata generate --story "Mobile fitness app with workout tracking" --use-llm

# Reverse engineer from chart description
misata graph "Revenue growing from $100K to $1M over 2 years with Q2 dips"
```

### Start Web UI

```bash
# Terminal 1: Start API server
misata serve --port 8000

# Terminal 2: Start web UI
cd web && npm run dev
```

Open http://localhost:3000 for the visual studio!

## 📖 Usage

### CLI Commands

| Command | Description |
|---------|-------------|
| `misata generate` | Generate data from story or config |
| `misata graph` | Reverse engineer data from chart description |
| `misata parse` | Parse story and output config file |
| `misata serve` | Start the API server |
| `misata examples` | Show usage examples |

### Python API

```python
from misata import DataSimulator, SchemaConfig
from misata.llm_parser import LLMSchemaGenerator

# With LLM (intelligent)
llm = LLMSchemaGenerator()
config = llm.generate_from_story(
    "A mobile fitness app with 50K users tracking workouts, "
    "heavy January signups, 60% drop by March, 15% premium conversion"
)

# Generate data
simulator = DataSimulator(config)
data = simulator.generate_all()

# Export
simulator.export_to_csv("./output")
```

### Graph Reverse Engineering

```python
from misata.llm_parser import LLMSchemaGenerator

llm = LLMSchemaGenerator()
config = llm.generate_from_graph("""
Monthly revenue line chart showing:
- Start: $100K in January 2023
- End: $1M by December 2024
- Exponential growth curve
- 20% seasonal dip every Q2
- One-time 50% crash in October 2023 with 3-month recovery
""")

# The generated data will produce exactly this pattern when plotted!
```

## 🎨 Web UI

The web UI provides three modes:

1. **Story Mode** - Natural language input with AI parsing
2. **Graph Mode** - Describe your desired chart, get matching data
3. **Visual Builder** - Drag-and-drop schema designer (coming soon)

## 🏗️ Architecture

```
misata/
├── misata/
│   ├── __init__.py          # Package exports
│   ├── schema.py            # Pydantic models
│   ├── simulator.py         # Vectorized generator
│   ├── modifiers.py         # Mathematical functions
│   ├── llm_parser.py        # Groq Llama 3.3 integration
│   ├── story_parser.py      # Rule-based parser
│   ├── api.py               # FastAPI backend
│   ├── codegen.py           # Script generator
│   └── cli.py               # CLI interface
├── web/                     # Next.js web UI
│   └── src/app/
├── examples/                # Demo scripts
└── pyproject.toml
```

## ⚡ Performance

| Rows | Time | Speed |
|------|------|-------|
| 10K | 0.04s | 250K rows/sec |
| 100K | 0.4s | 250K rows/sec |
| 1M | 4s | 250K rows/sec |

## 🔑 API Keys

### Groq (Required for LLM features)

1. Go to https://console.groq.com
2. Create an account (free)
3. Generate an API key
4. Set environment variable: `export GROQ_API_KEY=your_key`

**Free tier:** 30 requests/minute, sufficient for most use cases.

## 🛠️ Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black misata/

# Type check
mypy misata/
```

## 📄 License

MIT License - see LICENSE file.

## 👤 Author

Built with ❤️ by **Muhammed Rasin**

Powered by:
- 🧠 Groq Llama 3.3
- ⚡ NumPy & Pandas
- 🎭 Mimesis
- 🌐 FastAPI & Next.js

---

**Misata** - Making synthetic data indistinguishable from reality.
