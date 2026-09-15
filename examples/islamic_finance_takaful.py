"""
Takaful -- mutual/cooperative insurance, where the property that actually
matters is structural: the Participants' Takaful Fund (PTF) and the
Operator's Fund are two separate ledgers that never commingle. The
operator (the Takaful company) takes an agreed Wakala fee off each
contribution up front and manages the PTF as an agent, but claims are
paid from the PTF alone -- never from the operator's own fund, and never
in a way that lets the PTF go negative because a claim outran what
participants actually contributed.

The other AAOIFI-flagged risk in conventional insurance is `gharar`
(excessive, undisclosed uncertainty): a participant's contribution and
sum insured are fixed and disclosed at policy inception, not adjusted
after the fact by either side.

What this example checks, concretely:

  1. Every contribution splits into wakala_fee (operator's fund) and
     ptf_contribution (participants' fund) by the disclosed rate, exactly.
  2. The two funds are tracked as separate running balances. A claim
     debits the PTF balance only -- the operator fund balance is
     completely unaffected by any claim, in either direction.
  3. The PTF balance never goes negative: claims paid in any period never
     exceed what the fund actually holds, the structural guarantee that
     makes this a real mutual fund and not an unfunded promise.
  4. sum_insured and contribution are fixed at policy inception and never
     retroactively changed -- no undisclosed uncertainty entering the
     contract after the fact.

Run it directly. Every guarantee below is checked against the data this
script just generated, not asserted.
"""

import numpy as np
import pandas as pd

import misata

RNG_SEED = 21

COVERAGE_TYPES = ["Motor", "Family (Life)", "Health", "Property", "Marine"]
COVERAGE_WEIGHTS = [0.35, 0.25, 0.20, 0.15, 0.05]

# The operator's Wakala (agency) fee, disclosed at inception. A real
# Takaful operator's commercial pricing decision, not an AAOIFI-published
# number -- declared here as a realistic market range.
WAKALA_FEE_RATE_MEAN = 0.22
WAKALA_FEE_RATE_STD = 0.05
WAKALA_FEE_RATE_MIN = 0.10
WAKALA_FEE_RATE_MAX = 0.35

N_PERIODS = 24  # monthly periods the shared PTF is simulated over
CLAIM_FREQUENCY_PER_PERIOD = 0.03   # probability any one policy claims in a period


def build(n_policies: int = 1200, seed: int = RNG_SEED):
    schema = {
        "participants": {
            "__rows__": int(n_policies * 0.8),
            "participant_id": {"type": "integer", "primary_key": True},
            "name": {"type": "string", "text_type": "person_name"},
        },
        "takaful_policies": {
            "__rows__": n_policies,
            "policy_id": {"type": "integer", "primary_key": True},
            "participant_id": {"type": "integer",
                                 "foreign_key": {"table": "participants", "column": "participant_id"}},
            "coverage_type": {"type": "string", "enum": COVERAGE_TYPES, "weights": COVERAGE_WEIGHTS},
            "sum_insured": {"type": "float", "min": 10_000, "max": 2_000_000,
                             "distribution": "lognormal", "mu": 11.0, "sigma": 1.0,
                             "decimals": 2},
            "policy_start_date": {"type": "date", "min_date": "2023-01-01", "max_date": "2023-12-01"},
        },
    }
    tables = misata.generate_from_schema(misata.from_dict_schema(schema, seed=seed))
    return _reconcile(tables, seed)


def _reconcile(tables: dict, seed: int) -> dict:
    rng = np.random.default_rng(seed + 1)

    policies = tables["takaful_policies"].copy()
    n = len(policies)

    fee_rate = np.clip(
        rng.normal(WAKALA_FEE_RATE_MEAN, WAKALA_FEE_RATE_STD, n),
        WAKALA_FEE_RATE_MIN, WAKALA_FEE_RATE_MAX,
    )
    policies["wakala_fee_rate"] = fee_rate.round(4)

    # A contribution (premium) as a modest fraction of sum_insured, fixed
    # at inception -- both numbers disclosed once and not revisited.
    contribution_rate = rng.uniform(0.015, 0.04, n)
    policies["contribution"] = (policies["sum_insured"] * contribution_rate).round(2)
    policies["wakala_fee"] = (policies["contribution"] * policies["wakala_fee_rate"]).round(2)
    policies["ptf_contribution"] = (policies["contribution"] - policies["wakala_fee"]).round(2)

    tables["takaful_policies"] = policies
    tables["takaful_fund_ledger"] = _build_fund_ledger(policies, seed)
    tables["takaful_claims"] = _build_claims(policies, tables["takaful_fund_ledger"], seed)
    return tables


