"""SQLite storage layer."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CVDRecord:
    symbol: str
    timeframe: str
    timestamp: int
    price: float
    spot_cvd: float
    futures_cvd: float


class Database:
    def __init__(self, path: str = "data/cvd_monitor.sqlite3") -> None:
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
                    UNIQUE(symbol, timeframe, timestamp)
                )
                """
            )
            conn.commit()

    def save_cvd_data(self, record: CVDRecord, payload: dict[str, Any] | None = None) -> None:
        try:
            with self.connect() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO cvd_data
                    (symbol, timeframe, timestamp, price, spot_cvd, futures_cvd, payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.symbol,
                        record.timeframe,
                        record.timestamp,
                        record.price,
                        record.spot_cvd,
                        record.futures_cvd,
                        json.dumps(payload) if payload is not None else None,
                    ),
                )
                conn.commit()
        except sqlite3.DatabaseError as exc:
            raise RuntimeError(f"Failed to save CVD data: {exc}") from exc

    def query_cvd_data(self, symbol: str, timeframe: str, limit: int = 500) -> list[CVDRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT symbol, timeframe, timestamp, price, spot_cvd, futures_cvd
                FROM cvd_data
                WHERE symbol = ? AND timeframe = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (symbol, timeframe, limit),
            ).fetchall()
        return [
            CVDRecord(
                symbol=row["symbol"],
                timeframe=row["timeframe"],
                timestamp=row["timestamp"],
                price=row["price"],
                spot_cvd=row["spot_cvd"],
                futures_cvd=row["futures_cvd"],
            )
            for row in reversed(rows)
        ]
