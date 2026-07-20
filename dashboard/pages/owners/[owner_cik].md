---
title: Insider track record
---

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
dataset (which starts 2024-07-22). "First buy" marks their first open-market
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
    issuer_symbol as symbol,
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

{#if history.length === 0}

No transactions recorded for this filer in the dataset window.

{/if}

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
