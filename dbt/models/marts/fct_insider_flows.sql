-- Daily net insider flow per issuer, open-market transactions only.
-- Codes: P = open-market purchase, S = open-market sale. Grants (A), option
-- exercises (M), gifts (G) etc. are excluded because they don't express a
-- price-sensitive decision.

select
    issuer_cik,
    any_value(issuer_name)   as issuer_name,
    any_value(issuer_symbol) as issuer_symbol,
    transaction_date,
    sum(case when transaction_code = 'P' then shares * price_per_share end) as buy_value,
    sum(case when transaction_code = 'S' then shares * price_per_share end) as sell_value,
    coalesce(sum(case when transaction_code = 'P' then shares * price_per_share end), 0)
      - coalesce(sum(case when transaction_code = 'S' then shares * price_per_share end), 0)
        as net_flow,
    count(distinct owner_cik) filter (where transaction_code = 'P') as distinct_buyers,
    count(distinct owner_cik) filter (where transaction_code = 'S') as distinct_sellers
from {{ ref('stg_form4_transactions') }}
where transaction_code in ('P', 'S')
  and price_per_share is not null
  and not is_implausible
group by issuer_cik, transaction_date
