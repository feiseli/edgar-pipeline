# Frontend Sharpening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Terminal-styled Evidence dashboard with notable-trades feed, first-buy flags, owner track-record pages, external resource links, and per-page explainers.

**Architecture:** Theme Evidence via config + small `:global()` style blocks (no custom Svelte components — tabled per spec). One new dbt column (`is_first_buy`) powers badges everywhere. One new dynamic page (`/owners/[owner_cik]`). All data comes from existing marts; no new ingestion.

**Tech Stack:** Evidence 40.1.8 (markdown pages + DuckDB source), dbt-duckdb, existing Dagster deploy.

## Global Constraints

- Buys = blue, sells = orange, everywhere. Never green/red (colorblind-unsafe; Phase A decision). The existing CVD-validated palettes in `evidence.config.yaml` stay untouched.
- Dark-only. No light mode, no switcher.
- No webfonts — system monospace stack only (`ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`).
- No new npm/python dependencies. No custom Svelte components. No edits under `dashboard/.evidence/` (regenerated).
- First-buy language must always say "first in this dataset", never "first ever". The lake starts 2026-06-22.
- All dbt commands run from `dbt/` via `PATH="$PWD/.venv/bin:$PATH" make dbt` (repo root). Dashboard dev: `cd dashboard && npm run sources && npm run dev`.
- Verification floor: 15 pytest green, dbt build green, `npm run build` green.

---

### Task 1: dbt `is_first_buy` flag

**Files:**
- Modify: `dbt/models/marts/fct_owner_transactions.sql`
- Modify: `dbt/models/staging/schema.yml`
- Test: `dbt/tests/assert_first_buy_invariant.sql`

**Interfaces:**
- Produces: boolean column `is_first_buy` on `fct_owner_transactions` — true iff the row is a code-P transaction and its `transaction_date` equals the earliest code-P date for that (owner_cik, issuer_cik). Same-day ties: all tied rows flagged. Consumed by Tasks 3, 4, 5.

- [ ] **Step 1: Write the failing singular test**

Create `dbt/tests/assert_first_buy_invariant.sql`:

```sql
-- Rows violating the first-buy invariant. Empty result = pass.
-- Invariant: within each (owner, issuer), the flagged rows are exactly the
-- code-P rows on the earliest P date; non-P rows are never flagged.
with p as (
    select * from {{ ref('fct_owner_transactions') }}
    where transaction_code = 'P'
)

select owner_cik, issuer_cik, 'bad_p_flagging' as violation
from p
group by 1, 2
having count(*) filter (where is_first_buy) = 0
    or min(transaction_date) filter (where is_first_buy) <> min(transaction_date)
    or max(transaction_date) filter (where is_first_buy) <> min(transaction_date)

union all

select owner_cik, issuer_cik, 'non_p_flagged' as violation
from {{ ref('fct_owner_transactions') }}
where transaction_code is distinct from 'P' and is_first_buy
group by 1, 2
```

- [ ] **Step 2: Run to verify it fails**

Run (repo root): `PATH="$PWD/.venv/bin:$PATH" make dbt`
Expected: FAIL — compilation error, `is_first_buy` does not exist yet.

- [ ] **Step 3: Add the column**

In `dbt/models/marts/fct_owner_transactions.sql`, add after the `signed_value` case expression (keep the trailing comma structure intact):

```sql
    coalesce(
        transaction_code = 'P'
        and transaction_date = min(case when transaction_code = 'P' then transaction_date end)
                over (partition by owner_cik, issuer_cik),
        false
    ) as is_first_buy,
```

- [ ] **Step 4: Declare + test the column in schema.yml**

In `dbt/models/staging/schema.yml`, under `fct_owner_transactions` columns, add:

```yaml
      - name: is_first_buy
        description: >
          True iff this is a code-P transaction on the owner's earliest P date
          for this issuer within the lake (starts 2026-06-22). Not "first ever".
        tests: [not_null]
```

- [ ] **Step 5: Run to verify green**

Run: `PATH="$PWD/.venv/bin:$PATH" make dbt`
Expected: all green; object count goes 12 → 14 (new singular test + new not_null test).

- [ ] **Step 6: Refresh dashboard sources and commit**

```bash
cd dashboard && npm run sources && cd ..
git add dbt/models dbt/tests
git commit -m "feat(dbt): is_first_buy flag on fct_owner_transactions"
```

---

### Task 2: Terminal theme

