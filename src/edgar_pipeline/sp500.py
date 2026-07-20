"""S&P 500 daily index levels from FRED (keyless public CSV endpoint).

Layout: data/sp500/sp500.parquet — the full available history in a single
file, rewritten atomically on every refresh. Idempotent by construction; no
incremental bookkeeping.

FRED serves close prices only and caps history at 10 years (an S&P licensing
limit) — both fine here: the Form 4 lake is shallower than that, and only the
close is charted. Stooq was the original source; it now gates its CSV behind a
JavaScript anti-bot challenge, which this project does not circumvent.
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

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500"

# FRED's 10-year window is ~2500 trading days; a much shorter response is a
# truncation or an error page and must not replace a good file.
MIN_ROWS = 1000

SCHEMA = pa.schema([("date", pa.date32()), ("close", pa.float64())])


def parse_fred_csv(text: str) -> list[dict]:
    """Rows from FRED's CSV (header: observation_date,SP500).

    Market holidays carry "." as the value and are skipped — the index has no
    close on days it did not trade.
    """
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        value = r["SP500"].strip()
        if not value or value == ".":
            continue
        rows.append(
            {
                "date": dt.date.fromisoformat(r["observation_date"]),
                "close": float(value),
            }
        )
    return rows


def fetch_sp500() -> list[dict]:
    resp = httpx.get(FRED_URL, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    rows = parse_fred_csv(resp.text)
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
