"""S&P 500 daily index levels from Stooq (keyless CSV endpoint).

Layout: data/sp500/sp500.parquet — the full daily history in a single file,
rewritten atomically on every refresh. Idempotent by construction; no
incremental bookkeeping.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from .config import DATA_DIR

STOOQ_URL = "https://stooq.com/q/d/l/?s=%5Espx&i=d"

# Stooq's ^SPX daily history is tens of thousands of rows; a short response is
# a truncation or an error page and must not replace a good file.
MIN_ROWS = 5000

SCHEMA = pa.schema(
    [
        ("date", pa.date32()),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("volume", pa.float64()),
    ]
)


def parse_stooq_csv(text: str) -> list[dict]:
    """Rows from Stooq's daily CSV (header: Date,Open,High,Low,Close,Volume)."""
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        vol = r.get("Volume")
        rows.append(
            {
                "date": dt.date.fromisoformat(r["Date"]),
                "open": float(r["Open"]),
                "high": float(r["High"]),
                "low": float(r["Low"]),
                "close": float(r["Close"]),
                "volume": float(vol) if vol not in (None, "") else None,
            }
        )
    return rows


def fetch_sp500() -> list[dict]:
    resp = httpx.get(STOOQ_URL, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    rows = parse_stooq_csv(resp.text)
    if len(rows) < MIN_ROWS:
        raise ValueError(f"suspiciously short S&P 500 history ({len(rows)} rows)")
    return rows


def write_sp500(rows: list[dict]) -> Path:
    path = DATA_DIR / "sp500" / "sp500.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    tmp = path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp)
    tmp.replace(path)
    return path
