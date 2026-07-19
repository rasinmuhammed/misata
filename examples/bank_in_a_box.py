"""
Bank in a Box — GCC Retail Bank Demo
=====================================
Generates a complete synthetic UAE retail bank: customers → accounts →
transactions + loans. Every FK resolves, the fraud rate follows a declared
per-month curve exactly, rollups reconcile to the fils, and the whole dataset
passes the coherence audit before it ships.

This is increment A1 of the Bank-in-a-Box vertical (see the master build plan).
GCC vocabulary capsule (A2), calendar preset (A3), and fraud typologies (A4)
land on top of this schema.

Run:
    python examples/bank_in_a_box.py
"""

import os
import sys
import warnings

from pathlib import Path as _Path
CAPSULE_PATH = str(_Path(__file__).resolve().parent / "gcc_banking.capsule.json")

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # for fraud_typologies

import misata
import pandas as pd

SEED = 42

EMIRATES = ["Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Ras Al Khaimah", "Fujairah", "Umm Al Quwain"]
EMIRATE_W = [0.42, 0.28, 0.17, 0.05, 0.04, 0.03, 0.01]

NATIONALITIES = ["India", "UAE", "Pakistan", "Philippines", "Egypt", "Bangladesh", "United Kingdom", "Jordan"]
NATIONALITY_W = [0.30, 0.115, 0.14, 0.08, 0.07, 0.07, 0.045, 0.18]

schema_dict = {
    "customers": {
        "__rows__": 8000,
        "customer_id": {"type": "integer", "primary_key": True},
        "full_name": {"type": "string", "text_type": "person_name"},
        "emirates_id": {"type": "string", "pattern": "784-\\d{4}-\\d{7}-\\d"},
        "nationality": {"type": "string", "enum": NATIONALITIES, "probabilities": NATIONALITY_W},
        "emirate": {"type": "string", "enum": EMIRATES, "probabilities": EMIRATE_W},
        "segment": {"type": "string", "enum": ["mass", "premium", "private"], "probabilities": [0.80, 0.17, 0.03]},
        "monthly_salary_aed": {
            "type": "float", "distribution": "lognormal",
            "mu": 8.7, "sigma": 0.5, "min": 2500, "max": 400000, "decimals": 2,
            # Segment-stratified: mass ≈ 6K median, premium ≈ 20K, private ≈ 80K.
            "profiles": [
                {"when": "segment == 'premium'", "distribution": "lognormal", "mu": 9.9, "sigma": 0.45},
                {"when": "segment == 'private'", "distribution": "lognormal", "mu": 11.3, "sigma": 0.5},
            ],
        },
        "kyc_risk": {"type": "string", "enum": ["low", "medium", "high"], "probabilities": [0.86, 0.11, 0.03]},
        "onboarded_date": {"type": "date", "min_date": "2019-01-01", "max_date": "2025-06-30"},
    },
    "accounts": {
        "__rows__": 11000,
        "account_id": {"type": "integer", "primary_key": True},
        "customer_id": {"type": "foreign_key", "foreign_key": {"table": "customers", "column": "customer_id"}},
        "iban": {"type": "string", "pattern": "AE\\d{21}", "unique": True},
        "account_type": {
            "type": "string",
            "enum": ["current", "savings", "salary", "call_deposit"],
            "probabilities": [0.38, 0.27, 0.30, 0.05],
        },
        "currency": {"type": "string", "enum": ["AED", "USD", "EUR"], "probabilities": [0.90, 0.08, 0.02]},
        "status": {"type": "string", "enum": ["active", "dormant", "closed"], "probabilities": [0.87, 0.09, 0.04]},
        "opened_date": {"type": "date", "min_date": "2019-01-01", "max_date": "2025-06-30"},
        # Exact rollups: these reconcile with the transactions table under JOIN, to the fils.
        "txn_count": {
            "type": "integer",
            "rollup": {"from_table": "transactions", "fk": "account_id", "agg": "count", "column": "txn_id"},
        },
        "total_spend_aed": {
            "type": "float", "decimals": 2,
            "rollup": {"from_table": "transactions", "fk": "account_id", "agg": "sum", "column": "amount_aed"},
        },
    },
    "transactions": {
        "__rows__": 90000,
        "txn_id": {"type": "integer", "primary_key": True},
        "account_id": {"type": "foreign_key", "foreign_key": {"table": "accounts", "column": "account_id"}},
        "txn_ts": {"type": "datetime", "min_date": "2025-01-01", "max_date": "2025-06-30"},
        "channel": {
            "type": "string",
            "enum": ["card_pos", "card_online", "transfer", "atm", "wallet", "standing_order"],
            "probabilities": [0.34, 0.22, 0.18, 0.12, 0.10, 0.04],
        },
        # No enum and no declared distribution below — the gcc-banking capsule
        # drives both: category is conditioned on channel (an ATM row is Cash,
        # a standing order is Utilities/Telecom), and each amount draws
        # log-uniform inside its category's AED band (fuel is never 80,000;
        # gold is never 12). Explicit shapes would override the capsule.
        "merchant_category": {"type": "string"},
        # Filled from the gcc-banking capsule, conditioned on merchant_category:
        # a Fuel transaction gets ADNOC/ENOC, never Damas Jewellery.
        "merchant_name": {"type": "string"},
        # amount_aed comes from a custom generator (below): log-uniform inside
        # the capsule's per-category band, with ATM/Cash snapped to 100-AED
        # notes — real ATMs don't dispense AED 892.67. Drawn during generation
        # so the account rollups still reconcile to the fils.
        "amount_aed": {"type": "float", "decimals": 2},
        "description": {"type": "string"},
        "is_fraud": {"type": "boolean"},
    },
    "loans": {
        "__rows__": 2600,
        "loan_id": {"type": "integer", "primary_key": True},
        "customer_id": {"type": "foreign_key", "foreign_key": {"table": "customers", "column": "customer_id"}},
        "loan_type": {
            "type": "string",
            "enum": ["personal", "auto", "mortgage", "credit_card"],
            "probabilities": [0.42, 0.24, 0.14, 0.20],
        },
        "principal_aed": {
            "type": "float", "distribution": "lognormal",
            "mu": 11.2, "sigma": 0.9, "min": 5000, "max": 5000000, "decimals": 2,
        },
        "outstanding_aed": {"type": "float", "formula": "principal_aed * 0.62", "decimals": 2},
        "status": {"type": "string", "enum": ["performing", "watchlist", "npl"], "probabilities": [0.925, 0.05, 0.025]},
        "originated_date": {"type": "date", "min_date": "2020-01-01", "max_date": "2025-06-30"},
    },
    # Declared fraud-rate curve: the answer key. Monthly rates hold EXACTLY,
    # so an evalpack question like "true fraud rate in March 2025" has one
    # verifiable correct answer.
    "__rate_curves__": [
        {
            "table": "transactions",
            "column": "is_fraud",
            "time_column": "txn_ts",
            "rate_points": [
                {"period": "2025-01", "rate": 0.020},
                {"period": "2025-02", "rate": 0.022},
                {"period": "2025-03", "rate": 0.025},
                {"period": "2025-04", "rate": 0.028},
                {"period": "2025-05", "rate": 0.032},
                {"period": "2025-06", "rate": 0.035},
            ],
        }
    ],
}


