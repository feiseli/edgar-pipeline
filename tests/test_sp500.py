import datetime as dt
from pathlib import Path

import pytest

import edgar_pipeline.sp500 as sp500

CSV = (Path(__file__).parent / "fixtures" / "sp500_sample.csv").read_text()


def test_parse_fred_csv_skips_holidays():
    rows = sp500.parse_fred_csv(CSV)
    # The "." row (a market holiday) is dropped, not coerced to 0.0.
    assert len(rows) == 2
    assert rows[0] == {"date": dt.date(2026, 7, 15), "close": 6280.12}
    assert rows[1]["date"] == dt.date(2026, 7, 17)
    assert dt.date(2026, 7, 16) not in [r["date"] for r in rows]


class FakeResp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_fetch_refuses_short_history(monkeypatch):
    # A truncated/error response must never replace a good file.
    monkeypatch.setattr(sp500.httpx, "get", lambda *a, **k: FakeResp(CSV))
    with pytest.raises(ValueError, match="short"):
        sp500.fetch_sp500()


def test_write_roundtrip(tmp_path, monkeypatch):
    import duckdb

    monkeypatch.setattr(sp500, "DATA_DIR", tmp_path)
    rows = sp500.parse_fred_csv(CSV)
    path = sp500.write_sp500(rows)
    assert path == tmp_path / "sp500" / "sp500.parquet"
    n, last = duckdb.sql(f"select count(*), max(close) from read_parquet('{path}')").fetchone()
    assert n == 2
    assert last == 6321.78

    # Idempotent overwrite
    sp500.write_sp500(rows)
    (n2,) = duckdb.sql(f"select count(*) from read_parquet('{path}')").fetchone()
    assert n2 == 2
