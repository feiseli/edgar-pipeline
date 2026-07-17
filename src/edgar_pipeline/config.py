"""Runtime configuration.

The SEC requires a descriptive User-Agent identifying you and a contact
address on every request (see https://www.sec.gov/os/accessing-edgar-data).
Requests without one get 403s. Set EDGAR_USER_AGENT, e.g.:

    EDGAR_USER_AGENT="Eli Rose eli@example.com"
"""

from __future__ import annotations

import os
from pathlib import Path

EDGAR_BASE = "https://www.sec.gov"
DATA_DIR = Path(os.environ.get("EDGAR_DATA_DIR", "data"))

# SEC fair-access policy caps clients at 10 requests/second. Stay under it.
MAX_REQUESTS_PER_SECOND = 8.0

# Form types this pipeline ingests. 4/A amendments are ingested and flagged so
# the dbt layer can supersede the originals they amend.
FORM_TYPES = frozenset({"4", "4/A"})


def user_agent() -> str:
    ua = os.environ.get("EDGAR_USER_AGENT", "").strip()
    if not ua:
        raise RuntimeError(
            "EDGAR_USER_AGENT is not set. The SEC requires a User-Agent with "
            'your name and contact email, e.g. EDGAR_USER_AGENT="Jane Doe jane@example.com"'
        )
    return ua
