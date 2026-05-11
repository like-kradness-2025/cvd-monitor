"""CVD calculation utilities.

The current implementation estimates CVD from OHLCV candles. This is useful for
coarse monitoring, but it is not the same as trade-level buy/sell delta.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(slots=True, frozen=True)
class ParsedSymbol:
    market_symbol: str
    exchange_code: str = ""


@dataclass(slots=True, frozen=True)
class CVDPoint:
    timestamp: int | None
    price: float
    cvd: float
    signed_volume: float


def parse_coinalyze_symbol(symbol: str) -> ParsedSymbol:
    """Split `BTCUSDT.Binance` into market symbol and exchange code."""

    normalized = symbol.strip()
    if "." not in normalized:
        return ParsedSymbol(market_symbol=normalized)
    market_symbol, exchange_code = normalized.rsplit(".", 1)
    return ParsedSymbol(market_symbol=market_symbol, exchange_code=exchange_code)


def calculate_cvd_from_ohlcv(candles: Iterable[dict[str, Any]]) -> list[float]:
    """Return only the cumulative approximate CVD values.

    Kept for backward compatibility. Prefer `calculate_cvd_points` when the
    timestamp, price, or per-candle signed volume is needed.
    """

    return [point.cvd for point in calculate_cvd_points(candles)]


def calculate_cvd_points(candles: Iterable[dict[str, Any]]) -> list[CVDPoint]:
    """Calculate an approximate CVD series from OHLCV candles.

    When buy volume is available as `bv`, signed volume is estimated as
    `buy_volume - sell_volume`, where sell volume is `volume - buy_volume`.
    Otherwise, candle direction is used as a fallback.
    """

    cvd = 0.0
    points: list[CVDPoint] = []

    for candle in candles:
        open_price = _as_float(candle.get("open", candle.get("o")))
        close_price = _as_float(candle.get("close", candle.get("c")))
        volume = _as_float(candle.get("volume", candle.get("vol", candle.get("v"))))
        buy_volume = _as_optional_float(candle.get("buy_volume", candle.get("bv")))
        signed_volume = _signed_volume(
            open_price=open_price,
            close_price=close_price,
            volume=volume,
            buy_volume=buy_volume,
        )
        cvd += signed_volume

        points.append(
            CVDPoint(
                timestamp=_as_optional_int(candle.get("timestamp", candle.get("time", candle.get("t")))),
                price=close_price,
                cvd=cvd,
                signed_volume=signed_volume,
            )
        )

    return points


def _signed_volume(
    *,
    open_price: float,
    close_price: float,
    volume: float,
    buy_volume: float | None,
) -> float:
    if buy_volume is not None:
        sell_volume = max(volume - buy_volume, 0.0)
        return buy_volume - sell_volume
    if close_price > open_price:
        return volume
    if close_price < open_price:
        return -volume
    return 0.0


def _as_float(value: Any, default: float = 0.0) -> float:
    parsed = _as_optional_float(value)
    return default if parsed is None else parsed


def _as_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
