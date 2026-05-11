from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 2

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL,
    applied_at INTEGER NOT NULL
);

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

CREATE TABLE IF NOT EXISTS cvd_history (
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    market_type TEXT NOT NULL DEFAULT 'unknown',
    interval TEXT NOT NULL,
    buy_volume REAL,
    sell_volume REAL,
    volume_delta REAL,
    cumulative_cvd REAL,
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

CREATE TABLE IF NOT EXISTS ohlcv_fetch_state (
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    market_type TEXT NOT NULL DEFAULT 'unknown',
    interval TEXT NOT NULL,
    last_timestamp INTEGER,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (symbol, exchange, market_type, interval)
);

CREATE TABLE IF NOT EXISTS open_interest_history (
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    market_type TEXT NOT NULL DEFAULT 'unknown',
    interval TEXT NOT NULL,
    open_interest REAL,
    source TEXT DEFAULT 'coinalyze',
    fetched_at INTEGER,
    raw_json TEXT,
    UNIQUE(timestamp, symbol, exchange, market_type, interval)
);

CREATE TABLE IF NOT EXISTS open_interest_fetch_state (
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    market_type TEXT NOT NULL DEFAULT 'unknown',
    interval TEXT NOT NULL,
    last_timestamp INTEGER,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (symbol, exchange, market_type, interval)
);

CREATE TABLE IF NOT EXISTS funding_rate_history (
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    market_type TEXT NOT NULL DEFAULT 'unknown',
    interval TEXT NOT NULL,
    funding_rate REAL,
    source TEXT DEFAULT 'coinalyze',
    fetched_at INTEGER,
    raw_json TEXT,
    UNIQUE(timestamp, symbol, exchange, market_type, interval)
);

CREATE TABLE IF NOT EXISTS funding_rate_fetch_state (
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    market_type TEXT NOT NULL DEFAULT 'unknown',
    interval TEXT NOT NULL,
    last_timestamp INTEGER,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (symbol, exchange, market_type, interval)
);

CREATE TABLE IF NOT EXISTS liquidation_history (
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    market_type TEXT NOT NULL DEFAULT 'unknown',
    interval TEXT NOT NULL,
    long_liquidation REAL,
    short_liquidation REAL,
    source TEXT DEFAULT 'coinalyze',
    fetched_at INTEGER,
    raw_json TEXT,
    UNIQUE(timestamp, symbol, exchange, market_type, interval)
);

CREATE TABLE IF NOT EXISTS liquidation_fetch_state (
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    market_type TEXT NOT NULL DEFAULT 'unknown',
    interval TEXT NOT NULL,
    last_timestamp INTEGER,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (symbol, exchange, market_type, interval)
);

CREATE TABLE IF NOT EXISTS long_short_ratio_history (
    timestamp INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    market_type TEXT NOT NULL DEFAULT 'unknown',
    interval TEXT NOT NULL,
    long_short_ratio REAL,
    source TEXT DEFAULT 'coinalyze',
    fetched_at INTEGER,
    raw_json TEXT,
    UNIQUE(timestamp, symbol, exchange, market_type, interval)
);

CREATE TABLE IF NOT EXISTS long_short_ratio_fetch_state (
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    market_type TEXT NOT NULL DEFAULT 'unknown',
    interval TEXT NOT NULL,
    last_timestamp INTEGER,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (symbol, exchange, market_type, interval)
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


@dataclass(frozen=True)
class CVDRecord:
    timestamp: int
    symbol: str
    exchange: str
    market_type: str | None
    interval: str
    buy_volume: float | None
    sell_volume: float | None
    volume_delta: float | None
    cumulative_cvd: float | None
    source: str = "coinalyze"
    fetched_at: int | None = None
    raw_json: str | None = None


@dataclass(frozen=True)
class OpenInterestRecord:
    timestamp: int
    symbol: str
    exchange: str
    market_type: str | None
    interval: str
    open_interest: float | None
    source: str = "coinalyze"
    fetched_at: int | None = None
    raw_json: str | None = None


@dataclass(frozen=True)
class FundingRateRecord:
    timestamp: int
    symbol: str
    exchange: str
    market_type: str | None
    interval: str
    funding_rate: float | None
    source: str = "coinalyze"
    fetched_at: int | None = None
    raw_json: str | None = None


@dataclass(frozen=True)
class LiquidationRecord:
    timestamp: int
    symbol: str
    exchange: str
    market_type: str | None
    interval: str
    long_liquidation: float | None
    short_liquidation: float | None
    source: str = "coinalyze"
    fetched_at: int | None = None
    raw_json: str | None = None


@dataclass(frozen=True)
class LongShortRatioRecord:
    timestamp: int
    symbol: str
    exchange: str
    market_type: str | None
    interval: str
    long_short_ratio: float | None
    source: str = "coinalyze"
    fetched_at: int | None = None
    raw_json: str | None = None


Record = OHLCVRecord | CVDRecord | OpenInterestRecord | FundingRateRecord | LiquidationRecord | LongShortRatioRecord
AnyRow = dict[str, Any]
