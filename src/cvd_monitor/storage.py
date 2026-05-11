from __future__ import annotations

import json
from contextlib import contextmanager
import math
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence, TypeVar

from coinalyze_ohlcv.client import sanitize_for_persistence

from .db import connect_db, get_schema_version, init_db, migrate, transaction
from .schemas import (
    CVDRecord,
    FundingRateRecord,
    LiquidationRecord,
    LongShortRatioRecord,
    OHLCVRecord,
    OpenInterestRecord,
    SCHEMA_VERSION,
)


class StorageError(Exception):
    pass


class StorageConnectionError(StorageError):
    pass


class StorageQueryError(StorageError):
    pass


class StorageNotFoundError(StorageError, LookupError):
    pass


class StorageTransientError(StorageError):
    pass


@dataclass(frozen=True)
class StorageDependencies:
    db_path: str | None = None
    connect: Callable[[str], sqlite3.Connection] = connect_db
    now: Callable[[], float] = time.time
    retries: int = 2
    retry_delay: float = 0.05


T = TypeVar("T")


def _is_transient_sqlite_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "database is locked" in message or "database is busy" in message or "locked" in message or "busy" in message


def _with_retry(deps: StorageDependencies, func: Callable[[], T], *, op: str) -> T:
    last: Exception | None = None
    for attempt in range(deps.retries + 1):
        try:
            return func()
        except sqlite3.OperationalError as exc:
            if not _is_transient_sqlite_error(exc):
                raise StorageQueryError(f"{op} failed: {exc}") from exc
            last = exc
            if attempt >= deps.retries:
                raise StorageTransientError(f"{op} failed after retries: {exc}") from exc
            time.sleep(deps.retry_delay * (attempt + 1))
        except sqlite3.Error as exc:
            raise StorageQueryError(f"{op} failed: {exc}") from exc
    assert last is not None
    raise StorageError(f"{op} failed: {last}")


def _write_transaction(conn: sqlite3.Connection, *, op: str, func: Callable[[], T]) -> T:
    if conn.in_transaction:
        raise RuntimeError(
            f"{op} must be called in autocommit mode with no active transaction or savepoint; "
            "commit or rollback the caller-managed transaction before calling this helper."
        )
    try:
        result = func()
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def _write_in_transaction(conn: sqlite3.Connection, *, func: Callable[[], T]) -> T:
    return func()


@contextmanager
def write_transaction(conn: sqlite3.Connection):
    """Open an atomic transaction for composing multiple storage writes.

    Use this when a caller needs several storage operations to succeed or fail
    together. The existing single-write helpers continue to autocommit via
    :func:`_write_transaction` for backward compatibility.
    """
    with transaction(conn):
        yield conn


def _normalize_market_type(market_type: str | None) -> str:
    value = (market_type or "unknown").strip().lower()
    return value or "unknown"


def _normalize_exchange(exchange: str | None) -> str:
    value = (exchange or "").strip().lower()
    return value or "unknown"


def _normalize_symbol(symbol: str | None) -> str:
    value = (symbol or "").strip()
    return value or "unknown"


def _normalize_interval(interval: str | None) -> str:
    value = (interval or "").strip().lower()
    return value or "unknown"


def _deps(dependencies: StorageDependencies | None = None, db_path: str | None = None) -> StorageDependencies:
    if dependencies is not None:
        return dependencies
    return StorageDependencies(db_path=db_path)