**Files:**
- Modify: `dashboard/evidence.config.yaml:1-3` (appearance block), `:43-45` (base color)
- Modify: `dashboard/pages/index.md`, `dashboard/pages/cluster-buys.md`, `dashboard/pages/issuers/[issuer_cik].md` (style block at end of each)

**Interfaces:**
- Produces: the shared style block below. Task 4 pastes the same block into the new owners page. Keep the four copies identical (marker comment included).

- [ ] **Step 1: Dark-only appearance**

In `dashboard/evidence.config.yaml` replace the `appearance:` block:

```yaml
appearance:
  default: dark
  switcher: false
```

- [ ] **Step 2: Terminal background**

In the same file, change the `base` color token's dark value (light value is now unused but harmless):

```yaml
    base:
      light: "#ffffff"
      dark: "#0d1117"
```

- [ ] **Step 3: Add the shared style block**

Append this exact block to the END of each of the three pages (`index.md`, `cluster-buys.md`, `issuers/[issuer_cik].md`):

```html
<!-- terminal-theme block: keep identical across all pages -->
<style>
  :global(main table),
  :global(main .markdown table),
  :global(main [class*="bigvalue"]),
  :global(main [class*="big-value"]) {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-variant-numeric: tabular-nums;
  }
  :global(main h2) {
    text-transform: uppercase;
    font-size: 0.95rem;
    letter-spacing: 0.08em;
  }
  :global(main h3) {
    text-transform: uppercase;
    font-size: 0.85rem;
    letter-spacing: 0.06em;
    opacity: 0.8;
  }
</style>
```

- [ ] **Step 4: Verify in dev**

Run: `cd dashboard && npm run dev`, open http://localhost:3000.
Expected: near-black background everywhere, no theme switcher in the menu, table numerals monospace, section headings uppercase. If BigValue numerals are NOT monospace, inspect one in devtools, find its stable class, and add that class to the first `:global()` selector group in all copies of the block.

- [ ] **Step 5: Commit**

```bash
git add dashboard/evidence.config.yaml dashboard/pages
git commit -m "feat(dashboard): dark-only terminal theme"
```

---

### Task 3: Overview — status line, notable trades, explainer

**Files:**
- Modify: `dashboard/pages/index.md`

**Interfaces:**
- Consumes: `is_first_buy` (Task 1).
- Produces: owner-page URL convention `'/owners/' || owner_cik::bigint` — Task 4's page must live at that route.

- [ ] **Step 1: Status line**

In `index.md`, directly after the `anchor` SQL block, add:

```markdown
```sql lake_status
select
    (select max(transaction_date)::date from edgar.owner_transactions) as through_date,
    count(*) as rows_total,
    count(distinct issuer_cik) as issuers_total
from edgar.owner_transactions
```

<p class="status-line">
  DATA THROUGH <Value data={lake_status} column=through_date/> ·
  <Value data={lake_status} column=rows_total fmt='#,##0'/> ROWS ·
  <Value data={lake_status} column=issuers_total fmt='#,##0'/> ISSUERS ·
  UPDATED EACH BUSINESS DAY FROM SEC EDGAR
</p>
```

And add to the terminal-theme style block on this page (inside the existing `<style>`):

```css
  :global(.status-line) {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.75rem;
    letter-spacing: 0.06em;
    opacity: 0.65;
    border-bottom: 1px solid rgba(139, 148, 158, 0.3);
    padding-bottom: 0.5em;
  }
```

- [ ] **Step 2: Notable trades section**

Add before the `## Net-flow leaderboard` section:

```markdown
## Notable trades

Largest individual open-market trades reported in the trailing 7 days.
"First buy" marks an insider's first purchase of that issuer in this dataset
(which starts 2026-06-22) — not necessarily their first ever.

```sql notable
select
    transaction_code as code,
    any_value(issuer_symbol) as symbol,
    owner_name,
    transaction_date,
    sum(gross_value) as value,
    max(case when is_first_buy then 'FIRST BUY' else '' end) as flag,
    '/issuers/' || issuer_cik::bigint as issuer_link,
    '/owners/'  || owner_cik::bigint  as owner_link,
    'https://www.sec.gov/Archives/edgar/data/' || issuer_cik::bigint || '/'
        || replace(accession_number, '-', '') || '/'
        || accession_number || '-index.htm' as filing
from edgar.owner_transactions
where transaction_code in ('P', 'S')
  and transaction_date > (select max_date from ${anchor}) - 7