def _load_bands():
    import json

    cap = json.load(open(CAPSULE_PATH))
    return cap["price_bands"]["amount_aed"]["bands"]


def _amount_aed(partial_df, context_tables):
    """Per-category amount, log-uniform inside the capsule band, ATM in notes.

    Reads the capsule's own bands so there is one source of truth. Cash /
    ATM rows snap to the nearest AED 100 (real dispensers hold 100 and 500
    notes); everything else keeps 2-decimal retail precision.
    """
    import numpy as np

    bands = _load_bands()
    rng = np.random.default_rng(SEED + 11)
    n = len(partial_df)
    cats = partial_df["merchant_category"].astype(str).values
    channel = partial_df["channel"].astype(str).values
    lo_all = min(b[0] for b in bands.values())
    hi_all = max(b[1] for b in bands.values())

    out = np.empty(n, dtype=float)
    for i in range(n):
        lo, hi = bands.get(cats[i], (lo_all, hi_all))
        # log-uniform: cheap-heavy, like real card spend
        val = float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
        if channel[i] == "atm" or cats[i] == "Cash":
            val = max(100.0, round(val / 100.0) * 100.0)
            out[i] = val
        else:
            out[i] = round(val, 2)
    return out


def _txn_timestamps(partial_df, context_tables):
    """Transaction timestamps with the rhythms a GCC banker expects to see.

    Three real signals, all seeded and reproducible:
      - Weekend is Friday-Saturday (not Sat-Sun): those days carry more
        discretionary card spend.
      - Salary-run window (25th-28th): the WPS payroll cycle lands salaries,
        so transaction volume bumps in the last week of each month.
      - Ramadan 2025 (~1-30 March): spend shifts to post-Iftar evening hours;
        the rest of the year peaks late afternoon/early evening.
    Timestamps stay inside 2025-01-01..2025-06-30 so the declared monthly
    fraud-rate curve still binds exactly on this column.
    """
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(SEED + 5)
    n = len(partial_df)
    start = pd.Timestamp("2025-01-01")
    end = pd.Timestamp("2025-06-30")
    days = pd.date_range(start, end, freq="D")

    # Per-day weight: weekend (Fri=4, Sat=5) heavier, salary window heavier.
    dow = days.dayofweek.values  # Mon=0 .. Sun=6
    dom = days.day.values
    w = np.ones(len(days))
    w[(dow == 4) | (dow == 5)] *= 1.6            # Fri/Sat weekend
    w[(dom >= 25) & (dom <= 28)] *= 1.5          # WPS salary-run bump
    w = w / w.sum()

    chosen = rng.choice(len(days), size=n, p=w)
    picked = days[chosen]
    ram = np.asarray(picked.month == 3)  # March 2025 ≈ Ramadan

    # Hour: Ramadan evenings post-Iftar (19-25 → wraps past midnight),
    # otherwise a late-afternoon/evening retail peak (~11-22).
    hours = np.empty(n, dtype=int)
    n_ram = int(ram.sum())
    if n_ram:
        hours[ram] = (rng.normal(21.5, 2.2, n_ram).round().astype(int)) % 24
    reg = ~ram
    n_reg = int(reg.sum())
    if n_reg:
        hours[reg] = np.clip(rng.normal(16.5, 3.5, n_reg).round().astype(int), 6, 23)

    mins = rng.integers(0, 60, n)
    secs = rng.integers(0, 60, n)
    ts = (
        pd.to_datetime(picked)
        + pd.to_timedelta(hours, unit="h")
        + pd.to_timedelta(mins, unit="m")
        + pd.to_timedelta(secs, unit="s")
    )
    return ts.values


