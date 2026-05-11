from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator

from .schemas import SCHEMA_SQL, SCHEMA_VERSION


@dataclass(frozen=True)
class DBDependencies:
    db_path: str | None = None
    connection_factory: type[sqlite3.Connection] = sqlite3.Connection


def connect_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)


def init_db(conn: sqlite3.Connection) -> None:
    init_schema(conn)
    conn.execute(
        "INSERT INTO schema_version (id, version, applied_at) VALUES (1, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET version = excluded.version, applied_at = excluded.applied_at",
        (SCHEMA_VERSION, int(time.time())),
    )
    conn.commit()


def get_schema_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return 0
        raise
    return 0 if row is None else int(row[0])


def _migration_1_to_2(conn: sqlite3.Connection) -> None:
    for table in (
        "ohlcv_history",
        "cvd_history",
        "open_interest_history",
        "funding_rate_history",
        "liquidation_history",
        "long_short_ratio_history",
        "ohlcv_fetch_state",
        "open_interest_fetch_state",
        "funding_rate_fetch_state",
        "liquidation_fetch_state",
        "long_short_ratio_fetch_state",
    ):
        conn.execute(f"UPDATE {table} SET exchange = lower(trim(exchange)) WHERE exchange IS NOT NULL")


MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {1: _migration_1_to_2}


def migrate(conn: sqlite3.Connection, target_version: int = SCHEMA_VERSION) -> int:
    current = get_schema_version(conn)
    if current == 0:
        init_db(conn)
        current = get_schema_version(conn)
    if current > target_version:
        raise ValueError(f"database schema version {current} is newer than target {target_version}")
    while current < target_version:
        migration = MIGRATIONS.get(current)
        if migration is None:
            raise ValueError(f"no migration available from version {current} to {current + 1}")
        with transaction(conn):
            migration(conn)
            conn.execute(
                "UPDATE schema_version SET version = ?, applied_at = ? WHERE id = 1",
                (current + 1, int(time.time())),
            )
        current = get_schema_version(conn)
    return current
