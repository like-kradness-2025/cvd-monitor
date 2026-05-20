from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import requests

from .constants import CANDLE_CUTOFF_SECONDS
from .db import save_raw_ohlcv_rows
from .models import MarketConfig, RawOhlcvRow, Settings


@dataclass(slots=True)
class CoinalyzeClient:
    api_key: str
    base_url: str = 'https://api.coinalyze.net/v1'
    session: requests.Session = field(init=False)
    _last_request_at: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({'api_key': self.api_key})

    def fetch_ohlcv_history(self, symbols: list[str], interval: str, from_ts: int, to_ts: int) -> list[dict[str, Any]]:
        url = f'{self.base_url}/ohlcv-history'
        params = {'symbols': ','.join(symbols), 'interval': interval, 'from': from_ts, 'to': to_ts}
        last_exc: Exception | None = None
        for attempt in range(4):
            self._respect_rate_limit()
            try:
                resp = self.session.get(url, params=params, timeout=30)
                self._last_request_at = time.time()
                if resp.status_code == 429:
                    retry_after = resp.headers.get('Retry-After')
                    wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else 30
                    time.sleep(wait_seconds)
                    continue
                resp.raise_for_status()
                data = self._normalize_payload(resp.json())
                return data
            except Exception as exc:
                last_exc = exc
                if attempt < 3:
                    time.sleep(2 ** attempt)
        if last_exc is not None:
            raise last_exc
        return []

    def _normalize_payload(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ('data', 'result', 'ohlcv_history', 'ohlcv', 'items'):
                value = data.get(key)
                if isinstance(value, list):
                    return value
            if all(isinstance(value, list) for value in data.values()):
                return [{'symbol': str(symbol).upper(), 'history': history} for symbol, history in data.items()]
        return []

    def _respect_rate_limit(self) -> None:
        if self._last_request_at:
            elapsed = time.time() - self._last_request_at
            min_delay = 60 / 36
            if elapsed < min_delay:
                time.sleep(min_delay - elapsed)


class CoinalyzeOhlcvReceiver:
    def __init__(self, settings: Settings, markets: list[MarketConfig]) -> None:
        self.settings = settings
        self.markets = [m for m in markets if m.enabled and m.coinalyze_symbol]
        api_key = (os.getenv('COINALYZE_API_KEY') or '').strip()
        if not api_key:
            raise RuntimeError('COINALYZE_API_KEY is required')
        self.client: Any = CoinalyzeClient(api_key)

    def run(self, interval: str, lookback_hours: int, once: bool = False) -> bool:
        del once
        any_ok = False
        for batch in _chunked(self.markets, 10):
            try:
                self._receive_batch(batch, interval, lookback_hours)
                any_ok = True
            except Exception:
                logging.exception('Receiver failed for batch starting %s', batch[0].market_key if batch else 'n/a')
        return any_ok

    def _receive_batch(self, markets: list[MarketConfig], interval: str, lookback_hours: int) -> None:
        now = datetime.now(timezone.utc)
        now_s = int(now.timestamp())
        interval_seconds = CANDLE_CUTOFF_SECONDS if interval == '5min' else CANDLE_CUTOFF_SECONDS
        overlap_seconds = max(3600, interval_seconds * 2)
        lookback_seconds = lookback_hours * 3600
        fetch_from = now_s - (lookback_seconds + overlap_seconds)
        persist_from = now_s - lookback_seconds
        try:
            rows = self._fetch_rows_for_markets(markets, interval, fetch_from, persist_from, now_s)
        except Exception:
            if len(markets) <= 1:
                raise
            logging.warning(
                'Receiver batch failed for %d markets; retrying individually to isolate unsupported or temporarily unavailable symbols.',
                len(markets),
            )
            for market in markets:
                try:
                    rows = self._fetch_rows_for_markets([market], interval, fetch_from, persist_from, now_s)
                    save_raw_ohlcv_rows(self.settings.db_path, rows)
                except Exception:
                    logging.exception('Receiver failed for %s', market.market_key)
            return
        save_raw_ohlcv_rows(self.settings.db_path, rows)

    def _fetch_rows_for_markets(self, markets: list[MarketConfig], interval: str, fetch_from: int, persist_from: int, now_s: int) -> list[RawOhlcvRow]:
        payload = self.client.fetch_ohlcv_history([m.coinalyze_symbol for m in markets], interval, fetch_from, now_s)
        by_symbol = {str(item.get('symbol', '')).upper(): item.get('history') or [] for item in payload if isinstance(item, dict)}
        rows: list[RawOhlcvRow] = []
        for market in markets:
            raw_rows = by_symbol.get(market.coinalyze_symbol.upper(), [])
            for item in raw_rows:
                try:
                    ts = _normalize_timestamp(item.get('t'), now_s)
                    if ts is None or ts < persist_from or ts > now_s:
                        continue
                    rows.append(RawOhlcvRow(
                        symbol=market.symbol,
                        market_key=market.market_key,
                        exchange=market.exchange,
                        symbol_on_exchange=market.symbol_on_exchange,
                        market_type=market.market_type,
                        category=market.category,
                        interval=interval,
                        ts=ts,
                        open=_num(item.get('o')),
                        high=_num(item.get('h')),
                        low=_num(item.get('l')),
                        close=_num(item.get('c')),
                        volume=_num(item.get('v')),
                        buy_volume=_num(item.get('bv')),
                        tx=_int(item.get('tx')),
                        buy_tx=_int(item.get('btx')),
                        fetched_at=now_s,
                    ))
                except Exception:
                    logging.exception('Receiver failed to normalize row for %s', market.market_key)
        return rows


def _chunked(items: list[MarketConfig], size: int) -> list[list[MarketConfig]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


def _int(value: Any) -> int | None:
    return None if value is None else int(value)


def _normalize_timestamp(value: Any, reference_now: int | None = None) -> int | None:
    if value is None:
        return None
    ts = int(value)
    if ts > 10_000_000_000:
        return ts // 1000
    if reference_now is not None and ts > reference_now * 10:
        return ts // 1000
    return ts
