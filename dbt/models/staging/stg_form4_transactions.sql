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

select * exclude (recency_rank)
from ranked
where recency_rank = 1