group by accession_number, transaction_code, issuer_cik, owner_cik, owner_name, transaction_date
order by value desc
limit 10
```

<DataTable data={notable} link=issuer_link>
    <Column id=code align=center/>
    <Column id=symbol/>
    <Column id=owner_link contentType=link linkLabel=owner_name title="Owner"/>
    <Column id=transaction_date/>
    <Column id=value fmt='$#,##0.0,,"M"'/>
    <Column id=flag/>
    <Column id=filing contentType=link linkLabel="EDGAR →"/>
</DataTable>
```

- [ ] **Step 3: Explainer block**

Replace the intro paragraph of `index.md` (lines 5–8, "Open-market insider transactions … shares × reported price.") with:

```markdown
Open-market insider transactions reported to the SEC on Form 4.

<Details title="What am I looking at?">

Corporate insiders — officers, directors, 10% owners — must report their
trades to the SEC on Form 4 within two business days. This dashboard tracks
**open-market buys and sells only** (transaction codes P and S): actual
purchases and sales at market price, where an insider put their own money at
stake. Grants, option exercises, gifts, and tax withholdings are excluded —
they carry no price-sensitive signal.

Value is shares × reported price. Data starts 2026-06-22 and updates each
business day. Rows with implausible filer-entered values (e.g. aggregate
proceeds typed into the per-share price field) are excluded by an automated
guard.

</Details>
```

- [ ] **Step 4: Verify in dev**

`cd dashboard && npm run dev` → overview shows status line under the title, notable-trades table with an EDGAR link per row and at least one non-empty `flag` cell (scan the table; if none in the current 7-day window, temporarily widen `- 7` to `- 30` to confirm the flag renders, then set it back).
Expected: no SQL errors, all values formatted.

- [ ] **Step 5: Commit**

```bash
git add dashboard/pages/index.md
git commit -m "feat(dashboard): status line, notable trades, overview explainer"
```

---

### Task 4: Owner pages + owner links

**Files:**
- Create: `dashboard/pages/owners/[owner_cik].md`
- Modify: `dashboard/pages/issuers/[issuer_cik].md` (owners table gains link; header gains external links)

**Interfaces:**
- Consumes: route convention `/owners/<cik>` (Task 3), `is_first_buy` (Task 1), terminal style block (Task 2).

- [ ] **Step 1: Create the owner page**

Create `dashboard/pages/owners/[owner_cik].md`:

````markdown
```sql owner_info
select
    any_value(owner_name) as owner_name,
    string_agg(distinct owner_role, ' · ') as roles,
    'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK='
        || owner_cik::bigint || '&type=4' as edgar_owner
from edgar.owner_transactions
where owner_cik = ${params.owner_cik}
group by owner_cik
```

# <Value data={owner_info} column=owner_name/>

<Value data={owner_info} column=roles/> · <a href={owner_info[0]?.edgar_owner} target="_blank" rel="noopener">Filings on EDGAR →</a>

<Details title="What am I looking at?">

Every Form 4 transaction this person has reported, across all issuers in this
dataset (which starts 2026-06-22). "First buy" marks their first open-market
purchase of an issuer within the dataset — not necessarily their first ever.

</Details>

## Net position by issuer

Open-market activity only (codes P and S).

```sql by_issuer
select
    any_value(issuer_symbol) as symbol,
    any_value(issuer_name)   as issuer,
    sum(case when transaction_code = 'P' then gross_value end) as bought,
    sum(case when transaction_code = 'S' then gross_value end) as sold,
    sum(signed_value)        as net,
    max(transaction_date)    as last_activity,
    '/issuers/' || issuer_cik::bigint as issuer_link
from edgar.owner_transactions
where owner_cik = ${params.owner_cik}
group by issuer_cik
order by coalesce(bought, 0) + coalesce(sold, 0) desc
```

<DataTable data={by_issuer} link=issuer_link>
    <Column id=symbol/>
    <Column id=issuer/>
    <Column id=bought fmt='$#,##0.0,,"M"'/>
    <Column id=sold fmt='$#,##0.0,,"M"'/>
    <Column id=net fmt='$#,##0.0,,"M"' contentType=delta/>
    <Column id=last_activity/>
</DataTable>

## Transaction history

```sql history
select
    transaction_date,
    any_value(issuer_symbol) as symbol,
    transaction_code,
    acquired_disposed,
    shares,
    price_per_share,
    gross_value,
    case when is_first_buy then 'FIRST BUY' else '' end as flag,
    'https://www.sec.gov/Archives/edgar/data/' || issuer_cik::bigint || '/'
        || replace(accession_number, '-', '') || '/'
        || accession_number || '-index.htm' as filing
from edgar.owner_transactions
where owner_cik = ${params.owner_cik}
group by all
order by transaction_date desc
```