def _connection(deps: StorageDependencies) -> sqlite3.Connection:
    if not deps.db_path:
        raise StorageConnectionError("db_path is required")
    conn = deps.connect(deps.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _sanitize_raw(raw_json: Any) -> str | None:
    safe = sanitize_for_persistence(raw_json)
    if isinstance(safe, (dict, list, tuple)):
        return json.dumps(safe, ensure_ascii=False)
    if safe is not None and not isinstance(safe, str):
        return json.dumps(safe, ensure_ascii=False)
    return safe


def init_db_with_dependencies(dependencies: StorageDependencies | None = None, *, db_path: str | None = None) -> None:
    deps = _deps(dependencies, db_path)
    if deps.db_path is None:
        return
    conn = _connection(deps)
    try:
        init_db(conn)
    finally:
        conn.close()


def create_fetch_run(conn: sqlite3.Connection, *, symbols_file: str, db_path: str, interval: str, hours: int, limit_symbols: int, sleep_seconds: float, market_type: str, dry_run: bool, requested_count: int, dependencies: StorageDependencies | None = None) -> int:
    deps = _deps(dependencies, db_path)

    def _op() -> int:
        cur = conn.execute("INSERT INTO fetch_runs (started_at, symbols_file, db_path, interval, hours, limit_symbols, sleep_seconds, market_type, dry_run, status, requested_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (int(deps.now()), symbols_file, db_path, interval, hours, limit_symbols, sleep_seconds, market_type, 1 if dry_run else 0, "running", requested_count))
        return int(cur.lastrowid)

    return _with_retry(deps, lambda: _write_transaction(conn, op="create_fetch_run", func=_op), op="create_fetch_run")


def finalize_fetch_run(conn: sqlite3.Connection, run_id: int, *, status: str, succeeded_count: int, failed_count: int, warning_count: int, notes: str | None = None, dependencies: StorageDependencies | None = None) -> bool:
    """Finalize a fetch run using the standard storage write transaction policy."""
    deps = _deps(dependencies)

    def _op() -> bool:
        cur = conn.execute("UPDATE fetch_runs SET finished_at = ?, status = ?, succeeded_count = ?, failed_count = ?, warning_count = ?, notes = COALESCE(?, notes) WHERE id = ?", (int(deps.now()), status, succeeded_count, failed_count, warning_count, notes, run_id))
        if cur.rowcount == 0:
            raise StorageNotFoundError(f"finalize_fetch_run found no fetch_runs row for run_id={run_id}")
        if cur.rowcount != 1:
            raise StorageQueryError(f"finalize_fetch_run updated an unexpected number of rows for run_id={run_id}: {cur.rowcount}")
        return True

    return _with_retry(deps, lambda: _write_transaction(conn, op="finalize_fetch_run", func=_op), op="finalize_fetch_run")


def save_error(conn: sqlite3.Connection, *, run_id: int | None, symbol: str | None, exchange: str | None, market_type: str | None, interval: str | None, error_type: str, message: str, http_status: int | None = None, retry_after: float | None = None, raw_json: Any = None, dependencies: StorageDependencies | None = None) -> None:
    deps = _deps(dependencies)
    safe_message = sanitize_for_persistence(message)
    safe_raw_json = _sanitize_raw(raw_json)

    def _op() -> None:
        conn.execute("INSERT INTO fetch_errors (run_id, symbol, exchange, market_type, interval, error_type, message, http_status, retry_after, created_at, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (run_id, symbol, exchange, market_type, interval, error_type, safe_message, http_status, retry_after, int(deps.now()), safe_raw_json))

    _with_retry(deps, lambda: _write_transaction(conn, op="save_error", func=_op), op="save_error")


def _coerce_number(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        raise ValueError(f"invalid numeric value: {value!r}")
    return number


def record_from_candle(candle: Mapping[str, Any], *, symbol: str, exchange: str, market_type: str | None, interval: str, fetched_at: int | None = None) -> OHLCVRecord:
    timestamp = int(candle["t"])
    open_ = _coerce_number(candle.get("o", candle.get("open")))
    high = _coerce_number(candle.get("h", candle.get("high")))
    low = _coerce_number(candle.get("l", candle.get("low")))
    close = _coerce_number(candle.get("c", candle.get("close")))
    volume = _coerce_number(candle.get("v", candle.get("volume")))
    if volume is None:
        raise ValueError("volume is required")
    buy_volume = _coerce_number(candle.get("bv", candle.get("buy_volume")))
    if buy_volume is not None and buy_volume > volume:
        raise ValueError("buy_volume cannot exceed volume")
    sell_volume = volume - buy_volume if buy_volume is not None else None
    volume_delta = buy_volume - sell_volume if buy_volume is not None and sell_volume is not None else None
    return OHLCVRecord(timestamp=timestamp, symbol=symbol, exchange=_normalize_exchange(exchange), market_type=_normalize_market_type(market_type), interval=interval, open=open_, high=high, low=low, close=close, volume=volume, buy_volume=buy_volume, sell_volume=sell_volume, volume_delta=volume_delta, fetched_at=fetched_at, raw_json=sanitize_for_persistence(json.dumps(candle, ensure_ascii=False)))


def _upsert_records(conn: sqlite3.Connection, *, table_sql: str, rows: Sequence[tuple[Any, ...]], dependencies: StorageDependencies | None = None) -> int:
    deps = _deps(dependencies)
    if not rows:
        return 0

    def _op() -> int:
        conn.executemany(table_sql, rows)
        return len(rows)

    return _with_retry(deps, lambda: _write_transaction(conn, op="upsert_records", func=_op), op="upsert_records")


def _upsert_records_in_transaction(conn: sqlite3.Connection, *, table_sql: str, rows: Sequence[tuple[Any, ...]]) -> int:
    if not rows:
        return 0
    conn.executemany(table_sql, rows)
    return len(rows)


def upsert_ohlcv_records(conn: sqlite3.Connection, records: Sequence[OHLCVRecord], dependencies: StorageDependencies | None = None) -> int:
    rows = [(r.timestamp, _normalize_symbol(r.symbol), _normalize_exchange(r.exchange), _normalize_market_type(r.market_type), _normalize_interval(r.interval), r.open, r.high, r.low, r.close, r.volume, r.buy_volume, r.sell_volume, r.volume_delta, r.source, r.fetched_at, r.raw_json) for r in records]
    return _upsert_records(conn, table_sql="INSERT INTO ohlcv_history (timestamp, symbol, exchange, market_type, interval, open, high, low, close, volume, buy_volume, sell_volume, volume_delta, source, fetched_at, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(timestamp, symbol, exchange, market_type, interval) DO UPDATE SET open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close, volume=excluded.volume, buy_volume=excluded.buy_volume, sell_volume=excluded.sell_volume, volume_delta=excluded.volume_delta, source=excluded.source, fetched_at=excluded.fetched_at, raw_json=excluded.raw_json", rows=rows, dependencies=dependencies)


def upsert_ohlcv_records_in_transaction(conn: sqlite3.Connection, records: Sequence[OHLCVRecord]) -> int:
    rows = [(r.timestamp, _normalize_symbol(r.symbol), _normalize_exchange(r.exchange), _normalize_market_type(r.market_type), _normalize_interval(r.interval), r.open, r.high, r.low, r.close, r.volume, r.buy_volume, r.sell_volume, r.volume_delta, r.source, r.fetched_at, r.raw_json) for r in records]
    return _upsert_records_in_transaction(conn, table_sql="INSERT INTO ohlcv_history (timestamp, symbol, exchange, market_type, interval, open, high, low, close, volume, buy_volume, sell_volume, volume_delta, source, fetched_at, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(timestamp, symbol, exchange, market_type, interval) DO UPDATE SET open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close, volume=excluded.volume, buy_volume=excluded.buy_volume, sell_volume=excluded.sell_volume, volume_delta=excluded.volume_delta, source=excluded.source, fetched_at=excluded.fetched_at, raw_json=excluded.raw_json", rows=rows)


def upsert_cvd_records(conn: sqlite3.Connection, records: Sequence[CVDRecord], dependencies: StorageDependencies | None = None) -> int:
    rows = [(r.timestamp, _normalize_symbol(r.symbol), _normalize_exchange(r.exchange), _normalize_market_type(r.market_type), _normalize_interval(r.interval), r.buy_volume, r.sell_volume, r.volume_delta, r.cumulative_cvd, r.source, r.fetched_at, r.raw_json) for r in records]
    return _upsert_records(conn, table_sql="INSERT INTO cvd_history (timestamp, symbol, exchange, market_type, interval, buy_volume, sell_volume, volume_delta, cumulative_cvd, source, fetched_at, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(timestamp, symbol, exchange, market_type, interval) DO UPDATE SET buy_volume=excluded.buy_volume, sell_volume=excluded.sell_volume, volume_delta=excluded.volume_delta, cumulative_cvd=excluded.cumulative_cvd, source=excluded.source, fetched_at=excluded.fetched_at, raw_json=excluded.raw_json", rows=rows, dependencies=dependencies)


def upsert_cvd_records_in_transaction(conn: sqlite3.Connection, records: Sequence[CVDRecord]) -> int:
    rows = [(r.timestamp, _normalize_symbol(r.symbol), _normalize_exchange(r.exchange), _normalize_market_type(r.market_type), _normalize_interval(r.interval), r.buy_volume, r.sell_volume, r.volume_delta, r.cumulative_cvd, r.source, r.fetched_at, r.raw_json) for r in records]
    return _upsert_records_in_transaction(conn, table_sql="INSERT INTO cvd_history (timestamp, symbol, exchange, market_type, interval, buy_volume, sell_volume, volume_delta, cumulative_cvd, source, fetched_at, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(timestamp, symbol, exchange, market_type, interval) DO UPDATE SET buy_volume=excluded.buy_volume, sell_volume=excluded.sell_volume, volume_delta=excluded.volume_delta, cumulative_cvd=excluded.cumulative_cvd, source=excluded.source, fetched_at=excluded.fetched_at, raw_json=excluded.raw_json", rows=rows)


def upsert_open_interest_records(conn: sqlite3.Connection, records: Sequence[OpenInterestRecord], dependencies: StorageDependencies | None = None) -> int:
    rows = [(r.timestamp, _normalize_symbol(r.symbol), _normalize_exchange(r.exchange), _normalize_market_type(r.market_type), _normalize_interval(r.interval), r.open_interest, r.source, r.fetched_at, r.raw_json) for r in records]
    return _upsert_records(conn, table_sql="INSERT INTO open_interest_history (timestamp, symbol, exchange, market_type, interval, open_interest, source, fetched_at, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(timestamp, symbol, exchange, market_type, interval) DO UPDATE SET open_interest=excluded.open_interest, source=excluded.source, fetched_at=excluded.fetched_at, raw_json=excluded.raw_json", rows=rows, dependencies=dependencies)


def upsert_funding_rate_records(conn: sqlite3.Connection, records: Sequence[FundingRateRecord], dependencies: StorageDependencies | None = None) -> int:
    rows = [(r.timestamp, _normalize_symbol(r.symbol), _normalize_exchange(r.exchange), _normalize_market_type(r.market_type), _normalize_interval(r.interval), r.funding_rate, r.source, r.fetched_at, r.raw_json) for r in records]
    return _upsert_records(conn, table_sql="INSERT INTO funding_rate_history (timestamp, symbol, exchange, market_type, interval, funding_rate, source, fetched_at, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(timestamp, symbol, exchange, market_type, interval) DO UPDATE SET funding_rate=excluded.funding_rate, source=excluded.source, fetched_at=excluded.fetched_at, raw_json=excluded.raw_json", rows=rows, dependencies=dependencies)


def upsert_liquidation_records(conn: sqlite3.Connection, records: Sequence[LiquidationRecord], dependencies: StorageDependencies | None = None) -> int:
    rows = [(r.timestamp, _normalize_symbol(r.symbol), _normalize_exchange(r.exchange), _normalize_market_type(r.market_type), _normalize_interval(r.interval), r.long_liquidation, r.short_liquidation, r.source, r.fetched_at, r.raw_json) for r in records]
    return _upsert_records(conn, table_sql="INSERT INTO liquidation_history (timestamp, symbol, exchange, market_type, interval, long_liquidation, short_liquidation, source, fetched_at, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(timestamp, symbol, exchange, market_type, interval) DO UPDATE SET long_liquidation=excluded.long_liquidation, short_liquidation=excluded.short_liquidation, source=excluded.source, fetched_at=excluded.fetched_at, raw_json=excluded.raw_json", rows=rows, dependencies=dependencies)


def upsert_long_short_ratio_records(conn: sqlite3.Connection, records: Sequence[LongShortRatioRecord], dependencies: StorageDependencies | None = None) -> int:
    rows = [(r.timestamp, _normalize_symbol(r.symbol), _normalize_exchange(r.exchange), _normalize_market_type(r.market_type), _normalize_interval(r.interval), r.long_short_ratio, r.source, r.fetched_at, r.raw_json) for r in records]
    return _upsert_records(conn, table_sql="INSERT INTO long_short_ratio_history (timestamp, symbol, exchange, market_type, interval, long_short_ratio, source, fetched_at, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(timestamp, symbol, exchange, market_type, interval) DO UPDATE SET long_short_ratio=excluded.long_short_ratio, source=excluded.source, fetched_at=excluded.fetched_at, raw_json=excluded.raw_json", rows=rows, dependencies=dependencies)


def _fetch_state_key(symbol: str, exchange: str | None, market_type: str | None, interval: str):
    return _normalize_symbol(symbol), _normalize_exchange(exchange), _normalize_market_type(market_type), _normalize_interval(interval)


def get_last_fetched_timestamp(conn: sqlite3.Connection, symbol: str, exchange: str | None, market_type: str | None, interval: str, dependencies: StorageDependencies | None = None) -> int | None:
    row = conn.execute("SELECT last_timestamp FROM ohlcv_fetch_state WHERE symbol = ? AND exchange = ? AND market_type = ? AND interval = ?", _fetch_state_key(symbol, exchange, market_type, interval)).fetchone()
    return None if row is None or row[0] is None else int(row[0])


def upsert_fetch_state(conn: sqlite3.Connection, symbol: str, exchange: str | None, market_type: str | None, interval: str, last_timestamp: int, updated_at: int | None = None, dependencies: StorageDependencies | None = None) -> None:
    deps = _deps(dependencies)
    ts = int(updated_at if updated_at is not None else deps.now())

    def _op() -> None:
        conn.execute("INSERT INTO ohlcv_fetch_state (symbol, exchange, market_type, interval, last_timestamp, updated_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(symbol, exchange, market_type, interval) DO UPDATE SET last_timestamp=excluded.last_timestamp, updated_at=excluded.updated_at", (*_fetch_state_key(symbol, exchange, market_type, interval), int(last_timestamp), ts))

    _with_retry(deps, lambda: _write_transaction(conn, op="upsert_fetch_state", func=_op), op="upsert_fetch_state")


def upsert_fetch_state_in_transaction(conn: sqlite3.Connection, symbol: str, exchange: str | None, market_type: str | None, interval: str, last_timestamp: int, updated_at: int | None = None, dependencies: StorageDependencies | None = None) -> None:
    deps = _deps(dependencies)
    ts = int(updated_at if updated_at is not None else deps.now())
    _write_in_transaction(conn, func=lambda: conn.execute("INSERT INTO ohlcv_fetch_state (symbol, exchange, market_type, interval, last_timestamp, updated_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(symbol, exchange, market_type, interval) DO UPDATE SET last_timestamp=excluded.last_timestamp, updated_at=excluded.updated_at", (*_fetch_state_key(symbol, exchange, market_type, interval), int(last_timestamp), ts)))


def get_last_open_interest_fetched_timestamp(conn: sqlite3.Connection, symbol: str, exchange: str | None, market_type: str | None, interval: str, dependencies: StorageDependencies | None = None) -> int | None:
    row = conn.execute("SELECT last_timestamp FROM open_interest_fetch_state WHERE symbol = ? AND exchange = ? AND market_type = ? AND interval = ?", _fetch_state_key(symbol, exchange, market_type, interval)).fetchone()
    return None if row is None or row[0] is None else int(row[0])


def upsert_open_interest_fetch_state(conn: sqlite3.Connection, symbol: str, exchange: str | None, market_type: str | None, interval: str, last_timestamp: int, updated_at: int | None = None, dependencies: StorageDependencies | None = None) -> None:
    deps = _deps(dependencies)
    ts = int(updated_at if updated_at is not None else deps.now())

    def _op() -> None:
        conn.execute("INSERT INTO open_interest_fetch_state (symbol, exchange, market_type, interval, last_timestamp, updated_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(symbol, exchange, market_type, interval) DO UPDATE SET last_timestamp=excluded.last_timestamp, updated_at=excluded.updated_at", (*_fetch_state_key(symbol, exchange, market_type, interval), int(last_timestamp), ts))

    _with_retry(deps, lambda: _write_transaction(conn, op="upsert_open_interest_fetch_state", func=_op), op="upsert_open_interest_fetch_state")


def get_last_funding_rate_fetched_timestamp(conn: sqlite3.Connection, symbol: str, exchange: str | None, market_type: str | None, interval: str, dependencies: StorageDependencies | None = None) -> int | None:
    row = conn.execute("SELECT last_timestamp FROM funding_rate_fetch_state WHERE symbol = ? AND exchange = ? AND market_type = ? AND interval = ?", _fetch_state_key(symbol, exchange, market_type, interval)).fetchone()
    return None if row is None or row[0] is None else int(row[0])


def upsert_funding_rate_fetch_state(conn: sqlite3.Connection, symbol: str, exchange: str | None, market_type: str | None, interval: str, last_timestamp: int, updated_at: int | None = None, dependencies: StorageDependencies | None = None) -> None:
    deps = _deps(dependencies)
    ts = int(updated_at if updated_at is not None else deps.now())

    def _op() -> None:
        conn.execute("INSERT INTO funding_rate_fetch_state (symbol, exchange, market_type, interval, last_timestamp, updated_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(symbol, exchange, market_type, interval) DO UPDATE SET last_timestamp=excluded.last_timestamp, updated_at=excluded.updated_at", (*_fetch_state_key(symbol, exchange, market_type, interval), int(last_timestamp), ts))

    _with_retry(deps, lambda: _write_transaction(conn, op="upsert_funding_rate_fetch_state", func=_op), op="upsert_funding_rate_fetch_state")


def get_last_liquidation_fetched_timestamp(conn: sqlite3.Connection, symbol: str, exchange: str | None, market_type: str | None, interval: str, dependencies: StorageDependencies | None = None) -> int | None:
    row = conn.execute("SELECT last_timestamp FROM liquidation_fetch_state WHERE symbol = ? AND exchange = ? AND market_type = ? AND interval = ?", _fetch_state_key(symbol, exchange, market_type, interval)).fetchone()
    return None if row is None or row[0] is None else int(row[0])


def upsert_liquidation_fetch_state(conn: sqlite3.Connection, symbol: str, exchange: str | None, market_type: str | None, interval: str, last_timestamp: int, updated_at: int | None = None, dependencies: StorageDependencies | None = None) -> None:
    deps = _deps(dependencies)
    ts = int(updated_at if updated_at is not None else deps.now())

    def _op() -> None:
        conn.execute("INSERT INTO liquidation_fetch_state (symbol, exchange, market_type, interval, last_timestamp, updated_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(symbol, exchange, market_type, interval) DO UPDATE SET last_timestamp=excluded.last_timestamp, updated_at=excluded.updated_at", (*_fetch_state_key(symbol, exchange, market_type, interval), int(last_timestamp), ts))

    _with_retry(deps, lambda: _write_transaction(conn, op="upsert_liquidation_fetch_state", func=_op), op="upsert_liquidation_fetch_state")


def get_last_long_short_ratio_fetched_timestamp(conn: sqlite3.Connection, symbol: str, exchange: str | None, market_type: str | None, interval: str, dependencies: StorageDependencies | None = None) -> int | None:
    row = conn.execute("SELECT last_timestamp FROM long_short_ratio_fetch_state WHERE symbol = ? AND exchange = ? AND market_type = ? AND interval = ?", _fetch_state_key(symbol, exchange, market_type, interval)).fetchone()
    return None if row is None or row[0] is None else int(row[0])


def upsert_long_short_ratio_fetch_state(conn: sqlite3.Connection, symbol: str, exchange: str | None, market_type: str | None, interval: str, last_timestamp: int, updated_at: int | None = None, dependencies: StorageDependencies | None = None) -> None:
    deps = _deps(dependencies)
    ts = int(updated_at if updated_at is not None else deps.now())

    def _op() -> None:
        conn.execute("INSERT INTO long_short_ratio_fetch_state (symbol, exchange, market_type, interval, last_timestamp, updated_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(symbol, exchange, market_type, interval) DO UPDATE SET last_timestamp=excluded.last_timestamp, updated_at=excluded.updated_at", (*_fetch_state_key(symbol, exchange, market_type, interval), int(last_timestamp), ts))

    _with_retry(deps, lambda: _write_transaction(conn, op="upsert_long_short_ratio_fetch_state", func=_op), op="upsert_long_short_ratio_fetch_state")


def get_cvd_offset(conn: sqlite3.Connection, symbol: str, exchange: str | None, market_type: str | None, interval: str, before_timestamp: int, dependencies: StorageDependencies | None = None) -> float:
    row = conn.execute("SELECT cumulative_cvd FROM cvd_history WHERE symbol = ? AND exchange = ? AND market_type = ? AND interval = ? AND timestamp < ? ORDER BY timestamp DESC LIMIT 1", (*_fetch_state_key(symbol, exchange, market_type, interval), int(before_timestamp))).fetchone()
    return float(row[0]) if row is not None and row[0] is not None else 0.0
