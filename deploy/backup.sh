#!/usr/bin/env bash
# Nightly backup: tar the Parquet lake + Dagster home to Backblaze B2.
# Prereqs on the VPS host: rclone with a remote named "b2" (rclone config),
# EDGAR_B2_BUCKET in the repo .env. Cron it after the 23:30 ET dashboard job:
#   15 5 * * 2-6  /opt/edgar-pipeline/deploy/backup.sh >> /var/log/edgar-backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
: "${EDGAR_B2_BUCKET:?set EDGAR_B2_BUCKET in .env}"

archive="edgar-$(date +%F).tar.gz"
tar czf "/tmp/$archive" data .dagster
rclone copy "/tmp/$archive" "b2:$EDGAR_B2_BUCKET"
rm "/tmp/$archive"
# Rolling month of dailies; the lake is small and B2's free tier is 10 GB.
rclone delete "b2:$EDGAR_B2_BUCKET" --min-age 35d
