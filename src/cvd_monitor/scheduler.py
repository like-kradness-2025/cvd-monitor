from __future__ import annotations

from .dashboard import build_dashboard, build_dashboard_data, render_dashboard
from .fetcher import run_fetch_job
from .config import parse_args


def collect_and_save_selected20(args) -> int:
    return run_fetch_job(args)


def generate_dashboard(db_path: str, *, symbol: str | None = None, interval: str | None = None, hours: int | None = None, limit: int | None = None):
    return build_dashboard_data(db_path, symbol=symbol, interval=interval, hours=hours, limit=limit)


def get_dashboard_data(db_path: str, *, symbol: str | None = None, interval: str | None = None, hours: int | None = None, limit: int | None = None):
    return build_dashboard_data(db_path, symbol=symbol, interval=interval, hours=hours, limit=limit)


def main() -> int:
    return collect_and_save_selected20(parse_args())
