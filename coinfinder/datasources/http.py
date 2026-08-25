"""Shared HTTP client: retries, rate limiting, and a hard timeout.

Free market-data endpoints rate limit aggressively and fail transiently. A scan
issues dozens of requests, so a single unhandled 429 shouldn't sink it.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class RateLimiter:
    """Token-free minimum-interval limiter, safe across threads."""

    def __init__(self, calls_per_minute: int) -> None:
        self._min_interval = 60.0 / max(1, calls_per_minute)
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            remaining = self._min_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
            self._last_call = time.monotonic()


class HttpClient:
    def __init__(
        self,
        timeout: float = 12.0,
        user_agent: str = "coinfinder/0.1",
        calls_per_minute: int = 240,
        max_retries: int = 3,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self._limiter = RateLimiter(calls_per_minute)
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET and parse JSON. Returns None when the request can't be satisfied."""
        backoff = 1.0
        for attempt in range(1, self.max_retries + 1):
            self._limiter.wait()
            try:
                response = self._session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                log.warning("request failed (%s/%s) %s: %s", attempt, self.max_retries, url, exc)
            else:
                if response.status_code == 200:
                    try:
                        return response.json()
                    except ValueError:
                        log.warning("non-JSON response from %s", url)
                        return None
                if response.status_code not in RETRY_STATUS:
                    log.warning("HTTP %s from %s", response.status_code, url)
                    return None
                log.warning(
                    "HTTP %s from %s (%s/%s), retrying", response.status_code, url, attempt, self.max_retries
                )

            if attempt < self.max_retries:
                time.sleep(backoff)
                backoff *= 2
        return None

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
