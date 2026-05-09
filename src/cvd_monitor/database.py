"""SQLite storage layer (skeleton)."""

import sqlite3
from pathlib import Path


class Database:
    def __init__(self, path: str = 'data/cvd_monitor.sqlite3'):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS market_data (id INTEGER PRIMARY KEY, symbol TEXT, payload TEXT)")
