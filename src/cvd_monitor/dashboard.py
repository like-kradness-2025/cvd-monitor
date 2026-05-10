from __future__ import annotations

from pathlib import Path
from typing import Any

from .database import fetch_ohlcv_history_from_db
from .storage import connect_db, init_db


def build_dashboard_data(db_path: str, *, symbol: str | None = None, interval: str | None = None) -> dict[str, Any]:
    rows = fetch_ohlcv_history_from_db(db_path, symbol=symbol, interval=interval)
    if not rows:
        return {
            "status": "empty",
            "message": "表示できるデータがありません",
            "rows": [],
            "symbols": [],
        }
    symbols = sorted({row["symbol"] for row in rows if row.get("symbol")})
    return {
        "status": "ok",
        "message": f"{len(rows)} 件のデータを取得しました",
        "rows": rows,
        "symbols": symbols,
    }


def render_dashboard(db_path: str, output_path: str | None = None, *, symbol: str | None = None, interval: str | None = None) -> dict[str, Any]:
    data = build_dashboard_data(db_path, symbol=symbol, interval=interval)
    if output_path:
        Path(output_path).write_text(data["message"], encoding="utf-8")
    return data
