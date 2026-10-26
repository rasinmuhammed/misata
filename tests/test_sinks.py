"""Streaming output: every format holds exactly the rows generation produced."""

from __future__ import annotations

import subprocess
import sys
import warnings

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("pyarrow")
duckdb = pytest.importorskip("duckdb")

import misata
from misata.attestation import attest
from misata.simulator import DataSimulator
from misata.sinks import (
    DUCKDB_FILE,
    HIVE_NULL,
    MAX_PARTITIONS,
    SinkError,
    _hive_value,
    open_sink,
)


@pytest.fixture(autouse=True)
def _quiet():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


def _schema(rows: int = 2_500) -> misata.SchemaConfig:
    return misata.from_dict_schema({
        "customers": {"__rows__": 300,
                      "customer_id": {"type": "int", "primary_key": True},
                      "tier": {"type": "categorical", "choices": ["free", "pro", "team"]}},
        "orders": {"__rows__": rows,
                   "order_id": {"type": "int", "primary_key": True},
                   "customer_id": {"type": "foreign_key", "references": "customers.customer_id"},
                   "status": {"type": "categorical", "choices": ["paid", "open", "void"]},
                   "amount": {"type": "float", "min": 1, "max": 900},
                   "note": {"type": "text", "null_rate": 0.97}},
    }, seed=5)


def _write(schema, fmt, root, partition_by=None, batch_size=1_000):
    sim = DataSimulator(schema, batch_size=batch_size)
    with open_sink(fmt, root, schema, partition_by=partition_by) as sink:
        for table, batch in sim.generate_all():
            sink.write(table, batch)
    return sink


def _expected(schema, batch_size=1_000):
    out: dict = {}
    for table, batch in DataSimulator(schema, batch_size=batch_size).generate_all():
        out.setdefault(table, []).append(batch)
    return {t: pd.concat(b, ignore_index=True) for t, b in out.items()}


def _same_rows(got: pd.DataFrame, want: pd.DataFrame) -> None:
    got = got[want.columns].sort_values("order_id" if "order_id" in want else want.columns[0])
    want = want.sort_values("order_id" if "order_id" in want else want.columns[0])
    pd.testing.assert_frame_equal(got.reset_index(drop=True), want.reset_index(drop=True),
                                  check_dtype=False, check_categorical=False)


@pytest.mark.parametrize("fmt", ["parquet", "duckdb"])
def test_typed_formats_hold_the_generated_rows(tmp_path, fmt):
    schema = _schema()
    sink = _write(schema, fmt, tmp_path)
    want = _expected(schema)
    for table, frame in want.items():
        assert sink.rows[table] == len(frame)
        _same_rows(sink.read(table), frame)


def test_parquet_streams_many_batches_into_one_file(tmp_path):
    import pyarrow.parquet as pq

    _write(_schema(), "parquet", tmp_path, batch_size=500)
    meta = pq.ParquetFile(tmp_path / "orders.parquet").metadata
    assert meta.num_rows == 2_500 and meta.num_row_groups == 5


