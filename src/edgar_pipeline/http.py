"""Rate-limited HTTP client for EDGAR.

One shared client, hard rate limit under the SEC's 10 req/s policy, retries
with exponential backoff on 429/5xx, and the mandatory User-Agent header.
"""

from __future__ import annotations

import threading
import time

import httpx

from . import config


class RateLimiter:
    """Simple thread-safe minimum-interval limiter."""

    def __init__(self, max_per_second: float) -> None:
        self._interval = 1.0 / max_per_second
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._next_at - now
            self._next_at = max(now, self._next_at) + self._interval
        if delay > 0:
            time.sleep(delay)


class EdgarClient:
    RETRIABLE = {429, 500, 502, 503, 504}

    def __init__(
        self,
        max_per_second: float = config.MAX_REQUESTS_PER_SECOND,
        max_retries: int = 4,
        timeout: float = 30.0,
    ) -> None:
        self._limiter = RateLimiter(max_per_second)
        self._max_retries = max_retries
        self._client = httpx.Client(
            headers={
                "User-Agent": config.user_agent(),
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=timeout,
            follow_redirects=True,
        )

    def get(self, url: str) -> httpx.Response:
        backoff = 1.0
        for attempt in range(self._max_retries + 1):
            self._limiter.wait()
            try:
                resp = self._client.get(url)
            except httpx.TransportError:
                if attempt == self._max_retries:
                    raise
                time.sleep(backoff)
                backoff *= 2
                continue
            if resp.status_code in self.RETRIABLE and attempt < self._max_retries:
                time.sleep(backoff)
                backoff *= 2
                continue
            resp.raise_for_status()
            return resp
        raise RuntimeError("unreachable")  # pragma: no cover

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> EdgarClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
