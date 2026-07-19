---
title: Insider Flow
---

Open-market insider transactions reported to the SEC on Form 4. **Buys and sells
here are codes P and S only** — actual purchases and sales at market, the
transactions where an insider put money at stake. Grants, option exercises, and
gifts are excluded. Value is shares × reported price.

```sql anchor
select max(transaction_date)::date as max_date from edgar.insider_flows
```

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
