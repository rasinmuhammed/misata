# Faker vs SDV vs Misata

These tools solve different problems.

## Faker

Best for:
- quick standalone fake rows
- simple apps
- one-off scripts

Limits:
- no built-in multi-table planning
- no exact business aggregates
- no workflow semantics
- little control over cross-table realism

## SDV

Best for:
- learning statistical patterns from real data
- single-table and some relational synthetic modeling
- model-based generation workflows

Limits:
- less direct control over exact business stories
- harder to guarantee hand-authored scenario logic
- less naturally suited to story-driven generation

## Misata

Best for:
- synthetic data generation from a story or declared schema
- multi-table test data with referential integrity
- database seeding
- BI and scenario demos with exact targets
- workflow-aware business datasets

## The Practical Difference

Use Faker when you want quick fake values.

Use SDV when you want a model trained against real data.

Use Misata when you want a controllable synthetic world that follows business logic, temporal rules, and explicit constraints.

## Related Docs

- [docs/python-synthetic-data-generator.md](/Users/muhammedrasin/misata-project/Misata/docs/python-synthetic-data-generator.md)
- [docs/multi-table-synthetic-data.md](/Users/muhammedrasin/misata-project/Misata/docs/multi-table-synthetic-data.md)
- [docs/synthetic-data-for-bi-demos.md](/Users/muhammedrasin/misata-project/Misata/docs/synthetic-data-for-bi-demos.md)
