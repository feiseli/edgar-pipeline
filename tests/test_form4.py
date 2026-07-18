import datetime as dt
from pathlib import Path

import pytest

from edgar_pipeline.form4 import find_ownership_xml, parse_form4

XML = (Path(__file__).parent / "fixtures" / "form4_sample.xml").read_bytes()
ACC = "0000320193-26-000045"


@pytest.fixture()
def filing():
    return parse_form4(XML, ACC)


def test_header_fields(filing):
    assert filing.accession_number == ACC
    assert not filing.is_amendment
    assert filing.period_of_report == dt.date(2026, 7, 14)
    assert filing.issuer_cik == 320193
    assert filing.issuer_symbol == "AAPL"
    assert filing.owner_name == "DOE JANE"
    assert filing.is_officer and not filing.is_director
    assert filing.officer_title == "Senior Vice President"


def test_transactions(filing):
    assert len(filing.transactions) == 2
    sale, gift = filing.transactions
    assert sale.transaction_code == "S"
    assert sale.shares == 10000
    assert sale.price_per_share == pytest.approx(231.505)
    assert sale.acquired_disposed == "D"
    assert sale.shares_owned_after == 152340
    assert sale.ownership_form == "D"
    # Gift has no price element -> None, not 0.0
    assert gift.transaction_code == "G"
    assert gift.price_per_share is None
    assert gift.ownership_form == "I"


def test_flatten_grain(filing):
    rows = filing.flatten()
    assert len(rows) == 2
    assert rows[0]["transaction_seq"] == 0
    assert rows[1]["transaction_seq"] == 1
    assert all(r["accession_number"] == ACC for r in rows)
    assert all(r["issuer_name"] == "Apple Inc." for r in rows)


def test_rejects_non_ownership_xml():
    with pytest.raises(ValueError, match="ownershipDocument"):
        parse_form4(b"<html><body>viewer page</body></html>", ACC)


def test_find_ownership_xml_prefers_agent_file():
    index = {
        "directory": {
            "item": [
                {"name": "0000320193-26-000045-index.htm"},
                {"name": "primary_doc.xml"},
                {"name": "wk-form4_1626389.xml"},
            ]
        }
    }
    assert find_ownership_xml(index) == "wk-form4_1626389.xml"
    assert find_ownership_xml({"directory": {"item": [{"name": "primary_doc.xml"}]}}) == (
        "primary_doc.xml"
    )
    assert find_ownership_xml({"directory": {"item": [{"name": "a.htm"}]}}) is None


def test_fetch_form4_empty_body_is_skip():
    # Observed live 2026-07-08: a filing's XML fetch returned an empty body;
    # ET.ParseError (a SyntaxError, not ValueError) must count as a skip.
    from edgar_pipeline.form4 import fetch_form4
    from edgar_pipeline.models import IndexEntry

    class StubResponse:
        content = b""

        @staticmethod
        def json():
            return {"directory": {"item": [{"name": "form4.xml"}]}}

    class StubClient:
        def get(self, url):
            return StubResponse()

    entry = IndexEntry(
        form_type="4",
        company_name="DOE JANE",
        cik=1214156,
        date_filed=dt.date(2026, 7, 8),
        file_name="edgar/data/320193/0000320193-26-000045.txt",
    )
    assert fetch_form4(StubClient(), entry) is None
