from __future__ import annotations

from typing import Any, Mapping

from .storage import OHLCVRecord, record_from_candle as _record_from_candle


def normalize_candle(candle: Mapping[str, Any]) -> dict[str, Any]:
    """CoinAlYZe の OHLCV 形式を CVD 計算で扱える形に正規化する。"""
    normalized = dict(candle)
    aliases = {"open": "o", "high": "h", "low": "l", "close": "c", "volume": "v", "buy_volume": "bv"}
    for target, source in aliases.items():
        if target not in normalized and source in normalized:
            normalized[target] = normalized[source]
    return normalized


def record_from_candle(
    candle: Mapping[str, Any],
    *,
    symbol: str,
    exchange: str,
    market_type: str | None,
    interval: str,
    fetched_at: int | None = None,
) -> OHLCVRecord:
    return _record_from_candle(normalize_candle(candle), symbol=symbol, exchange=exchange, market_type=market_type, interval=interval, fetched_at=fetched_at)
