from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sqlite3
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from .storage import connect_db, init_db

_DASHBOARD_COLUMNS = {
    "ohlcv_history": "timestamp, symbol, exchange, interval, close",
    "cvd_history": "timestamp, symbol, exchange, interval, volume_delta, cumulative_cvd",
}


def _load_rows(
    db_path: str,
    table: str,
    *,
    symbol: str | None = None,
    interval: str | None = None,
    hours: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    conn = connect_db(db_path)
    try:
        init_db(conn)
        sql = [f"SELECT {_DASHBOARD_COLUMNS[table]} FROM {table}"]
        params: list[Any] = []
        where: list[str] = []
        if symbol:
            where.append("symbol = ?")
            params.append(symbol)
        if interval:
            where.append("interval = ?")
            params.append(interval)
        if hours is not None and hours > 0:
            where.append("timestamp >= ?")
            params.append(int(time.time()) - hours * 3600)
        if where:
            sql.append("WHERE " + " AND ".join(where))
        sql.append("ORDER BY timestamp ASC, symbol ASC, exchange ASC")
        if limit is not None and limit > 0:
            sql.append("LIMIT ?")
            params.append(limit)
        cur = conn.execute(" ".join(sql), params)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()



def build_dashboard_data(
    db_path: str,
    *,
    symbol: str | None = None,
    interval: str | None = None,
    hours: int | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    ohlcv_rows = _load_rows(db_path, "ohlcv_history", symbol=symbol, interval=interval, hours=hours, limit=limit)
    cvd_rows = _load_rows(db_path, "cvd_history", symbol=symbol, interval=interval, hours=hours, limit=limit)
    if not ohlcv_rows and not cvd_rows:
        return {"status": "empty", "message": "表示できるデータがありません", "rows": [], "symbols": []}
    symbols = sorted({row["symbol"] for row in ohlcv_rows + cvd_rows if row.get("symbol")})
    series: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: {"price": [], "cvd": []})
    for row in ohlcv_rows:
        series[row["symbol"]]["price"].append(row)
    for row in cvd_rows:
        series[row["symbol"]]["cvd"].append(row)
    return {"status": "ok", "message": f"{len(ohlcv_rows) + len(cvd_rows)} 件のデータを取得しました", "rows": ohlcv_rows, "cvd_rows": cvd_rows, "symbols": symbols, "series": series}


def _ts_to_dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def build_dashboard(db_path: str, output_path: str, *, symbol: str | None = None, interval: str | None = None, hours: int | None = None, limit: int | None = None) -> str:
    data = build_dashboard_data(db_path, symbol=symbol, interval=interval, hours=hours, limit=limit)
    if data["status"] != "ok":
        raise ValueError(data["message"])

    rows = data["rows"]
    cvd_rows = data["cvd_rows"]
    by_symbol_price: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_symbol_cvd: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_symbol_price[row["symbol"]].append(row)
    for row in cvd_rows:
        by_symbol_cvd[row["symbol"]].append(row)
    fig, axes = plt.subplots(3, 1, figsize=(16, 12), sharex=True)
    for sym, sym_rows in sorted(by_symbol_price.items()):
        xs = [_ts_to_dt(int(r["timestamp"])) for r in sym_rows]
        axes[0].plot(xs, [r.get("close") for r in sym_rows], label=sym)
    axes[0].set_title("Price")
    axes[0].legend(loc="upper left")
    for sym, sym_rows in sorted(by_symbol_cvd.items()):
        xs = [_ts_to_dt(int(r["timestamp"])) for r in sym_rows]
        axes[1].plot(xs, [r.get("cumulative_cvd") for r in sym_rows], label=f"{sym} Spot/Futures CVD")
    axes[1].set_title("CVD")
    axes[1].legend(loc="upper left")
    for sym, sym_rows in sorted(by_symbol_cvd.items()):
        xs = [_ts_to_dt(int(r["timestamp"])) for r in sym_rows]
        delta = [r.get("volume_delta") for r in sym_rows]
        axes[2].plot(xs, delta, label=f"{sym} Delta")
    axes[2].set_title("Per-candle Delta")
    axes[2].legend(loc="upper left")
    locator = mdates.AutoDateLocator()
    formatter = mdates.ConciseDateFormatter(locator)
    axes[2].xaxis.set_major_locator(locator)
    axes[2].xaxis.set_major_formatter(formatter)
    for ax in axes:
        ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def render_dashboard(db_path: str, output_path: str | None = None, *, symbol: str | None = None, interval: str | None = None) -> dict[str, Any]:
    if output_path is None:
        output_path = "artifacts/test_dashboard.png"
    path = build_dashboard(db_path, output_path, symbol=symbol, interval=interval)
    return {"status": "ok", "message": f"dashboard saved to {path}", "output_path": path}
