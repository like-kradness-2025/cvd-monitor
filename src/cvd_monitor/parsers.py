from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_INTERVAL_SECONDS = {
    "1m": 60,
    "1min": 60,
    "5m": 300,
    "5min": 300,
    "15m": 900,
    "15min": 900,
    "30m": 1800,
    "30min": 1800,
    "1h": 3600,
    "1hour": 3600,
    "2h": 7200,
    "2hour": 7200,
    "4h": 14400,
    "4hour": 14400,
    "6h": 21600,
    "6hour": 21600,
    "12h": 43200,
    "12hour": 43200,
    "1d": 86400,
    "daily": 86400,
}


@dataclass(frozen=True)
class MetricPoint:
    timestamp: int
    value: float | tuple[float | None, float | None] | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class FetchPlan:
    symbol: str
    exchange: str
    market_type: str | None
    interval: str
    from_ts: int
    to_ts: int
    metrics: tuple[str, ...] = ("ohlcv", "open_interest", "funding_rate", "liquidation", "long_short_ratio")


def normalize_interval(interval: str) -> str:
    interval = str(interval).strip()
    if interval not in _INTERVAL_SECONDS:
        raise ValueError(f"unsupported interval: {interval}")
    return interval


def interval_seconds(interval: str) -> int:
    return _INTERVAL_SECONDS[normalize_interval(interval)]


def validate_query_params(*, symbol: str | None, exchange: str | None, interval: str, from_ts: int, to_ts: int) -> None:
    if not symbol or not str(symbol).strip():
        raise ValueError("symbol is required")
    if exchange is None or not str(exchange).strip():
        raise ValueError("exchange is required")
    if from_ts < 0 or to_ts < 0:
        raise ValueError("timestamps must be non-negative")
    if from_ts >= to_ts:
        raise ValueError("from_ts must be earlier than to_ts")
    normalize_interval(interval)


def clamp_timestamp(timestamp: int, *, lower: int = 0, upper: int | None = None) -> int:
    timestamp = int(timestamp)
    if upper is not None:
        return max(lower, min(timestamp, upper))
    return max(lower, timestamp)


def parse_timestamp(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid timestamp: {value!r}") from exc


def compute_fetch_from_ts(*, last_timestamp: int | None, default_from_ts: int, overlap_candles: int, interval_seconds: int, now: int) -> int:
    overlap_seconds = max(0, overlap_candles * interval_seconds)
    candidate = (last_timestamp - overlap_seconds) if last_timestamp is not None else default_from_ts
    return clamp_timestamp(candidate, lower=0, upper=now - 1)


def history_points(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        history = payload[0].get("history", [])
        if isinstance(history, list):
            return sorted((p for p in history if isinstance(p, dict)), key=lambda x: x.get("t", 0))
    return []


def required_field(point: dict[str, Any], key: str, context: str) -> Any:
    """Return a required field from a parsed point.

    Raises:
        ValueError: If the key is missing or maps to ``None``.
    """
    value = point.get(key)
    if value is None:
        raise ValueError(f"{context} missing required field '{key}'")
    return value


def _optional_float(point: dict[str, Any], key: str) -> float | None:
    value = point.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid value for '{key}': {value!r}") from exc


def parse_ohlcv_record(point: dict[str, Any], *, symbol: str, exchange: str, market_type: str | None, interval: str, fetched_at: int) -> dict[str, Any]:
    return {
        "timestamp": parse_timestamp(required_field(point, "t", "OHLCV candle")),
        "symbol": symbol,
        "exchange": exchange,
        "market_type": market_type,
        "interval": normalize_interval(interval),
        "open": _optional_float(point, "o"),
        "high": _optional_float(point, "h"),
        "low": _optional_float(point, "l"),
        "close": _optional_float(point, "c"),
        "volume": _optional_float(point, "v"),
        "buy_volume": _optional_float(point, "bv"),
        "sell_volume": _optional_float(point, "sv"),
        "volume_delta": (float(point.get("bv")) - float(point.get("sv"))) if point.get("bv") is not None and point.get("sv") is not None else None,
        "fetched_at": fetched_at,
        "raw_json": point,
    }


def _first_float(point: dict[str, Any], keys: tuple[str, ...], *, context: str, required: bool = False) -> float | None:
    for key in keys:
        value = point.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid value for '{key}': {value!r}") from exc
    if required:
        raise ValueError(f"{context} missing required field '{keys[0]}'")
    return None


def transform_open_interest(point: dict[str, Any]) -> float:
    value = _first_float(point, ("oi", "open_interest", "openInterest", "value", "v"), required=True, context="open interest point")
    assert value is not None
    return value


def transform_funding_rate(point: dict[str, Any]) -> float | None:
    return _first_float(point, ("funding_rate", "fundingRate", "fr", "value", "v"), context="funding rate point")


def transform_liquidation(point: dict[str, Any]) -> tuple[float | None, float | None]:
    return (
        _first_float(point, ("long_liquidation", "longLiquidation", "long", "buy", "long_volume"), context="liquidation point"),
        _first_float(point, ("short_liquidation", "shortLiquidation", "short", "sell", "short_volume"), context="liquidation point"),
    )


def transform_long_short_ratio(point: dict[str, Any]) -> float | None:
    return _first_float(point, ("long_short_ratio", "longShortRatio", "ratio", "value", "v"), context="long-short ratio point")
