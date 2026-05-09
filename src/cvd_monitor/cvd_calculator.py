"""CVD calculation utilities."""

from typing import Iterable


def calculate_cvd(candles: Iterable[dict]) -> list[float]:
    cvd = 0.0
    values: list[float] = []
    for candle in candles:
        delta = float(candle.get('close', 0)) - float(candle.get('open', 0))
        cvd += delta
        values.append(cvd)
    return values
