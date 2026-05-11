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
    normalized = exchange_code.strip()
    if not normalized:
        return ""
    return EXCHANGE_MAP.get(normalized.lower(), normalized)


def filter_btc_markets(markets: list[dict[str, Any]], exchange_code: str | None = None) -> list[dict[str, Any]]:
    """Return BTC markets, optionally filtered by exchange code/name."""

    target_exchange = normalize_exchange_name(exchange_code or "").lower()
    filtered: list[dict[str, Any]] = []

    for market in markets:
        if not _is_btc_market(market):
            continue
        if target_exchange and target_exchange not in _market_exchange_candidates(market):
            continue
        filtered.append(market)

    return filtered


def pick_first_symbol(markets: list[dict[str, Any]], default_symbol: str) -> str:
    for market in markets:
        symbol = market.get("symbol")
        if symbol:
            return str(symbol)
    return default_symbol


def _is_btc_market(market: dict[str, Any]) -> bool:
    symbol = str(market.get("symbol", "")).upper()
    base_asset = str(market.get("base_asset", market.get("base", ""))).upper()
    return base_asset == "BTC" or symbol in {"BTC", "BTCUSDT", "BTCUSD"} or symbol.startswith(("BTC/", "BTC-", "BTC_"))


def _market_exchange_candidates(market: dict[str, Any]) -> set[str]:
    values = {
        str(market.get("exchange", "")),
        str(market.get("exchange_code", "")),
        str(market.get("market", "")),
    }
    return {normalize_exchange_name(value).lower() for value in values if value}
