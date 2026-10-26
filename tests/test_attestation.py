"""Attestation: an in-toto Statement that a dataset holds what its schema declared."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

import misata
from misata.attestation import (DSSE_FILE, ODCS_API_VERSION, PAYLOAD_TYPE, PREDICATE_TYPE,
                                STATEMENT_FILE, AttestationError, attest, derive_invariants,
                                to_odcs, to_openlineage)
from misata.attestation_verify import format_value

pytest.importorskip("duckdb")

SCHEMA = {
    "__outcome_curves__": [{
        "table": "orders", "column": "amount", "time_column": "order_date",
        "time_unit": "month", "value_mode": "absolute", "start_date": "2024-01-01",
        "avg_transaction_value": 40.0,
        "curve_points": [{"month": 1, "target_value": 20000.0},
                         {"month": 2, "target_value": 26000.0},
                         {"month": 3, "target_value": 31000.0}],
    }],
    "__rate_curves__": [{
        "table": "orders", "column": "is_gift", "time_column": "order_date",
        "time_unit": "month", "rate_points": [{"period": "2024-02", "rate": 0.07}],
    }],
    "customers": {
        "__rows__": 200,
        "customer_id": {"type": "integer", "primary_key": True},
        "email": {"type": "string", "unique": True},
    },
    "orders": {
        "order_id": {"type": "integer", "primary_key": True},
        "customer_id": {"type": "foreign_key",
                        "foreign_key": {"table": "customers", "column": "customer_id"}},
        "amount": {"type": "float", "min": 0},
        "order_date": {"type": "date"},
        "is_gift": {"type": "boolean"},
    },
}


@pytest.fixture(scope="module")
def schema():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return misata.from_dict_schema(SCHEMA, seed=5)


@pytest.fixture(scope="module")
def tables(schema):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return misata.generate_from_schema(schema)


def _write(tables, directory: Path, fmt: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        if fmt == "parquet":
            df.to_parquet(directory / f"{name}.parquet", index=False)
        else:
            df.to_csv(directory / f"{name}.csv", index=False)
    return directory


@pytest.mark.parametrize("fmt", ["csv", "parquet"])
def test_a_generated_dataset_passes(tables, schema, tmp_path, fmt):
    result = attest(_write(tables, tmp_path, fmt), schema)
    assert result.passed, result.summary()
    kinds = {i["kind"] for i in result.invariants}
    assert {"outcome_curve_period", "rate_curve_anchor", "fk_integrity", "unique"} <= kinds


def test_statement_follows_in_toto_v1(tables, schema, tmp_path):
    result = attest(_write(tables, tmp_path, "csv"), schema)
    statement = json.loads((tmp_path / STATEMENT_FILE).read_text())
    assert statement["_type"] == "https://in-toto.io/Statement/v1"
    assert statement["predicateType"] == PREDICATE_TYPE
    assert [s["name"] for s in statement["subject"]] == ["customers.csv", "orders.csv"]
    for subject in statement["subject"]:
        assert len(subject["digest"]["sha256"]) == 64
    predicate = statement["predicate"]
    assert predicate["result"] == "PASSED"
    assert predicate["seed"] == 5
    assert predicate["producer"]["uri"] == f"pkg:pypi/misata@{misata.__version__}"
    assert predicate["verifiedAt"].endswith("Z")
    for invariant in predicate["invariants"]:
        assert set(invariant) == {"id", "kind", "table", "sql", "expected", "observed",
                                  "valueType", "comparator", "passed"}
        assert invariant["table"] in {"customers", "orders"}
        assert isinstance(invariant["expected"], str) and isinstance(invariant["observed"], str)
    assert len({i["id"] for i in predicate["invariants"]}) == len(predicate["invariants"])
    assert result.statement == statement


def test_dsse_payload_is_the_statement_bytes(tables, schema, tmp_path):
    attest(_write(tables, tmp_path, "csv"), schema)
    envelope = json.loads((tmp_path / DSSE_FILE).read_text())
    assert envelope["payloadType"] == PAYLOAD_TYPE
    assert envelope["signatures"] == []
    assert base64.b64decode(envelope["payload"]) == (tmp_path / STATEMENT_FILE).read_bytes()


def test_spec_file_is_hashed_when_given(tables, schema, tmp_path):
    spec = tmp_path / "misata.yaml"
    spec.write_text("name: example\n")
    result = attest(_write(tables, tmp_path / "data", "csv"), schema, spec_path=spec)
    assert result.statement["predicate"]["spec"]["name"] == "misata.yaml"


def _run_verifier(directory: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(directory / "verify.py")],
                          capture_output=True, text=True)


def test_standalone_verifier_passes_then_catches_one_byte(tables, schema, tmp_path):
    attest(_write(tables, tmp_path, "csv"), schema)
    done = _run_verifier(tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr

    orders = tmp_path / "orders.csv"
    data = bytearray(orders.read_bytes())
    data[-3] = ord("7") if data[-3] != ord("7") else ord("3")
    orders.write_bytes(bytes(data))
    done = _run_verifier(tmp_path)
    assert done.returncode == 1
    assert "orders.csv: sha256" in done.stdout


def test_a_broken_declaration_fails_and_is_named(tables, schema, tmp_path):
    broken = {name: df.copy() for name, df in tables.items()}
    broken["orders"].loc[0, "customer_id"] = 999_999
    result = attest(_write(broken, tmp_path, "csv"), schema)
    assert not result.passed
    assert [f["kind"] for f in result.failures] == ["fk_integrity"]
    assert result.statement["predicate"]["result"] == "FAILED"


def test_missing_table_file_is_refused(tables, schema, tmp_path):
    _write({"customers": tables["customers"]}, tmp_path, "csv")
    with pytest.raises(AttestationError, match="orders"):
        attest(tmp_path, schema)


def test_a_schema_with_nothing_to_check_is_refused(tmp_path):
    bare = misata.from_dict_schema({"notes": {"__rows__": 5, "body": {"type": "string"}}}, seed=1)
    pd.DataFrame({"body": ["a", "b"]}).to_csv(tmp_path / "notes.csv", index=False)
    with pytest.raises(AttestationError, match="nothing to attest"):
        attest(tmp_path, bare)


def test_tables_folder_layout_is_found(tables, schema, tmp_path):
    _write(tables, tmp_path / "tables", "csv")
    result = attest(tmp_path, schema)
    assert result.passed
    assert result.statement["subject"][0]["name"].startswith("tables/")


def test_verifier_refuses_subjects_outside_the_directory(tables, schema, tmp_path):
    attest(_write(tables, tmp_path, "csv"), schema)
    statement = json.loads((tmp_path / STATEMENT_FILE).read_text())
    statement["subject"][0]["name"] = "../elsewhere.csv"
    (tmp_path / STATEMENT_FILE).write_text(json.dumps(statement))
    done = _run_verifier(tmp_path)
    assert done.returncode == 1
    assert "outside the attested directory" in done.stdout


def test_invariants_come_from_the_schema_alone(schema):
    first = derive_invariants(schema)
    assert first == derive_invariants(schema)
    rate = next(i for i in first if i.kind == "rate_curve_anchor")
    assert rate.expected == "true" and rate.value_type == "boolean"
    curve = next(i for i in first if i.kind == "outcome_curve_period")
    assert curve.expected == "20000.00"


@pytest.mark.parametrize("value, value_type, like, expected", [
    (209999.99999999997, "decimal", "210000.00", "210000.00"),
    (0.1 + 0.2, "decimal", "0.3000", "0.3000"),
    (3.0, "integer", "3", "3"),
    (-1.4551915228366852e-11, "decimal", "0.00", "0.00"),
    (-0.4, "integer", "0", "0"),
    (True, "boolean", "true", "true"),
    (None, "decimal", "1.00", "null"),
    ("2024-03", "string", "2024-03", "2024-03"),
])
def test_values_are_written_at_the_expected_precision(value, value_type, like, expected):
    assert format_value(value, value_type, like) == expected


def test_cli_exit_codes(tables, schema, tmp_path):
    from click.testing import CliRunner

    from misata.cli import main

    spec = tmp_path / "schema.json"
    spec.write_text(schema.model_dump_json())
    data = _write(tables, tmp_path / "ok", "csv")
    runner = CliRunner()
    assert runner.invoke(main, ["attest", str(data), "-s", str(spec)]).exit_code == 0

    broken = {name: df.copy() for name, df in tables.items()}
    broken["orders"].loc[0, "customer_id"] = 999_999
    bad = _write(broken, tmp_path / "bad", "csv")
    assert runner.invoke(main, ["attest", str(bad), "-s", str(spec)]).exit_code == 1

    empty = tmp_path / "empty"
    empty.mkdir()
    assert runner.invoke(main, ["attest", str(empty), "-s", str(spec)]).exit_code == 2

    as_json = runner.invoke(main, ["attest", str(data), "-s", str(spec), "--json"])
    assert json.loads(as_json.output)["data"]["statement"]["predicateType"] == PREDICATE_TYPE


def test_evalpack_carries_an_attestation(schema, tmp_path):
    from misata.evalpack import build_evalpack

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = build_evalpack(schema.model_copy(deep=True), tmp_path)
    assert result.certificate["attestation"]["result"] == "PASSED"
    assert (tmp_path / "verify.py").read_text() != (tmp_path / "verify_attestation.py").read_text()
    done = subprocess.run([sys.executable, "-I", str(tmp_path / "verify_attestation.py")],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout


def test_odcs_export_carries_one_sql_rule_per_invariant(tables, schema, tmp_path):
    result = attest(_write(tables, tmp_path, "parquet"), schema)
    contract = to_odcs(result, schema)
    assert contract["apiVersion"] == ODCS_API_VERSION and contract["kind"] == "DataContract"
    assert contract["servers"] == [{"server": "local", "type": "local", "format": "parquet",
                                    "path": "./{model}.parquet"}]
    rules = [r for obj in contract["schema"] for r in obj.get("quality", [])]
    assert len(rules) == len(result.invariants)
    assert all(r["type"] == "sql" and "mustBe" in r for r in rules)
    rate = next(r for r in rules if "rate_curve_anchor" in r["name"])
    assert rate["mustBe"] == 1 and rate["query"].startswith("SELECT CAST((")


def test_odcs_rules_hold_when_run_in_duckdb(tables, schema, tmp_path):
    import duckdb

    result = attest(_write(tables, tmp_path, "parquet"), schema)
    con = duckdb.connect()
    for name in tables:
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{tmp_path / name}.parquet')")
    for obj in to_odcs(result, schema)["schema"]:
        for rule in obj.get("quality", []):
            value = con.execute(rule["query"]).fetchone()[0]
            assert round(float(value), 2) == rule["mustBe"], rule["name"]


def test_openlineage_export_is_stable_and_complete(tables, schema, tmp_path):
    result = attest(_write(tables, tmp_path, "csv"), schema)
    event = to_openlineage(result)
    assert event == to_openlineage(result)
    assert event["eventType"] == "COMPLETE" and event["eventTime"].endswith("Z")
    assertions = [a for i in event["inputs"]
                  for a in i["inputFacets"]["dataQualityAssertions"]["assertions"]]
    assert len(assertions) == len(result.invariants)
    assert all(set(a) == {"assertion", "success"} for a in assertions)
    certificate = event["inputs"][0]["facets"]["misata_certificate"]
    assert certificate["predicateType"] == PREDICATE_TYPE and certificate["seed"] == 5


def test_cli_writes_requested_exports(tables, schema, tmp_path):
    from click.testing import CliRunner

    from misata.cli import main

    spec = tmp_path / "schema.json"
    spec.write_text(schema.model_dump_json())
    data = _write(tables, tmp_path / "out", "csv")
    done = CliRunner().invoke(main, ["attest", str(data), "-s", str(spec),
                                     "--export", "odcs", "--export", "openlineage"])
    assert done.exit_code == 0, done.output
    assert (data / "datacontract.odcs.yaml").is_file()
    assert json.loads((data / "openlineage.json").read_text())["eventType"] == "COMPLETE"


DDL = """
CREATE TABLE accounts (
  id SERIAL PRIMARY KEY,
  plan VARCHAR(10) NOT NULL CHECK (plan IN ('free', 'team', 'enterprise'))
);
CREATE TABLE invoices (
  id SERIAL PRIMARY KEY,
  account_id INT NOT NULL REFERENCES accounts(id),
  issued_on DATE NOT NULL,
  due_on DATE NOT NULL,
  CHECK (due_on > issued_on)
);
"""


class TestRowRules:
    """CHECK constraints, declared domains and NOT NULL are attested, not assumed."""

    @pytest.fixture()
    def ddl_dir(self, tmp_path):
        spec = tmp_path / "schema.sql"
        spec.write_text(DDL, encoding="utf-8")
        schema = misata.yaml_schema.load_schema_file(spec, seed=3, rows=300)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _write(misata.generate_from_schema(schema), tmp_path / "out", "csv")
        return tmp_path / "out", schema

    def test_ddl_rules_become_invariants(self, ddl_dir):
        directory, schema = ddl_dir
        result = attest(directory, schema, write=False)
        kinds = {i["id"]: i["kind"] for i in result.invariants}
        assert kinds["accounts.plan.domain"] == "domain"
        assert kinds["invoices.due_on>issued_on.inequality"] == "inequality"
        assert kinds["invoices.issued_on.not_null"] == "not_null"
        assert result.passed

    def test_a_value_outside_the_domain_fails(self, ddl_dir):
        directory, schema = ddl_dir
        accounts = pd.read_csv(directory / "accounts.csv")
        accounts.loc[0, "plan"] = "platinum"
        accounts.to_csv(directory / "accounts.csv", index=False)
        failures = {f["id"] for f in attest(directory, schema, write=False).failures}
        assert failures == {"accounts.plan.domain"}

    def test_a_broken_inequality_fails(self, ddl_dir):
        directory, schema = ddl_dir
        invoices = pd.read_csv(directory / "invoices.csv")
        invoices.loc[0, "due_on"] = invoices.loc[0, "issued_on"]
        invoices.to_csv(directory / "invoices.csv", index=False)
        failures = {f["id"] for f in attest(directory, schema, write=False).failures}
        assert failures == {"invoices.due_on>issued_on.inequality"}

    def test_the_model_default_is_not_a_declaration(self):
        from misata.schema import Column, SchemaConfig, Table

        schema = SchemaConfig(name="t", tables=[Table(name="t", row_count=5)], columns={"t": [
            Column(name="a", type="int"), Column(name="b", type="int", nullable=False)]})
        ids = {i.id for i in derive_invariants(schema)}
        assert "t.b.not_null" in ids and "t.a.not_null" not in ids

    def test_columns_dirt_is_declared_on_are_left_out(self):
        schema = misata.from_dict_schema({
            "__typos__": [{"table": "t", "column": "status", "count": 3}],
            "t": {"__rows__": 50, "status": {"type": "categorical", "choices": ["a", "b"]},
                  "kind": {"type": "categorical", "choices": ["x", "y"]}}})
        ids = {i.id for i in derive_invariants(schema)}
        assert "t.kind.domain" in ids and "t.status.domain" not in ids


def test_the_cli_reads_ddl(tmp_path):
    from click.testing import CliRunner

    from misata.cli import main

    (tmp_path / "schema.sql").write_text(DDL, encoding="utf-8")
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as here:
        Path(here, "schema.sql").write_text(DDL, encoding="utf-8")
        generated = runner.invoke(main, ["generate", "-c", "schema.sql", "-o", "out", "-n", "200",
                                         "--seed", "5", "--attest"])
        assert generated.exit_code == 0, generated.output
        attested = runner.invoke(main, ["attest", "out", "-s", "schema.sql", "--json"])
        assert attested.exit_code == 0, attested.output
        invariants = json.loads(attested.output)["data"]["statement"]["predicate"]["invariants"]
        assert any(i["kind"] == "inequality" for i in invariants)


GRAPH = {
    "accounts": {"__rows__": 800, "id": {"type": "integer", "unique": True, "min": 1, "max": 800}},
    "transfers": {"__rows__": 9_000, "src": {"type": "integer", "min": 1, "max": 800},
                  "dst": {"type": "integer", "min": 1, "max": 800},
                  "amount": {"type": "float", "min": 1, "max": 5_000}},
    "__dag_edges__": [{"name": "background", "table": "transfers", "node_table": "accounts",
                       "node_key": "id", "from_column": "src", "to_column": "dst"}],
    "__graph_motifs__": [{"name": "rings", "table": "transfers", "node_table": "accounts",
                          "node_key": "id", "from_column": "src", "to_column": "dst",
                          "rate": 0.02, "shares": {"cycle": 0.5, "fan_in": 0.3, "chain": 0.2},
                          "benign_rate": 0.0011, "benign_shares": {"cycle": 0.7, "fan_out": 0.3},
                          "flag_column": "is_suspicious"}],
}


class TestGraphs:
    """Declared graph structure is attested: an acyclic background and exact motif counts."""

    @pytest.fixture()
    def graph_dir(self, tmp_path):
        schema = misata.from_dict_schema(GRAPH, seed=13)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _write(misata.generate_from_schema(schema), tmp_path, "csv")
        return tmp_path, schema

    def test_graph_declarations_become_invariants_and_hold(self, graph_dir):
        directory, schema = graph_dir
        result = attest(directory, schema, write=False)
        observed = {i["id"]: i["observed"] for i in result.invariants}
        assert observed["transfers.src->dst.acyclic"] == "0"
        # 180 flagged edges split 90/54/36. Ten benign edges split 7/3, and
        # three edges are fewer than the smallest fan-out, so it gets none.
        assert observed["transfers.rings.cycle.motif_edges"] == "97"
        assert observed["transfers.rings.fan_in.motif_edges"] == "54"
        assert observed["transfers.rings.chain.motif_edges"] == "36"
        assert observed["transfers.rings.fan_out.motif_edges"] == "0"
        assert observed["transfers.rings.flagged_edges"] == "180"
        assert result.passed, result.summary()

    @pytest.mark.parametrize("seed", [1, 2, 3])
    def test_planned_counts_match_every_seed(self, seed):
        from misata.graphs import planned_motif_edges

        schema = misata.from_dict_schema(GRAPH, seed=seed)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            edges = misata.generate_from_schema(schema)["transfers"]
        spec = schema.graph_motifs[0]
        planned = planned_motif_edges(spec, len(edges))
        cased = edges[edges["motif_case"].fillna("") != ""]
        for (kind, flagged), count in planned.items():
            rows = cased[(cased["motif"] == kind) & (cased["is_suspicious"] == flagged)]
            assert len(rows) == count, (kind, flagged)

    def test_a_planted_cycle_fails_only_the_acyclic_invariant(self, graph_dir):
        directory, schema = graph_dir
        transfers = pd.read_csv(directory / "transfers.csv", keep_default_na=False)
        background = transfers.index[transfers["motif_case"] == ""]
        first, second = background[0], background[1]
        a, b = transfers.loc[first, "src"], transfers.loc[first, "dst"]
        transfers.loc[second, ["src", "dst"]] = [b, a]
        transfers.to_csv(directory / "transfers.csv", index=False)
        failures = {f["id"] for f in attest(directory, schema, write=False).failures}
        assert failures == {"transfers.src->dst.acyclic"}


class TestLedgerAcrossBatches:
    """A ledger balances whole entries, so an entry whose lines span two batches
    keeps every line and its declared minimum."""

    @pytest.fixture()
    def books(self, tmp_path):
        schema = misata.from_dict_schema({
            "entries": {"__rows__": 3_000,
                        "entry_id": {"type": "integer", "unique": True, "min": 1, "max": 3_000}},
            "lines": {"__rows__": 13_000,
                      "line_id": {"type": "integer", "unique": True, "min": 1, "max": 13_000},
                      "entry_id": {"type": "foreign_key", "references": "entries.entry_id"},
                      "debit": {"type": "float", "min": 1, "max": 900},
                      "credit": {"type": "float", "min": 1, "max": 900},
                      "__constraints__": [{"name": "double_entry", "type": "balanced_ledger",
                                           "group_by": ["entry_id"], "debit_column": "debit",
                                           "credit_column": "credit"}]},
            "__relationships__": [{"parent_table": "entries", "parent_key": "entry_id",
                                   "child_table": "lines", "child_key": "entry_id",
                                   "min_children": 2}],
        }, seed=4)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tables = misata.generate_from_schema(schema)
        return tables, schema, tmp_path

    def test_every_entry_keeps_two_lines_and_balances(self, books):
        tables, schema, directory = books
        lines = tables["lines"]
        per_entry = lines.groupby("entry_id").size().reindex(tables["entries"]["entry_id"],
                                                             fill_value=0)
        assert per_entry.min() >= 2
        sides = lines.groupby("entry_id")[["debit", "credit"]].sum().round(2)
        assert (sides["debit"] == sides["credit"]).all()
        result = attest(_write(tables, directory, "csv"), schema, write=False)
        assert result.passed, result.summary()
        assert "entries.entry_id->lines.entry_id.min_children" in {
            i["id"] for i in result.invariants}

    def test_an_entry_left_with_one_line_fails_min_children(self, books):
        tables, schema, directory = books
        _write(tables, directory, "csv")
        lines = pd.read_csv(directory / "lines.csv")
        entry = lines["entry_id"].value_counts().idxmin()
        doomed = lines.index[lines["entry_id"] == entry][1:]
        lines.drop(index=doomed).to_csv(directory / "lines.csv", index=False)
        failures = {f["id"] for f in attest(directory, schema, write=False).failures}
        assert "entries.entry_id->lines.entry_id.min_children" in failures


def test_a_partitioned_relationship_is_attested_and_a_leak_fails(tmp_path):
    schema = misata.from_dict_schema({
        "workspaces": {"__rows__": 6, "workspace_id": {"type": "integer", "unique": True,
                                                       "min": 1, "max": 6}},
        "users": {"__rows__": 40, "user_id": {"type": "integer", "unique": True,
                                              "min": 1, "max": 40},
                  "workspace_id": {"type": "foreign_key", "references": "workspaces.workspace_id"}},
        "tasks": {"__rows__": 300, "task_id": {"type": "integer", "unique": True,
                                               "min": 1, "max": 300},
                  "workspace_id": {"type": "foreign_key", "references": "workspaces.workspace_id"},
                  "assignee_id": {"type": "foreign_key", "references": "users.user_id"}},
        "__relationships__": [{"parent_table": "users", "parent_key": "user_id",
                               "child_table": "tasks", "child_key": "assignee_id",
                               "partition_by": ["workspace_id"]}],
    }, seed=6)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _write(misata.generate_from_schema(schema), tmp_path, "csv")
    invariant = "users.user_id->tasks.assignee_id.partition_by"
    result = attest(tmp_path, schema, write=False)
    assert invariant in {i["id"] for i in result.invariants} and result.passed

    tasks = pd.read_csv(tmp_path / "tasks.csv")
    users = pd.read_csv(tmp_path / "users.csv")
    stranger = users.loc[users["workspace_id"] != tasks.loc[0, "workspace_id"], "user_id"].iloc[0]
    tasks.loc[0, "assignee_id"] = stranger
    tasks.to_csv(tmp_path / "tasks.csv", index=False)
    assert {f["id"] for f in attest(tmp_path, schema, write=False).failures} == {invariant}


class TestLifecycles:
    """A declared lifecycle is attested: each row's history is its state's path,
    and the state mix is the declared weights to within one row."""

    ORDERS = {
        "orders": {
            "__rows__": 1_000,
            "order_id": {"type": "integer", "unique": True, "min": 1, "max": 1_000},
            "status": {"type": "string"},
            "ordered_on": {"type": "date", "start": "2025-01-01", "end": "2025-12-31"},
            "paid_at": {"type": "datetime", "nullable": True},
            "shipped_on": {"type": "date", "nullable": True},
            "cancelled_at": {"type": "datetime", "nullable": True},
            "__lifecycles__": [{
                "name": "fulfilment", "state_column": "status", "start_column": "ordered_on",
                "initial": "placed",
                "states": [{"name": "placed"}, {"name": "paid", "timestamp": "paid_at"},
                           {"name": "shipped", "timestamp": "shipped_on"},
                           {"name": "cancelled", "timestamp": "cancelled_at", "terminal": True}],
                "transitions": [["placed", "paid"], ["paid", "shipped"], ["placed", "cancelled"]],
                "weights": {"placed": 0.1, "paid": 0.25, "shipped": 0.5, "cancelled": 0.15},
            }],
        },
    }

    @pytest.fixture()
    def orders_dir(self, tmp_path):
        schema = misata.from_dict_schema(self.ORDERS, seed=21)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _write(misata.generate_from_schema(schema), tmp_path, "csv")
        return tmp_path, schema

    def test_history_and_mix_are_attested(self, orders_dir):
        directory, schema = orders_dir
        result = attest(directory, schema, write=False)
        ids = {i["id"] for i in result.invariants}
        assert {"orders.fulfilment.lifecycle_history", "orders.fulfilment.lifecycle_mix"} <= ids
        assert result.passed, result.summary()

    @pytest.mark.parametrize("column, value", [
        ("cancelled_at", "2026-01-01 00:00:00"),   # a shipped order that was also cancelled
        ("paid_at", ""),                            # shipped without being paid
        ("shipped_on", "2024-01-01"),               # shipped before it was ordered
    ])
    def test_an_impossible_history_fails(self, orders_dir, column, value):
        directory, schema = orders_dir
        orders = pd.read_csv(directory / "orders.csv", keep_default_na=False)
        row = orders.index[orders["status"] == "shipped"][0]
        orders.loc[row, column] = value
        orders.to_csv(directory / "orders.csv", index=False)
        failures = {f["id"] for f in attest(directory, schema, write=False).failures}
        assert failures == {"orders.fulfilment.lifecycle_history"}

    def test_a_shifted_mix_fails(self, orders_dir):
        directory, schema = orders_dir
        orders = pd.read_csv(directory / "orders.csv", keep_default_na=False)
        placed = orders.index[orders["status"] == "placed"][:2]
        orders = orders.drop(placed)
        orders.to_csv(directory / "orders.csv", index=False)
        failures = {f["id"] for f in attest(directory, schema, write=False).failures}
        assert "orders.fulfilment.lifecycle_mix" in failures
        assert "orders.fulfilment.lifecycle_history" not in failures
