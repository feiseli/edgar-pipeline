```sql issuer_info
select
    any_value(issuer_name)   as issuer_name,
    any_value(issuer_symbol) as issuer_symbol,
    'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK='
        || any_value(issuer_cik)::bigint || '&type=4' as edgar_issuer,
    'https://finance.yahoo.com/quote/' || any_value(issuer_symbol) as yahoo
from edgar.owner_transactions
where issuer_cik = ${params.issuer_cik}
```

# <Value data={issuer_info} column=issuer_name/> (<Value data={issuer_info} column=issuer_symbol/>)

<a href={issuer_info[0]?.edgar_issuer} target="_blank" rel="noopener">Form 4 filings on EDGAR →</a> · <a href={issuer_info[0]?.yahoo} target="_blank" rel="noopener">Yahoo Finance →</a>

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
    max(transaction_date) as last_activity,
    '/owners/' || owner_cik::bigint as owner_link
from edgar.owner_transactions
where issuer_cik = ${params.issuer_cik}
group by owner_cik
order by coalesce(bought, 0) + coalesce(sold, 0) desc
```

<DataTable data={owners} link=owner_link>
    <Column id=owner/>
    <Column id=role/>
    <Column id=bought fmt='$#,##0.0,,"M"'/>
    <Column id=sold fmt='$#,##0.0,,"M"'/>
    <Column id=last_activity/>
</DataTable>

## Transaction history

<Details title="Reading this table">

All resolved Form 4 rows, most recent first. Codes: P/S open-market buy/sell,
A grant, M option exercise, F tax withholding, G gift. Amended filings (4/A)
supersede their originals. FIRST BUY marks an owner's first open-market
purchase of this issuer in this dataset (which starts 2026-06-22).

</Details>

```sql history
select
    transaction_date,
    owner_name,
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
    <Column id=flag/>
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