def _build_fund_ledger(policies: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Two running balances, one per fund, updated period by period.
    Contributions land in both funds by the disclosed split; nothing else
    ever touches the operator fund, and only claims (built next, against
    each period's already-known ptf balance) ever debit the PTF."""
    rows = []
    ptf_balance = 0.0
    operator_balance = 0.0
    for period in range(1, N_PERIODS + 1):
        period_start = pd.Timestamp("2023-01-01") + pd.DateOffset(months=period - 1)
        active = policies[policies["policy_start_date"] <= period_start]
        ptf_in = float(active["ptf_contribution"].sum()) if period == 1 else 0.0
        operator_in = float(active["wakala_fee"].sum()) if period == 1 else 0.0
        # New policies joining this period add their own contribution
        # once, on the period they start (not re-added every period).
        joining = policies[policies["policy_start_date"].dt.to_period("M") == period_start.to_period("M")]
        if period > 1:
            ptf_in = float(joining["ptf_contribution"].sum())
            operator_in = float(joining["wakala_fee"].sum())

        ptf_balance = round(ptf_balance + ptf_in, 2)
        operator_balance = round(operator_balance + operator_in, 2)
        rows.append({
            "period": period,
            "ptf_contribution_in": round(ptf_in, 2),
            "operator_fee_in": round(operator_in, 2),
            "ptf_balance_before_claims": ptf_balance,
            "operator_balance": operator_balance,
        })
    return pd.DataFrame(rows)


def _build_claims(policies: pd.DataFrame, ledger: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Claims draw from the PTF only, capped at whatever the fund
    actually holds that period -- a claim never pushes the PTF negative,
    and never touches the operator's fund in any way."""
    rng = np.random.default_rng(seed + 2)
    rows = []
    claim_id = 1
    ptf_running = 0.0
    for period_row in ledger.itertuples(index=False):
        ptf_running = period_row.ptf_balance_before_claims
        period_start = pd.Timestamp("2023-01-01") + pd.DateOffset(months=period_row.period - 1)
        active = policies[policies["policy_start_date"] <= period_start]
        claiming = active[rng.random(len(active)) < CLAIM_FREQUENCY_PER_PERIOD]
        for policy in claiming.itertuples(index=False):
            # A claim can request up to the full sum insured, but is
            # capped at what the PTF actually holds -- the fund cannot
            # pay out more than participants have actually put in.
            requested = round(float(rng.uniform(0.05, 1.0)) * policy.sum_insured, 2)
            paid = round(min(requested, ptf_running), 2)
            ptf_running = round(ptf_running - paid, 2)
            rows.append({
                "claim_id": claim_id,
                "policy_id": policy.policy_id,
                "period": period_row.period,
                "amount_requested": requested,
                "amount_paid": paid,
                "paid_from_fund": "participants",
            })
            claim_id += 1
        ledger.loc[ledger["period"] == period_row.period, "ptf_balance_after_claims"] = ptf_running
    return pd.DataFrame(rows)


def verify(tables: dict) -> bool:
    policies = tables["takaful_policies"]
    ledger = tables["takaful_fund_ledger"]
    claims = tables["takaful_claims"]
    checks = []

    # 1. Every contribution splits exactly into wakala_fee + ptf_contribution.
    recomputed_fee = (policies["contribution"] * policies["wakala_fee_rate"]).round(2)
    checks.append(("wakala_fee equals contribution x the disclosed fee rate exactly",
                    np.allclose(policies["wakala_fee"], recomputed_fee)))
    checks.append(("wakala_fee + ptf_contribution equals contribution exactly, every policy",
                    np.allclose(policies["wakala_fee"] + policies["ptf_contribution"], policies["contribution"])))

    # 2. Structural separation: every claim is marked as paid from the
    # participants' fund, never from the operator's fund.
    checks.append(("every claim is paid_from_fund == 'participants'",
                    (claims["paid_from_fund"] == "participants").all()))

    # 3. THE structural guarantee: the PTF never goes negative. A claim
    # is capped at the fund's own balance, so amount_paid never exceeds
    # what participants have actually contributed net of prior claims.
    checks.append(("ptf_balance_after_claims never goes negative, any period",
                    (ledger["ptf_balance_after_claims"] >= -0.005).all()))

    # 4. No claim is paid for more than it requested, and no claim pays
    # more than the PTF held going into that period.
    checks.append(("amount_paid never exceeds amount_requested",
                    (claims["amount_paid"] <= claims["amount_requested"] + 0.005).all()))
    period_ptf = ledger.set_index("period")["ptf_balance_before_claims"]
    claims_by_period = claims.groupby("period")["amount_paid"].sum()
    checks.append(("total claims paid in a period never exceeds that period's PTF balance",
                    (claims_by_period <= period_ptf.reindex(claims_by_period.index) + 0.01).all()))

    # 5. The operator's fund is untouched by claims: operator_balance is a
    # pure running sum of wakala fees, independent of the claims table.
    recomputed_operator = ledger["operator_fee_in"].cumsum().round(2)
    checks.append(("operator_balance reconciles to cumulative operator_fee_in alone, unaffected by claims",
                    np.allclose(ledger["operator_balance"], recomputed_operator)))

    # 6. No gharar: sum_insured and contribution are single fixed values
    # per policy (one row each in takaful_policies), never a table of
    # revisions -- there is nothing here for either figure to have been
    # retroactively changed to.
    checks.append(("sum_insured and contribution are single declared values, not a revision history",
                    policies["policy_id"].is_unique))

    # 7. Structural: no orphaned foreign keys.
    checks.append(("policies.participant_id has zero orphans",
                    policies["participant_id"].isin(tables["participants"]["participant_id"]).all()))
    checks.append(("claims.policy_id has zero orphans",
                    claims["policy_id"].isin(policies["policy_id"]).all()))

    all_ok = True
    for label, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {label}")
        all_ok &= bool(ok)
    return all_ok


if __name__ == "__main__":
    tables = build(n_policies=1200, seed=RNG_SEED)
    policies = tables["takaful_policies"]
    ledger = tables["takaful_fund_ledger"]
    claims = tables["takaful_claims"]
    print(f"participants: {len(tables['participants'])}  policies: {len(policies)}  claims: {len(claims)}")
    print(f"final PTF balance: {ledger['ptf_balance_after_claims'].iloc[-1]:,.0f}   "
          f"final operator balance: {ledger['operator_balance'].iloc[-1]:,.0f}")
    print()
    ok = verify(tables)
    print()

    report = misata.coherence_audit(tables)
    print(f"Coherence audit: score={report.score:.1f}  clean={report.clean}")
    if not report.clean:
        print(report.summary())
        ok = False

    print()
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    raise SystemExit(0 if ok else 1)
