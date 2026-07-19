-- All Form 4 transaction rows from the Parquet lake, amendments resolved:
-- when a 4/A exists for an accession's (issuer, owner, period), the original
-- filing's rows are superseded. This is the textbook late-arriving-amendment
-- problem; keeping resolution here (not in ingestion) means raw data stays
-- immutable and the rule is testable.

with raw as (

    select *
    from read_parquet('../data/form4/*/*.parquet', hive_partitioning = true)

),

ranked as (

    select
        *,
        row_number() over (
            partition by issuer_cik, owner_cik, period_of_report, transaction_seq,
                         transaction_date, transaction_code
            order by is_amendment desc, filed_date desc, accession_number desc
        ) as recency_rank
    from raw

)

select
    * exclude (recency_rank),
    -- Filer-error guard; marts exclude flagged rows. Observed patterns:
    -- aggregate proceeds entered in the per-share price field (STNG
    -- 0001969452-26-000010: 15,000 sh at "$1,230,435"), JPY amounts in a USD
    -- field (MFG), both fields set to the dollar total (FINS, $1.6
    -- quadrillion). Every legit price in the lake is < $10k (TDG, MKL, FICO);
    -- the shares >= 100 clause spares small-lot BRK.A-style filings, the only
    -- real > $10k shares. ponytail: static thresholds, no market-price check;
    -- revisit if a legit > $10k / 100-share issuer besides BRK.A appears.
    coalesce(
        (price_per_share > 1e4 and shares >= 100)
        or price_per_share > 2e6
        or shares * price_per_share > 20e9, false)
        as is_implausible
from ranked
where recency_rank = 1