<DataTable data={history} rows=25>
    <Column id=transaction_date/>
    <Column id=symbol/>
    <Column id=transaction_code align=center/>
    <Column id=acquired_disposed title="A/D" align=center/>
    <Column id=shares fmt='#,##0'/>
    <Column id=price_per_share fmt='$#,##0.00'/>
    <Column id=gross_value fmt='$#,##0'/>
    <Column id=flag/>
    <Column id=filing contentType=link linkLabel="EDGAR →"/>
</DataTable>

<!-- terminal-theme block: keep identical across all pages -->
<style>
  :global(main table),
  :global(main .markdown table),
  :global(main [class*="bigvalue"]),
  :global(main [class*="big-value"]) {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-variant-numeric: tabular-nums;
  }
  :global(main h2) {
    text-transform: uppercase;
    font-size: 0.95rem;
    letter-spacing: 0.08em;
  }
  :global(main h3) {
    text-transform: uppercase;
    font-size: 0.85rem;
    letter-spacing: 0.06em;
    opacity: 0.8;
  }
</style>
````

Note: if Task 2's Step 4 extended the selector list, mirror that here.

- [ ] **Step 2: Link owners from the issuer page**

In `dashboard/pages/issuers/[issuer_cik].md`, in the `owners` SQL block, add inside the select:

```sql
    '/owners/' || owner_cik::bigint as owner_link,
```

and change the owners DataTable opening tag to:

```html
<DataTable data={owners} link=owner_link>
```

- [ ] **Step 3: External links on the issuer page**

In `issuers/[issuer_cik].md`, add to the `issuer_info` SQL block select list:

```sql
    'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK='
        || any_value(issuer_cik)::bigint || '&type=4' as edgar_issuer,
    'https://finance.yahoo.com/quote/' || any_value(issuer_symbol) as yahoo
```

(`any_value()` is required — the query has no `group by`, so a bare `issuer_cik` among aggregates is a SQL error.)

Directly under the `# <Value …/>` title line, add:

```html
<a href={issuer_info[0]?.edgar_issuer} target="_blank" rel="noopener">Form 4 filings on EDGAR →</a> · <a href={issuer_info[0]?.yahoo} target="_blank" rel="noopener">Yahoo Finance →</a>
```

- [ ] **Step 4: Verify in dev**

`npm run dev` → from any issuer page, click an owner row → owner page renders with roles, per-issuer table, history with FIRST BUY flags; EDGAR/Yahoo links open the right pages. Check one multi-issuer owner (pick one from the notable-trades feed) to confirm cross-issuer history.

- [ ] **Step 5: Commit**

```bash
git add dashboard/pages/owners dashboard/pages/issuers
git commit -m "feat(dashboard): owner track-record pages + external links"
```

---

### Task 5: Cluster-buys sharpening + remaining explainers

**Files:**
- Modify: `dashboard/pages/cluster-buys.md`
- Modify: `dashboard/pages/issuers/[issuer_cik].md`

**Interfaces:**
- Consumes: `is_first_buy` (Task 1).

- [ ] **Step 1: First-buy count on cluster-buys**

In `cluster-buys.md`'s `clusters` SQL, add to the select list:

```sql
    count(*) filter (where is_first_buy) as first_buys,
```

Add to the DataTable, after the `buyers` column:

```html
    <Column id=first_buys title="First buys"/>
```

- [ ] **Step 2: Cluster-buys explainer**

After the intro paragraph ("…several buying at once rarely is."), add:

```markdown
<Details title="What am I looking at?">

A cluster is two or more distinct insiders making open-market purchases
(code P) of the same issuer inside the window. "First buys" counts how many
of those purchases were the buyer's first for that issuer in this dataset
(which starts 2026-06-22). Clusters totaling under $100k are hidden as noise.

</Details>
```

Delete the now-redundant standalone line "Clusters totaling under $100k are hidden."

Known limitation (accepted): the `who` column is an aggregated string, so
individual buyer names there stay plain text — clicking through to the issuer
page gives the linked owner list. Do not restructure the clusters query for this.

- [ ] **Step 3: Issuer-page explainer + first-buy flag in history**

In `issuers/[issuer_cik].md`: replace the transaction-history intro sentence
("All resolved Form 4 rows … G gift.") with:

```markdown
<Details title="Reading this table">

All resolved Form 4 rows, most recent first. Codes: P/S open-market buy/sell,
A grant, M option exercise, F tax withholding, G gift. Amended filings (4/A)
supersede their originals. FIRST BUY marks an owner's first open-market
purchase of this issuer in this dataset (which starts 2026-06-22).

</Details>
```

