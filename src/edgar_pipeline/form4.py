"""Parse Form 4 ownership XML documents.

EDGAR filings are folders; the ownership document is an XML file whose root
element is <ownershipDocument>. We locate it via the filing's index.json
rather than guessing filenames (they vary by filing agent: form4.xml,
doc4.xml, wk-form4_*.xml, ...).

Values are frequently wrapped as <tag><value>x</value></tag>, and prices are
sometimes absent (footnoted) — the parser treats those as None rather than
guessing.
"""

from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET

from .config import EDGAR_BASE
from .http import EdgarClient
from .models import Form4Filing, Form4Transaction, IndexEntry


def _text(node: ET.Element | None) -> str | None:
    """Unwrap <tag>text</tag> or <tag><value>text</value></tag>."""
    if node is None:
        return None
    value = node.find("value")
    raw = (value.text if value is not None else node.text) or ""
    return raw.strip() or None


def _float(node: ET.Element | None) -> float | None:
    raw = _text(node)
    return float(raw) if raw is not None else None


def _flag(node: ET.Element | None) -> bool:
    return (_text(node) or "").lower() in {"1", "true"}


def _date(raw: str | None) -> dt.date:
    if raw is None:
        raise ValueError("missing required date")
    return dt.date.fromisoformat(raw)


def parse_form4(xml_bytes: bytes, accession_number: str) -> Form4Filing:
    root = ET.fromstring(xml_bytes)
    if root.tag != "ownershipDocument":
        raise ValueError(f"expected ownershipDocument, got <{root.tag}>")

    issuer = root.find("issuer")
    if issuer is None:
        raise ValueError("Form 4 has no <issuer>")
    owner = root.find("reportingOwner")
    if owner is None:
        raise ValueError("Form 4 has no <reportingOwner>")
    owner_id = owner.find("reportingOwnerId")
    rel = owner.find("reportingOwnerRelationship")

    transactions = []
    for txn in root.iter("nonDerivativeTransaction"):
        amounts = txn.find("transactionAmounts")
        post = txn.find("postTransactionAmounts")
        transactions.append(
            Form4Transaction(
                security_title=_text(txn.find("securityTitle")) or "",
                transaction_date=_date(_text(txn.find("transactionDate"))),
                transaction_code=_text(txn.find("transactionCoding/transactionCode")) or "",
                shares=_float(amounts.find("transactionShares") if amounts is not None else None),
                price_per_share=_float(
                    amounts.find("transactionPricePerShare") if amounts is not None else None
                ),
                acquired_disposed=_text(
                    amounts.find("transactionAcquiredDisposedCode") if amounts is not None else None
                )
                or "",
                shares_owned_after=_float(
                    post.find("sharesOwnedFollowingTransaction") if post is not None else None
                ),
                ownership_form=_text(txn.find("ownershipNature/directOrIndirectOwnership")),
            )
        )

    return Form4Filing(
        accession_number=accession_number,
        is_amendment=(_text(root.find("documentType")) or "") == "4/A",
        period_of_report=_date(_text(root.find("periodOfReport"))),
        issuer_cik=int(_text(issuer.find("issuerCik")) or 0),
        issuer_name=_text(issuer.find("issuerName")) or "",
        issuer_symbol=_text(issuer.find("issuerTradingSymbol")),
        owner_cik=int((_text(owner_id.find("rptOwnerCik")) if owner_id is not None else None) or 0),
        owner_name=(_text(owner_id.find("rptOwnerName")) if owner_id is not None else None) or "",
        is_director=_flag(rel.find("isDirector") if rel is not None else None),
        is_officer=_flag(rel.find("isOfficer") if rel is not None else None),
        is_ten_percent_owner=_flag(rel.find("isTenPercentOwner") if rel is not None else None),
        officer_title=_text(rel.find("officerTitle") if rel is not None else None),
        transactions=transactions,
    )


def find_ownership_xml(index_json: dict) -> str | None:
    """Pick the ownership XML filename out of a filing's index.json listing.

    Prefers XML files that aren't the SEC-generated 'primary_doc' viewer copy
    only if others exist; any .xml is a candidate — the caller verifies the
    root tag.
    """
    items = index_json.get("directory", {}).get("item", [])
    xml_names = [i["name"] for i in items if i.get("name", "").lower().endswith(".xml")]
    non_primary = [n for n in xml_names if not n.lower().startswith("primary_doc")]
    candidates = non_primary or xml_names
    return candidates[0] if candidates else None


def fetch_form4(client: EdgarClient, entry: IndexEntry) -> Form4Filing | None:
    """Fetch and parse the ownership document for one index entry.

    Returns None when the filing contains no parseable ownership XML (rare,
    but paper filings and exotic agents exist) — callers count these as skips,
    not errors.
    """
    dir_url = f"{EDGAR_BASE}{entry.filing_dir_url}"
    index = client.get(f"{dir_url}/index.json").json()
    name = find_ownership_xml(index)
    if name is None:
        return None
    xml_bytes = client.get(f"{dir_url}/{name}").content
    try:
        return parse_form4(xml_bytes, entry.accession_number)
    except ValueError:
        return None
