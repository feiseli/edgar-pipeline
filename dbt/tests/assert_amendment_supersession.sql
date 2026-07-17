-- Supersession invariant: after resolution, each transaction grain key
-- appears exactly once. A failure means a 4/A and its original both survived.
select
    issuer_cik, owner_cik, period_of_report, transaction_seq,
    transaction_date, transaction_code,
    count(*) as n
from {{ ref('stg_form4_transactions') }}
group by all
having count(*) > 1
