from __future__ import annotations

from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    yaml = None

from .constants import ALLOWED_CATEGORIES
from .exceptions import ConfigError
from .models import MarketConfig


def load_markets_config(path: Path) -> list[MarketConfig]:
    if yaml is None:
        raise ConfigError('PyYAML is not installed. Run: pip install -r requirements.txt')
    if not path.exists():
        raise ConfigError(f'Markets config not found: {path}')

    payload = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    raw_markets = payload.get('markets')
    if not isinstance(raw_markets, list) or not raw_markets:
        raise ConfigError('markets.yaml must contain a non-empty "markets" list')

    markets: list[MarketConfig] = []
    for idx, raw in enumerate(raw_markets, start=1):
        if not isinstance(raw, dict):
            raise ConfigError(f'markets[{idx}] must be an object')

        exchange = str(raw.get('exchange', '')).strip().lower()
        coinalyze_symbol = str(raw.get('coinalyze_symbol', '')).strip().upper()
        symbol_on_exchange = str(raw.get('symbol_on_exchange', raw.get('symbol', ''))).strip()
        symbol = str(raw.get('symbol', symbol_on_exchange)).strip().upper()
        display_pair = str(raw.get('display_pair', symbol)).strip()
        base_symbol = str(raw.get('base', raw.get('base_symbol', ''))).strip().upper()
        quote_symbol = str(raw.get('quote', raw.get('quote_symbol', ''))).strip().upper()
        category = str(raw.get('category', 'other')).strip().lower()
        market_key = str(raw.get('market_key', f'{exchange}:{symbol.lower()}')).strip().lower()
        enabled = bool(raw.get('enabled', True))
        priority = int(raw.get('priority', 100))
        market_type = str(raw.get('market_type', 'spot')).strip().lower()

        markets.append(MarketConfig(market_key, exchange, coinalyze_symbol, symbol, symbol_on_exchange or symbol, display_pair or symbol, market_type, base_symbol, quote_symbol, category, priority, enabled))

    validate_markets(markets)
    return sorted(markets, key=lambda item: item.priority)


def validate_markets(markets: list[MarketConfig]) -> None:
    seen: set[str] = set()
    for market in markets:
        if not market.exchange:
            raise ConfigError('market exchange must not be empty')
        if not market.symbol or (market.symbol.isalnum() and market.coinalyze_symbol == market.symbol):
            raise ConfigError(f'invalid market symbol for {market.market_key}: {market.symbol}')
        if not market.base_symbol or not market.quote_symbol:
            raise ConfigError(f'base/quote must not be empty for {market.market_key}')
        if market.base_symbol == market.quote_symbol:
            raise ConfigError(f'base and quote must differ for {market.market_key}')
        if market.category not in ALLOWED_CATEGORIES:
            raise ConfigError(f'invalid category for {market.market_key}: {market.category}')
        if market.market_key in seen:
            raise ConfigError(f'duplicate market_key: {market.market_key}')
        seen.add(market.market_key)


def enabled_markets(markets: list[MarketConfig]) -> list[MarketConfig]:
    return [market for market in markets if market.enabled]


def build_market_resolution_index(markets: list[MarketConfig]) -> dict[str, list[MarketConfig]]:
    index: dict[str, list[MarketConfig]] = {}
    for market in markets:
        for key in (
            market.market_key.upper(),
            market.coinalyze_symbol.upper(),
            market.symbol.upper(),
            market.symbol_on_exchange.upper(),
        ):
            if not key:
                continue
            index.setdefault(key, []).append(market)
    return index


def resolve_markets_by_symbol(markets: list[MarketConfig], symbols: list[str]) -> list[MarketConfig]:
    wanted = [symbol.strip().upper() for symbol in symbols if symbol and symbol.strip()]
    if not wanted:
        return []

    index = build_market_resolution_index(markets)
    selected: list[MarketConfig] = []
    seen: set[str] = set()
    for symbol in wanted:
        for market in index.get(symbol, []):
            if market.market_key in seen:
                continue
            selected.append(market)
            seen.add(market.market_key)
    return selected


def market_label(market_key: str) -> str:
    exchange, symbol = market_key.split(':', 1)
    return f'{exchange} {symbol.upper()}'
