---
title: Generate Fintech Synthetic Data in Python | Misata
description: Generate realistic fintech synthetic datasets in Python, customers, bank accounts, transactions, fraud flags, and credit scores with locale-aware IBANs and configurable fraud rates. No real data required.
---

# Generate Fintech Synthetic Data in Python

Fintech applications handle sensitive financial data, transaction histories, credit scores, account balances, and fraud signals. Using real customer data for development, ML training, or load testing creates compliance risk. Misata generates statistically accurate fintech synthetic data: customers with realistic FICO-distributed credit scores, accounts with locale-aware IBANs, and transaction streams with configurable fraud rates.

The schema is designed around real-world fintech compliance requirements: `kyc_status` tracks verification state, `is_fraud` is a boolean flag on transactions (not just a random column), and fraud rate is extracted directly from your story description so you can control the class imbalance in training datasets.

```python
import misata

tables = misata.generate("A fintech with 2k customers and 3% fraud rate", rows=2000, seed=42)
print(list(tables.keys()))   # ['customers', 'accounts', 'transactions']
print(tables["transactions"]["is_fraud"].mean())  # ~0.03
```

## What Misata generates

Three tables: `customers` → `accounts` → `transactions`. Every transaction references a real account; every account references a real customer. Credit scores, transaction amounts, and fraud flags are statistically correlated.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `customers` | `customer_id`, `name`, `email`, `date_of_birth`, `credit_score`, `kyc_status`, `country` |
| `accounts` | `account_id`, `customer_id`, `account_type`, `balance`, `currency`, `iban`, `opened_at` |
| `transactions` | `transaction_id`, `account_id`, `amount`, `type`, `status`, `is_fraud`, `transaction_date`, `merchant` |

### Realistic distributions

- **Credit scores** are lognormal centered on FICO mean (~700, σ=75), the right bell shape for creditworthiness modeling
- **Fraud rate** is configurable from the story: `"2% fraud"`, `"high fraud rate"`, `"3% fraud rate"` all work
- **IBAN format** follows locale: DE IBANs start with `DE`, BR with `BR`, GB with `GB`, not random strings
- **Transaction types:** credit 45%, debit 35%, transfer 15%, withdrawal 5%
- **Transaction amounts** are lognormal, realistic mix of small everyday purchases and large transfers

## Quick start

```python
import misata

tables = misata.generate(
    "Brazilian fintech with 2k customers, R$ payments, CPF verification, 3% fraud rate",
    rows=2000,
    seed=42,
)

# Fraud rate matches description
fraud_rate = tables["transactions"]["is_fraud"].mean()
print(f"Fraud rate: {fraud_rate:.1%}")  # ~3.0%

# Credit score distribution
print(tables["customers"]["credit_score"].describe())

# IBAN format is locale-correct
print(tables["accounts"]["iban"].head())  # BR## format
```

## Common use cases

- **Fraud detection ML**: generate training datasets with precise class imbalances (1% fraud for baseline, 10% fraud for stress-testing) without touching production transactions
- **Credit scoring model development**: get customers with realistic FICO distributions across KYC verification states
- **Anti-money laundering (AML) testing**: generate transaction graphs with configurable anomaly rates for rule engine validation
- **Open banking API testing**: seed test accounts with realistic transaction histories before connecting to sandbox providers
- **Regulatory sandbox**: replace real customer PII with synthetic equivalents that preserve statistical properties for compliance testing
- **Payment infrastructure load testing**: generate millions of transactions with valid FK references to stress-test processing pipelines

## Advanced: fraud scenario curves

Generate a dataset where fraud spikes during a specific period, useful for training models on temporal fraud patterns:

```python
tables = misata.generate(
    "Fintech with 5k customers — fraud spike in March due to phishing campaign, "
    "normal rate 1%, March rate 8%, back to normal by April",
    rows=5000,
    seed=42,
)
```

## Advanced: multi-locale fintech

```python
# German banking — EUR, German IBANs (DE##...), German names
tables = misata.generate("German neo-bank with 3k customers, SEPA payments", rows=3000)

# US fintech — USD, US credit scores, SSN-format verification
tables = misata.generate("US lending fintech with 5k customers, FICO scoring", rows=5000)

# Indian fintech — INR, UPI payments, Aadhaar verification
tables = misata.generate("Indian fintech with UPI payments and 2k customers", rows=2000)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "Fintech with 5k customers and 2% fraud rate",
    min_quality_score=85,
    smart_correlations=True,  # auto-adds credit_score↔loan_amount correlation
    rows=5000,
    seed=42,
)
```

## Privacy and compliance

Misata generates fully synthetic data, no real customer records, no real account numbers, no real transaction data. All IBANs are format-correct but not valid real bank accounts. All names, emails, and dates of birth are generated, not sampled from real people. Safe to use in development, staging, and demo environments without data protection review.

## Related guides

- [Multi-table Synthetic Data](../guides/multi-table-synthetic-data.md)
- [Anomaly Injection](../guides/anomaly-injection.md)
- [Localisation](../localisation.md)
- [Database Seeding in Python](../guides/database-seeding-python.md)
- [Faker vs SDV vs Misata](../guides/faker-vs-sdv-vs-misata.md)
