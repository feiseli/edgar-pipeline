#!/usr/bin/env bash
# Resumable Form 4 backfill: materialize every missing weekday partition,
# oldest first. Run on the VPS from the repo root, inside tmux:
#
#   tmux new -s backfill './deploy/backfill.sh 2024-07-22 2026-06-20'
#
# Skips partitions already on disk, so it can be killed and restarted freely.
# Sleeps through 22:15-23:45 ET: the nightly ingest carries its own 8 req/s
# limiter, and two concurrent fetchers would exceed the SEC's 10 req/s cap.
# GNU date only (Debian) - not macOS-portable, by design.
set -euo pipefail

start=${1:?usage: backfill.sh START_DATE END_DATE}
end=${2:?usage: backfill.sh START_DATE END_DATE}

d="$start"
while [[ ! "$d" > "$end" ]]; do
  dow=$(date -d "$d" +%u)
  if (( dow <= 5 )) && [[ ! -f "data/form4/filed_date=$d/form4.parquet" ]]; then
    et=$(TZ=America/New_York date +%H%M)
    while [[ "$et" > "2214" && "$et" < "2346" ]]; do
      echo "$(date -Is) in nightly-ingest window (ET $et); sleeping 10m"
      sleep 600
      et=$(TZ=America/New_York date +%H%M)
    done
    echo "=== $d"
    docker compose exec -T dagster-daemon \
      dagster asset materialize --select '*form4_parquet' \
      --partition "$d" -m edgar_pipeline.definitions
  fi
  d=$(date -d "$d + 1 day" +%F)
done
echo "backfill complete: $start..$end"
