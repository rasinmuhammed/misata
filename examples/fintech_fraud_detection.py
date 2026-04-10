"""
Fintech Fraud Detection Dataset
================================
Generates a realistic fintech dataset: customers → accounts → transactions.
Demonstrates domain-realistic distributions — credit scores match real-world
FICO statistics, transaction types follow Zipf's law, fraud rate is calibrated.

Run:
    python examples/fintech_fraud_detection.py
"""

import warnings
warnings.filterwarnings("ignore")

import misata
import pandas as pd
import numpy as np

# ── Generate ──────────────────────────────────────────────────────────────────

tables = misata.generate(
    "A fintech company with 2000 customers and banking transactions.",
    rows=2000,
    seed=42,
)

customers    = tables["customers"]
accounts     = tables["accounts"]
transactions = tables["transactions"]

print()
print("━" * 62)
print("  Misata — Fintech Fraud Detection Demo")
print("━" * 62)
print(f"  Customers:    {len(customers):>7,}")
print(f"  Accounts:     {len(accounts):>7,}")
print(f"  Transactions: {len(transactions):>7,}")
print()

# ── Referential integrity ─────────────────────────────────────────────────────

cust_ids  = set(customers["customer_id"])
acct_ids  = set(accounts["account_id"])
orphan_accounts = (~accounts["customer_id"].isin(cust_ids)).sum()
orphan_txns     = (~transactions["account_id"].isin(acct_ids)).sum()

print("  Referential integrity")
print(f"  {'customers → accounts':<30} {'✓ 0 orphans' if orphan_accounts == 0 else f'✗ {orphan_accounts} orphans':>18}")
print(f"  {'accounts → transactions':<30} {'✓ 0 orphans' if orphan_txns == 0 else f'✗ {orphan_txns} orphans':>18}")
print()

# ── Credit score distribution (real FICO: mean≈714, std≈82) ──────────────────

cs = customers["credit_score"].dropna()
print("  Credit score distribution  (real-world FICO: mean≈680–720, std≈70–90)")
print(f"  {'Metric':<12} {'Generated':>12}  {'Real-world':>12}")
print(f"  {'─'*12}  {'─'*12}  {'─'*12}")
print(f"  {'Mean':<12} {cs.mean():>12.0f}  {'680–720':>12}")
print(f"  {'Std dev':<12} {cs.std():>12.0f}  {'70–90':>12}")
print(f"  {'Min':<12} {cs.min():>12.0f}  {'300':>12}")
print(f"  {'Max':<12} {cs.max():>12.0f}  {'850':>12}")

buckets = [(300,579,"Poor"),(580,669,"Fair"),(670,739,"Good"),(740,799,"Very Good"),(800,850,"Exceptional")]
print()
print(f"  {'Score range':<14} {'Band':<14} {'Share':>8}  {'Distribution'}")
for lo, hi, label in buckets:
    n   = ((cs >= lo) & (cs <= hi)).sum()
    pct = n / len(cs) * 100
    bar = "█" * int(pct / 2)
    print(f"  {lo}–{hi:<8}  {label:<14} {pct:>7.1f}%  {bar}")
print()

# ── Fraud rate ────────────────────────────────────────────────────────────────

fraud_rate = transactions["is_fraud"].mean() * 100
print(f"  Fraud rate:  {fraud_rate:.2f}%  (calibrated target: 2.00%)")
fraud_count = transactions["is_fraud"].sum()
print(f"  Fraud txns:  {fraud_count:,} / {len(transactions):,}")
print()

# ── Transaction types — Zipf law ──────────────────────────────────────────────

print("  Transaction types  (Zipf — one type dominates naturally)")
type_counts = transactions["transaction_type"].value_counts()
for ttype, count in type_counts.items():
    pct = count / len(transactions) * 100
    bar = "█" * int(pct / 2)
    print(f"  {ttype:<14} {bar:<25} {pct:>5.1f}%")

print()
print("━" * 62)
print()
