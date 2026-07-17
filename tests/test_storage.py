import datetime as dt
from pathlib import Path

from edgar_pipeline.form4 import parse_form4

XML = (Path(__file__).parent / "fixtures" / "form4_sample.xml").read_bytes()


def test_write_and_query_roundtrip(tmp_path, monkeypatch):
    import edgar_pipeline.config as config
    import edgar_pipeline.storage as storage

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)

    rows = parse_form4(XML, "0000320193-26-000045").flatten()
    path = storage.write_partition(rows, dt.date(2026, 7, 15))
    assert path.exists()
    assert "filed_date=2026-07-15" in str(path)

    con = storage.connect()
    n, gross = con.execute(
        "SELECT count(*), sum(shares * price_per_share) FROM form4_transactions"
    ).fetchone()
    assert n == 2
    assert round(gross) == round(10000 * 231.505)  # gift row has NULL price, excluded by SQL sum

    # Idempotent re-write of the same partition
    storage.write_partition(rows, dt.date(2026, 7, 15))
    (n2,) = storage.connect().execute("SELECT count(*) FROM form4_transactions").fetchone()
    assert n2 == 2


def test_empty_partition_ok(tmp_path, monkeypatch):
    import edgar_pipeline.config as config
    import edgar_pipeline.storage as storage

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)

    path = storage.write_partition([], dt.date(2026, 7, 18))  # a Saturday
    assert path.exists()
