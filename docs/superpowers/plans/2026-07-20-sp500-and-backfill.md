# S&P 500 Market Context + 2-Year Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest daily S&P 500 index levels into a new lake bucket, overlay them on the overview chart, and backfill the Form 4 lake to 2024-07-22.

**Architecture:** New `sp500.py` module (fetch/parse/write, mirroring `storage.py`'s atomic-overwrite pattern) + a thin unpartitioned Dagster asset on its own 23:00 ET schedule; `stg_sp500` dbt view; Evidence source + second-axis line on the existing overview chart; `start_date` moved to 2024-07-22 with a resumable VPS backfill script.

**Tech Stack:** Python 3.12, httpx, pyarrow, Dagster, dbt-duckdb, Evidence (v40), bash, Docker on the VPS.

**Spec:** `docs/superpowers/specs/2026-07-20-sp500-and-backfill-design.md`

## Global Constraints

- **No new dependencies.** Stdlib `csv` + already-installed httpx/pyarrow only.
- Local test commands: `PYTHONPATH=src .venv/bin/pytest` (15 tests green before this work), `PATH="$PWD/.venv/bin:$PATH" make dbt` (15 objects green before this work). dbt must run from `dbt/` (model paths are relative); `make dbt` handles that.
- Chart palette rule: blue/orange is the only categorical pair; the S&P line must be a neutral color, and the Evidence delta-chip green/red exemption stays untouched.
- The backfill script targets Debian (GNU `date`); it does NOT need to run on macOS.
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- The lake-start date `2026-06-22` appears in user-facing explainer text in 5 places + 1 dbt description; all move to `2024-07-22` (Task 5 lists every location).

---

### Task 1: `sp500.py` module (fetch, parse, guard, atomic write)

**Files:**
- Create: `src/edgar_pipeline/sp500.py`
- Create: `tests/fixtures/sp500_sample.csv`
- Test: `tests/test_sp500.py`

**Interfaces:**
- Consumes: `edgar_pipeline.config.DATA_DIR` (existing).
- Produces: `parse_stooq_csv(text: str) -> list[dict]`, `fetch_sp500() -> list[dict]` (raises `ValueError` on short history), `write_sp500(rows: list[dict]) -> Path` writing `data/sp500/sp500.parquet`. Task 2's asset calls `fetch_sp500` + `write_sp500`; Task 3's dbt model reads the parquet with columns `date, open, high, low, close, volume` (lowercase).

- [ ] **Step 1: Write the fixture**

`tests/fixtures/sp500_sample.csv`:

```csv
Date,Open,High,Low,Close,Volume
2026-07-15,6270.30,6295.80,6255.12,6280.12,2501234000
2026-07-16,6280.12,6315.44,6270.01,6304.55,2451234000
2026-07-17,6304.55,6330.00,6295.10,6321.78,2389456000
```

- [ ] **Step 2: Write the failing tests**

`tests/test_sp500.py`:

```python
import datetime as dt
from pathlib import Path

import pytest

import edgar_pipeline.sp500 as sp500

CSV = (Path(__file__).parent / "fixtures" / "sp500_sample.csv").read_text()


def test_parse_stooq_csv():
    rows = sp500.parse_stooq_csv(CSV)
    assert len(rows) == 3
    assert rows[0]["date"] == dt.date(2026, 7, 15)
    assert rows[2]["close"] == 6321.78
    assert rows[1]["volume"] == 2451234000.0


def test_parse_handles_missing_volume():
    # Old index rows sometimes have an empty or absent Volume field.
    text = "Date,Open,High,Low,Close,Volume\n1990-01-02,359.69,359.69,351.98,359.69,\n"
    rows = sp500.parse_stooq_csv(text)
    assert rows[0]["volume"] is None
    assert rows[0]["close"] == 359.69


class FakeResp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_fetch_refuses_short_history(monkeypatch):
    # A truncated/error response must never replace a good file.
    monkeypatch.setattr(sp500.httpx, "get", lambda *a, **k: FakeResp(CSV))
    with pytest.raises(ValueError, match="short"):
        sp500.fetch_sp500()


def test_write_roundtrip(tmp_path, monkeypatch):
    import duckdb

    monkeypatch.setattr(sp500, "DATA_DIR", tmp_path)
    rows = sp500.parse_stooq_csv(CSV)
    path = sp500.write_sp500(rows)
    assert path == tmp_path / "sp500" / "sp500.parquet"
    n, last = duckdb.sql(
        f"select count(*), max(close) from read_parquet('{path}')"
    ).fetchone()
    assert n == 3
    assert last == 6321.78

    # Idempotent overwrite
    sp500.write_sp500(rows)
    (n2,) = duckdb.sql(f"select count(*) from read_parquet('{path}')").fetchone()
    assert n2 == 3
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_sp500.py -v`
Expected: FAIL / collection error with `ModuleNotFoundError: No module named 'edgar_pipeline.sp500'`

- [ ] **Step 4: Write the implementation**

`src/edgar_pipeline/sp500.py`:

```python
"""S&P 500 daily index levels from Stooq (keyless CSV endpoint).

Layout: data/sp500/sp500.parquet — the full daily history in a single file,
rewritten atomically on every refresh. Idempotent by construction; no
incremental bookkeeping.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from .config import DATA_DIR

STOOQ_URL = "https://stooq.com/q/d/l/?s=%5Espx&i=d"

# Stooq's ^SPX daily history is tens of thousands of rows; a short response is
# a truncation or an error page and must not replace a good file.
MIN_ROWS = 5000

SCHEMA = pa.schema(
    [
        ("date", pa.date32()),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("volume", pa.float64()),
    ]
)


def parse_stooq_csv(text: str) -> list[dict]:
    """Rows from Stooq's daily CSV (header: Date,Open,High,Low,Close,Volume)."""
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        vol = r.get("Volume")
        rows.append(
            {
                "date": dt.date.fromisoformat(r["Date"]),
                "open": float(r["Open"]),
                "high": float(r["High"]),
                "low": float(r["Low"]),
                "close": float(r["Close"]),
                "volume": float(vol) if vol not in (None, "") else None,
            }
        )
    return rows


def fetch_sp500() -> list[dict]:
    resp = httpx.get(STOOQ_URL, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    rows = parse_stooq_csv(resp.text)
    if len(rows) < MIN_ROWS:
        raise ValueError(f"suspiciously short S&P 500 history ({len(rows)} rows)")
    return rows


def write_sp500(rows: list[dict]) -> Path:
    path = DATA_DIR / "sp500" / "sp500.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    tmp = path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp)
    tmp.replace(path)
    return path
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_sp500.py -v`
Expected: 4 passed

- [ ] **Step 6: Full suite still green**

Run: `PYTHONPATH=src .venv/bin/pytest`
Expected: 19 passed (15 + 4)

- [ ] **Step 7: Commit**

```bash
git add src/edgar_pipeline/sp500.py tests/test_sp500.py tests/fixtures/sp500_sample.csv
git commit -m "feat: S&P 500 daily-levels module (Stooq CSV, atomic parquet)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Dagster wiring (asset, job, schedule, start_date, job-selection fix)

**Files:**
- Modify: `src/edgar_pipeline/definitions.py`
- Test: `tests/test_definitions.py` (create)

**Interfaces:**
- Consumes: `fetch_sp500`, `write_sp500` from Task 1.
- Produces: asset `sp500_parquet`, job `sp500_daily`, schedule at 23:00 ET weekdays; `daily.start_date == "2024-07-22"`. **Critical:** `form4_daily`'s selection changes from `"*"` to `"*form4_parquet"` — with an unpartitioned asset registered, `"*"` would pull it into the partitioned job and break definitions.

- [ ] **Step 1: Write the failing test**

`tests/test_definitions.py`:

```python
def test_definitions_load_with_sp500():
    # Loading defs validates the partitioned form4 job no longer selects '*'
    # (which would illegally include the unpartitioned sp500 asset).
    from edgar_pipeline.definitions import daily, defs

    assert daily.start.date().isoformat() == "2024-07-22"
    schedules = {s.name for s in defs.schedules}
    assert schedules == {"form4_daily_schedule", "sp500_daily_schedule", "dashboard_nightly_schedule"}
    assert defs.get_assets_def("sp500_parquet") is not None
```

Note: `ScheduleDefinition(job=...)` derives names as `<job_name>_schedule`. If the assert fails on names, print `[s.name for s in defs.schedules]` and match the test to reality — the three schedules existing is the invariant, not the exact strings.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_definitions.py -v`
Expected: FAIL (start date is 2026-06-22; no sp500 schedule)

- [ ] **Step 3: Modify `definitions.py`**

Change the partitions definition (line 42):

```python
daily = DailyPartitionsDefinition(start_date="2024-07-22", timezone="US/Eastern")
```

Add the import near the other module imports:

```python
from .sp500 import fetch_sp500, write_sp500
```

Add after `form4_parquet` (before the `rebuild_dashboard` op):

```python
@asset
def sp500_parquet(context: AssetExecutionContext) -> str:
    """Full ^SPX daily history from Stooq, atomically rewritten each refresh."""
    rows = fetch_sp500()
    path = write_sp500(rows)
    context.add_output_metadata(
        {"rows": len(rows), "through": rows[-1]["date"].isoformat()}
    )
    return str(path)
```

Change the form4 job selection (was `selection="*"`) and add the sp500 job/schedule:

```python
form4_job = define_asset_job("form4_daily", selection="*form4_parquet")
sp500_job = define_asset_job("sp500_daily", selection="sp500_parquet")

# 23:00 ET: after the 22:30 Form 4 ingest, before the 23:30 dashboard rebuild,
# so the nightly dashboard picks up same-day closes.
sp500_schedule = ScheduleDefinition(
    job=sp500_job,
    cron_schedule="0 23 * * 1-5",
    execution_timezone="US/Eastern",
)
```

Update the `Definitions` at the bottom:

```python
defs = Definitions(
    assets=[form4_index_entries, form4_records, form4_parquet, sp500_parquet],
    jobs=[dashboard_nightly],
    schedules=[form4_schedule, sp500_schedule, dashboard_schedule],
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_definitions.py -v` then `PYTHONPATH=src .venv/bin/pytest`
Expected: 20 passed

- [ ] **Step 5: Materialize the asset locally (real fetch, seeds dbt/dashboard work)**

Run: `PYTHONPATH=src .venv/bin/python -c "from edgar_pipeline.sp500 import fetch_sp500, write_sp500; p = write_sp500(fetch_sp500()); print(p)"`
Expected: prints `data/sp500/sp500.parquet`; spot-check with
`.venv/bin/python -c "import duckdb; print(duckdb.sql(\"select min(date), max(date), count(*) from read_parquet('data/sp500/sp500.parquet')\").fetchone())"`
Expected: max date within the last few business days, count ≥ 5000.

- [ ] **Step 6: Commit**

```bash
git add src/edgar_pipeline/definitions.py tests/test_definitions.py
git commit -m "feat: sp500_parquet asset + 23:00 ET schedule; start_date to 2024-07-22

form4_daily selection narrowed to '*form4_parquet' so the partitioned job
doesn't swallow the unpartitioned S&P asset.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: dbt `stg_sp500` view + schema tests

**Files:**
- Create: `dbt/models/staging/stg_sp500.sql`
- Modify: `dbt/models/staging/schema.yml`

**Interfaces:**
- Consumes: `data/sp500/sp500.parquet` (Task 2 Step 5 materialized it locally).
- Produces: view `stg_sp500` with columns `date` (unique, not_null), `close` (not_null), `daily_return`. Task 4's Evidence source reads it.

- [ ] **Step 1: Write the model**

`dbt/models/staging/stg_sp500.sql`:

```sql
-- Daily S&P 500 (^SPX) index levels; source parquet is a full-history
-- atomic snapshot refreshed nightly from Stooq.

select
    date,
    close,
    close / lag(close) over (order by date) - 1 as daily_return
from read_parquet('../data/sp500/sp500.parquet')
```

- [ ] **Step 2: Add schema entry + tests**

In `dbt/models/staging/schema.yml`, append under `models:`:

```yaml
  - name: stg_sp500
    description: Daily S&P 500 (^SPX) index close from Stooq; full-history snapshot.
    columns:
      - name: date
        tests: [not_null, unique]
      - name: close
        tests: [not_null]
```

- [ ] **Step 3: Run dbt**

Run: `PATH="$PWD/.venv/bin:$PATH" make dbt`
Expected: 19 objects green (was 15: +1 model, +3 tests).

- [ ] **Step 4: Commit**

```bash
git add dbt/models/staging/stg_sp500.sql dbt/models/staging/schema.yml
git commit -m "feat(dbt): stg_sp500 view over the S&P parquet snapshot

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Dashboard overlay (Evidence source + overview chart)

**Files:**
- Create: `dashboard/sources/edgar/sp500.sql`
- Modify: `dashboard/pages/index.md` (the `daily_flows` query block, lines 59–80)

**Interfaces:**
- Consumes: dbt view `stg_sp500` (Task 3).
- Produces: Evidence table `edgar.sp500`; overview chart with S&P close on y2.

- [ ] **Step 1: Add the Evidence source**

`dashboard/sources/edgar/sp500.sql`:

```sql
select * from stg_sp500
```

- [ ] **Step 2: Rewrite the `daily_flows` block in `dashboard/pages/index.md`**

Replace the existing ```` ```sql daily_flows ```` query and its `<BarChart>` with:

````markdown
```sql daily_flows
with flows as (
    select transaction_date, 'Buys' as side, sum(buy_value) as value
    from edgar.insider_flows
    where transaction_date > (select max_date from ${anchor}) - 30
    group by 1
    union all
    select transaction_date, 'Sells', sum(sell_value)
    from edgar.insider_flows
    where transaction_date > (select max_date from ${anchor}) - 30
    group by 1
)
select flows.*, s.close as sp500_close
from flows
left join edgar.sp500 s on s.date = flows.transaction_date
order by transaction_date
```

<BarChart
    data={daily_flows}
    x=transaction_date
    y=value
    series=side
    type=grouped
    yFmt='$#,##0,,"M"'
    y2=sp500_close
    y2SeriesType=line
    y2Fmt='#,##0'
    seriesColors={{"sp500_close": "#8b949e"}}
    title="Open-market transaction value per day vs. S&P 500"
/>
````

Notes for the implementer:
- Each date appears twice (Buys/Sells rows) with the same `sp500_close`; Evidence plots the duplicate y2 points on top of each other — harmless.
- If `seriesColors` does not recolor the y2 line in this Evidence version, delete that prop and accept the palette's third slot (#85c7c6, muted teal) — do NOT touch the palette in `evidence.config.yaml` (first two slots are the CVD-validated buy/sell pair).

- [ ] **Step 3: Rebuild sources and site**

Run: `cd dashboard && npm run sources && npm run build`
Expected: both green; build log shows the `sp500` source table. Eyeball the chart via `npm run dev` if convenient (gray/neutral line on second axis, blue/orange bars unchanged).

- [ ] **Step 4: Commit**

```bash
git add dashboard/sources/edgar/sp500.sql dashboard/pages/index.md
git commit -m "feat(dashboard): S&P 500 close overlaid on daily flow chart

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Lake-start date in explainer text

**Files:**
- Modify: `dashboard/pages/index.md:16` ("Data starts 2026-06-22 and updates each")
- Modify: `dashboard/pages/index.md:86` ("(which starts 2026-06-22) — not necessarily their first ever.")
- Modify: `dashboard/pages/cluster-buys.md:14` ("(which starts 2026-06-22).")
- Modify: `dashboard/pages/owners/[owner_cik].md:23` ("dataset (which starts 2026-06-22).")
- Modify: `dashboard/pages/issuers/[issuer_cik].md:85` ("dataset (which starts 2026-06-22).")
- Modify: `dbt/models/staging/schema.yml:36` (is_first_buy description "(starts 2026-06-22)")

**Interfaces:** none — text only.

- [ ] **Step 1: Replace the date in all six locations**

In each file, replace the string `2026-06-22` with `2024-07-22` (line numbers above are pre-edit references from the current files; `grep -rn "2026-06-22" dashboard/pages dbt/models` must return nothing afterwards). The backfill runs oldest-first, so the 2024 partitions land within the first hour of the backfill — the text is accurate by the time this deploys.

- [ ] **Step 2: Verify no stragglers and dbt/docs still parse**

Run: `grep -rn "2026-06-22" dashboard/pages dbt/models; PATH="$PWD/.venv/bin:$PATH" make dbt`
Expected: no grep hits; dbt 19 objects green.

- [ ] **Step 3: Commit**

```bash
git add dashboard/pages dbt/models/staging/schema.yml
git commit -m "docs: lake start date moves to 2024-07-22 in explainers

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: `deploy/backfill.sh`

**Files:**
- Create: `deploy/backfill.sh` (mode 755)

**Interfaces:**
- Consumes: the VPS compose stack (service `dagster-daemon`, repo bind-mounted `data/`), Task 2's `'*form4_parquet'` selection string.
- Produces: resumable backfill runner, used in Task 7.

- [ ] **Step 1: Write the script**

`deploy/backfill.sh`:

```bash
#!/usr/bin/env bash
# Resumable Form 4 backfill: materialize every missing weekday partition,
# oldest first. Run on the VPS from the repo root, inside tmux:
#
#   tmux new -s backfill './deploy/backfill.sh 2024-07-22 2026-06-20'
#
# Skips partitions already on disk, so it can be killed and restarted freely.
# Sleeps through 22:15-23:45 ET: the nightly ingest carries its own 8 req/s
# limiter, and two concurrent fetchers would exceed the SEC's 10 req/s cap.
# GNU date only (Debian) - not macOS-portable, by design.
set -euo pipefail

start=${1:?usage: backfill.sh START_DATE END_DATE}
end=${2:?usage: backfill.sh START_DATE END_DATE}

d="$start"
while [[ ! "$d" > "$end" ]]; do
  dow=$(date -d "$d" +%u)
  if (( dow <= 5 )) && [[ ! -f "data/form4/filed_date=$d/form4.parquet" ]]; then
    et=$(TZ=America/New_York date +%H%M)
    while [[ "$et" > "2214" && "$et" < "2346" ]]; do
      echo "$(date -Is) in nightly-ingest window (ET $et); sleeping 10m"
      sleep 600
      et=$(TZ=America/New_York date +%H%M)
    done
    echo "=== $d"
    docker compose exec -T dagster-daemon \
      dagster asset materialize --select '*form4_parquet' \
      --partition "$d" -m edgar_pipeline.definitions
  fi
  d=$(date -d "$d + 1 day" +%F)
done
echo "backfill complete: $start..$end"
```

- [ ] **Step 2: Syntax-check and dry-run the date logic locally**

Run: `bash -n deploy/backfill.sh`
Expected: no output (parses clean). The loop/window logic uses GNU date, so behavioral testing happens on the VPS in Task 7 (first invocation IS the test — `set -e` aborts loudly on any failure, and re-running is safe by construction).

- [ ] **Step 3: Commit**

```bash
chmod +x deploy/backfill.sh
git add deploy/backfill.sh
git commit -m "feat(deploy): resumable 2-year backfill runner with ingest-window guard

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Deploy + start the backfill

**Files:** none new locally (VPS operations). Modify: `handoff.md` at the end.

**Interfaces:**
- Consumes: everything above, pushed to `origin/main`; SSH alias `edgar`; VPS repo at `/opt/edgar-pipeline`.

- [ ] **Step 1: Commit the pending housekeeping and push everything**

```bash
git add .gitignore
git commit -m "chore: untrack .DS_Store, ignore dbt-notes.md

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

(The `.DS_Store` deletion is already staged from earlier in the session; this commit picks it up.)

- [ ] **Step 2: Pull and rebuild on the VPS**

```bash
ssh edgar 'cd /opt/edgar-pipeline && git pull && docker compose build && docker compose up -d && docker compose ps'
```

Expected: pull fast-forwards past `15d94ed` to the new head; all services `running`.

- [ ] **Step 3: Enable the new schedule and seed the S&P bucket**

```bash
ssh edgar 'cd /opt/edgar-pipeline && docker compose exec -T dagster-daemon dagster schedule start --location edgar_pipeline.definitions sp500_daily_schedule || docker compose exec -T dagster-daemon dagster schedule list -m edgar_pipeline.definitions'
ssh edgar 'cd /opt/edgar-pipeline && docker compose exec -T dagster-daemon dagster asset materialize --select sp500_parquet -m edgar_pipeline.definitions'
```

Expected: schedule listed as RUNNING (exact `schedule start` invocation may need the same flags used on 2026-07-19 for the other two — mirror those if the above errors); materialization succeeds; `ls data/sp500/` on the VPS shows `sp500.parquet`.

- [ ] **Step 4: Verify the site end-to-end once**

```bash
ssh edgar 'cd /opt/edgar-pipeline && docker compose exec -T dagster-daemon dagster job execute -j dashboard_nightly -m edgar_pipeline.definitions'
curl -s https://edgar.edgartracker.xyz/status.json
```

Expected: job green (dbt 19 objects, Evidence build OK); site shows the S&P line on the overview chart (human check from a browser).

- [ ] **Step 5: Start the backfill in tmux**

```bash
ssh edgar 'cd /opt/edgar-pipeline && tmux new -d -s backfill "./deploy/backfill.sh 2024-07-22 2026-06-20 2>&1 | tee -a backfill.log"'
```

Expected: `tmux ls` shows the session; `tail -f backfill.log` shows `=== 2024-07-22` then materialization output. Watch the first 2–3 partitions complete (~5 min each), then leave it.

- [ ] **Step 6: Update `handoff.md` and commit**

Add a dated section: backfill started (range, tmux session, log path, expected ~2-day duration), sp500 asset/schedule live, soak clock restarts after backfill completes, monitoring = `tail backfill.log` + `ls data/form4 | wc -l` + skip-warnings grep (`grep -c "unparseable" backfill.log`). Replace the stale "soak starts Mon 2026-07-20" next-step.

```bash
git add handoff.md
git commit -m "Handoff: S&P 500 bucket live, 2-year backfill running, soak deferred

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```

---

## Self-Review Notes

- Spec coverage: ingest (T1/T2), dbt (T3), overlay (T4), explainer dates (T5), backfill script + rate-cap window (T6), deploy/rollout order + soak sequencing (T7). Evidence-build-growth risk is monitored post-backfill per spec ("do not pre-engineer") — deliberately no task.
- Schedule/job names in T2's test are best-guess derivations; the test includes instructions to reconcile against reality rather than fight the framework.
- T7 Step 3 flags that the exact `dagster schedule start` invocation should mirror what worked on 2026-07-19.
