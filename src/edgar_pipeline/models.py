"""Typed records flowing through the pipeline."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class IndexEntry(BaseModel):
    """One row of an EDGAR daily form index."""

    form_type: str
    company_name: str
    cik: int
    date_filed: dt.date
    file_name: str  # e.g. edgar/data/320193/0000320193-26-000045.txt

    @property
    def accession_number(self) -> str:
        return self.file_name.rsplit("/", 1)[-1].removesuffix(".txt")

    @property
    def filing_dir_url(self) -> str:
        # Derive the directory from file_name, not from this row's CIK: for
        # ownership forms the daily index lists a row per filer (issuer and
        # owner), but the filing lives under the single CIK in file_name.
        dir_cik = self.file_name.split("/")[2]
        acc = self.accession_number.replace("-", "")
        return f"/Archives/edgar/data/{dir_cik}/{acc}"


class Form4Transaction(BaseModel):
    """One non-derivative transaction line from a Form 4."""

    security_title: str
    transaction_date: dt.date
    transaction_code: str  # P=open-market buy, S=sale, A=grant, M=option exercise, ...
    shares: float | None
    price_per_share: float | None  # None when the price is footnoted, not stated
    acquired_disposed: str  # A or D
    shares_owned_after: float | None
    ownership_form: str | None  # D=direct, I=indirect


class Form4Filing(BaseModel):
    """A parsed Form 4 ownership document."""

    accession_number: str
    is_amendment: bool
    period_of_report: dt.date
    issuer_cik: int
    issuer_name: str
    issuer_symbol: str | None
    owner_cik: int
    owner_name: str
    is_director: bool
    is_officer: bool
    is_ten_percent_owner: bool
    officer_title: str | None
    transactions: list[Form4Transaction]

    def flatten(self) -> list[dict]:
        """One dict per transaction, filing fields denormalized on — the
        Parquet/warehouse grain."""
        base = self.model_dump(exclude={"transactions"})
        rows = []
        for i, txn in enumerate(self.transactions):
            row = base | txn.model_dump()
            row["transaction_seq"] = i
            rows.append(row)
        return rows
