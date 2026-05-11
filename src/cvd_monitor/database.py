"""SQLite storage layer."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

DEFAULT_DATABASE_PATH = "data/cvd_monitor.sqlite3"


@dataclass(slots=True, frozen=True)
class CVDRecord:
    symbol: str
    timeframe: str
    timestamp: int
    price: float
    spot_cvd: float
    futures_cvd: float


class Database:
    def __init__(self, path: str = DEFAULT_DATABASE_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cvd_data (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    price REAL NOT NULL,
                    spot_cvd REAL NOT NULL,
                    futures_cvd REAL NOT NULL,
                    payload TEXT,
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                    UNIQUE(symbol, timeframe, timestamp)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cvd_data_symbol_timeframe_timestamp
                ON cvd_data(symbol, timeframe, timestamp)
                """
            )
            conn.commit()

    def save_cvd_data(self, record: CVDRecord, payload: dict[str, Any] | None = None) -> bool:
        """Insert a single record.

        Returns True when a row was inserted, False when it was skipped by the
        unique constraint.
        """

        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO cvd_data
                (symbol, timeframe, timestamp, price, spot_cvd, futures_cvd, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                _record_to_row(record, payload),
            )
            conn.commit()
            return cursor.rowcount > 0

    def save_many(self, records: Iterable[tuple[CVDRecord, dict[str, Any] | None]]) -> int:
        """Insert multiple records and return the number of inserted rows."""

        rows = [_record_to_row(record, payload) for record, payload in records]
        if not rows:
            return 0

        with self.connect() as conn:
            cursor = conn.executemany(
                """
                INSERT OR IGNORE INTO cvd_data
                (symbol, timeframe, timestamp, price, spot_cvd, futures_cvd, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
            return cursor.rowcount

    def query_cvd_data(self, symbol: str, timeframe: str, limit: int = 500) -> list[CVDRecord]:
        safe_limit = max(1, int(limit))
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT symbol, timeframe, timestamp, price, spot_cvd, futures_cvd
                FROM cvd_data
                WHERE symbol = ? AND timeframe = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (symbol, timeframe, safe_limit),
            ).fetchall()
        return [_row_to_record(row) for row in reversed(rows)]


def _record_to_row(record: CVDRecord, payload: dict[str, Any] | None) -> tuple[Any, ...]:
    return (
        record.symbol,
        record.timeframe,
        int(record.timestamp),
        float(record.price),
        float(record.spot_cvd),
        float(record.futures_cvd),
        json.dumps(payload, ensure_ascii=False, sort_keys=True) if payload is not None else None,
    )


def _row_to_record(row: sqlite3.Row) -> CVDRecord:
    return CVDRecord(
        symbol=row["symbol"],
        timeframe=row["timeframe"],
        timestamp=int(row["timestamp"]),
        price=float(row["price"]),
        spot_cvd=float(row["spot_cvd"]),
        futures_cvd=float(row["futures_cvd"]),
    )
