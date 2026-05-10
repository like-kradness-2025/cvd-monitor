"""CoinAlYZe API client."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

import requests


class _SessionLike(Protocol):
    def get(
        self,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any] | None,
        timeout: float,
    ) -> Any: ...


@dataclass(slots=True)
class MarketData:
    symbol: str
    timeframe: str
    ohlcv: list[dict[str, Any]]


class CoinAlYZeError(RuntimeError):
    """Raised when the CoinAlYZe API request fails."""


class CoinAlYZeClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.coinalyze.net/v1",
        timeout: float = 30.0,
        max_retries: int = 3,
        session: _SessionLike | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("COINALYZE_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

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
                    retry_after = response.headers.get("Retry-After")
                    sleep_seconds = min(max(float(retry_after) if retry_after else 1.0, 0.0), 120.0)
                    if attempt < self.max_retries:
                        time.sleep(sleep_seconds)
                        continue
                    raise CoinAlYZeError("Rate limit exceeded")
                if response.status_code in {502, 503, 504}:
                    if attempt < self.max_retries:
                        time.sleep(min(2**attempt, 120.0))
                        continue
                    raise CoinAlYZeError(f"Upstream error: {response.status_code}")
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(min(2**attempt, 120.0))

        raise CoinAlYZeError(f"CoinAlYZe request failed: {last_error}") from last_error

    def exchanges(self) -> list[dict[str, Any]]:
        data = self._request("exchanges")
        return list(data) if isinstance(data, list) else data.get("data", [])

    def spot_markets(self) -> list[dict[str, Any]]:
        data = self._request("spot-markets")
        return list(data) if isinstance(data, list) else data.get("data", [])

    def future_markets(self) -> list[dict[str, Any]]:
        data = self._request("future-markets")
        return list(data) if isinstance(data, list) else data.get("data", [])

    def ohlcv_history(self, symbol: str, timeframe: str = "1h", limit: int = 500) -> MarketData:
        data = self._request(
            "ohlcv-history",
            params={"symbol": symbol, "interval": timeframe, "limit": limit},
        )
        ohlcv = data if isinstance(data, list) else data.get("data", data.get("ohlcv", []))
        return MarketData(symbol=symbol, timeframe=timeframe, ohlcv=list(ohlcv))
