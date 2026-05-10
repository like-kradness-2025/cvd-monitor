from __future__ import annotations

from .dashboard import build_dashboard_data, render_dashboard
from .database import fetch_ohlcv_history_from_db


def generate_dashboard(db_path: str, *, symbol: str | None = None, interval: str | None = None):
    # symbol 未指定時は全 symbol を対象にする
    return build_dashboard_data(db_path, symbol=symbol, interval=interval)


def get_dashboard_data(db_path: str):
    return fetch_ohlcv_history_from_db(db_path)
