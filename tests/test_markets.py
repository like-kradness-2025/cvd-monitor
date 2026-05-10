from __future__ import annotations

from cvd_monitor.markets import filter_btc_markets, normalize_exchange_name


def test_normalize_exchange_name() -> None:
    assert normalize_exchange_name("binance") == "Binance"


def test_filter_btc_markets() -> None:
    markets = [
        {"symbol": "BTCUSDT", "exchange": "Binance"},
        {"symbol": "ETHUSDT", "exchange": "Binance"},
        {"symbol": "BTCUSD", "exchange_code": "Bybit"},
        {"symbol": "XBTCUSDT", "exchange": "Binance"},
    ]

    assert filter_btc_markets(markets) == [markets[0], markets[2]]
    assert filter_btc_markets(markets, exchange_code="bybit") == [markets[2]]
