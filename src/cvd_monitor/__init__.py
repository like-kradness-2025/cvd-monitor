"""CVD Monitor package."""

from .coinalyze import CoinAlYZeClient, CoinAlYZeError, MarketData
from .cvd_calculator import CVDPoint, ParsedSymbol, calculate_cvd_from_ohlcv, calculate_cvd_points, parse_coinalyze_symbol
from .database import CVDRecord, Database
from .dashboard import build_dashboard
from .discord_sender import send_chart
from .markets import EXCHANGE_MAP, filter_btc_markets, normalize_exchange_name, pick_first_symbol
from .scheduler import Scheduler, SchedulerConfig

__all__ = [
    "CoinAlYZeClient",
    "CoinAlYZeError",
    "MarketData",
    "CVDPoint",
    "ParsedSymbol",
    "calculate_cvd_from_ohlcv",
    "calculate_cvd_points",
    "parse_coinalyze_symbol",
    "CVDRecord",
    "Database",
    "build_dashboard",
    "send_chart",
    "EXCHANGE_MAP",
    "filter_btc_markets",
    "normalize_exchange_name",
    "pick_first_symbol",
    "Scheduler",
    "SchedulerConfig",
]

__version__ = "0.1.0"
