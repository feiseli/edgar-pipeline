# One image for dagster-webserver and dagster-daemon. Node is included because
# the nightly dashboard_nightly job rebuilds the Evidence site in-process —
# one orchestrator (Dagster) instead of a second cron surface.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Non-editable install — retires the macOS editable-install flakiness by design.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[dev]"

COPY dashboard/package.json dashboard/package-lock.json ./dashboard/
RUN cd dashboard && npm ci

COPY dbt ./dbt
RUN cp dbt/profiles.example.yml dbt/profiles.yml
COPY dashboard ./dashboard
COPY .dagster/dagster.yaml ./.dagster/dagster.yaml

ENV DAGSTER_HOME=/app/.dagster \
    EDGAR_PROJECT_ROOT=/app
