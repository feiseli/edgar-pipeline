```sql issuer_info
select
    any_value(issuer_name)   as issuer_name,
    any_value(issuer_symbol) as issuer_symbol
from edgar.owner_transactions
where issuer_cik = ${params.issuer_cik}
```

# <Value data={issuer_info} column=issuer_name/> (<Value data={issuer_info} column=issuer_symbol/>)

```sql open_market
select transaction_date, sum(signed_value) as net
from edgar.owner_transactions
where issuer_cik = ${params.issuer_cik}
  and transaction_code in ('P', 'S')
group by 1 order by 1
```

```sql running_flow
select transaction_date, sum(net) over (order by transaction_date) as cumulative_net
from ${open_market}
order by transaction_date
```

## Running net open-market flow

Cumulative buys minus sells across all reported open-market transactions.

<LineChart
    data={running_flow}
    x=transaction_date
    y=cumulative_net
    yFmt='$#,##0.0,,"M"'
    title="Cumulative net insider flow"
/>

## Owners

```sql owners
select
    any_value(owner_name) as owner,
    any_value(owner_role) as role,
    sum(case when transaction_code = 'P' then gross_value end) as bought,
    sum(case when transaction_code = 'S' then gross_value end) as sold,
    max(transaction_date) as last_activity
from edgar.owner_transactions
where issuer_cik = ${params.issuer_cik}
group by owner_cik
order by coalesce(bought, 0) + coalesce(sold, 0) desc
```

<DataTable data={owners}>
    <Column id=owner/>
    <Column id=role/>
    <Column id=bought fmt='$#,##0.0,,"M"'/>
    <Column id=sold fmt='$#,##0.0,,"M"'/>
    <Column id=last_activity/>
</DataTable>

## Transaction history

All resolved Form 4 rows, most recent first. Codes: P/S open-market buy/sell,
A grant, M option exercise, F tax withholding, G gift.

```sql history
select
    transaction_date,
    owner_name,
    transaction_code,
    acquired_disposed,
    shares,
    price_per_share,
    gross_value,
    'https://www.sec.gov/Archives/edgar/data/' || issuer_cik::bigint || '/'
        || replace(accession_number, '-', '') || '/'
        || accession_number || '-index.htm' as filing
from edgar.owner_transactions
where issuer_cik = ${params.issuer_cik}
order by transaction_date desc, owner_name
```

<DataTable data={history} rows=25>
    <Column id=transaction_date/>
    <Column id=owner_name/>
    <Column id=transaction_code align=center/>
    <Column id=acquired_disposed title="A/D" align=center/>
    <Column id=shares fmt='#,##0'/>
    <Column id=price_per_share fmt='$#,##0.00'/>
    <Column id=gross_value fmt='$#,##0'/>
    <Column id=filing contentType=link linkLabel="EDGAR →"/>
</DataTable>

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
</style>
