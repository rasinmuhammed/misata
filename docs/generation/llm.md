# LLM-Assisted Generation

Use a language model to produce a richer schema from an open-ended story — useful for complex or unusual domains where the rule-based parser falls short.

```bash
pip install "misata[llm]"
```

## Supported providers

| Provider | Env var | Notes |
|:--|:--|:--|
| `groq` | `GROQ_API_KEY` | Fast, free tier available |
| `openai` | `OPENAI_API_KEY` | GPT-4o / GPT-4-turbo |
| `anthropic` | `ANTHROPIC_API_KEY` | Claude Sonnet / Opus |
| `gemini` | `GOOGLE_API_KEY` | Gemini Pro via OpenAI-compat endpoint |
| `ollama` | — | Fully local, no API key |

## Usage

```python
from misata import LLMSchemaGenerator

gen = LLMSchemaGenerator(provider="groq")
# gen = LLMSchemaGenerator(provider="anthropic")
# gen = LLMSchemaGenerator(provider="ollama", model="llama3")

schema = gen.generate_from_story(
    "A fraud detection dataset — 2% positive rate, FICO scores, "
    "transaction velocity features, device fingerprints"
)

import misata
tables = misata.generate_from_schema(schema)
```

## When to use it

- Your domain is niche and the story parser returns a generic schema
- You need column-level semantics that require world knowledge (e.g. realistic medical codes)
- You want to iterate on schema design in natural language before committing to YAML

!!! tip "LLM → YAML → version control"
    Generate once with the LLM, save the schema to YAML, then commit it so future runs are deterministic and free.

    ```python
    schema = gen.generate_from_story("A logistics company …")
    misata.save_yaml_schema(schema, "logistics.yaml")
    ```
