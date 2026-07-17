"""End-to-end smoke run against live EDGAR for a single day, no Dagster.

    EDGAR_USER_AGENT="You you@example.com" python -m edgar_pipeline.smoke 2026-07-15 --limit 25

Fetches that day's Form 4 index, parses up to --limit filings, writes the
Parquet partition, and prints a DuckDB summary. Use this to verify the
pipeline before standing up orchestration.
"""

from __future__ import annotations

import argparse
import datetime as dt

from .daily_index import fetch_form4_entries
from .form4 import fetch_form4
from .http import EdgarClient
from .storage import connect, write_partition


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("date", type=dt.date.fromisoformat)
    ap.add_argument("--limit", type=int, default=25, help="max filings to fetch (default 25)")
    args = ap.parse_args()

    with EdgarClient() as client:
        entries = fetch_form4_entries(client, args.date)
        print(f"{len(entries)} Form 4/4-A filings in the {args.date} index")
        rows: list[dict] = []
        skipped = 0
        for entry in entries[: args.limit]:
            filing = fetch_form4(client, entry)
            if filing is None:
                skipped += 1
                continue
            rows.extend(filing.flatten())

    path = write_partition(rows, args.date)
    print(f"wrote {len(rows)} transactions ({skipped} filings skipped) -> {path}")

    con = connect()
    rows = con.execute(
        """
        SELECT transaction_code, count(*) AS n,
               round(sum(shares * price_per_share)) AS gross_value
        FROM form4_transactions
        GROUP BY 1 ORDER BY n DESC
        """
    ).fetchall()
    print(f"{'code':<6}{'txns':>8}{'gross_value':>16}")
    for code, n, gross in rows:
        gross_s = f"{gross:,.0f}" if gross is not None else "-"
        print(f"{code:<6}{n:>8}{gross_s:>16}")


if __name__ == "__main__":
    main()