def _statement_description(partial_df, context_tables):
    """Statement-line text the way UAE bank statements actually print it.

    Vectorised custom generator: derives each line from the row's channel and
    merchant so the text never contradicts its own row ("ATM CASH WDL" on a
    card_online row would be an instant tell).
    """
    import numpy as np

    rng = np.random.default_rng(SEED + 7)
    n = len(partial_df)
    channel = partial_df["channel"].astype(str).values
    merchant = (
        partial_df["merchant_name"].astype(str).str.upper().values
        if "merchant_name" in partial_df
        else np.full(n, "MERCHANT")
    )
    city = rng.choice(["DUBAI", "ABU DHABI", "SHARJAH", "AJMAN", "AL AIN"], size=n, p=[0.44, 0.28, 0.18, 0.05, 0.05])
    ref = rng.integers(10**7, 10**8, size=n)
    terminal = rng.integers(1000, 9999, size=n)

    out = np.empty(n, dtype=object)
    for i in range(n):
        ch = channel[i]
        if ch == "card_pos":
            out[i] = f"POS PURCHASE {merchant[i]} {city[i]} AE REF{ref[i]}"
        elif ch == "card_online":
            out[i] = f"ECOM PURCHASE {merchant[i]} DUBAI AE REF{ref[i]}"
        elif ch == "atm":
            out[i] = f"ATM CASH WDL {terminal[i]} {city[i]} AE"
        elif ch == "transfer":
            out[i] = f"IPI TRANSFER {merchant[i]} REF{ref[i]}"
        elif ch == "wallet":
            out[i] = f"WALLET PAYMENT {merchant[i]} REF{ref[i]}"
        else:  # standing_order
            out[i] = f"SO PAYMENT {merchant[i]} REF{ref[i]}"
    return out


