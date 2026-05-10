from __future__ import annotations

import sqlite3
from typing import Any

from .storage import connect_db, init_db


def fetch_ohlcv_history(
    conn: sqlite3.Connection,
    *,
    symbol: str | None = None,
    interval: str | None = None,
) -> list[dict[str, Any]]:
    """DB から OHLCV 履歴を取得する。

    symbol 未指定なら全 symbol を返す。
    """
    sql = [
        "SELECT timestamp, symbol, exchange, market_type, interval, open, high, low, close, volume, buy_volume, sell_volume, volume_delta, source, fetched_at, raw_json",
        "FROM ohlcv_history",
    ]
    params: list[Any] = []
    where: list[str] = []
    if symbol:
        where.append("symbol = ?")
        params.append(symbol)
    if interval:
        where.append("interval = ?")
        params.append(interval)
    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY timestamp ASC, symbol ASC, exchange ASC")
    cur = conn.execute(" ".join(sql), params)
    return [dict(row) for row in cur.fetchall()]


def fetch_ohlcv_history_from_db(
    db_path: str,
    *,
    symbol: str | None = None,
    interval: str | None = None,
) -> list[dict[str, Any]]:
    conn = connect_db(db_path)
    try:
        init_db(conn)
        return fetch_ohlcv_history(conn, symbol=symbol, interval=interval)
    finally:
        conn.close()
