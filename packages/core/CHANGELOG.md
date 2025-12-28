# Changelog

All notable changes to Misata will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0-beta] - 2024-12-28

### Added

#### Data Quality Improvements
- **35 domain patterns** for smart value generation (up from 15)
  - 🍽️ Food: restaurant_name, cuisine_type, menu_item
  - 🎓 Education: course_name, university, degree
  - 📅 Events: event_name, venue
  - 📋 Projects: project_name, task_name, milestone
  - ⭐ Reviews: review_title, review_text
  - 📍 Location: city, country, address
  - 🏢 Business: company_name, industry
  - 💻 Tech: feature_name, bug_type, api_endpoint, skill

- **30 curated fallback pools** for domain-specific values without LLM
- **Smart distribution defaults** in LLM prompt for realistic data:
  - Age: normal(mean=35, std=12)
  - Rating: realistic 1-5 star skew
  - Price: exponential distribution
  - Status: 70/20/10 active/inactive/pending

#### New Modules
- `misata.quality` - Data quality validation
  - `DataQualityChecker` class
  - `check_quality()` convenience function
  - Distribution plausibility checks
  - Referential integrity validation
  - Temporal consistency checks
  - Quality scoring (0-100)

- `misata.templates.library` - Pre-built schema templates
  - `load_template("ecommerce")` - 7 tables, ~230K rows
  - `load_template("saas")` - 5 tables, ~527K rows
  - `load_template("healthcare")` - 5 tables, ~135K rows
  - `load_template("fintech")` - 5 tables, ~560K rows
  - `list_templates()` - Show available templates

### Changed
- Enhanced LLM system prompt with smart distribution guidelines
- Expanded `__all__` exports to include new modules

## [0.1.0-beta] - 2024-11-15

### Added
- Initial beta release
- Core `DataSimulator` for synthetic data generation
- `SchemaConfig` for defining tables, columns, relationships
- LLM-powered schema generation (Groq, OpenAI, Ollama)
- CLI tool: `misata generate --story "..."`
- Reference tables with inline data
- Transactional tables with foreign keys
- Business rule constraints
- Noise injection for ML training data
- Streaming support for 10M+ rows
- Performance: 390K rows/second
