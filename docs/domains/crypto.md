---
title: Generate Crypto & Web3 Synthetic Data in Python | Misata
description: Generate realistic crypto and Web3 synthetic datasets in Python, wallets, tokens, blockchain transactions, and price history with correct hex addresses, gas fee distributions, and transaction type mixes. No real on-chain data required.
---

# Generate Crypto and Web3 Synthetic Data in Python

Blockchain analytics, DeFi protocol testing, and on-chain ML models all require transaction data that looks real: 0x-prefixed hex wallet addresses, gas fees that follow lognormal distributions reflecting network congestion variance, and transaction type mixes that match mainnet patterns (transfer 60%, swap 25%, stake 10%, bridge 5%). Misata generates a four-table Web3 dataset, wallets, tokens, transactions, and price history, with all of this built in.

Every `tx_hash` is unique. Every wallet address is correct EVM format. Token price records are temporally ordered. Transaction amounts are lognormal with a heavy tail reflecting DeFi's whale-dominated value distribution.

```python
import misata

tables = misata.generate(
    "A crypto exchange with wallets, blockchain transactions, and token prices",
    rows=2000,
    seed=42,
)
print(list(tables.keys()))   # ['wallets', 'tokens', 'transactions', 'token_prices']
print(tables["wallets"][["chain", "balance_usd"]].groupby("chain").describe())
```

## What Misata generates

Four tables: `wallets`, `tokens`, `transactions` (referencing wallets and tokens), and `token_prices` (time-series price records per token). Full FK integrity throughout.

### Tables and columns

| Table | Key columns |
|:--|:--|
| `wallets` | `wallet_id`, `address`, `chain`, `balance_usd`, `created_at`, `wallet_type` |
| `tokens` | `token_id`, `symbol`, `name`, `chain`, `contract_address`, `market_cap` |
| `transactions` | `tx_id`, `wallet_id`, `token_id`, `tx_hash`, `type`, `amount`, `gas_fee`, `timestamp`, `status` |
| `token_prices` | `price_id`, `token_id`, `price_usd`, `volume_24h`, `market_cap`, `recorded_at` |

### Realistic distributions

- **Wallet addresses** are 0x-prefixed hex strings of the correct 40-character EVM format
- **Gas fees** lognormal, realistic variance from low-congestion to peak-gas periods
- **Transaction types** match mainnet proportions: transfer 60%, swap 25%, stake 10%, bridge 5%
- **`balance_usd`** is Pareto-distributed, most wallets hold small amounts, a few whales hold most of the value
- **Price volatility** reflects realistic crypto price behavior with high variance

## Quick start

```python
import misata

tables = misata.generate(
    "An Ethereum DeFi protocol with wallets, swaps, and staking transactions",
    rows=2000,
    seed=42,
)

# Transaction type distribution
print(tables["transactions"]["type"].value_counts(normalize=True))

# Gas fee stats by transaction type
print(tables["transactions"].groupby("type")["gas_fee"].describe())

# Wallet address format check
print(tables["wallets"]["address"].head())  # all start with 0x
assert tables["wallets"]["address"].str.startswith("0x").all()
```

## Common use cases

- **Blockchain analytics tool development**: build wallet profiling, token flow, and transaction clustering dashboards before indexing a live node
- **DeFi protocol backend testing**: seed a test environment with wallets, token balances, and transaction histories for contract interaction testing
- **Transaction classification models**: train supervised classifiers to distinguish transfers, swaps, stakes, and bridges using realistic feature distributions
- **Fraud and anomaly detection**: generate normal transaction baselines with correct distributions, then inject anomalous patterns for detection algorithm development
- **Price feed and oracle testing**: use `token_prices` with realistic volume and market cap to test price feed consumers and TWAP calculations
- **Portfolio analytics development**: test P&L calculations, position tracking, and performance attribution against multi-token wallet histories

## Advanced: DeFi activity narrative

```python
tables = misata.generate(
    "DeFi protocol with high swap volume in Q1 liquidity mining campaign, "
    "declining activity in Q2, bear market transaction drop in Q3",
    rows=5000,
    seed=42,
)
```

## Advanced: multi-chain generation

```python
# Ethereum and Polygon focused
tables = misata.generate("Multi-chain DEX with Ethereum and Polygon wallets", rows=2000)

# Solana ecosystem — different address format, SOL-native tokens
tables = misata.generate("Solana DeFi protocol with wallet transactions", rows=1500)
```

## Advanced: quality-guaranteed generation

```python
tables = misata.generate(
    "Crypto exchange with 2k wallets",
    min_quality_score=85,
    smart_correlations=True,  # auto-adds gas_fee↔transaction_type complexity
    rows=2000,
    seed=42,
)
```

## Related guides

- [Multi-table Synthetic Data](../guides/multi-table-synthetic-data.md)
- [Anomaly Injection](../guides/anomaly-injection.md)
- [Database Seeding in Python](../guides/database-seeding-python.md)
- [Faker vs SDV vs Misata](../guides/faker-vs-sdv-vs-misata.md)
