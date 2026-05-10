from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_SYMBOLS_FILE = "/home/weed420/.hermes/data/coinalyze/coinalyze-btc-selected-20-symbol-market-map.json"
DEFAULT_DB = "/home/weed420/.hermes/data/coinalyze/cvd-monitor-ohlcv-test.sqlite3"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols-file", default=DEFAULT_SYMBOLS_FILE)
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--interval", default="5min")
    p.add_argument("--hours", type=int, default=1)
    p.add_argument("--limit", type=int, default=1)
    p.add_argument("--sleep-seconds", type=float, default=8.0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--market-type", default="all", choices=["spot", "future", "all"])
    p.add_argument("--max-retries", type=int, default=1)
    p.add_argument("--max-retry-after-seconds", type=float, default=120.0)
    p.add_argument("--min-retry-after-seconds", type=float, default=1.0)
    p.add_argument("--max-consecutive-failures", type=int, default=3)
    p.add_argument("--max-rate-limit-count", type=int, default=2)
    p.add_argument("--allow-partial-success", action="store_true")
    return p.parse_args()


def load_symbols(path: str, market_type: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if market_type != "all":
        data = [x for x in data if x.get("market_type") == market_type]
    return data
