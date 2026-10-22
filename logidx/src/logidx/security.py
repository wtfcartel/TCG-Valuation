"""Authentication helpers, CSRF, login rate limiting and secret redaction."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import threading
import time
from collections import defaultdict, deque

from logidx.settings import get_settings

_SCRYPT = {"n": 2**15, "r": 8, "p": 1, "maxmem": 64 * 1024 * 1024, "dklen": 32}


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("password must be at least 12 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_matches(expected: str | None, supplied: str | None) -> bool:
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


class LoginRateLimiter:
    """At most `limit` failed attempts per key per `window` seconds."""

    def __init__(self, limit: int = 5, window: float = 900.0) -> None:
        self.limit, self.window = limit, window
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _trim(self, key: str, now: float) -> deque[float]:
        q = self._failures[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def allowed(self, key: str) -> bool:
        with self._lock:
            return len(self._trim(key, time.monotonic())) < self.limit

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._trim(key, time.monotonic()).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


_KEY_PATTERNS = [
    re.compile(
        r"(?i)(api[_-]?key|app_key|app_id|password|secret|token|authorization)(['\"]?\s*[:=]\s*['\"]?)"
        r"(Bearer\s+)?([^\s'\"&,}]+)"
    ),
    re.compile(r"xai-[A-Za-z0-9]{10,}"),
]


def redact(text: str, extra_secrets: list[str] | None = None) -> str:
    for secret in extra_secrets if extra_secrets is not None else get_settings().secret_values():
        if secret and len(secret) >= 4:
            text = text.replace(secret, "***")
    text = _KEY_PATTERNS[0].sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3) or ''}***", text)
    return _KEY_PATTERNS[1].sub("xai-***", text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if record.args:
            record.args = tuple(
                redact(str(a)) for a in (record.args if isinstance(record.args, tuple) else (record.args,))
            )
        for key, value in list(record.__dict__.items()):
            if key in ("url", "error", "detail") and isinstance(value, str):
                setattr(record, key, redact(value))
        return True


class JsonFormatter(logging.Formatter):
    _STANDARD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in self._STANDARD:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its INFO lines include full URLs with API keys
