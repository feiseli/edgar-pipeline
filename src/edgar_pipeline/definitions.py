"""Dagster definitions: daily-partitioned assets and a schedule.

Asset graph, per filed-date partition:

    form4_index_entries -> form4_records -> form4_parquet

Weekends and market holidays materialize as empty partitions (EDGAR has no
index for them), which keeps the partition set dense and backfills trivial:

    dagster asset materialize --select '*' --partition 2026-07-16

Note: no `from __future__ import annotations` here — Dagster validates the
context parameter's annotation by identity, and stringified annotations fail.
"""

import datetime as dt

from dagster import (
    AssetExecutionContext,
    DailyPartitionsDefinition,
    Definitions,
    ScheduleDefinition,
    asset,
    define_asset_job,
)

from .daily_index import fetch_form4_entries
from .form4 import fetch_form4
from .http import EdgarClient
from .models import IndexEntry
from .storage import write_partition

daily = DailyPartitionsDefinition(start_date="2026-07-01", timezone="US/Eastern")


@asset(partitions_def=daily)
def form4_index_entries(context: AssetExecutionContext) -> list[dict]:
    """Form 4 / 4-A entries from the daily form index for this partition's date."""
    date = dt.date.fromisoformat(context.partition_key)
    with EdgarClient() as client:
        entries = fetch_form4_entries(client, date)
    context.add_output_metadata({"count": len(entries)})
    return [e.model_dump(mode="json") for e in entries]


@asset(partitions_def=daily)
def form4_records(context: AssetExecutionContext, form4_index_entries: list[dict]) -> list[dict]:
    """Fetched + parsed transactions, flattened to warehouse grain."""
    rows: list[dict] = []
    skipped = 0
    with EdgarClient() as client:
        for raw in form4_index_entries:
            filing = fetch_form4(client, IndexEntry.model_validate(raw))
            if filing is None:
                skipped += 1
                continue
            rows.extend(filing.flatten())
    context.add_output_metadata({"transactions": len(rows), "unparseable_filings": skipped})
    return rows


@asset(partitions_def=daily)
def form4_parquet(context: AssetExecutionContext, form4_records: list[dict]) -> str:
    """One Parquet file per filed-date partition; re-runs overwrite atomically."""
    date = dt.date.fromisoformat(context.partition_key)
    # Upstream asset serialized dates to ISO strings; restore them for Arrow.
    typed = [
        {
            **row,
            "period_of_report": dt.date.fromisoformat(row["period_of_report"]),
            "transaction_date": dt.date.fromisoformat(row["transaction_date"]),
        }
        for row in form4_records
    ]
    path = write_partition(typed, date)
    context.add_output_metadata({"path": str(path), "rows": len(typed)})
    return str(path)


form4_job = define_asset_job("form4_daily", selection="*")

# 22:30 US/Eastern: EDGAR's daily index is complete well after the 22:00 ET
# filing deadline for the day.
form4_schedule = ScheduleDefinition(
    job=form4_job,
    cron_schedule="30 22 * * 1-5",
    execution_timezone="US/Eastern",
)

defs = Definitions(
    assets=[form4_index_entries, form4_records, form4_parquet],
    schedules=[form4_schedule],
)
