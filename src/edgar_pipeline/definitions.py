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
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from dagster import (
    AssetExecutionContext,
    DailyPartitionsDefinition,
    Definitions,
    ScheduleDefinition,
    asset,
    define_asset_job,
    job,
    op,
)

from . import config
from .daily_index import fetch_form4_entries
from .form4 import fetch_form4
from .http import EdgarClient
from .models import IndexEntry
from .storage import write_partition

daily = DailyPartitionsDefinition(start_date="2026-06-22", timezone="US/Eastern")


@asset(partitions_def=daily)
def form4_index_entries(context: AssetExecutionContext) -> list[dict]:
    """Form 4 / 4-A entries from the daily form index for this partition's date."""
    date = dt.date.fromisoformat(context.partition_key)
    with EdgarClient() as client:
        entries = fetch_form4_entries(client, date)
    context.add_output_metadata({"count": len(entries)})
    return [e.model_dump(mode="json") for e in entries]


@asset(partitions_def=daily)
def form4_records(context: AssetExecutionContext, form4_index_entries: list[dict]) -> dict:
    """Fetched + parsed transactions (warehouse grain) plus fetch stats."""
    rows: list[dict] = []
    skipped = 0
    entries = [IndexEntry.model_validate(raw) for raw in form4_index_entries]
    # Sequential fetch is latency-bound (~2 req/s at ~250ms RTT); a small pool
    # keeps the shared RateLimiter (8 req/s) the binding constraint instead.
    with EdgarClient() as client, ThreadPoolExecutor(max_workers=6) as pool:
        filings = list(pool.map(lambda e: fetch_form4(client, e), entries))
    for entry, filing in zip(entries, filings, strict=True):
        if filing is None:
            skipped += 1
            # Named so a drift incident can be captured as a fixture.
            context.log.warning(f"unparseable filing skipped: {entry.accession_number}")
            continue
        rows.extend(filing.flatten())
    context.add_output_metadata({"transactions": len(rows), "unparseable_filings": skipped})
    return {"rows": rows, "unparseable_filings": skipped, "filings_attempted": len(entries)}


@asset(partitions_def=daily)
def form4_parquet(context: AssetExecutionContext, form4_records: dict) -> str:
    """One Parquet file per filed-date partition; re-runs overwrite atomically.

    Also refreshes data/status.json (partition, rows, skip rate) — the public
    freshness endpoint the README badge reads — unless a newer partition has
    already written it (backfills must not roll freshness backwards).
    """
    date = dt.date.fromisoformat(context.partition_key)
    rows = form4_records["rows"]
    # Rows arrive via the pickle IO manager with dt.date values intact —
    # exactly what write_partition's Arrow schema expects. No conversion.
    path = write_partition(rows, date)
    context.add_output_metadata({"path": str(path), "rows": len(rows)})

    status_path = config.DATA_DIR / "status.json"
    prior = json.loads(status_path.read_text()) if status_path.exists() else {}
    if prior.get("partition", "") <= context.partition_key:
        attempted = form4_records["filings_attempted"]
        skipped = form4_records["unparseable_filings"]
        status_path.write_text(
            json.dumps(
                {
                    "partition": context.partition_key,
                    "rows": len(rows),
                    "filings_attempted": attempted,
                    "unparseable_filings": skipped,
                    "skip_rate": round(skipped / attempted, 4) if attempted else 0.0,
                    "written_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                },
                indent=2,
            )
        )
    return str(path)


@op
def rebuild_dashboard(context) -> None:
    """dbt build + Evidence static rebuild; pings healthchecks.io on success.

    Runs where dbt and npm are installed alongside the package (the Docker
    image, or a dev machine from the repo root). EDGAR_PROJECT_ROOT points at
    the checkout when the package itself is installed elsewhere.
    """
    root = Path(os.environ.get("EDGAR_PROJECT_ROOT", "."))
    for desc, cmd, cwd in [
        ("dbt build", ["dbt", "build", "--profiles-dir", "."], root / "dbt"),
        ("evidence sources", ["npm", "run", "sources"], root / "dashboard"),
        ("evidence build", ["npm", "run", "build"], root / "dashboard"),
    ]:
        context.log.info(desc)
        subprocess.run(cmd, cwd=cwd, check=True)
    if ping := os.environ.get("HEALTHCHECKS_URL"):
        httpx.get(ping, timeout=10)


@job
def dashboard_nightly():
    rebuild_dashboard()


form4_job = define_asset_job("form4_daily", selection="*")

# 22:30 US/Eastern: EDGAR's daily index is complete well after the 22:00 ET
# filing deadline for the day. The dashboard rebuild follows at 23:30 — the
# ingest takes minutes, and the healthchecks ping at its end covers the whole
# chain (no ping fires if either stage died).
form4_schedule = ScheduleDefinition(
    job=form4_job,
    cron_schedule="30 22 * * 1-5",
    execution_timezone="US/Eastern",
)

dashboard_schedule = ScheduleDefinition(
    job=dashboard_nightly,
    cron_schedule="30 23 * * 1-5",
    execution_timezone="US/Eastern",
)

defs = Definitions(
    assets=[form4_index_entries, form4_records, form4_parquet],
    jobs=[dashboard_nightly],
    schedules=[form4_schedule, dashboard_schedule],
)
