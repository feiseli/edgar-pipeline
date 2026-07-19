-- Owner-level transaction detail for the issuer pages: full resolved history
-- with a readable role and a signed value for open-market rows (P/S only —
-- grants, exercises, gifts carry no price-sensitive signal, so no sign).

select
    accession_number,
    issuer_cik,
    issuer_name,
    issuer_symbol,
    owner_cik,
    owner_name,
    case
        when is_officer then coalesce(officer_title, 'Officer')
        when is_director then 'Director'
        when is_ten_percent_owner then '10% owner'
        else 'Other'
    end as owner_role,
    filed_date,
    transaction_date,
    transaction_code,
    acquired_disposed,
    security_title,
    shares,
    price_per_share,
    shares * price_per_share as gross_value,
    case
        when transaction_code = 'P' then shares * price_per_share
        when transaction_code = 'S' then -(shares * price_per_share)
    end as signed_value,
    shares_owned_after,
    is_amendment
from {{ ref('stg_form4_transactions') }}
where not is_implausible
