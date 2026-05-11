"""CoinAlYZe API client."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

import requests

DEFAULT_BASE_URL = "https://api.coinalyze.net/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 3

_INTERVAL_ALIASES: dict[str, str] = {
    "1m": "1min",
    "1min": "1min",
    "5m": "5min",
    "5min": "5min",
    "15m": "15min",
    "15min": "15min",
    "30m": "30min",
    "30min": "30min",
    "1h": "1hour",
    "1hour": "1hour",
    "2h": "2hour",
    "2hour": "2hour",
    "4h": "4hour",
    "4hour": "4hour",
    "6h": "6hour",
    "6hour": "6hour",
    "12h": "12hour",
    "12hour": "12hour",
    "1d": "daily",
    "1day": "daily",
    "daily": "daily",
}


class _SessionLike(Protocol):
    def get(
        self,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any] | None,
        timeout: float,
    ) -> Any: ...


@dataclass(slots=True, frozen=True)
class MarketData:
    """Normalized OHLCV history response."""

    symbol: str
    timeframe: str
    ohlcv: list[dict[str, Any]]


class CoinAlYZeError(RuntimeError):
    """Raised when a CoinAlYZe request fails."""


class CoinAlYZeClient:
    """Small, retry-aware CoinAlYze REST client.

    CoinAlYze accepts the API key as `api_key` in either the request header or
    query string. The header form keeps credentials out of URLs.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        session: _SessionLike | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("COINALYZE_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["api_key"] = self.api_key
        return headers

    @staticmethod
    def normalize_interval(timeframe: str) -> str:
        """Return the interval name expected by CoinAlYze."""

        key = timeframe.strip().lower()
        return _INTERVAL_ALIASES.get(key, key)

    def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    headers=self._headers(),
                    params=params,
                    timeout=self.timeout,
                )

                if response.status_code == 429:
                    if attempt < self.max_retries:
                        time.sleep(_retry_after_seconds(response.headers.get("Retry-After")))
                        continue
                    raise CoinAlYZeError("CoinAlYZe rate limit exceeded")

                if response.status_code in {502, 503, 504}:
                    if attempt < self.max_retries:
                        time.sleep(_backoff_seconds(attempt))
                        continue
                    raise CoinAlYZeError(f"CoinAlYZe upstream error: HTTP {response.status_code}")

                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(_backoff_seconds(attempt))

        raise CoinAlYZeError(f"CoinAlYZe request failed: {last_error}") from last_error

    def exchanges(self) -> list[dict[str, Any]]:
        return _extract_list(self._request("exchanges"))

    def spot_markets(self) -> list[dict[str, Any]]:
        return _extract_list(self._request("spot-markets"))

    def future_markets(self) -> list[dict[str, Any]]:
        return _extract_list(self._request("future-markets"))

    def ohlcv_history(self, symbols: str, from_ts: int, to_ts: int, interval: str = "1h") -> MarketData:
        normalized_interval = self.normalize_interval(interval)
        data = self._request(
            "ohlcv-history",
            params={
                "symbols": symbols,
                "interval": normalized_interval,
                "from": int(from_ts),
                "to": int(to_ts),
            },
        )
        return MarketData(
            symbol=symbols,
            timeframe=normalized_interval,
            ohlcv=_extract_ohlcv(data),
        )


def _extract_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        nested = data.get("data", [])
        return [item for item in nested if isinstance(item, dict)]
    return []


def _extract_ohlcv(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []

    nested = data.get("data", data.get("ohlcv", []))
    if isinstance(nested, list):
        return [item for item in nested if isinstance(item, dict)]
    return []


def _retry_after_seconds(value: str | None) -> float:
    if value is None:
        return 1.0
    try:
        return min(max(float(value), 0.0), 120.0)
    except ValueError:
        return 1.0


def _backoff_seconds(attempt: int) -> float:
    return min(2.0**attempt, 120.0)
