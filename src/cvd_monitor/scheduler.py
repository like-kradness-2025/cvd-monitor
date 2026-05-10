"""Background scheduler."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone


_TIMEFRAME_SECONDS = {
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

from .coinalyze import CoinAlYZeClient
from .cvd_calculator import calculate_cvd_from_ohlcv, parse_coinalyze_symbol
from .database import CVDRecord, Database
from .dashboard import build_dashboard
from .discord_sender import send_chart
from .markets import filter_btc_markets, normalize_exchange_name
from .selected20_markets import SELECTED20_MARKETS

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SchedulerConfig:
    symbol: str = "BTCUSDT"
    timeframe: str = "1h"
    output_path: str = "artifacts/dashboard.png"
    webhook_url: str | None = None
    interval_seconds: int = 3600
    use_selected20_markets: bool = False


class Scheduler:
    def __init__(self, config: SchedulerConfig | None = None) -> None:
        self.config = config or SchedulerConfig()
        self.client = CoinAlYZeClient()
        self.database = Database()
        self.database.init_schema()

    def _select_market_symbol(self, markets: list[dict[str, object]], exchange_code: str, default_symbol: str) -> str:
        filtered = filter_btc_markets(markets, exchange_code=exchange_code)
        if filtered:
            return str(filtered[0].get("symbol", default_symbol))
        exchange_name = normalize_exchange_name(exchange_code)
        return f"{default_symbol}.{exchange_name}" if exchange_name else default_symbol

    def _history_window(self, timeframe: str, candles: int = 500) -> tuple[int, int]:
        seconds = _TIMEFRAME_SECONDS.get(timeframe.lower(), 60 * 60)
        to_ts = int(datetime.now(timezone.utc).timestamp())
        from_ts = to_ts - (seconds * candles)
        return from_ts, to_ts

    def collect_and_save(self) -> CVDRecord:
        if self.config.use_selected20_markets:
            return self.collect_and_save_selected20()
        try:
            parsed = parse_coinalyze_symbol(self.config.symbol)
            spot_markets = self.client.spot_markets()
            futures_markets = self.client.future_markets()
            spot_symbol = self._select_market_symbol(spot_markets, parsed.exchange_code, parsed.market_symbol)
            futures_symbol = self._select_market_symbol(futures_markets, parsed.exchange_code, parsed.market_symbol)
            spot_from_ts, spot_to_ts = self._history_window(self.config.timeframe)
            futures_from_ts, futures_to_ts = self._history_window(self.config.timeframe)
            spot_data = self.client.ohlcv_history(spot_symbol, spot_from_ts, spot_to_ts, self.config.timeframe)
            futures_data = self.client.ohlcv_history(futures_symbol, futures_from_ts, futures_to_ts, self.config.timeframe)
            spot_cvd = calculate_cvd_from_ohlcv(spot_data.ohlcv)
            futures_cvd = calculate_cvd_from_ohlcv(futures_data.ohlcv)
            latest_price = float(spot_data.ohlcv[-1].get("close", 0.0)) if spot_data.ohlcv else 0.0
            now = int(datetime.now(timezone.utc).timestamp())

            spot_record = CVDRecord(
                symbol=f"{self.config.symbol}:spot",
                timeframe=self.config.timeframe,
                timestamp=now,
                price=latest_price,
                spot_cvd=spot_cvd[-1] if spot_cvd else 0.0,
                futures_cvd=0.0,
            )
            futures_record = CVDRecord(
                symbol=f"{self.config.symbol}:futures",
                timeframe=self.config.timeframe,
                timestamp=now,
                price=latest_price,
                spot_cvd=0.0,
                futures_cvd=futures_cvd[-1] if futures_cvd else 0.0,
            )
            self.database.save_cvd_data(
                spot_record,
                payload={"market_type": "spot", "symbol": spot_symbol, "ohlcv_count": len(spot_data.ohlcv)},
            )
            self.database.save_cvd_data(
                futures_record,
                payload={"market_type": "futures", "symbol": futures_symbol, "ohlcv_count": len(futures_data.ohlcv)},
            )
            return spot_record
        except Exception:
            logger.exception("collect_and_save failed")
            raise

    def collect_and_save_selected20(self) -> CVDRecord:
        now = int(datetime.now(timezone.utc).timestamp())
        primary_record: CVDRecord | None = None
        for market in SELECTED20_MARKETS:
            from_ts, to_ts = self._history_window(self.config.timeframe)
            data = self.client.ohlcv_history(market.symbol, from_ts, to_ts, self.config.timeframe)
            cvd = calculate_cvd_from_ohlcv(data.ohlcv)
            latest_price = float(data.ohlcv[-1].get("close", 0.0)) if data.ohlcv else 0.0
            record = CVDRecord(
                symbol=market.symbol,
                timeframe=self.config.timeframe,
                timestamp=now,
                price=latest_price,
                spot_cvd=cvd[-1] if market.market_type == "spot" and cvd else 0.0,
                futures_cvd=cvd[-1] if market.market_type == "future" and cvd else 0.0,
            )
            self.database.save_cvd_data(record, payload={"market_name": market.market_name, "market_type": market.market_type, "symbol": market.symbol_on_exchange, "ohlcv_count": len(data.ohlcv)})
            if primary_record is None:
                primary_record = record
        if primary_record is None:
            raise RuntimeError("No selected20 markets were collected")
        self.config.symbol = primary_record.symbol
        return primary_record

    def generate_and_send_dashboard(self) -> bool:
        try:
            records = self.database.query_cvd_data(self.config.symbol, self.config.timeframe)
            image_path = build_dashboard(records, self.config.output_path)
            if image_path is None:
                logger.warning("No records available for dashboard")
                return False
            return send_chart(self.config.webhook_url, str(image_path))
        except Exception:
            logger.exception("generate_and_send_dashboard failed")
            raise

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
