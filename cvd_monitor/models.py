from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

Category = Literal['btc_stable', 'stable_fiat', 'stable_cross', 'other']


@dataclass(slots=True)
class Settings:
    discord_webhook_url: str | None
    db_path: Path
    output_dir: Path
    poll_interval_seconds: int
    fetch_interval_seconds: int
    render_interval_seconds: int
    history_days: int
    retention_days: int
    request_timeout_seconds: int
    markets_config_path: Path
    ohlcv_timeframe: str
    ohlcv_limit: int
    flow_delta_threshold_quote: float


@dataclass(slots=True)
class MarketConfig:
    market_key: str
    exchange: str
    coinalyze_symbol: str
    symbol: str
    symbol_on_exchange: str
    display_pair: str
    market_type: str
    base_symbol: str
    quote_symbol: str
    category: str
    priority: int
    enabled: bool


@dataclass(slots=True)
class OhlcvBar:
    bucket_start_utc: datetime
    market_key: str
    exchange: str
    symbol: str
    base_symbol: str
    quote_symbol: str
    category: str
    timeframe: str
    timeframe_seconds: int
    open: float
    high: float
    low: float
    close: float
    volume_base: float
    volume_quote: float
    proxy_delta_base: float
    proxy_delta_quote: float


@dataclass(slots=True)
class RawOhlcvRow:
    market_key: str
    symbol: str
    exchange: str
    symbol_on_exchange: str
    market_type: str
    category: str
    interval: str
    ts: int
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    buy_volume: float | None
    tx: int | None
    buy_tx: int | None
    fetched_at: int


@dataclass(slots=True)
class CvdFeatureRow:
    market_key: str
    symbol: str
    interval: str
    ts: int
    delta: float | None
    delta_quote: float | None
    cvd: float | None
    cvd_quote: float | None
    buy_ratio: float | None
    buy_tx_ratio: float | None
    cvd_change_15m: float | None
    cvd_change_1h: float | None
    computed_at: int


@dataclass(slots=True)
class RunOnceResult:
    success: bool
    received_rows: int
    computed_rows: int
    selected_markets_count: int
    markets_with_feature_rows_count: int
    plotted_series_count: int
    omitted_for_crowding_count: int
    skipped_no_feature_rows_count: int
    skipped_no_usable_cvd_values_count: int
    unresolved_symbols_count: int
    failed_symbols: list[str]
    rendered_path: str | None
    discord_enabled: bool
    discord_sent: bool
    discord_error: str | None
    summary: str
