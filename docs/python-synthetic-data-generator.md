# Python Synthetic Data Generator

Misata is a Python synthetic data generator for teams who need more than random rows.

If you are searching for a Python library that can generate realistic test data, multi-table synthetic data, or scenario-based business data, this is the page you want.

## What Misata Does

Misata can:
- generate synthetic data from a plain-English story
- build related tables with foreign keys
- shape time-based scenarios such as growth, seasonality, and dips
- apply realism rules so rows do not contradict themselves
- validate the result with streaming-safe reporting

This makes it useful for:
- software testing
- database seeding
- BI demos
- local development
- sandbox environments

## Quick Example

```python
from misata import DataSimulator
from misata.story_parser import StoryParser

story = "An ecommerce app with 5K customers, repeat orders, and a peak in November"

config = StoryParser().parse(story)
result = DataSimulator(config).generate_with_reports()

print(result.table_row_counts)
print(result.validation_report.summary())
```

## Why People Use Misata Instead of Simpler Fake Data Tools

Simple fake data generators are great when you only need standalone rows.

Misata is for the next step up:
- relational tables
- business logic
- temporal scenarios
- repeatable generation
- validation you can inspect

## Related Examples

- [examples/python_synthetic_data_generator.py](../examples/python_synthetic_data_generator.py)
- [examples/multi_table_synthetic_data.py](../examples/multi_table_synthetic_data.py)
- [examples/bi_demo_dataset.py](../examples/bi_demo_dataset.py)

## Related Docs

- [README.md](../README.md)
- [FEATURES.md](../FEATURES.md)
- [QUICKSTART.md](../QUICKSTART.md)
