from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

API_URL = "https://api.coinalyze.net/v1/ohlcv-history"


def _clamp_retry_after(value: float | None, *, min_seconds: float = 1.0, max_seconds: float = 120.0) -> float | None:
    if value is None:
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return max(min_seconds, min(max_seconds, value))


@dataclass
class FetchResult:
    ok: bool
    status: int | None
    data: Any = None
    error: str | None = None
    retry_after: float | None = None


def load_api_key() -> str | None:
    key = os.environ.get("COINALYZE_API_KEY")
    if key:
        return key.strip() or None
    env_path = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "COINALYZE_API_KEY":
                    return v.strip().strip('"').strip("'") or None
    return None


def _request(url: str, timeout: int = 30) -> tuple[int, bytes, dict[str, str]]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        headers = {k.lower(): v for k, v in resp.headers.items()}
        return resp.status, resp.read(), headers


def _build_url(*, symbol: str, interval: str, from_ts: int, to_ts: int, api_key: str) -> str:
    params = urllib.parse.urlencode({"symbols": symbol, "interval": interval, "from": str(from_ts), "to": str(to_ts), "api_key": api_key})
    return f"{API_URL}?{params}"


SECRET_PATTERNS = (
    (re.compile(r"(?i)authorization\s*[:=]\s*Bearer\s+[^\s,;]+"), "authorization=[REDACTED]"),
    (re.compile(r"(?i)(api[_-]?key|coinalyze_api_key|token|password|secret)\s*[:=]\s*([\"']?)([^\s,;\"']+)\2"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)(Bearer\s+)([^\s,;]+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)https?://[^\s]*?(?:webhook|hooks|slack|discord|telegram)[^\s]*"), "[REDACTED_WEBHOOK_URL]"),
)

SECRET_KEYS = {"api_key", "apikey", "key", "token", "access_token", "refresh_token", "password", "secret", "authorization", "webhook", "webhook_url", "cookie", "set-cookie"}


def _normalize_secret_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _is_secret_key(key: Any) -> bool:
    normalized = _normalize_secret_key(key)
    if normalized in SECRET_KEYS:
        return True
    if normalized.endswith("token"):
        return True
    return any(token in normalized for token in ("apikey", "api_key", "password", "secret", "authorization", "webhook", "cookie"))


def _sanitize_url_query(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if not parsed.query:
        return value
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    sanitized_pairs: list[tuple[str, str]] = []
    for key, item_value in pairs:
        sanitized_pairs.append((key, "[REDACTED]" if _is_secret_key(key) else item_value))
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(sanitized_pairs), parsed.fragment))


def sanitize_for_persistence(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        sanitized = _sanitize_url_query(value)
        for pattern, replacement in SECRET_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            sanitized[key] = "[REDACTED]" if _is_secret_key(key) else sanitize_for_persistence(v)
        return sanitized
    if isinstance(value, list):
        return [sanitize_for_persistence(v) for v in value]
    if isinstance(value, tuple):
        return tuple(sanitize_for_persistence(v) for v in value)
    return value


def _sanitize_error_message(message: str, url: str) -> str:
    return sanitize_for_persistence(message.replace(url, API_URL))


def fetch_ohlcv_history(*, symbol: str, interval: str, from_ts: int, to_ts: int, api_key: str, timeout: int = 30, max_retries: int = 1, min_retry_after_seconds: float = 1.0, max_retry_after_seconds: float = 120.0) -> FetchResult:
    url = _build_url(symbol=symbol, interval=interval, from_ts=from_ts, to_ts=to_ts, api_key=api_key)
    attempt = 0
    backoff = 1.0
    while True:
        attempt += 1
        try:
            status, body, headers = _request(url, timeout=timeout)
            data = json.loads(body.decode("utf-8")) if body else None
            if status >= 400:
                retry_after = _clamp_retry_after(_parse_retry_after(headers.get("retry-after")), min_seconds=min_retry_after_seconds, max_seconds=max_retry_after_seconds) if status == 429 else None
                if status == 429 and attempt <= max_retries + 1:
                    time.sleep(_retry_after_or_backoff(retry_after, backoff))
                    backoff *= 2
                    continue
                return FetchResult(False, status, data, _sanitize_error_message(f"HTTP {status} {url}", url), retry_after)
            return FetchResult(True, status, data, None, None)
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            data = None
            if body:
                try:
                    data = json.loads(body.decode("utf-8"))
                except Exception:
                    data = body.decode("utf-8", errors="replace")
            retry_after = _clamp_retry_after(_parse_retry_after(exc.headers.get("Retry-After")), min_seconds=min_retry_after_seconds, max_seconds=max_retry_after_seconds) if exc.code == 429 else None
            if exc.code == 429 and attempt <= max_retries + 1:
                time.sleep(retry_after if retry_after is not None else backoff)
                backoff *= 2
                continue
            return FetchResult(False, exc.code, data, _sanitize_error_message(str(exc), url), retry_after)
        except Exception as exc:
            return FetchResult(False, None, None, _sanitize_error_message(str(exc), url), None)


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _retry_after_or_backoff(retry_after: float | None, backoff: float) -> float:
    """Use the server-provided delay when valid; otherwise fall back to exponential backoff."""
    return retry_after if retry_after is not None else backoff
