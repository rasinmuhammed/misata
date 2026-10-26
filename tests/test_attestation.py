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
