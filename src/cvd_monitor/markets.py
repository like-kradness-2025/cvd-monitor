"""Market selection helpers."""

from __future__ import annotations

from typing import Any

EXCHANGE_MAP: dict[str, str] = {
    "binance": "Binance",
    "bybit": "Bybit",
    "okx": "OKX",
    "coinbase": "Coinbase",
    "kraken": "Kraken",
    "bitfinex": "Bitfinex",
}


def normalize_exchange_name(exchange_code: str) -> str:
    return EXCHANGE_MAP.get(exchange_code.lower(), exchange_code)


def filter_btc_markets(markets: list[dict[str, Any]], exchange_code: str | None = None) -> list[dict[str, Any]]:
    """Return BTC markets, optionally filtered by exchange code."""

    filtered: list[dict[str, Any]] = []
    for market in markets:
        symbol = str(market.get("symbol", "")).upper()
        base_asset = str(market.get("base_asset", market.get("base", ""))).upper()
        exchange = normalize_exchange_name(str(market.get("exchange", market.get("exchange_code", ""))))
        is_btc_symbol = symbol == "BTC" or symbol.startswith("BTC/") or symbol.startswith("BTC-") or symbol.startswith("BTC_") or symbol.startswith("BTC")
        is_btc_base = base_asset == "BTC"
        if not (is_btc_symbol or is_btc_base):
            continue
        if exchange_code and exchange.lower() != exchange_code.lower() and str(market.get("exchange_code", "")).lower() != exchange_code.lower():
            continue
        filtered.append(market)
    return filtered
