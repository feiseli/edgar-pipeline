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


def test_form4_parquet_asset_accepts_flattened_rows(tmp_path, monkeypatch):
    # Regression: the asset once assumed upstream rows carried ISO date strings,
    # but the pickle IO manager delivers dt.date objects — flatten() output as-is.
    import json

    from dagster import build_asset_context

    import edgar_pipeline.config as config
    import edgar_pipeline.storage as storage
    from edgar_pipeline.definitions import form4_parquet

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)

    rows = parse_form4(XML, "0000320193-26-000045").flatten()
    ctx = build_asset_context(partition_key="2026-07-15")
    records = {"rows": rows, "unparseable_filings": 1, "filings_attempted": 2}
    path = form4_parquet(ctx, records)
    assert Path(path).exists()

    # The freshness endpoint reflects this partition...
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["partition"] == "2026-07-15"
    assert status["rows"] == len(rows)
    assert status["skip_rate"] == 0.5

    # ...and an older backfilled partition must not roll it backwards.
    ctx2 = build_asset_context(partition_key="2026-07-01")
    form4_parquet(ctx2, {"rows": rows, "unparseable_filings": 0, "filings_attempted": 2})
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["partition"] == "2026-07-15"


def test_empty_partition_ok(tmp_path, monkeypatch):
    import edgar_pipeline.config as config
    import edgar_pipeline.storage as storage

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)

    path = storage.write_partition([], dt.date(2026, 7, 18))  # a Saturday
    assert path.exists()
