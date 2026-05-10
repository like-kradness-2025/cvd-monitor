from __future__ import annotations

import json
import math
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from coinalyze_ohlcv.client import sanitize_for_persistence

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ohlcv_history (
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    market_type TEXT NOT NULL DEFAULT 'unknown',
    interval TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    buy_volume REAL,
    sell_volume REAL,
    volume_delta REAL,
    source TEXT DEFAULT 'coinalyze',
    fetched_at INTEGER,
    raw_json TEXT,
    UNIQUE(timestamp, symbol, exchange, market_type, interval)
);

CREATE TABLE IF NOT EXISTS fetch_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at INTEGER NOT NULL,
    finished_at INTEGER,
    symbols_file TEXT,
    db_path TEXT,
    interval TEXT,
    hours INTEGER,
    limit_symbols INTEGER,
    sleep_seconds REAL,
    market_type TEXT,
    dry_run INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    requested_count INTEGER NOT NULL DEFAULT 0,
    succeeded_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS fetch_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    symbol TEXT,
    exchange TEXT,
    market_type TEXT,
    interval TEXT,
    error_type TEXT,
    message TEXT,
    http_status INTEGER,
    retry_after REAL,
    created_at INTEGER NOT NULL,
    raw_json TEXT,
    FOREIGN KEY(run_id) REFERENCES fetch_runs(id)
);
"""


@dataclass(frozen=True)
class OHLCVRecord:
    timestamp: int
    symbol: str
    exchange: str
    market_type: str | None
    interval: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    buy_volume: float | None
    sell_volume: float | None
    volume_delta: float | None
    source: str = "coinalyze"
    fetched_at: int | None = None
    raw_json: str | None = None


def connect_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_market_type(market_type: str | None) -> str:
    value = (market_type or "unknown").strip()
    return value or "unknown"


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def create_fetch_run(conn: sqlite3.Connection, *, symbols_file: str, db_path: str, interval: str, hours: int, limit_symbols: int, sleep_seconds: float, market_type: str, dry_run: bool, requested_count: int) -> int:
    cur = conn.execute("""INSERT INTO fetch_runs (started_at, symbols_file, db_path, interval, hours, limit_symbols, sleep_seconds, market_type, dry_run, status, requested_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (int(time.time()), symbols_file, db_path, interval, hours, limit_symbols, sleep_seconds, market_type, 1 if dry_run else 0, "running", requested_count))
    conn.commit()
    return int(cur.lastrowid)


def finalize_fetch_run(conn: sqlite3.Connection, run_id: int, *, status: str, succeeded_count: int, failed_count: int, warning_count: int, notes: str | None = None) -> None:
    conn.execute("""UPDATE fetch_runs SET finished_at = ?, status = ?, succeeded_count = ?, failed_count = ?, warning_count = ?, notes = COALESCE(?, notes) WHERE id = ?""", (int(time.time()), status, succeeded_count, failed_count, warning_count, notes, run_id))
    conn.commit()


def save_error(conn: sqlite3.Connection, *, run_id: int | None, symbol: str | None, exchange: str | None, market_type: str | None, interval: str | None, error_type: str, message: str, http_status: int | None = None, retry_after: float | None = None, raw_json: Any = None) -> None:
    safe_message = sanitize_for_persistence(message)
    safe_raw_json = sanitize_for_persistence(raw_json)
    if isinstance(safe_raw_json, (dict, list, tuple)):
        safe_raw_json = json.dumps(safe_raw_json, ensure_ascii=False)
    elif safe_raw_json is not None and not isinstance(safe_raw_json, str):
        safe_raw_json = json.dumps(safe_raw_json, ensure_ascii=False)
    conn.execute("""INSERT INTO fetch_errors (run_id, symbol, exchange, market_type, interval, error_type, message, http_status, retry_after, created_at, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (run_id, symbol, exchange, market_type, interval, error_type, safe_message, http_status, retry_after, int(time.time()), safe_raw_json))
    conn.commit()


def _coerce_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"invalid numeric value: {value!r}")
    if math.isnan(number) or math.isinf(number):
        raise ValueError(f"invalid numeric value: {value!r}")
    return number


def record_from_candle(candle: Mapping[str, Any], *, symbol: str, exchange: str, market_type: str | None, interval: str, fetched_at: int | None = None) -> OHLCVRecord:
    timestamp = int(candle["t"])
    open_ = _coerce_number(candle.get("o", candle.get("open")))
    high = _coerce_number(candle.get("h", candle.get("high")))
    low = _coerce_number(candle.get("l", candle.get("low")))
    close = _coerce_number(candle.get("c", candle.get("close")))
    volume_raw = candle.get("v", candle.get("volume"))
    if volume_raw is None:
        raise ValueError("volume is required")
    volume = _coerce_number(volume_raw)
    buy_volume = _coerce_number(candle.get("bv", candle.get("buy_volume")))
    if volume is not None and buy_volume is not None and buy_volume > volume:
        raise ValueError(f"buy_volume cannot exceed volume: bv={buy_volume} v={volume}")
    sell_volume = volume - buy_volume if volume is not None and buy_volume is not None else None
    volume_delta = buy_volume - sell_volume if volume is not None and buy_volume is not None else None
    return OHLCVRecord(timestamp=timestamp, symbol=symbol, exchange=exchange, market_type=_normalize_market_type(market_type), interval=interval, open=open_, high=high, low=low, close=close, volume=volume, buy_volume=buy_volume, sell_volume=sell_volume, volume_delta=volume_delta, fetched_at=fetched_at, raw_json=sanitize_for_persistence(json.dumps(candle, ensure_ascii=False)))


def upsert_ohlcv_records(conn: sqlite3.Connection, records: Sequence[OHLCVRecord]) -> int:
    if not records:
        return 0
    rows = [(r.timestamp, r.symbol, r.exchange, _normalize_market_type(r.market_type), r.interval, r.open, r.high, r.low, r.close, r.volume, r.buy_volume, r.sell_volume, r.volume_delta, r.source, r.fetched_at, r.raw_json) for r in records]
    conn.executemany("""INSERT INTO ohlcv_history (timestamp, symbol, exchange, market_type, interval, open, high, low, close, volume, buy_volume, sell_volume, volume_delta, source, fetched_at, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(timestamp, symbol, exchange, market_type, interval) DO UPDATE SET open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close, volume=excluded.volume, buy_volume=excluded.buy_volume, sell_volume=excluded.sell_volume, volume_delta=excluded.volume_delta, source=excluded.source, fetched_at=excluded.fetched_at, raw_json=excluded.raw_json""", rows)
    conn.commit()
    return len(records)
