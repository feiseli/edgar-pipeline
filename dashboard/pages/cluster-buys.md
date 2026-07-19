---
title: Cluster Buys
---

Issuers where **two or more distinct insiders bought at market** (code P) inside
the trailing window — the classic conviction signal. One insider buying can be
noise; several buying at once rarely is.

<ButtonGroup name=window>
    <ButtonGroupItem valueLabel="7 days" value=7/>
    <ButtonGroupItem valueLabel="14 days" value=14 default/>
    <ButtonGroupItem valueLabel="30 days" value=30/>
</ButtonGroup>

Clusters totaling under $100k are hidden.

```sql clusters
select
    any_value(issuer_symbol) as symbol,
    any_value(issuer_name)   as issuer,
    count(distinct owner_cik)                  as buyers,
    sum(gross_value)                           as total_bought,
    max(transaction_date)                      as latest_buy,
    array_to_string((array_agg(distinct owner_name))[1:4], ', ')
        || case when count(distinct owner_cik) > 4 then ', …' else '' end as who,
    '/issuers/' || issuer_cik::bigint          as issuer_link
from edgar.owner_transactions
where transaction_code = 'P'
  and transaction_date >
      (select max(transaction_date)::date from edgar.owner_transactions where transaction_code = 'P')
      - ${inputs.window}::int
group by issuer_cik
having count(distinct owner_cik) >= 2 and sum(gross_value) >= 1e5
order by total_bought desc, buyers desc
```

<DataTable data={clusters} link=issuer_link rows=25>
    <Column id=symbol/>
    <Column id=issuer/>
    <Column id=buyers/>
    <Column id=total_bought fmt='$#,##0.0,,"M"'/>
    <Column id=latest_buy/>
    <Column id=who title="Buyers" wrap=true/>
</DataTable>

{#if clusters.length === 0}

No cluster buys in this window — widen it.

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
