# Handoff — edgar-pipeline

*Updated 2026-07-20. Companion to `~/Desktop/Personal Projects/edgar-scope.md` (the scope doc); this file tracks where work actually stands.*

## Done: S&P 500 bucket live + 2-year backfill running (2026-07-20)

Spec/plan in `docs/superpowers/` (`2026-07-20-sp500-and-backfill-*`). All merged to main, deployed to the VPS.

- **S&P 500 ingest**: `sp500.py` (FRED CSV — Stooq now gates its CSV behind an
  anti-bot challenge we don't circumvent; spec amended), unpartitioned
  `sp500_parquet` asset, `sp500_daily_schedule` 23:00 ET RUNNING on the VPS,
  bucket seeded (`data/sp500/sp500.parquet`, ~2,500 rows). `form4_daily`
  selection narrowed to `'*form4_parquet'` so the partitioned job doesn't
  swallow the unpartitioned asset.
- **dbt**: `stg_sp500` view (date, close, daily_return) + 3 schema tests → 19
  objects green. **pytest**: 19 green (+4 sp500, +1 definitions). CI ruff
  clean after a wrap/format fix.
- **Dashboard**: S&P close overlaid on the overview daily-flow chart (y2 line,
  neutral gray `#8b949e` — blue/orange categorical pair untouched). Explainer
  lake-start text moved to 2024-07-22 in all 5 pages + dbt description.
  Verified via `dashboard_nightly` run on the VPS (green, 1m41s).
- **Backfill**: `deploy/backfill.sh` running on the VPS since ~07:39 UTC,
  range 2024-07-22 → 2026-06-20, oldest-first, resumable (skips partitions on
  disk), sleeps through the 22:15–23:45 ET ingest window. Started under
  `nohup` (pid 745809, log `/opt/edgar-pipeline/backfill.log`) — **not tmux**:
  tmux isn't installed on the VPS and this session had no sudo password.
  `apt install tmux` next time root access is handy; restarting the script
  inside tmux later is safe by construction. Expected duration ~2 days.
- **Monitoring**: `ssh edgar 'tail -5 /opt/edgar-pipeline/backfill.log'`,
  `ls /opt/edgar-pipeline/data/form4 | wc -l` (target ≈ 525),
  `grep -ci unparseable backfill.log` for skip-rate drift (capture logged
  accessions as fixtures on a spike).
- **Soak clock restarts after the backfill completes** (~Wed): the
  5-business-day unattended soak validates the end state (deep history + S&P
  job). Watch the first post-backfill nightly Evidence build for memory
  growth (~10× pages; swap is in place, `NODE_OPTIONS=--max-old-space-size`
  is the next lever).

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
  `dagster asset materialize --select '*form4_parquet' --partition <YYYY-MM-DD> -m edgar_pipeline.definitions` with `PYTHONPATH=src` and `.env` sourced. (Plain `'*'` would also select the unpartitioned `sp500_parquet`, which takes no `--partition`.)
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

## Done: frontend sharpening shipped (2026-07-19, evening)

- Spec + plan in `docs/superpowers/` (brainstormed, 6 tasks, per-task + whole-branch reviewed). Live on the VPS.
- Terminal theme (dark-only, monospace numerals, uppercase headings) via config + per-page style blocks — deliberately duplicated byte-identical across 4 pages (Evidence 40 has no global-CSS hook; human-approved). BigValue selector is markup-pinned (`div.text-xl.font-medium`) — recheck after any Evidence upgrade.
- New: `is_first_buy` dbt flag (invariant-tested incl. same-day ties), overview status line + notable-trades feed, `/owners/<cik>` track-record pages, EDGAR/Yahoo links, per-page explainers, cluster first-buy counts, favicon, empty states.
- **Recorded exemption**: Evidence delta chips keep green/red (▲/▼ + sign are non-color channels); the blue/orange rule targets color-only chart encodings. In spec.
- **Static-crawl caveat (not a bug)**: only link-discovered pages prerender (61 issuers, 317 owners). All in-site links work; hand-typed URLs for unlinked CIKs 404. An all-issuers index page would make the crawl exhaustive if ever wanted.
- Verification at merge: pytest 15, dbt 15/15 (was 12; +3 first-buy tests), `npm run build` green, live-site parquet confirmed to carry `is_first_buy`.

### Post-deploy incident: stale-schema binder errors (fixed at the server)

Eli's browser kept showing `Binder Error: is_first_buy not found` after the deploy —
survived hard refresh AND DevTools "Clear site data" (Chrome doesn't reliably purge
the HTTP disk cache there); incognito was clean. Root cause: Caddy sent **no
Cache-Control headers**, so browsers heuristically cached `data/manifest.json` and
served a pre-deploy schema against post-deploy queries. Fix (deployed): Caddyfile
now sends `no-cache` for everything except `/_app/immutable/*` and `/data/edgar/*`
(content-hashed → `immutable, max-age=1y`). Future schema-changing deploys are safe
for all visitors. If a locally poisoned cache ever recurs: DevTools open →
long-press reload → "Empty Cache and Hard Reload" is the only reliable purge.

## Next steps (in order)

1. **Five-business-day unattended soak** (scope acceptance) — starts after the backfill completes (~Wed 2026-07-22). Watch: badge date advances daily, healthchecks stays green, `docker compose ps` clean. Also kill the daemon once mid-week to confirm healthchecks alerts (acceptance item).
2. **Human visual pass** (never done — no browser access from the CLI session): live site on desktop + ~390px mobile; confirm terminal theme, monospace BigValues, favicon in tab, delta chips acceptable, tables scroll not overflow. Eli started clicking around 07-19 evening; nothing flagged beyond the (fixed) cache issue.
3. **README framing** (per Eli's stated goal): present storage decisions as choices with rejected alternatives — Parquet-on-disk + DuckDB vs Postgres, when object-storage-primary/Iceberg would win, immutable raw + dbt-layer amendment resolution, atomic partition overwrites. Object-storage-primary was explicitly considered and declined; don't reopen it. The filer-error guard (aggregate-in-price-field pattern) is a good README data-quality story. The cache-header incident + frontend build-out are also good stories.
4. **Optional, parked**: all-issuers index page (makes the static crawl exhaustive — currently 61 issuers/317 owners, only link-discovered pages prerender); custom Svelte components (tabled by Eli — revisit only if the theme reads too cliché); site-volume cruft from old hashed parquet dirs accumulates per deploy (harmless, worth a cleanup step in the nightly job someday).

## Verification commands

```bash
PYTHONPATH=src .venv/bin/pytest          # 15 tests
PATH="$PWD/.venv/bin:$PATH" make dbt     # 15 dbt objects green
.venv/bin/python -c "import duckdb; print(duckdb.sql(\"select count(*) from read_parquet('data/form4/*/*.parquet', hive_partitioning=true)\").fetchone())"  # 40625 (through 2026-07-17; grows nightly once soak starts)
curl -s https://edgar.edgartracker.xyz/status.json   # freshness endpoint
```
