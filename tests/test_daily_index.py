import datetime as dt
from pathlib import Path

from edgar_pipeline.config import FORM_TYPES
from edgar_pipeline.daily_index import daily_index_url, parse_form_index

FIXTURE = (Path(__file__).parent / "fixtures" / "form_index_sample.idx").read_text()


def test_daily_index_url_quarters():
    assert daily_index_url(dt.date(2026, 7, 15)).endswith(
        "/daily-index/2026/QTR3/form.20260715.idx"
    )
    assert "/QTR1/" in daily_index_url(dt.date(2026, 1, 2))
    assert "/QTR4/" in daily_index_url(dt.date(2026, 12, 31))


def test_parse_form_index_all_rows():
    entries = parse_form_index(FIXTURE)
    assert len(entries) == 6
    assert {e.form_type for e in entries} == {"10-Q", "4", "4/A", "8-K", "SC 13G"}


def test_parse_form_index_fields():
    entry = next(e for e in parse_form_index(FIXTURE) if e.company_name == "DOE JANE")
    assert entry.form_type == "4"
    assert entry.cik == 1214156
    assert entry.date_filed == dt.date(2026, 7, 15)
    assert entry.accession_number == "0000320193-26-000045"
    # Directory comes from file_name's CIK (the issuer's), not the row CIK
    assert entry.filing_dir_url == "/Archives/edgar/data/320193/000032019326000045"


def test_form_type_filter_matches_config():
    entries = [e for e in parse_form_index(FIXTURE) if e.form_type in FORM_TYPES]
    assert len(entries) == 3
    assert all(e.form_type in {"4", "4/A"} for e in entries)
