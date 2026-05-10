from __future__ import annotations

from cvd_monitor.cvd_calculator import calculate_cvd_from_ohlcv, parse_coinalyze_symbol


def test_parse_coinalyze_symbol() -> None:
    parsed = parse_coinalyze_symbol("BTCUSDT.Binance")

    assert parsed.market_symbol == "BTCUSDT"
    assert parsed.exchange_code == "Binance"


def test_calculate_cvd_from_ohlcv() -> None:
    candles = [
        {"open": 1, "close": 2, "volume": 10},
        {"open": 2, "close": 1, "volume": 4},
        {"open": 1, "close": 1, "volume": 7},
    ]

    assert calculate_cvd_from_ohlcv(candles) == [10.0, 6.0, 6.0]
