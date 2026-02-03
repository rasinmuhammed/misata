# Changelog

All notable changes to Misata will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-02-03

### 🎯 Production-Ready Realism (Major Release)
**Synthetic data that looks and behaves like real data. No more placeholders!**

#### Value Pool Enrichment
- **15 NEW domain pools** with 300+ curated realistic values:
  - `medical_specialty`: 25 clinical specialties (Cardiology, Neurology, etc.)
  - `transaction_type`: 23 financial transaction types
  - `account_type`: 15 bank/financial account types
  - `brand`: 35 real-world brand names
  - `payment_method`: 18 payment options (Credit Card, PayPal, etc.)
  - `order_status`: 15 e-commerce order states
  - `customer_segment`: 17 B2B/B2C segments
  - `subscription_plan`: 16 SaaS plan types
  - `priority_level`: 10 priority/urgency values
  - `license_type`: 16 software license types
  - `file_type`: 18 document/file types
  - Generic fallbacks: `name`, `description`, `title`, `status`, `type`

#### Zero Placeholder Guarantee
- **`get_pool()` now NEVER returns empty** - cascading fallback logic ensures every column gets realistic values
- Automatic domain inference from column names (e.g., `product_name` → product pool)
- Ultimate fallback to curated generic pools when all else fails

#### Enhanced Domain Detection
- **8 NEW domain patterns** for automatic column matching
- Improved pattern matching for common column suffixes (`_name`, `_type`, `_status`)
- Generic pattern matching for ambiguous columns

### Changed
- Upgraded from beta (0.4.0b0) to stable release
- Improved LLM fallback behavior - never crashes on API failures

---

## [0.4.0b0] - 2026-01-03

### 📊 Outcome Curve Designer (KILLER FEATURE!)
**Draw the business outcome you want. Misata generates transactions that aggregate to your exact curve.**

```
User draws: Revenue from $100K → $700K over 12 months (hockey stick)
Misata generates: 36,863 individual transactions
When aggregated: 94.85% match score to target curve!
```

- 8 preset curve shapes: Linear, Exponential, Hockey Stick, Seasonal, SaaS, Churn Decline, V-Recovery, Plateau
- Configure metric type, time granularity, scale
- Dirichlet-based amount distribution for realistic variance
- Instant verification of generated vs target curve

### 🎨 Misata Studio GUI
- **4 Input Modes**: Outcome Curve, LLM Story, Distribution Designer, Sample Data
- **Schema Builder**: Review and edit columns before generating
- **Schema Inference**: Auto-detect types from uploaded CSV

### Installation
```bash
pip install misata[studio]
misata studio
```

### New Files
- `misata/studio/outcome_curve.py` - Reverse time-series generation engine
- `misata/studio/inference.py` - Schema inference from data
- `misata/studio/app.py` - Streamlit UI with 3-step wizard

---

## [0.3.1b0] - 2026-01-03

### Performance (3.8x Faster Text Generation!)
- **Text Pooling**: Generate pool of 10k values once, sample with NumPy
  - Before: 390K rows/sec → After: **1.48M rows/sec**
  - 1 million names now generates in 0.6s instead of 2.5s
- `TEXT_POOL_SIZE = 10,000` configurable constant

### Realism (Correlated Columns!)
- **`depends_on` parameter**: Columns can now depend on other column values
  - Numeric mapping: `salary` based on `job_title` (Intern→$40k, CTO→$250k)
  - Categorical mapping: `state` based on `country`
  - Boolean probability: `churned` based on `plan` (free→40%, enterprise→2%)
- Vectorized conditional generation using `np.select` for speed

### Memory Efficiency
- **`MAX_CONTEXT_ROWS = 50,000`**: Context storage capped to prevent RAM explosion
- Large parent tables (10M+ rows) no longer crash child generation
- Reservoir sampling for random FK selection from capped context

---

## [0.3.0b0] - 2025-12-29

### Added

#### Distribution Profiles (`misata.profiles`)
- **12+ pre-built statistical distributions** matching real-world patterns
- `salary_tech` - Gaussian mixture ($50k-$500k, mean ~$145k)
- `salary_usd` - Lognormal for general US salaries
- `age_adult` / `age_population` - Realistic age demographics
- `price_retail` / `price_saas` - E-commerce and SaaS pricing
- `transaction_amount` - Pareto distribution for transactions
- `rating_5star` - Beta distribution skewed toward high ratings
- `nps_score`, `conversion_rate`, `churn_rate` - Business metrics
- Helper functions: `get_profile()`, `list_profiles()`, `generate_with_profile()`

#### Conditional Generation
- **New Class**: `ConditionalCategoricalGenerator` for hierarchical data
- Generate values dependent on parent column (e.g., state matches country)
- 4 built-in lookup tables:
  - `country_to_state` - 8 countries with states/provinces
  - `department_to_role` - 7 departments with job titles
  - `category_to_subcategory` - Product category hierarchies
  - `industry_to_company_type` - Industry-specific company types
- Factory: `create_conditional_generator(lookup_name, parent_column)`

#### Realistic Edge Cases
- **Null Injection**: `BaseGenerator.inject_nulls(values, null_rate)`
- **Outlier Injection**: `BaseGenerator.inject_outliers(values, outlier_rate)`
- **Post-processing**: `BaseGenerator.post_process(values, params)`

#### Template Composition
- `SmartValueGenerator.generate_with_template()` for unlimited variety
- `SmartValueGenerator.generate_composite_pool()` for domain templates
- Templates: `address`, `email`, `product`, `company_name`
- ID templates: `order_id`, `invoice_number`, `sku`, `username`

#### Enhanced Exports
- All generators: `IntegerGenerator`, `FloatGenerator`, `BooleanGenerator`, etc.
- All constraints: `SumConstraint`, `RangeConstraint`, `UniqueConstraint`, etc.
- New: `GenerationContext`, `SmartValueGenerator`, `DistributionProfile`
- Exceptions: `MisataError`, `ColumnGenerationError`, `LLMError`, etc.

### Changed
- `SmartValueGenerator.get_pool()` now defaults to larger pool sizes
- Improved `smart_generate()` sampling with `random.choices()`

---

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
