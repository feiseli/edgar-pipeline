---
title: Insider Flow
---

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

```sql anchor
select max(transaction_date)::date as max_date from edgar.insider_flows
```

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

```sql kpis
select
    sum(buy_value)  as buys,
    sum(sell_value) as sells,
    sum(net_flow)   as net,
    count(distinct issuer_cik) as issuers
from edgar.insider_flows
where transaction_date > (select max_date from ${anchor}) - 30
```

<BigValue data={kpis} value=buys  title="Open-market buys, 30d"  fmt='$#,##0.0,,"M"'/>
<BigValue data={kpis} value=sells title="Open-market sells, 30d" fmt='$#,##0.0,,"M"'/>
<BigValue data={kpis} value=net   title="Net flow, 30d"          fmt='$#,##0.0,,"M"'/>
<BigValue data={kpis} value=issuers title="Issuers with activity, 30d"/>

## Daily buy vs sell value

```sql daily_flows
select transaction_date, 'Buys' as side, sum(buy_value) as value
from edgar.insider_flows
where transaction_date > (select max_date from ${anchor}) - 30
group by 1
union all
select transaction_date, 'Sells', sum(sell_value)
from edgar.insider_flows
where transaction_date > (select max_date from ${anchor}) - 30
group by 1
order by transaction_date
```

<BarChart
    data={daily_flows}
    x=transaction_date
    y=value
    series=side
    type=grouped
    yFmt='$#,##0,,"M"'
    title="Open-market transaction value per day"
/>

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

## Net-flow leaderboard

Issuers ranked by net open-market flow (buys − sells) over the trailing window.

<ButtonGroup name=window>
    <ButtonGroupItem valueLabel="30 days" value=30 default/>
    <ButtonGroupItem valueLabel="90 days" value=90/>
</ButtonGroup>

```sql leaders
select
    any_value(issuer_name)   as issuer,
    any_value(issuer_symbol) as symbol,
    sum(buy_value)           as buys,
    sum(sell_value)          as sells,
    sum(net_flow)            as net,
    '/issuers/' || issuer_cik::bigint as issuer_link
from edgar.insider_flows
where transaction_date > (select max_date from ${anchor}) - ${inputs.window}::int
group by issuer_cik
```

```sql top_buying
select * from ${leaders} order by net desc limit 10
```

```sql top_selling
select * from ${leaders} order by net asc limit 10
```

### Top net buying

<DataTable data={top_buying} link=issuer_link>
    <Column id=symbol/>
    <Column id=issuer/>
    <Column id=buys fmt='$#,##0.0,,"M"'/>
    <Column id=sells fmt='$#,##0.0,,"M"'/>
    <Column id=net fmt='$#,##0.0,,"M"' contentType=delta/>
</DataTable>

### Top net selling

<DataTable data={top_selling} link=issuer_link>
    <Column id=symbol/>
    <Column id=issuer/>
    <Column id=buys fmt='$#,##0.0,,"M"'/>
    <Column id=sells fmt='$#,##0.0,,"M"'/>
    <Column id=net fmt='$#,##0.0,,"M"' contentType=delta/>
</DataTable>

## Filing volume

```sql filing_volume
select filed_date, count(distinct accession_number) as filings
from edgar.owner_transactions
group by 1 order by 1
```

<BarChart
    data={filing_volume}
    x=filed_date
    y=filings
    title="Form 4 filings ingested per day"
/>

Data updates each business day from SEC EDGAR.
Latest transaction date: <Value data={anchor} column=max_date/>.

<!-- terminal-theme block: keep identical across all pages -->
<style>
  :global(main table),
  :global(main .markdown table),
  :global(main div.text-xl.font-medium) {
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
  /* page-specific: status line (index.md only) */
  :global(.status-line) {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.75rem;
    letter-spacing: 0.06em;
    opacity: 0.65;
    border-bottom: 1px solid rgba(139, 148, 158, 0.3);
    padding-bottom: 0.5em;
  }
</style>
