"""Collection scheduler and orchestration."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

from .coinalyze import CoinAlYZeClient
from .cvd_calculator import calculate_cvd_points, parse_coinalyze_symbol
from .database import DEFAULT_DATABASE_PATH, CVDRecord, Database
from .dashboard import DEFAULT_DASHBOARD_PATH, build_dashboard
from .discord_sender import send_chart
from .markets import filter_btc_markets, normalize_exchange_name, pick_first_symbol

logger = logging.getLogger(__name__)

_TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "1min": 60,
    "5m": 5 * 60,
    "5min": 5 * 60,
    "15m": 15 * 60,
    "15min": 15 * 60,
    "30m": 30 * 60,
    "30min": 30 * 60,
    "1h": 60 * 60,
    "1hour": 60 * 60,
    "2h": 2 * 60 * 60,
    "2hour": 2 * 60 * 60,
    "4h": 4 * 60 * 60,
    "4hour": 4 * 60 * 60,
    "6h": 6 * 60 * 60,
    "6hour": 6 * 60 * 60,
    "12h": 12 * 60 * 60,
    "12hour": 12 * 60 * 60,
    "1d": 24 * 60 * 60,
    "1day": 24 * 60 * 60,
    "daily": 24 * 60 * 60,
}


@dataclass(slots=True, frozen=True)
class SchedulerConfig:
    symbol: str = "BTCUSDT"
    timeframe: str = "1h"
    output_path: str = DEFAULT_DASHBOARD_PATH
    webhook_url: str | None = None
    database_path: str = DEFAULT_DATABASE_PATH
    interval_seconds: int = 3600
    history_candles: int = 500

    @classmethod
    def from_env(cls) -> "SchedulerConfig":
        load_dotenv()
        return cls(
            symbol=os.getenv("CVD_SYMBOL", cls.symbol),
            timeframe=os.getenv("CVD_TIMEFRAME", cls.timeframe),
            output_path=os.getenv("CVD_DASHBOARD_PATH", cls.output_path),
            webhook_url=os.getenv("DISCORD_WEBHOOK_URL") or None,
            database_path=os.getenv("DATABASE_PATH", cls.database_path),
            interval_seconds=_env_int("CVD_INTERVAL_SECONDS", cls.interval_seconds),
            history_candles=_env_int("CVD_HISTORY_CANDLES", cls.history_candles),
        )


class Scheduler:
    def __init__(
        self,
        config: SchedulerConfig | None = None,
        client: CoinAlYZeClient | None = None,
        database: Database | None = None,
    ) -> None:
        self.config = config or SchedulerConfig.from_env()
        self.client = client or CoinAlYZeClient()
        self.database = database or Database(self.config.database_path)
        self.database.init_schema()

    def collect_and_save(self) -> CVDRecord:
        """Collect latest spot/futures histories and store one combined record."""

        parsed = parse_coinalyze_symbol(self.config.symbol)
        spot_symbol = self._select_market_symbol(self.client.spot_markets(), parsed.exchange_code, parsed.market_symbol)
        futures_symbol = self._select_market_symbol(self.client.future_markets(), parsed.exchange_code, parsed.market_symbol)
        from_ts, to_ts = self._history_window()

        spot_data = self.client.ohlcv_history(spot_symbol, from_ts, to_ts, self.config.timeframe)
        futures_data = self.client.ohlcv_history(futures_symbol, from_ts, to_ts, self.config.timeframe)
        spot_points = calculate_cvd_points(spot_data.ohlcv)
        futures_points = calculate_cvd_points(futures_data.ohlcv)

        timestamp = _latest_timestamp(spot_points, futures_points) or int(datetime.now(timezone.utc).timestamp())
        latest_price = _latest_price(spot_points, futures_points)
        record = CVDRecord(
            symbol=self.config.symbol,
            timeframe=self.config.timeframe,
            timestamp=timestamp,
            price=latest_price,
            spot_cvd=spot_points[-1].cvd if spot_points else 0.0,
            futures_cvd=futures_points[-1].cvd if futures_points else 0.0,
        )

        self.database.save_cvd_data(
            record,
            payload={
                "spot_symbol": spot_symbol,
                "futures_symbol": futures_symbol,
                "spot_ohlcv_count": len(spot_data.ohlcv),
                "futures_ohlcv_count": len(futures_data.ohlcv),
                "from_ts": from_ts,
                "to_ts": to_ts,
                "cvd_type": "approx_ohlcv",
            },
        )
        return record

    def generate_and_send_dashboard(self) -> bool:
        records = self.database.query_cvd_data(self.config.symbol, self.config.timeframe)
        image_path = build_dashboard(records, self.config.output_path)
        if image_path is None:
            logger.warning("No records available for dashboard")
            return False
        return send_chart(self.config.webhook_url, str(image_path))

    def run_once(self) -> bool:
        self.collect_and_save()
        return self.generate_and_send_dashboard()

    def run_forever(self) -> None:
        while True:
            try:
                self.run_once()
            except Exception:
                logger.exception("Scheduler loop failed")
            time.sleep(self.config.interval_seconds)

    def _select_market_symbol(self, markets: list[dict[str, Any]], exchange_code: str, default_symbol: str) -> str:
        filtered = filter_btc_markets(markets, exchange_code=exchange_code or None)
        if filtered:
            return pick_first_symbol(filtered, default_symbol)

        exchange_name = normalize_exchange_name(exchange_code)
        return f"{default_symbol}.{exchange_name}" if exchange_name else default_symbol

    def _history_window(self) -> tuple[int, int]:
        seconds = _timeframe_seconds(self.config.timeframe)
        to_ts = int(datetime.now(timezone.utc).timestamp())
        from_ts = to_ts - (seconds * max(1, self.config.history_candles))
        return from_ts, to_ts


def _timeframe_seconds(timeframe: str) -> int:
    return _TIMEFRAME_SECONDS.get(timeframe.strip().lower(), 60 * 60)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid integer env var %s=%r; using %s", name, value, default)
        return default


def _latest_timestamp(*point_sets: Any) -> int | None:
    timestamps: list[int] = []
    for points in point_sets:
        if points and points[-1].timestamp is not None:
            timestamps.append(points[-1].timestamp)
    return max(timestamps) if timestamps else None


def _latest_price(*point_sets: Any) -> float:
    for points in point_sets:
        if points:
            return points[-1].price
    return 0.0
