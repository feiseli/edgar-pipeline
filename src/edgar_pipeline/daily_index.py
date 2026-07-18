"""Fetch and parse EDGAR daily form indexes.

EDGAR publishes one form index per business day at
/Archives/edgar/daily-index/{year}/QTR{q}/form.{YYYYMMDD}.idx — a preamble,
a header, a dashed separator, then one fixed-width-ish row per filing.

We deliberately do NOT parse via header column offsets: in current EDGAR
files the header labels wrap across two physical lines, so header-derived
offsets are unreliable. Instead each data row is matched by its own rigid
structure, anchored from the right:

    <form type>  <company name>  <CIK digits>  <YYYYMMDD>  edgar/data/...

Form types and company names may contain single internal spaces; the row
regex requires 2+ spaces between form type and company (guaranteed by the
fixed-width form-type column) and anchors CIK/date/file-name so trailing
digits in company names can't misalign the match.
"""

from __future__ import annotations

import datetime as dt
import re

import httpx

from .config import EDGAR_BASE, FORM_TYPES
from .http import EdgarClient
from .models import IndexEntry

ROW_RE = re.compile(
    r"^(?P<form>\S+(?: \S+)*)"  # form type: tokens split by single spaces
    r"\s{2,}"
    r"(?P<company>\S.*?)"  # company name, non-greedy
    r"\s+(?P<cik>\d+)"
    r"\s+(?P<date>\d{8})"
    r"\s+(?P<file>edgar/\S+)"
    r"\s*$"
)


def daily_index_url(date: dt.date) -> str:
    quarter = (date.month - 1) // 3 + 1
    return (
        f"{EDGAR_BASE}/Archives/edgar/daily-index/{date.year}/QTR{quarter}/form.{date:%Y%m%d}.idx"
    )


def parse_form_index(text: str) -> list[IndexEntry]:
    if "<html" in text[:500].lower():
        raise ValueError(
            "EDGAR returned an HTML page instead of an index file — usually a "
            "bot-challenge/block page. Check that EDGAR_USER_AGENT identifies "
            f"you per SEC guidelines. Response starts:\n{text[:300]}"
        )

    entries: list[IndexEntry] = []
    for line in text.splitlines():
        m = ROW_RE.match(line)
        if m is None:
            continue  # preamble, header, separator, blank lines
        entries.append(
            IndexEntry(
                form_type=m["form"],
                company_name=m["company"].strip(),
                cik=int(m["cik"]),
                date_filed=dt.datetime.strptime(m["date"], "%Y%m%d").date(),
                file_name=m["file"],
            )
        )

    if not entries and text.strip():
        preview = "\n".join(line for line in text.splitlines() if line.strip())[:600]
        raise ValueError(f"no parseable rows in form index. File starts:\n{preview}")
    return entries


def fetch_form4_entries(client: EdgarClient, date: dt.date) -> list[IndexEntry]:
    """Form 4 / 4-A index entries for one day. Empty on weekends/holidays.

    EDGAR serves 403 (observed live on the 2026-07-03 holiday), not 404,
    for index files that don't exist; accept both as "no filings that day".
    """
    try:
        resp = client.get(daily_index_url(date))
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (403, 404):
            return []
        raise
    return [e for e in parse_form_index(resp.text) if e.form_type in FORM_TYPES]
