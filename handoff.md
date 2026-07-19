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

## Next steps (in order)

1. **Keep partitions fresh** — materialize the previous business day each morning, or start the Dagster schedule. After each: `make dbt` + `cd dashboard && npm run sources`.
2. **Phase B (deployment)** per scope: Hetzner VPS, Docker Compose, Caddy, healthchecks.io, B2 backups, freshness badge. Before it: profile the 2 req/s throughput and set a persistent `DAGSTER_HOME`. The compose build step should run `dbt build` + `npm run sources` + `npm run build` and serve `dashboard/build/` statically.
3. **README framing** (per Eli's stated goal): present storage decisions as choices with rejected alternatives — Parquet-on-disk + DuckDB vs Postgres, when object-storage-primary/Iceberg would win, immutable raw + dbt-layer amendment resolution, atomic partition overwrites. Object-storage-primary was explicitly considered and declined; don't reopen it. The filer-error guard (aggregate-in-price-field pattern) is a good README data-quality story.

## Verification commands

```bash
PYTHONPATH=src .venv/bin/pytest          # 15 tests
PATH="$PWD/.venv/bin:$PATH" make dbt     # 12 dbt objects green
.venv/bin/python -c "import duckdb; print(duckdb.sql(\"select count(*) from read_parquet('data/form4/*/*.parquet', hive_partitioning=true)\").fetchone())"  # 40625
```
