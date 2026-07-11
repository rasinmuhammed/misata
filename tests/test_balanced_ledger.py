"""Double-entry ledger invariant: per journal entry, debits == credits, exactly.

This is the identity no imitation synthesiser reproduces and no accounting
agent environment can do without. The contract: after generation, every
journal entry balances to the cent, the global trial balance nets to zero,
and no single ledger line carries both a debit and a credit.
"""

import numpy as np
import pandas as pd
import pytest

import misata
from misata.schema import Column, Constraint, Relationship, SchemaConfig, Table


def _ledger_schema(seed: int = 42, lines: int = 1500, entries: int = 500) -> SchemaConfig:
    return SchemaConfig(
        name="ledger",
        seed=seed,
        tables=[
            Table(name="accounts", row_count=20),
            Table(name="journal_entries", row_count=entries),
            Table(
                name="journal_lines",
                row_count=lines,
                constraints=[
                    Constraint(
                        name="double_entry",
                        type="balanced_ledger",
                        group_by=["entry_id"],
                        debit_column="debit",
                        credit_column="credit",
                    )
                ],
            ),
        ],
        columns={
            "accounts": [
                Column(name="account_id", type="int", unique=True,
                       distribution_params={"min": 1000, "max": 9999}),
                Column(name="account_name", type="text"),
            ],
            "journal_entries": [
                Column(name="entry_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 100000}),
                Column(name="entry_date", type="date",
                       distribution_params={"start": "2025-01-01", "end": "2025-12-31"}),
            ],
            "journal_lines": [
                Column(name="line_id", type="int", unique=True,
                       distribution_params={"min": 1, "max": 10_000_000}),
                Column(name="entry_id", type="foreign_key"),
                Column(name="account_id", type="foreign_key"),
                Column(name="debit", type="float",
                       distribution_params={"min": 0, "max": 5000, "decimals": 2}),
                Column(name="credit", type="float",
                       distribution_params={"min": 0, "max": 5000, "decimals": 2}),
            ],
        },
        relationships=[
            Relationship(parent_table="journal_entries", child_table="journal_lines",
                         parent_key="entry_id", child_key="entry_id"),
            Relationship(parent_table="accounts", child_table="journal_lines",
                         parent_key="account_id", child_key="account_id"),
        ],
    )


@pytest.fixture(scope="module")
def ledger():
    return misata.generate_from_schema(_ledger_schema())


class TestDoubleEntryInvariant:
    def test_every_entry_balances_to_the_cent(self, ledger):
        lines = ledger["journal_lines"]
        net = (lines.groupby("entry_id")["debit"].sum()
               - lines.groupby("entry_id")["credit"].sum()).round(2)
        assert (net == 0).all(), f"{(net != 0).sum()} entries do not balance"

    def test_global_trial_balance_is_zero(self, ledger):
        lines = ledger["journal_lines"]
        assert round(lines["debit"].sum() - lines["credit"].sum(), 2) == 0.0

    def test_no_line_is_both_debit_and_credit(self, ledger):
        lines = ledger["journal_lines"]
        both = ((lines["debit"] > 0) & (lines["credit"] > 0)).sum()
        assert both == 0, f"{both} lines carry both a debit and a credit"

    def test_every_populated_entry_has_at_least_two_lines(self, ledger):
        lines = ledger["journal_lines"]
        sizes = lines.groupby("entry_id").size()
        assert (sizes >= 2).all(), "a journal entry with a single line cannot balance"

    def test_fk_integrity_survives_entry_reassignment(self, ledger):
        lines, entries, accounts = (
            ledger["journal_lines"], ledger["journal_entries"], ledger["accounts"])
        assert lines["entry_id"].isin(entries["entry_id"]).all()
        assert lines["account_id"].isin(accounts["account_id"]).all()

    def test_reproducible_under_same_seed(self):
        a = misata.generate_from_schema(_ledger_schema(seed=7))
        b = misata.generate_from_schema(_ledger_schema(seed=7))
        pd.testing.assert_frame_equal(a["journal_lines"], b["journal_lines"])

    def test_balances_across_seeds(self):
        for seed in (1, 2, 3):
            lines = misata.generate_from_schema(_ledger_schema(seed=seed))["journal_lines"]
            net = (lines.groupby("entry_id")["debit"].sum()
                   - lines.groupby("entry_id")["credit"].sum()).round(2)
            assert (net == 0).all()
