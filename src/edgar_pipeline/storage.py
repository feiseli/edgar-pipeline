"""Parquet writing and DuckDB access.

Layout: data/form4/filed_date=YYYY-MM-DD/form4.parquet — one file per
partition, rewritten atomically on re-runs, so backfills and Dagster
partition re-materializations are idempotent.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .config import DATA_DIR

SCHEMA = pa.schema(
    [
        ("accession_number", pa.string()),
        ("is_amendment", pa.bool_()),
        ("period_of_report", pa.date32()),
        ("issuer_cik", pa.int64()),
        ("issuer_name", pa.string()),
        ("issuer_symbol", pa.string()),
        ("owner_cik", pa.int64()),
        ("owner_name", pa.string()),
        ("is_director", pa.bool_()),
        ("is_officer", pa.bool_()),
        ("is_ten_percent_owner", pa.bool_()),
        ("officer_title", pa.string()),
        ("transaction_seq", pa.int32()),
        ("security_title", pa.string()),
        ("transaction_date", pa.date32()),
        ("transaction_code", pa.string()),
        ("shares", pa.float64()),
        ("price_per_share", pa.float64()),
        ("acquired_disposed", pa.string()),
        ("shares_owned_after", pa.float64()),
        ("ownership_form", pa.string()),
    ]
)


def partition_path(filed_date: dt.date) -> Path:
    return DATA_DIR / "form4" / f"filed_date={filed_date.isoformat()}" / "form4.parquet"


def write_partition(rows: list[dict], filed_date: dt.date) -> Path:
    path = partition_path(filed_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    tmp = path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp)
    tmp.replace(path)
    return path


def connect(db_path: str | Path = ":memory:") -> duckdb.DuckDBPyConnection:
    """DuckDB connection with a view over all Form 4 partitions."""
    con = duckdb.connect(str(db_path))
    glob = str(DATA_DIR / "form4" / "*" / "*.parquet")
    con.execute(
        f"""
        CREATE OR REPLACE VIEW form4_transactions AS
        SELECT * FROM read_parquet('{glob}', hive_partitioning = true)
        """
    )
    return con
