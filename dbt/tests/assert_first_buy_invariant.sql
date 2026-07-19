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
