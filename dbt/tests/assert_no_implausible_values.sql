-- The staging plausibility guard must keep filer-error rows (e.g. the $1.6
-- quadrillion FINS purchase, accession 0000905148-26-003232) out of the marts.

select *
from {{ ref('fct_owner_transactions') }}
where (price_per_share > 1e4 and shares >= 100)
   or price_per_share > 2e6
   or gross_value > 20e9