def main() -> None:
    schema = misata.from_dict_schema(schema_dict, seed=SEED)
    tables = misata.generate_from_schema(
        schema,
        capsule=CAPSULE_PATH,
        custom_generators={
            "transactions": {
                "txn_ts": _txn_timestamps,
                "amount_aed": _amount_aed,
                "description": _statement_description,
            }
        },
    )

    customers = tables["customers"]
    accounts = tables["accounts"]
    txns = tables["transactions"]
    loans = tables["loans"]

    w = 66
    print()
    print("━" * w)
    print("  Bank in a Box — GCC Retail Bank (Misata, seed=42)")
    print("━" * w)
    print(f"  Customers:    {len(customers):>9,}")
    print(f"  Accounts:     {len(accounts):>9,}")
    print(f"  Transactions: {len(txns):>9,}")
    print(f"  Loans:        {len(loans):>9,}")
    print()

    # ── Referential integrity ────────────────────────────────────────────
    cust_ids = set(customers["customer_id"])
    acct_ids = set(accounts["account_id"])
    checks = [
        ("customers → accounts", (~accounts["customer_id"].isin(cust_ids)).sum()),
        ("accounts → transactions", (~txns["account_id"].isin(acct_ids)).sum()),
        ("customers → loans", (~loans["customer_id"].isin(cust_ids)).sum()),
    ]
    print("  Referential integrity")
    for label, orphans in checks:
        mark = "✓ 0 orphans" if orphans == 0 else f"✗ {orphans} orphans"
        print(f"    {label:<28} {mark:>18}")
    print()

    # ── Declared fraud-rate curve vs. generated ──────────────────────────
    monthly = (
        txns.assign(month=pd.to_datetime(txns["txn_ts"]).dt.to_period("M").astype(str))
        .groupby("month")["is_fraud"]
        .agg(["mean", "sum", "count"])
    )
    declared = {p["period"]: p["rate"] for p in schema_dict["__rate_curves__"][0]["rate_points"]}
    print("  Fraud-rate curve  (declared vs. generated, per month)")
    print(f"    {'Month':<10} {'Declared':>9} {'Generated':>10} {'Fraud txns':>11}")
    max_dev = 0.0
    for month, row in monthly.iterrows():
        target = declared.get(month)
        if target is None:
            continue
        dev = abs(row["mean"] - target)
        max_dev = max(max_dev, dev)
        print(f"    {month:<10} {target:>8.2%} {row['mean']:>9.2%} {int(row['sum']):>8,}/{int(row['count']):,}")
    print(f"    Max deviation from declared curve: {max_dev:.4%}")
    print()

    # ── Rollup reconciliation (to the fils) ──────────────────────────────
    spend = txns.groupby("account_id")["amount_aed"].sum().round(2)
    joined = accounts.set_index("account_id")["total_spend_aed"].round(2)
    recon = (joined.subtract(spend, fill_value=0.0).abs() < 0.005)
    counts = txns.groupby("account_id")["txn_id"].count()
    cnt_ok = (accounts.set_index("account_id")["txn_count"].subtract(counts, fill_value=0) == 0)
    print("  Rollup reconciliation (accounts vs. their transactions)")
    print(f"    total_spend_aed exact under JOIN:  {recon.sum():,}/{len(recon):,} accounts")
    print(f"    txn_count exact under JOIN:        {cnt_ok.sum():,}/{len(cnt_ok):,} accounts")
    print()

    # ── Format & demographic spot checks ─────────────────────────────────
    iban_ok = accounts["iban"].str.fullmatch(r"AE\d{21}").all()
    eid_ok = customers["emirates_id"].str.fullmatch(r"784-\d{4}-\d{7}-\d").all()
    print("  Format checks")
    print(f"    IBAN matches AE + 21 digits:       {'✓ all' if iban_ok else '✗'}")
    print(f"    Emirates ID matches 784-…:         {'✓ all' if eid_ok else '✗'}")
    print()
    print("  Nationality mix (declared UAE demographics)")
    for nat, share in customers["nationality"].value_counts(normalize=True).head(5).items():
        print(f"    {nat:<16} {share:>6.1%}")
    print()
    print("  Sample customers  (names must match nationality — engine-repaired)")
    cols = ["full_name", "nationality", "emirate", "segment"]
    for _, r in customers[cols].head(6).iterrows():
        print(f"    {r.full_name:<28} {r.nationality:<14} {r.emirate:<12} {r.segment}")
    print()

    # ── Merchant ⇄ category coherence (capsule conditional vocab) ────────
    cat_map = {
        cat: set(names)
        for cat, names in __import__("json")
        .load(open(CAPSULE_PATH))["conditional_vocabularies"]["merchant_name"]["map"]
        .items()
    }
    in_map = txns.apply(lambda r: r["merchant_name"] in cat_map.get(r["merchant_category"], set()), axis=1)
    print(f"  Merchant ⇄ category coherence:  {in_map.mean():.1%} of transactions")
    print("    e.g.", ", ".join(
        f"{r.merchant_category}→{r.merchant_name}"
        for _, r in txns[["merchant_category", "merchant_name"]].drop_duplicates("merchant_category").head(4).iterrows()
    ))
    print()

    # ── Amounts inside per-category AED bands (capsule price bands) ──────
    bands = __import__("json").load(open(CAPSULE_PATH))["price_bands"]["amount_aed"]["bands"]
    ok = txns.apply(
        lambda r: bands[r["merchant_category"]][0] <= r["amount_aed"] <= bands[r["merchant_category"]][1]
        if r["merchant_category"] in bands else True,
        axis=1,
    )
    print(f"  Amounts within category band:   {ok.mean():.1%} of transactions")
    med = txns.groupby("merchant_category")["amount_aed"].median().sort_values()
    print(f"    Median AED — {med.index[0]}: {med.iloc[0]:,.0f} … {med.index[-1]}: {med.iloc[-1]:,.0f}")
    print()

    # ── Salary stratification by segment ─────────────────────────────────
    sal = customers.groupby("segment")["monthly_salary_aed"].median()
    print("  Median monthly salary by segment (AED)")
    for seg in ("mass", "premium", "private"):
        if seg in sal.index:
            print(f"    {seg:<10} {sal[seg]:>12,.0f}")
    print()

    # ── Statement descriptions ───────────────────────────────────────────
    print("  Sample statement lines")
    for _, r in txns[["channel", "description", "amount_aed"]].drop_duplicates("channel").head(6).iterrows():
        print(f"    {r.description:<52} AED {r.amount_aed:>10,.2f}")
    print()

    # ── Organized-fraud overlay + answer key (the moat) ──────────────────
    from fraud_typologies import plant_fraud_typologies, recompute_account_rollups

    plant = plant_fraud_typologies(transactions=txns, accounts=accounts, seed=SEED)
    txns = plant.transactions
    accounts = recompute_account_rollups(accounts, txns)  # books reconcile incl. rings

    print("  " + plant.summary().replace("\n", "\n  "))
    print()
    rings = txns[txns["fraud_case_id"].notna()]
    caught_by_naive = rings["is_fraud"].mean()
    print("  Answer key vs. the naive is_fraud flag")
    print(f"    Ring transactions planted:        {len(rings):>6,}")
    print(f"    Caught by naive is_fraud flag:    {caught_by_naive:>6.1%}  ← organized fraud evades it")
    print(f"    Recoverable from answer key:       {'100.0%':>6}  ← ground truth by construction")
    print()
    print("  Sample cases (a detection model is scored against these)")
    for _, r in plant.answer_key.head(3).iterrows():
        print(f"    {r.case_id:<12} {r.typology:<13} {r.n_accounts:>2} acct / {r.n_transactions:>2} txn  — {r.note}")
    print()

    # Re-verify integrity holds on the FINAL shipped table (rings included)
    final_orphans = (~txns["account_id"].isin(set(accounts["account_id"]))).sum()
    spend2 = txns.groupby("account_id")["amount_aed"].sum().round(2)
    recon2 = accounts.set_index("account_id")["total_spend_aed"].round(2).subtract(spend2, fill_value=0.0).abs().lt(0.005)
    print("  Post-overlay integrity (final shipped dataset)")
    print(f"    transactions → accounts orphans:  {final_orphans}")
    print(f"    txn_id still unique:              {txns['txn_id'].is_unique}")
    print(f"    rollups reconcile:                {recon2.sum():,}/{len(recon2):,} accounts")
    print()

    # ── Calendar rhythm (WPS salary window, Fri-Sat weekend, Ramadan) ────
    ts = pd.to_datetime(txns["txn_ts"])
    dow = ts.dt.dayofweek
    weekend_share = dow.isin([4, 5]).mean()          # Fri, Sat
    baseline = 2 / 7
    salary_win = ts.dt.day.between(25, 28)
    salary_daily = txns[salary_win].shape[0] / 4
    other_daily = txns[~salary_win].shape[0] / 26
    ram = ts.dt.month == 3
    ram_evening = ts[ram].dt.hour.between(19, 23).mean()
    non_ram_evening = ts[~ram].dt.hour.between(19, 23).mean()
    print("  Calendar rhythm")
    print(f"    Fri-Sat weekend share:   {weekend_share:>6.1%}  (flat calendar = {baseline:.1%})")
    print(f"    Salary-window daily vol:  {salary_daily:>6.0f}/day vs {other_daily:.0f}/day rest of month")
    print(f"    Ramadan evening spend:   {ram_evening:>6.1%}  vs {non_ram_evening:.1%} other months")
    print()

    # ── Coherence audit — the release gate ───────────────────────────────
    report = misata.coherence_audit(tables)
    print(f"  Coherence audit:  score={report.score:.1f}  clean={report.clean}")
    if not report.clean:
        for line in report.summary().splitlines():
            print(f"    {line}")
    print("━" * w)
    print()


if __name__ == "__main__":
    main()
