# Handoff — edgar-pipeline

*Updated 2026-07-18. Companion to `~/Desktop/Personal Projects/edgar-scope.md` (the scope doc); this file tracks where work actually stands.*

## Where things stand

Phase A is two of four tasks done. The lake is fully backfilled and modeled; the dashboard is untouched.

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

1. **Evidence dashboard** — the remaining bulk of Phase A. Three pages per scope §Phase A: overview (net-flow leaderboard 30/90d, buy/sell time series, filing volume), cluster-buy screen (2+ distinct open-market buyers in a window), issuer detail (history, owners, running net flow). Marts are ready: `fct_insider_flows`, `fct_owner_transactions`. Acceptance: `npm run dev` renders all three from local data; a stranger understands the overview unaided.
2. **Keep partitions fresh** while working — materialize the previous business day each morning, or start the Dagster schedule.
3. **Phase B (deployment)** per scope: Hetzner VPS, Docker Compose, Caddy, healthchecks.io, B2 backups, freshness badge. Before it: profile the 2 req/s throughput and set a persistent `DAGSTER_HOME`.
4. **README framing** (per Eli's stated goal): present storage decisions as choices with rejected alternatives — Parquet-on-disk + DuckDB vs Postgres, when object-storage-primary/Iceberg would win, immutable raw + dbt-layer amendment resolution, atomic partition overwrites. Object-storage-primary was explicitly considered and declined; don't reopen it.

## Verification commands

```bash
PYTHONPATH=src .venv/bin/pytest          # 15 tests
PATH="$PWD/.venv/bin:$PATH" make dbt     # 12 dbt objects green
.venv/bin/python -c "import duckdb; print(duckdb.sql(\"select count(*) from read_parquet('data/form4/*/*.parquet', hive_partitioning=true)\").fetchone())"  # 40625
```
