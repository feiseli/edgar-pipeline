# Handoff — edgar-pipeline

*Updated 2026-07-19. Companion to `~/Desktop/Personal Projects/edgar-scope.md` (the scope doc); this file tracks where work actually stands.*

## Where things stand

Phase A is complete. The lake is backfilled through 2026-07-17 (20 partitions), modeled, and the Evidence dashboard renders all three pages from local data.

### Done: evidence dashboard (acceptance met)

- Evidence app in `dashboard/` (template scaffold + duckdb source pointed at `data/edgar.duckdb`). `cd dashboard && npm run dev` for live dev; `npm run build` prerenders the static site (all issuer pages crawled from leaderboard/cluster links).
- Three pages per scope: overview (30d KPIs, daily buy/sell chart, 30/90d net-flow leaderboards, filing volume), cluster-buy screen (2+ distinct open-market buyers, window toggle, <$100k clusters hidden), issuer detail (`/issuers/<cik>`: running net flow, owners, full history with EDGAR links).
- Rebuild flow after new partitions: `make dbt`, then `cd dashboard && npm run sources` (dev picks it up; `npm run build` for static).
- Buy/sell chart colors are blue/orange, not green/red — the green/red pair fails colorblind (deutan) contrast checks; palette lives in `dashboard/evidence.config.yaml`.

### Done: data-quality guard found while building the dashboard

