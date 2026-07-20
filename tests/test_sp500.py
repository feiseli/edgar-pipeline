import datetime as dt
from pathlib import Path

import pytest

import edgar_pipeline.sp500 as sp500

CSV = (Path(__file__).parent / "fixtures" / "sp500_sample.csv").read_text()


def test_parse_stooq_csv():
    rows = sp500.parse_stooq_csv(CSV)
    assert len(rows) == 3
    assert rows[0]["date"] == dt.date(2026, 7, 15)
    assert rows[2]["close"] == 6321.78
    assert rows[1]["volume"] == 2451234000.0


def test_parse_handles_missing_volume():
    # Old index rows sometimes have an empty or absent Volume field.
    text = "Date,Open,High,Low,Close,Volume\n1990-01-02,359.69,359.69,351.98,359.69,\n"
    rows = sp500.parse_stooq_csv(text)
    assert rows[0]["volume"] is None
    assert rows[0]["close"] == 359.69


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
    rows = sp500.parse_stooq_csv(CSV)
    path = sp500.write_sp500(rows)
    assert path == tmp_path / "sp500" / "sp500.parquet"
    n, last = duckdb.sql(
        f"select count(*), max(close) from read_parquet('{path}')"
    ).fetchone()
    assert n == 3
    assert last == 6321.78

    # Idempotent overwrite
    sp500.write_sp500(rows)
    (n2,) = duckdb.sql(f"select count(*) from read_parquet('{path}')").fetchone()
    assert n2 == 3
