"""CoinAlYZe API helpers (skeleton)."""

from dataclasses import dataclass


@dataclass
class MarketData:
    symbol: str
    timeframe: str
    ohlcv: list[dict]


class CoinAlYZeClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    def fetch_ohlcv(self, symbol: str, timeframe: str = '1h') -> MarketData:
        return MarketData(symbol=symbol, timeframe=timeframe, ohlcv=[])
