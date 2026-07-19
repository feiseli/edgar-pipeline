# Deploying to the VPS (Phase B)

Everything below `docker compose up` is automated; the numbered steps are the
one-time manual provisioning.

## One-time provisioning

1. **VPS**: Hetzner CX22 (CX32 if sharing with synth-index). Debian 12, install
   Docker + compose plugin. Create a non-root user with docker group.
2. **DNS**: point `edgar.<yourdomain>` A/AAAA records at the VPS.
3. **Clone + seed**: clone the repo to `/opt/edgar-pipeline`, then seed the
   lake from the laptop (faster than re-backfilling, and identical by
   idempotency): `rsync -a data/ vps:/opt/edgar-pipeline/data/`
4. **.env** on the VPS (never committed):

   ```
   EDGAR_USER_AGENT="Eli Rose <email>"
   DOMAIN=edgar.example.com
   HEALTHCHECKS_URL=https://hc-ping.com/<uuid>     # optional but wanted
   EDGAR_B2_BUCKET=<bucket>                        # for deploy/backup.sh
   ```

5. **healthchecks.io**: create a check with a ~26h period, weekdays-only
   schedule; put its ping URL in `HEALTHCHECKS_URL`. The nightly dashboard job
   pings it after dbt + Evidence succeed, so a silently dead daemon, a failed
   ingest, or a failed build all page within a day.
6. **Backblaze B2**: create a bucket + app key, `rclone config` a remote named
   `b2`, add the cron line from `deploy/backup.sh`'s header.

## Run

```bash
docker compose up -d --build
# First deploy only — build the site without waiting for the 23:30 schedule:
docker compose exec dagster-daemon dagster job execute -m edgar_pipeline.definitions -j dashboard_nightly
```

- Dashboard: `https://$DOMAIN` (Caddy auto-HTTPS)
- Freshness: `https://$DOMAIN/status.json`
- Dagster UI: `ssh -L 3000:localhost:3000 <vps>` → http://localhost:3000
  (deliberately not exposed publicly — admin surface, not portfolio surface)
- Schedules (both US/Eastern, weekdays): 22:30 ingest, 23:30 dbt + Evidence
  rebuild + healthchecks ping. Enable them once in the Dagster UI.

## README freshness badge

Shields dynamic-JSON badge reading `status.json` (replace the domain):

```markdown
![data through](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fedgar.example.com%2Fstatus.json&query=%24.partition&label=data%20through&color=blue)
```

## Restore rehearsal (do once, per scope acceptance)

```bash
rclone copy b2:$EDGAR_B2_BUCKET/edgar-<date>.tar.gz /tmp/
tar xzf /tmp/edgar-<date>.tar.gz -C /tmp/restore-test
# spot-check: row count matches status.json, then discard /tmp/restore-test
```

## Acceptance (from scope)

Schedule fires unattended five consecutive business days; badge shows the
correct date; killing the daemon produces a healthchecks alert; restore
rehearsed once.