def test_a_column_null_in_the_first_batch_keeps_its_declared_type(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    schema = _schema()
    with open_sink("parquet", tmp_path, schema) as sink:
        first = pd.DataFrame({"order_id": [1, 2], "customer_id": [1, 1],
                              "status": ["paid", "open"], "amount": [None, None],
                              "note": [None, None]})
        later = first.assign(order_id=[3, 4], amount=[5.5, 6.25], note=["a", "b"])
        sink.write("orders", first)
        sink.write("orders", later)
    types = pq.read_schema(tmp_path / "orders.parquet")
    assert types.field("amount").type == pa.float64()
    assert types.field("note").type == pa.string()


def test_partitions_match_hive_and_drop_the_column_from_files(tmp_path):
    import pyarrow.parquet as pq

    schema = _schema()
    _write(schema, "parquet", tmp_path, partition_by="status")
    folders = sorted(p.name for p in (tmp_path / "orders").iterdir())
    assert folders == ["status=open", "status=paid", "status=void"]
    part = next((tmp_path / "orders" / "status=paid").glob("*.parquet"))
    assert "status" not in pq.read_schema(part).names
    assert (tmp_path / "customers.parquet").is_file()

    read = duckdb.sql(f"SELECT * FROM read_parquet('{tmp_path}/orders/**/*.parquet', "
                      f"hive_partitioning = true)").df()
    _same_rows(read, _expected(schema)["orders"])


def test_partition_values_are_escaped_like_hive():
    assert _hive_value("a/b=c") == "a%2Fb%3Dc"
    assert _hive_value(None) == HIVE_NULL
    assert _hive_value(np.nan) == HIVE_NULL
    assert _hive_value(pd.Timestamp("2024-03-01")) == "2024-03-01"
    assert _hive_value(pd.Timestamp("2024-03-01 10:30")) == "2024-03-01T10%3A30%3A00"
    assert _hive_value(True) == "true"


def test_a_near_unique_partition_column_is_refused(tmp_path):
    schema = _schema(rows=MAX_PARTITIONS + 10)
    with pytest.raises(SinkError, match="fewer distinct values"):
        _write(schema, "parquet", tmp_path, partition_by="order_id", batch_size=50_000)


@pytest.mark.parametrize("fmt,column,match", [
    ("csv", "status", "needs --format parquet"),
    ("parquet", "nope", "no table has a column"),
    ("xml", None, "unknown format"),
])
def test_impossible_requests_are_refused_before_writing(tmp_path, fmt, column, match):
    with pytest.raises(SinkError, match=match):
        open_sink(fmt, tmp_path, _schema(), partition_by=column)
    assert not any(tmp_path.iterdir())


@pytest.mark.parametrize("fmt,partition_by", [("parquet", "status"), ("duckdb", None)])
def test_partitioned_and_duckdb_outputs_attest_and_catch_tampering(tmp_path, fmt, partition_by):
    schema = _schema()
    _write(schema, fmt, tmp_path, partition_by=partition_by)
    result = attest(tmp_path, schema)
    assert result.passed, result.summary()
    verify = [sys.executable, str(tmp_path / "verify.py")]
    assert subprocess.run(verify, capture_output=True).returncode == 0

    target = (next((tmp_path / "orders" / "status=paid").glob("*.parquet"))
              if partition_by else tmp_path / DUCKDB_FILE)
    data = bytearray(target.read_bytes())
    middle = len(data) // 2
    data[middle:middle + 64] = bytes(b ^ 0xFF for b in data[middle:middle + 64])
    target.write_bytes(bytes(data))
    report = subprocess.run(verify, capture_output=True, text=True)
    assert report.returncode == 1, report.stdout + report.stderr
    assert "does not match the attested" in report.stdout
    assert "Traceback" not in report.stderr


def test_each_partition_streams_into_one_file(tmp_path):
    schema = _schema(rows=3_000)
    _write(schema, "parquet", tmp_path, partition_by="status", batch_size=200)
    for folder in (tmp_path / "orders").iterdir():
        assert [p.name for p in folder.iterdir()] == ["part-00000.parquet"]
    read = duckdb.sql(f"SELECT * FROM read_parquet('{tmp_path}/orders/**/*.parquet', "
                      f"hive_partitioning = true)").df()
    _same_rows(read, _expected(schema, batch_size=200)["orders"])


def test_open_partition_files_are_bounded(tmp_path, monkeypatch):
    import misata.sinks as sinks

    monkeypatch.setattr(sinks, "MAX_OPEN_PARTITIONS", 2)
    schema = _schema(rows=3_000)
    _write(schema, "parquet", tmp_path, partition_by="status", batch_size=200)
    files = sorted((tmp_path / "orders").glob("*/*.parquet"))
    assert len(files) > 3
    read = duckdb.sql(f"SELECT * FROM read_parquet('{tmp_path}/orders/**/*.parquet', "
                      f"hive_partitioning = true)").df()
    _same_rows(read, _expected(schema, batch_size=200)["orders"])
