-- Daily S&P 500 index close; source parquet is a full-history atomic
-- snapshot refreshed nightly from FRED.

select
    date,
    close,
    close / lag(close) over (order by date) - 1 as daily_return
from read_parquet('../data/sp500/sp500.parquet')
