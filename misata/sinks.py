"""Write generated tables to disk batch by batch, as they arrive.

A sink receives each table's batches in generation order and never holds a
whole table, so output size is bounded by disk, not memory. Three formats:

``csv``
    ``<table>.csv`` per table.
``jsonl``
    ``<table>.jsonl`` per table, one JSON object per row, timestamps in ISO
    8601.
``parquet``
    ``<table>.parquet`` per table, streamed through one writer. With
    ``partition_by``, every table holding that column is written Hive-style
    instead: ``<table>/<column>=<value>/part-00000.parquet``, the column
    carried by the path and dropped from the files, as Hive, Spark, DuckDB and
    Polars expect. Each partition streams into one file, a row group per
    batch, unless more partitions are live than :data:`MAX_OPEN_PARTITIONS`;
    then the least recently written one is closed and continues in a new
    part file when its rows return.
``duckdb``
    One ``data.duckdb`` file holding every table.

Parquet and DuckDB fix each table's column types from its first batch. A
column that batch left entirely null takes its type from the schema, so a
later batch or partition cannot disagree with an earlier one.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

import pandas as pd

if TYPE_CHECKING:
    from misata.schema import SchemaConfig

FORMATS = ("csv", "jsonl", "parquet", "duckdb")
DUCKDB_FILE = "data.duckdb"

#: More partitions than this means the column is close to unique, which makes
#: millions of tiny files rather than a dataset anyone can read.
MAX_PARTITIONS = 10_000

#: Partition files open for writing at once, well under the usual limit on
#: open file descriptors.
MAX_OPEN_PARTITIONS = 64

HIVE_NULL = "__HIVE_DEFAULT_PARTITION__"
_HIVE_UNSAFE = re.compile(r"[\x00-\x1f\"#%'*/:=?\\\x7f{}\[\]^]")


class SinkError(ValueError):
    """A table cannot be written in the way that was asked for."""


def _hive_value(value: Any) -> str:
    """A partition value as Hive writes it in a path, escaped the same way."""
    if value is None or (not isinstance(value, (str, bytes)) and pd.isna(value)):
        return HIVE_NULL
    if isinstance(value, pd.Timestamp):
        text = value.date().isoformat() if value == value.normalize() else value.isoformat()
    elif isinstance(value, bool) or type(value).__name__ == "bool_":
        text = str(bool(value)).lower()
    else:
        text = str(value)
    return _HIVE_UNSAFE.sub(lambda m: f"%{ord(m.group()):02X}", text)


def _arrow_types() -> Dict[str, Any]:
    import pyarrow as pa

    return {"int": pa.int64(), "float": pa.float64(), "boolean": pa.bool_(),
            "date": pa.timestamp("ns"), "datetime": pa.timestamp("ns"),
            "foreign_key": pa.int64()}


class Sink:
    """Receives batches table by table; :meth:`close` finishes every file."""

    def __init__(self, root: Path, schema: Optional["SchemaConfig"] = None) -> None:
        self.root = root
        self.schema = schema
        self.rows: Dict[str, int] = {}
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, table: str, batch: pd.DataFrame) -> None:
        self._write(table, batch)
        self.rows[table] = self.rows.get(table, 0) + len(batch)

    def files(self, table: str) -> List[Path]:
        """The files holding ``table``."""
        raise NotImplementedError

    def read(self, table: str) -> pd.DataFrame:
        """``table`` read back whole, for reports that need every row."""
        raise NotImplementedError

    def close(self) -> None:
        """Flush and close everything still open."""

    def _write(self, table: str, batch: pd.DataFrame) -> None:
        raise NotImplementedError

    def __enter__(self) -> "Sink":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def _column_types(self, table: str) -> Dict[str, str]:
        if self.schema is None:
            return {}
        return {c.name: str(c.type) for c in self.schema.get_columns(table) or []}


class CsvSink(Sink):
    def _write(self, table: str, batch: pd.DataFrame) -> None:
        first = table not in self.rows
        batch.to_csv(self.root / f"{table}.csv", mode="w" if first else "a",
                     header=first, index=False)

    def files(self, table: str) -> List[Path]:
        return [self.root / f"{table}.csv"]

    def read(self, table: str) -> pd.DataFrame:
        return pd.read_csv(self.root / f"{table}.csv")


class JsonlSink(Sink):
    def _write(self, table: str, batch: pd.DataFrame) -> None:
        mode = "a" if table in self.rows else "w"
        with open(self.root / f"{table}.jsonl", mode, encoding="utf-8") as fh:
            batch.to_json(fh, orient="records", lines=True, date_format="iso",
                          date_unit="s", double_precision=15, force_ascii=False)

    def files(self, table: str) -> List[Path]:
        return [self.root / f"{table}.jsonl"]

    def read(self, table: str) -> pd.DataFrame:
        return pd.read_json(self.root / f"{table}.jsonl", lines=True)


class _ArrowSink(Sink):
    """Shared by Parquet and DuckDB: one Arrow schema per table, fixed early."""

    def __init__(self, root: Path, schema: Optional["SchemaConfig"] = None) -> None:
        super().__init__(root, schema)
        self._schemas: Dict[str, Any] = {}

    def _arrow(self, table: str, batch: pd.DataFrame) -> Any:
        import pyarrow as pa

        schema = self._schemas.get(table)
        if schema is None:
            inferred = pa.Schema.from_pandas(batch, preserve_index=False).remove_metadata()
            declared = self._column_types(table)
            fallback = _arrow_types()
            schema = pa.schema([
                pa.field(f.name, fallback.get(declared.get(f.name, ""), pa.string()))
                if pa.types.is_null(f.type) else f
                for f in inferred
            ])
            self._schemas[table] = schema
        try:
            return pa.Table.from_pandas(batch, schema=schema, preserve_index=False)
        except (pa.ArrowInvalid, pa.ArrowTypeError, KeyError) as exc:
            raise SinkError(f"{table}: a later batch does not fit the column types of the "
                            f"first ({exc})") from exc


class ParquetSink(_ArrowSink):
    def __init__(self, root: Path, schema: Optional["SchemaConfig"] = None,
                 partition_by: Optional[str] = None, compression: str = "snappy") -> None:
        super().__init__(root, schema)
        self.partition_by = partition_by
        self.compression = compression
        self._writers: Dict[str, Any] = {}
        self._parts: Dict[str, List[Path]] = {}
        self._partitions: Dict[str, Set[str]] = {}
        self._open: "OrderedDict[Tuple[str, str], Any]" = OrderedDict()
        self._part_numbers: Dict[Tuple[str, str], int] = {}

    def _partitioned(self, table: str, batch: pd.DataFrame) -> bool:
        return self.partition_by is not None and self.partition_by in batch.columns

    def _write(self, table: str, batch: pd.DataFrame) -> None:
        import pyarrow.parquet as pq

        if not self._partitioned(table, batch):
            data = self._arrow(table, batch)
            writer = self._writers.get(table)
            if writer is None:
                writer = pq.ParquetWriter(self.root / f"{table}.parquet", data.schema,
                                          compression=self.compression)
                self._writers[table] = writer
            writer.write_table(data)
            return

        column = self.partition_by
        assert column is not None
        values = batch.drop(columns=[column])
        self._arrow(table, values)  # fixes the table's types before the first split
        seen = self._partitions.setdefault(table, set())
        for key, group in batch.groupby(column, dropna=False, sort=True):
            folder = f"{column}={_hive_value(key)}"
            seen.add(folder)
            if len(seen) > MAX_PARTITIONS:
                raise SinkError(
                    f"partitioning {table} by {column} makes more than {MAX_PARTITIONS:,} "
                    f"partitions; choose a column with fewer distinct values")
            data = self._arrow(table, group.drop(columns=[column]))
            self._partition_writer(table, folder, data.schema).write_table(data)

    def _partition_writer(self, table: str, folder: str, schema: Any) -> Any:
        """The open writer for one partition, opening a new part file if needed."""
        import pyarrow.parquet as pq

        slot = (table, folder)
        writer = self._open.pop(slot, None)
        if writer is None:
            if len(self._open) >= MAX_OPEN_PARTITIONS:
                self._open.popitem(last=False)[1].close()
            number = self._part_numbers.get(slot, 0)
            self._part_numbers[slot] = number + 1
            path = self.root / table / folder / f"part-{number:05d}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            writer = pq.ParquetWriter(path, schema, compression=self.compression)
            self._parts.setdefault(table, []).append(path)
        self._open[slot] = writer
        return writer

    def files(self, table: str) -> List[Path]:
        return list(self._parts.get(table) or [self.root / f"{table}.parquet"])

    def read(self, table: str) -> pd.DataFrame:
        if table in self._parts:
            return pd.read_parquet(self.root / table)
        return pd.read_parquet(self.root / f"{table}.parquet")

    def close(self) -> None:
        for writer in [*self._writers.values(), *self._open.values()]:
            writer.close()
        self._writers.clear()
        self._open.clear()


class DuckDBSink(_ArrowSink):
    def __init__(self, root: Path, schema: Optional["SchemaConfig"] = None) -> None:
        import duckdb

        super().__init__(root, schema)
        self.path = root / DUCKDB_FILE
        for stale in (self.path, self.path.with_name(self.path.name + ".wal")):
            stale.unlink(missing_ok=True)
        self._con: Any = duckdb.connect(str(self.path))

    def _write(self, table: str, batch: pd.DataFrame) -> None:
        from misata.sqlutil import quote_ident

        data = self._arrow(table, batch)
        self._con.register("misata_batch", data)
        try:
            if table in self.rows:
                self._con.execute(f"INSERT INTO {quote_ident(table)} SELECT * FROM misata_batch")
            else:
                self._con.execute(f"CREATE TABLE {quote_ident(table)} AS "
                                  f"SELECT * FROM misata_batch")
        finally:
            self._con.unregister("misata_batch")

    def files(self, table: str) -> List[Path]:
        return [self.path]

    def read(self, table: str) -> pd.DataFrame:
        from misata.sqlutil import quote_ident

        if self._con is None:
            import duckdb

            with duckdb.connect(str(self.path), read_only=True) as con:
                return con.execute(f"SELECT * FROM {quote_ident(table)}").df()
        return self._con.execute(f"SELECT * FROM {quote_ident(table)}").df()

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None


def open_sink(fmt: str, output_dir: Any, schema: Optional["SchemaConfig"] = None,
              partition_by: Optional[str] = None) -> Sink:
    """A sink writing ``fmt`` into ``output_dir``.

    Raises:
        SinkError: for an unknown format, ``partition_by`` with a format other
            than Parquet, or a ``partition_by`` column no table has.
        ImportError: when the format's library is not installed.
    """
    if fmt not in FORMATS:
        raise SinkError(f"unknown format {fmt!r}; choose one of {', '.join(FORMATS)}")
    if partition_by and fmt != "parquet":
        raise SinkError("--partition-by needs --format parquet")
    if partition_by and schema is not None and not any(
            partition_by in {c.name for c in schema.get_columns(t.name) or []}
            for t in schema.tables):
        raise SinkError(f"no table has a column named {partition_by!r} to partition by")
    root = Path(output_dir)
    if fmt == "csv":
        return CsvSink(root, schema)
    if fmt == "jsonl":
        return JsonlSink(root, schema)
    if fmt == "parquet":
        _require("pyarrow", "parquet")
        return ParquetSink(root, schema, partition_by=partition_by)
    _require("pyarrow", "duckdb")
    _require("duckdb", "duckdb")
    return DuckDBSink(root, schema)


def _require(module: str, extra: str) -> None:
    import importlib.util

    if importlib.util.find_spec(module) is None:
        raise ImportError(f"{module} is needed for this format: pip install \"misata[{extra}]\"")
