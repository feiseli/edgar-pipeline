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


def test_parse_2026_wrapped_header_format():
    """Current EDGAR files wrap the header across two lines; the row-anchored
    parser must not care. Fixture replicates a real 2026-07-16 index."""
    text = (Path(__file__).parent / "fixtures" / "form_index_2026_wrapped_header.idx").read_text()
    entries = parse_form_index(text)
    assert [e.form_type for e in entries] == ["1-A POS", "4", "4/A", "10-K"]
    # Company name ending in digits must not bleed into the CIK match
    trust = next(e for e in entries if e.form_type == "4/A")
    assert trust.company_name == "TRUST FUND 2020"
    assert trust.cik == 1555001
    assert trust.date_filed == dt.date(2026, 7, 16)
    assert trust.accession_number == "0001555001-26-000007"


def test_form_type_filter_matches_config():
    entries = [e for e in parse_form_index(FIXTURE) if e.form_type in FORM_TYPES]
    assert len(entries) == 3
    assert all(e.form_type in {"4", "4/A"} for e in entries)


def test_missing_index_is_empty_day():
    # EDGAR serves 403 (observed live, 2026-07-03 holiday) or 404 for
    # nonexistent index files; both mean "no filings", not an error.
    import httpx

    from edgar_pipeline.daily_index import fetch_form4_entries

    class StubClient:
        def __init__(self, status):
            self.status = status

        def get(self, url):
            req = httpx.Request("GET", url)
            resp = httpx.Response(self.status, request=req)
            raise httpx.HTTPStatusError("nope", request=req, response=resp)

    for status in (403, 404):
        assert fetch_form4_entries(StubClient(status), dt.date(2026, 7, 3)) == []
