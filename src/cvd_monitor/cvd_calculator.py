"""CVD calculation utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(slots=True)
class ParsedSymbol:
    market_symbol: str
    exchange_code: str


def parse_coinalyze_symbol(symbol: str) -> ParsedSymbol:
    """Split CoinAlYZe symbol into market symbol and exchange code."""

    if "." not in symbol:
        return ParsedSymbol(market_symbol=symbol, exchange_code="")
    market_symbol, exchange_code = symbol.rsplit(".", 1)
    return ParsedSymbol(market_symbol=market_symbol, exchange_code=exchange_code)


def calculate_cvd_from_ohlcv(candles: Iterable[dict[str, Any]]) -> list[float]:
    """Calculate a simple CVD series from OHLCV candles.

    Uses candle direction as a proxy for delta:
    - bullish candle => positive volume
    - bearish candle => negative volume
    - flat => zero
    """

    cvd = 0.0
    values: list[float] = []
    for candle in candles:
        open_price = float(candle.get("open", 0.0))
        close_price = float(candle.get("close", 0.0))
        volume = float(candle.get("volume", candle.get("vol", 0.0)))
        if close_price > open_price:
            cvd += volume
        elif close_price < open_price:
            cvd -= volume
        values.append(cvd)
    return values
