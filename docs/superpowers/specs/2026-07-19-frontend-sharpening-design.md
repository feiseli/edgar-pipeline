# Frontend sharpening — design

*2026-07-19. Approved via brainstorming session. Work happens during the Phase B deployment soak week.*

## Goal

Make the Evidence dashboard at edgar.edgartracker.xyz read as a distinctive,
credible data product to both engineers (judging craft) and finance people
(judging the data). Priority order if time runs short: visual identity first,
then analytics, then explainers, then fit-and-finish.

## Decisions made

- **Aesthetic: terminal.** Dark, dense, monospace numerals, Bloomberg-adjacent.
  Chosen over editorial and SaaS-product directions.
- **Approach: theme Evidence, don't fight it.** All styling via
  `evidence.config.yaml` theme + one custom CSS file. No custom Svelte
  components — **tabled**; revisit only if the themed result looks too cliché.
  A custom SvelteKit rewrite was rejected outright.
- **Layout: single column.** Evidence-native flow; no custom grid work.
- **Color encoding: buys = blue, sells = orange, everywhere.** Carries forward
  the Phase A colorblind-safe convention; green/red terminal cliché
  deliberately rejected. Dark-only, no light mode.
  - *Recorded exemption (2026-07-19, final review):* Evidence `contentType=delta`
    chips (overview leaderboards, owner net-position table) keep their
    green/red — the ▲/▼ arrow and signed number are redundant non-color
    channels, so the CVD rationale doesn't apply. The ban targets color-only
    encodings (chart series).
- No new ingestion. Every feature below is computable from existing marts.

## Features

### 1. Terminal theme (all pages)

Near-black background, thin borders, uppercase muted-gray labels, system
monospace stack (no webfonts) for numerals and tables. Implemented in
`evidence.config.yaml` + custom CSS (Evidence's app-level CSS escape hatch).

### 2. Overview additions

- **Status line** under the header, fed from the data: data-through date, row
  count, skip rate. Quiet proof the pipeline is alive.
- **Notable trades**: 10 largest open-market trades (P/S) in the trailing 7
  days, market-wide. Each row: code, symbol → issuer page, owner → owner page,
  value, EDGAR filing link, FIRST BUY badge where applicable.

### 3. First-buy flags

Computed in dbt (window over existing mart data): a purchase is flagged when
it is the owner's first code-P transaction for that issuer **in the lake**.

**Honesty rule:** with ~1 month of history this must never present as "first
ever." Badge tooltip/explainer states the lake's start date and that the
signal strengthens as history accrues. Shown in: notable trades, cluster-buys,
issuer transaction history.

### 4. Owner pages — `/owners/[owner_cik]`

Insider track record: name and role(s), per-issuer net position table, full
cross-issuer transaction history (first-buys highlighted). Owner names across
the site become links to these pages (issuer owner tables, cluster-buys
buyer lists, notable trades).

### 5. External resource links

Constructed from data already stored, no new fetching:

- Issuer pages → EDGAR issuer filing index (by CIK), Yahoo Finance (by ticker)
- Owner pages/rows → EDGAR owner filing index (by CIK)
- Transaction rows → EDGAR filing (already existed)

### 6. Explainers

Collapsible "What am I looking at?" block per page: what Form 4 is, why
open-market P/S only, what the lake covers (start date), known caveats
(filer-error guard, multi-owner filings, holdings-only filings). Plain
English, short.

### 7. Fit and finish

Favicon, per-page titles, empty states for every table/chart, mobile
spot-check, consistent number formats.

## Data/model changes (dbt)

- First-buy flag: new boolean column `is_first_buy` on
  `fct_owner_transactions` (window: min transaction_date per owner×issuer for
  code P). Existing tests keep passing; add coverage for the flag.
- Notable trades and owner pages read existing marts; no schema changes
  expected beyond the flag.

## Out of scope

- Custom Svelte components (tabled — the "signature element" ticker-tape idea
  included)
- Right-rail layout
- Light mode
- Any new EDGAR fetching or Phase C (derivative table) work

## Rollout

Local dev via `npm run dev` against the local lake. Deploy = git push; the
nightly `dashboard_nightly` job rebuilds the site on the VPS (or run the job
manually for same-day deploy). No infra changes.

## Acceptance

- All three existing pages + new owner pages render in the terminal theme
- Notable trades, first-buy badges, explainers, external links present
- `dbt build` green including new flag coverage
- Evidence `npm run build` succeeds (static build crawls owner pages via links)
- No regression in existing 15 pytest / 12 dbt objects
