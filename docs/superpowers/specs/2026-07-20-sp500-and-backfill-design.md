# S&P 500 market context + 2-year backfill — design

*2026-07-20. Approved by Eli in session (data type, depth, UI placement, soak sequencing).*

## Goal

Two additions: (1) a new data bucket holding daily S&P 500 index price levels so
insider activity can be compared against market direction, and (2) a backfill of
the Form 4 lake from 2026-06-22 back to 2024-07-22 (~505 new weekday
partitions).

## Decisions made (with rejected alternatives)

- **Index price levels**, not constituent membership. Membership tagging (the
  README-roadmap "S&P 500 issuer enrichment") stays parked; it can be a second
  small bucket later.
- **Source: FRED daily CSV** (`https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500`)
  — one keyless HTTP GET, stdlib `csv` parse, zero new dependencies. Close
  prices only, 10 years of history (an S&P licensing limit); both are
  immaterial here — only the close is charted and the Form 4 lake is
  shallower. Market holidays arrive as `.` and are skipped.
  **Amended 2026-07-20 during implementation:** Stooq was the original choice
  and is now unusable — it gates its CSV behind a JavaScript proof-of-work
  anti-bot challenge (verified against default and browser user-agents).
  Circumventing it would contradict this project's stated policy of not
  scraping access-controlled endpoints, so the source moved to FRED. FRED had
  been rejected only for its 10-year cap, which does not bind a 2-year lake.
  Also rejected: yfinance (new dependency, unofficial API).
- **Comparison surfaces as an overlay** on the existing overview daily buy/sell
  chart (second y-axis line), not a separate page. Smallest change that makes
  the comparison visible.
- **Backfill depth: 2 years** (to 2024-07-22). Modern XML schema throughout, so
  parse risk is low; ~2 days of continuous fetching at the 8 req/s cap.
  Extending further back later is the same resumable procedure.
- **Sequencing: backfill now, soak after.** The 5-business-day unattended soak
  restarts once the backfill completes (~Wed), validating the system in its
  real end state (deep history + S&P job included).

## Component 1: S&P 500 ingest

New unpartitioned Dagster asset `sp500_parquet` in `definitions.py`:

- Fetch the daily S&P 500 series from FRED (plain `httpx`, not `EdgarClient` —
  this is not an EDGAR endpoint and needs no SEC headers/limiter; simple
  timeout + `raise_for_status`).
- Parse with stdlib `csv` → rows of `(date, close)`, skipping holiday `.`
  values.
- Write `data/sp500/sp500.parquet` atomically (write temp, `os.replace`) —
  full-file overwrite each run, idempotent by construction, no incremental
  bookkeeping. Sanity guard: refuse to overwrite if the fetched history is
  implausibly short (protects against a truncated/error response replacing a
  good file).
- Own asset job (`sp500_daily`) + weekday schedule at **23:00 ET** — after the
  22:30 Form 4 ingest, before the 23:30 dashboard rebuild, so the nightly
  dashboard picks up same-day closes. Can't join `form4_daily`: that job is
  partitioned, this asset is not.

## Component 2: dbt

- `stg_sp500` (view): `date`, `close`, `daily_return` (close / lag(close) − 1),
  reading `../data/sp500/sp500.parquet`. No mart — the dashboard queries the
  view directly.
- Schema tests: not_null on `date` and `close`, unique on `date`.

## Component 3: dashboard overlay

- Overview page, existing daily buy/sell chart: add S&P 500 close as a
  second-axis line (Evidence `y2` + `y2SeriesType="line"`).
- Line color: neutral gray from the terminal theme — preserves the
  colorblind-safe blue/orange pair as the only categorical chart encoding.
- Chart query joins daily flows to `stg_sp500` on date (left join from flows;
  market holidays that EDGAR has but Stooq lacks render as gaps in the line,
  which is honest).

## Component 4: backfill to 2024-07-22

- `daily = DailyPartitionsDefinition(start_date="2024-07-22", ...)` in
  `definitions.py`.
- `deploy/backfill.sh` (committed, run on the VPS under tmux): loop weekday
  dates oldest-first; skip any partition whose parquet file already exists
  (resumable); materialize via `docker compose exec` of the dagster container;
  **sleep during 22:15–23:45 ET** — the backfill and the nightly ingest each
  carry an independent 8 req/s limiter and running both would exceed the SEC's
  10 req/s cap.
- The `status.json` monotonic-partition guard (already regression-tested)
  keeps backfilled partitions from rolling the freshness badge backwards.
- Watch skip rate during the run; a spike means format drift → capture the
  logged accession as a fixture per the existing drift workflow.

## Testing

- Fixture test for the Stooq CSV→rows parse (same style as existing parser
  tests), including the short-response guard path.
- dbt schema tests above; `dbt build` count grows accordingly.
- Existing 15 pytest must stay green (start_date move touches no logic).

## Risks

- **Evidence build growth**: ~10× issuers/owners after backfill inflates the
  static crawl (currently 61 issuer + 317 owner pages) and node build memory
  (OOM'd once at 2.6GB; swap now in place). Levers in order:
  `NODE_OPTIONS=--max-old-space-size`, then capping prerendered pages to
  recent activity. Watch the first post-backfill nightly build; do not
  pre-engineer.
- **Stooq availability**: if a fetch fails, the schedule just retries next
  night and the dashboard shows yesterday's line — acceptable staleness, no
  special handling.
- **is_first_buy semantics deepen**: with 2 years of history the lake-relative
  flag becomes meaningfully closer to "first ever"; no code change, but the
  owner-page explainer text should say history starts 2024-07-22.

## Deploy / rollout order

1. Land code (branch → tests/dbt/build green → merge → push).
2. VPS: `git pull`, rebuild image, restart compose (schedules persist).
3. Start `deploy/backfill.sh` in tmux; monitor via `status.json`-adjacent
   Dagster run history and disk partitions.
4. After backfill completes: verify a nightly chain end-to-end, then restart
   the 5-business-day soak clock.