Dashboard totals exposed filer-error rows: a FINS filing with $40M in **both** the shares and price fields ($1.6 quadrillion row; EDGAR has since removed the filing entirely), and a pattern of **aggregate proceeds entered in the per-share price field** (STNG: 15,000 sh at "$1,230,435" — footnote admits it's the total; MFG rows are yen amounts). Fix: `is_implausible` flag in `stg_form4_transactions` (price > $10k with 100+ shares, price > $2M, or row value > $20B — thresholds chosen from the observed distribution; every legit price in the lake is < $10k), both marts exclude flagged rows, singular dbt test `assert_no_implausible_values` guards it. 19 rows currently flagged. Raw parquet stays untouched per the immutable-raw design.

### Done: dbt wiring (acceptance met)

- `dbt-duckdb` installed (in `[dev]` extras). Run with `make dbt` (= `cd dbt && dbt build --profiles-dir .` — model paths like `../data/...` are relative to `dbt/`, so always run from there). `dbt/profiles.yml` is local-only (gitignored); copy from `profiles.example.yml` on a fresh machine.
- `dbt build` green: 12 objects — `stg_form4_transactions` (view), `fct_insider_flows` + `fct_owner_transactions` (tables), 9 tests.
- The amendment-supersession invariant is a singular dbt test (`dbt/tests/assert_amendment_supersession.sql`), verified against 560 genuine 4/A rows.
- `fct_owner_transactions` (owner-level mart for the dashboard's issuer pages) is already built: role labeling, signed open-market value.

### Done: backfill (acceptance met)

- 19 weekday partitions on disk, 2026-06-22 → 2026-07-16 (Dagster `start_date` moved to 2026-06-22), 40,625 transaction rows, ~10k distinct filings. 07-03 is a legit empty holiday partition.
- Skip rate ≈ 0.01% (1 unparseable filing across the whole backfill) — far under the 2% bar.
- Idempotency demonstrated: re-materialized 2026-07-15 end-to-end; row count and content hash identical.
- Full-day ingest is implicitly validated (19 of them) — the scope's separate "full-day ingest test" task is effectively done. Real timing: **~7–30 min per day**, not the estimated 5; effective throughput is ~2 req/s vs the configured 8. Profile `src/edgar_pipeline/http.py` before nightly scheduling if that matters (suspect: per-request minimum-interval limiter + sequential fetch, no pipelining).

### Bugs found and fixed during backfill (all regression-tested, 15 tests green)

1. `form4_parquet` asset assumed upstream rows carried ISO date strings; the pickle IO manager delivers `dt.date`. Conversion deleted (`definitions.py`).
2. EDGAR serves **403, not 404**, for missing daily-index files (observed on the 07-03 holiday). `fetch_form4_entries` now treats both as an empty day.
3. An empty XML body raised `ET.ParseError`, which is a `SyntaxError` — it escaped `fetch_form4`'s `except ValueError` skip path and failed a whole partition. Now caught; skipped filings log their accession number so incidents can be captured as fixtures (the scope's drift workflow).

### Important non-bug: why lake accessions ≪ index rows

Expect the lake to hold ~40–50% of daily index *rows*. Two structural reasons, verified by sampling: the index lists one row **per reporting owner** (multi-owner filings duplicate accessions), and many Form 4s are **holdings-only or derivative-only** — zero non-derivative transaction rows, so they legitimately produce nothing until Phase C's `derivativeTable` parsing. Do not read the gap as data loss; the sampled gap contained zero parse failures.

## Operational notes

- The macOS editable install intermittently loses the package. Workaround baked into scripts: `PYTHONPATH=src` (or reinstall: `pip install -e ".[dev]" --force-reinstall --no-deps`). Docker deploy retires this.
- Long local runs: launch under `caffeinate -is` — an overnight run was killed by laptop sleep.
- Backfill script pattern (resumable, skips partitions already on disk) is in the session scratchpad; the core loop is just:
  `dagster asset materialize --select '*' --partition <YYYY-MM-DD> -m edgar_pipeline.definitions` with `PYTHONPATH=src` and `.env` sourced.
- Dagster CLI runs don't persist run history (ephemeral `DAGSTER_HOME`), and per-partition metadata isn't retained — skip-rate trending in the Dagster UI needs a real `DAGSTER_HOME`, worth setting up before Phase B.

## Done: Phase B build-out (2026-07-19) — verified locally, not yet on a VPS

- **Throughput fixed**: the ~2 req/s was the sequential fetch loop being latency-bound (~250ms RTT), not the limiter. `form4_records` now fans out over a 6-worker thread pool sharing the (thread-safe) client+limiter; a full day re-materialized in 5m31s vs 13m52s (~8 req/s, at the configured cap). Row count and content identical — idempotency holds under concurrency.
- **Persistent `DAGSTER_HOME`**: `.dagster/` (gitignored except `dagster.yaml`); `make dev` / `make materialize DATE=...` wire it in. Run history and per-partition skip-rate metadata now survive.
- **Freshness endpoint**: `form4_parquet` writes `data/status.json` (partition, rows, skip rate); guarded so backfilling an older partition can't roll freshness backwards (regression-tested). Badge template in `deploy/README.md` reads it via shields dynamic-JSON.
- **Docker stack**: one image (python + node, non-editable install — retires the editable-install quirk), compose services `dagster-webserver` (localhost-only, SSH tunnel — deliberately not public), `dagster-daemon`, `caddy` (auto-HTTPS, serves the Evidence build volume + `/status.json`). `data/` and `.dagster/` are bind mounts so backup/seed is plain tar/rsync.
- **Nightly rebuild is a second Dagster schedule** (`dashboard_nightly`, 23:30 ET): dbt + Evidence build + healthchecks.io ping on success — one orchestrator, and the ping covers the whole chain. Verified end-to-end in the local compose stack: job green in-container, Caddy served the site and status.json over HTTPS.
- **Backups**: `deploy/backup.sh` (tar lake + dagster home → B2 via rclone, rolling 35 days) with the cron line in its header.

## Done: deployed to VPS (2026-07-19)

- Hetzner CX22 (`167.233.216.161`, Debian 12), non-root `eli` user, password auth off, unattended-upgrades. Laptop `~/.ssh/config` has `Host edgar`.
- Live at **https://edgar.edgartracker.xyz** (Porkbun domain; Caddy auto-HTTPS working). `status.json` served; badge added to README (uncommitted).
- Lake seeded by rsync (20 partitions, status.json byte-identical), repo at `15d94ed` in `/opt/edgar-pipeline`.
- Both schedules RUNNING (enabled via `dagster schedule start` CLI — UI not needed): 22:30 ET ingest, 23:30 ET dashboard.
- healthchecks.io wired (`hc-ping.com/fbab85c3-...`); first successful `dashboard_nightly` run pinged it.
- Backups proven end-to-end: rclone remote `b2` → bucket `edgar-pipeline-backups`, cron `15 5 * * 2-6` under `eli`, first tarball uploaded, **restore rehearsed** (pulled from B2, 20 parquet files, status.json identical) — scope's restore-rehearsal item done.
- **Incident**: first `dashboard_nightly` run OOM-locked the box — Evidence's node build peaked ~2.6GB RSS on the 4GB CX22 (no swap by default on Hetzner); SSH froze until the OOM killer got node. Fix: 2GB swapfile (persistent via fstab). Rerun succeeded in 1m15s. If builds grow, next lever is `NODE_OPTIONS=--max-old-space-size` or a compose mem limit.

## Next steps (in order)

1. **Five-business-day unattended soak** (scope acceptance) — starts Mon 2026-07-20. Watch: badge date advances daily, healthchecks stays green, `docker compose ps` clean. Also kill the daemon once mid-week to confirm healthchecks alerts (acceptance item).
2. **README framing** (per Eli's stated goal): present storage decisions as choices with rejected alternatives — Parquet-on-disk + DuckDB vs Postgres, when object-storage-primary/Iceberg would win, immutable raw + dbt-layer amendment resolution, atomic partition overwrites. Object-storage-primary was explicitly considered and declined; don't reopen it. The filer-error guard (aggregate-in-price-field pattern) is a good README data-quality story.
3. **Frontend sharpening** during the soak week.

## Verification commands

```bash
PYTHONPATH=src .venv/bin/pytest          # 15 tests
PATH="$PWD/.venv/bin:$PATH" make dbt     # 12 dbt objects green
.venv/bin/python -c "import duckdb; print(duckdb.sql(\"select count(*) from read_parquet('data/form4/*/*.parquet', hive_partitioning=true)\").fetchone())"  # 40625
```
