"""Polite HTTP client used by every adapter and the verifier.

- explicit timeouts on every request
- retry with exponential backoff on connection errors, 429 and 5xx (honouring Retry-After)
- 401/403 are *not* retried: they are access controls, reported as ACCESS BLOCKED, never bypassed
- a per-host minimum interval between requests
- optional robots.txt check for HTML pages (APIs published for programmatic use are exempt)
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from logidx.settings import get_settings

log = logging.getLogger(__name__)


class SourceError(Exception):
    """A source could not be searched. `blocked` distinguishes access control from failure."""

    def __init__(self, message: str, *, blocked: bool = False, status_code: int | None = None) -> None:
        super().__init__(message)
        self.blocked = blocked
        self.status_code = status_code


class HttpClient:
    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        max_attempts: int = 3,
        backoff_base: float = 1.0,
        min_interval: float | None = None,
        sleep=time.sleep,
    ) -> None:  # type: ignore[no-untyped-def]
        settings = get_settings()
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(settings.http_timeout_seconds, connect=10.0),
            headers={"User-Agent": settings.user_agent, "Accept-Language": "en-AU,en;q=0.8"},
            follow_redirects=True,
        )
        self.max_attempts = max_attempts
        self.backoff_base = backoff_base
        self.min_interval = settings.http_min_interval_seconds if min_interval is None else min_interval
        self._sleep = sleep
        self._last_request: dict[str, float] = {}
        self._lock = threading.Lock()
        self._robots: dict[str, RobotFileParser | None] = {}

    def _pace(self, url: str) -> None:
        host = urlsplit(url).netloc
        with self._lock:
            last = self._last_request.get(host)
            now = time.monotonic()
            if last is not None and self.min_interval > 0:
                wait = self.min_interval - (now - last)
                if wait > 0:
                    self._sleep(wait)
            self._last_request[host] = time.monotonic()

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            self._pace(url)
            try:
                resp = self.client.request(method, url, **kwargs)
            except httpx.TransportError as exc:  # connect/read timeouts, DNS, resets
                last_exc = exc
                log.warning("http transport error", extra={"url": url, "attempt": attempt, "error": str(exc)})
            else:
                if resp.status_code in (401, 403, 407):
                    raise SourceError(
                        f"HTTP {resp.status_code} from {urlsplit(url).netloc}: access refused",
                        blocked=True,
                        status_code=resp.status_code,
                    )
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_exc = SourceError(
                        f"HTTP {resp.status_code} from {urlsplit(url).netloc}", status_code=resp.status_code
                    )
                    if attempt < self.max_attempts:
                        self._sleep(self._retry_delay(resp, attempt))
                    continue
                return resp
            if attempt < self.max_attempts:
                self._sleep(self.backoff_base * 2 ** (attempt - 1))
        if isinstance(last_exc, SourceError):
            raise last_exc
        raise SourceError(f"request to {urlsplit(url).netloc} failed: {last_exc}")

    def _retry_delay(self, resp: httpx.Response, attempt: int) -> float:
        retry_after = resp.headers.get("Retry-After", "")
        if retry_after.isdigit():
            return min(float(retry_after), 60.0)
        return self.backoff_base * 2 ** (attempt - 1)

    def get_json(self, url: str, **kwargs: Any) -> Any:
        resp = self.request("GET", url, **kwargs)
        return self._json(resp, url)

    def post_json(self, url: str, payload: Any, **kwargs: Any) -> Any:
        resp = self.request("POST", url, json=payload, **kwargs)
        return self._json(resp, url)

    @staticmethod
    def _json(resp: httpx.Response, url: str) -> Any:
        if resp.status_code >= 400:
            raise SourceError(f"HTTP {resp.status_code} from {urlsplit(url).netloc}", status_code=resp.status_code)
        try:
            return resp.json()
        except ValueError as exc:
            raise SourceError(f"non-JSON response from {urlsplit(url).netloc}") from exc

    def robots_allows(self, url: str) -> bool:
        """robots.txt check for HTML fetches. Unreachable robots.txt → allowed (standard behaviour)."""
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots:
            parser: RobotFileParser | None = RobotFileParser()
            try:
                resp = self.client.get(f"{base}/robots.txt", timeout=10.0)
                if resp.status_code >= 400:
                    parser = None
                else:
                    assert parser is not None
                    parser.parse(resp.text.splitlines())
            except httpx.HTTPError:
                parser = None
            self._robots[base] = parser
        parser = self._robots[base]
        if parser is None:
            return True
        return parser.can_fetch(get_settings().user_agent, url)

    def close(self) -> None:
        self.client.close()
