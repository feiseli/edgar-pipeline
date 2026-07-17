"""Fetch and parse EDGAR daily form indexes.

EDGAR publishes one form index per business day at
/Archives/edgar/daily-index/{year}/QTR{q}/form.{YYYYMMDD}.idx — a header
followed by a dashed separator line and fixed-width columns. Column widths
drift across vintages, so instead of hardcoding offsets we derive them from
the header row's label positions.
"""

from __future__ import annotations

import datetime as dt

import httpx

from .config import EDGAR_BASE, FORM_TYPES
from .http import EdgarClient
from .models import IndexEntry

_COLUMNS = ["Form Type", "Company Name", "CIK", "Date Filed", "File Name"]


def daily_index_url(date: dt.date) -> str:
    quarter = (date.month - 1) // 3 + 1
    return (
        f"{EDGAR_BASE}/Archives/edgar/daily-index/{date.year}/QTR{quarter}/form.{date:%Y%m%d}.idx"
    )


def parse_form_index(text: str) -> list[IndexEntry]:
    lines = text.splitlines()
    header_i = next((i for i, line in enumerate(lines) if all(c in line for c in _COLUMNS)), None)
    if header_i is None:
        raise ValueError("no header row found in form index")

    header = lines[header_i]
    starts = [header.index(c) for c in _COLUMNS]
    bounds = list(zip(starts, starts[1:] + [None], strict=True))

    entries: list[IndexEntry] = []
    for line in lines[header_i + 1 :]:
        if not line.strip() or set(line.strip()) == {"-"}:
            continue
        fields = [line[a:b].strip() for a, b in bounds]
        form_type, company, cik, date_filed, file_name = fields
        if not cik.isdigit():
            continue  # malformed row; EDGAR indexes occasionally contain them
        entries.append(
            IndexEntry(
                form_type=form_type,
                company_name=company,
                cik=int(cik),
                date_filed=dt.datetime.strptime(date_filed, "%Y%m%d").date(),
                file_name=file_name,
            )
        )
    return entries


def fetch_form4_entries(client: EdgarClient, date: dt.date) -> list[IndexEntry]:
    """Form 4 / 4-A index entries for one day. Empty on weekends/holidays
    (EDGAR returns 404 for days with no index)."""
    try:
        resp = client.get(daily_index_url(date))
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return []
        raise
    return [e for e in parse_form_index(resp.text) if e.form_type in FORM_TYPES]