In the `history` SQL, add to the select list:

```sql
    case when is_first_buy then 'FIRST BUY' else '' end as flag,
```

Add to the history DataTable after the `gross_value` column:

```html
    <Column id=flag/>
```

- [ ] **Step 4: Verify in dev**

`npm run dev` → cluster-buys shows a First buys column (same-day tie rows can push the count above the buyer count — that's correct, not a bug); both explainers collapse/expand; issuer history shows FIRST BUY on the earliest P row of an owner.

- [ ] **Step 5: Commit**

```bash
git add dashboard/pages
git commit -m "feat(dashboard): cluster first-buy counts + explainers"
```

---

### Task 6: Fit-and-finish + full verification + deploy

**Files:**
- Create: `dashboard/static/favicon.ico` (fallback location: `dashboard/pages/favicon.ico`)
- Modify: `dashboard/pages/cluster-buys.md` (empty state exists; confirm), `dashboard/pages/owners/[owner_cik].md` (empty state)

**Interfaces:** none new.

- [ ] **Step 1: Favicon**

Evidence serves SvelteKit static assets. Create `dashboard/static/favicon.ico` from a 32×32 dark square with "▮▯" bar motif — simplest honest route, macOS has no ImageMagick by default:

```bash
cd dashboard && mkdir -p static
python3 - <<'PY'
# 32x32 ICO, dark bg + one blue and one orange bar (buy/sell motif), stdlib only
import struct, zlib
W = H = 32
px = bytearray()
for y in range(H):
    for x in range(W):
        if 6 <= x <= 12 and 8 <= y <= 26 and y >= 14:   r,g,b = (0x58,0xA6,0xFF)  # blue bar
        elif 19 <= x <= 25 and 8 <= y <= 26:            r,g,b = (0xD2,0x99,0x22)  # orange bar
        else:                                            r,g,b = (0x0D,0x11,0x17)  # bg
        px += bytes((r,g,b,255))
def chunk(t,d): return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d))
raw = b''.join(b'\x00'+bytes(px[y*W*4:(y+1)*W*4]) for y in range(H))
png = (b'\x89PNG\r\n\x1a\n'
       + chunk(b'IHDR', struct.pack('>IIBBBBB', W,H,8,6,0,0,0))
       + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
ico = struct.pack('<HHH',0,1,1)+struct.pack('<BBBBHHII',W,H,0,0,1,32,len(png),22)+png
open('static/favicon.ico','wb').write(ico)
PY
```

Verify: `npm run dev`, hard-reload → tab shows the icon. If 404 in the network tab, move the file to `dashboard/pages/favicon.ico` and re-verify.

- [ ] **Step 2: Page titles**

Add frontmatter to the two dynamic pages (static tab titles; the h1 stays dynamic).

Top of `dashboard/pages/owners/[owner_cik].md`:

```yaml
---
title: Insider track record
---
```

Top of `dashboard/pages/issuers/[issuer_cik].md`:

```yaml
---
title: Issuer detail
---
```

- [ ] **Step 3: Owner-page empty state**

In `owners/[owner_cik].md`, after the history DataTable, add:

```markdown
{#if history.length === 0}

No transactions recorded for this filer in the dataset window.

{/if}
```

- [ ] **Step 4: Full local verification**

```bash
PYTHONPATH=src .venv/bin/pytest                 # expect: 15 passed
PATH="$PWD/.venv/bin:$PATH" make dbt            # expect: 14 objects green
cd dashboard && npm run sources && npm run build  # expect: build succeeds, owner pages crawled
```

Spot-check `dashboard/build/` contains `owners/<some-cik>/index.html`.

- [ ] **Step 5: Mobile spot-check**

In dev, devtools responsive mode at 390px: overview, cluster-buys, one issuer, one owner page. Tables scroll horizontally rather than overflow the viewport; status line wraps acceptably.

- [ ] **Step 6: Commit and deploy**

```bash
git add dashboard
git commit -m "feat(dashboard): favicon, empty states, mobile pass"
git push
ssh edgar 'cd /opt/edgar-pipeline && git pull && docker compose exec -T dagster-daemon dagster job execute -m edgar_pipeline.definitions -j dashboard_nightly'
```

Then verify https://edgar.edgartracker.xyz shows the terminal theme, and https://edgar.edgartracker.xyz/status.json still serves (Caddy config untouched).

Note: the dbt change ships with the same push; the nightly job runs dbt in-container before the Evidence build, so `is_first_buy` exists on the server before the site builds. No migration step.
