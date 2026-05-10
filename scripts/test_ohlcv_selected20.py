from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cvd_monitor.client import fetch_ohlcv_history, load_api_key, sanitize_for_persistence
from cvd_monitor.storage import connect_db, create_fetch_run, finalize_fetch_run, init_db, record_from_candle, save_error, upsert_ohlcv_records

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


def main() -> int:
    args = parse_args()
    symbols = load_symbols(args.symbols_file, args.market_type)
    symbols = symbols[: args.limit]
    now = int(time.time())
    from_ts = now - args.hours * 3600
    print(f"db={args.db}")
    print(f"symbols_file={args.symbols_file}")
    print(f"interval={args.interval} window={from_ts}..{now}")
    print(f"selected_symbols={len(symbols)} limit={args.limit} market_type={args.market_type}")
    if args.dry_run:
        print("dry-run: no API call")
        return 0

    api_key = load_api_key()
    if not api_key:
        print("COINALYZE_API_KEY is missing", file=sys.stderr)
        return 2

    conn = connect_db(args.db)
    init_db(conn)
    run_id = create_fetch_run(conn, symbols_file=args.symbols_file, db_path=args.db, interval=args.interval, hours=args.hours, limit_symbols=args.limit, sleep_seconds=args.sleep_seconds, market_type=args.market_type, dry_run=False, requested_count=len(symbols))
    ok = failed = warnings = consecutive_failures = rate_limit_count = 0
    try:
        for idx, item in enumerate(symbols, 1):
            symbol = item.get("symbol")
            exchange = item.get("exchange_name") or item.get("exchange_code") or ""
            market_type = item.get("market_type")
            print(f"[{idx}/{len(symbols)}] fetch {symbol} @ {exchange}")
            result = fetch_ohlcv_history(symbol=symbol, interval=args.interval, from_ts=from_ts, to_ts=now, api_key=api_key, max_retries=args.max_retries, min_retry_after_seconds=args.min_retry_after_seconds, max_retry_after_seconds=args.max_retry_after_seconds)
            if not result.ok:
                failed += 1
                consecutive_failures += 1
                if result.status == 429:
                    rate_limit_count += 1
                safe_error_meta = {"error_type": "fetch_error", "http_status": result.status, "retry_after": result.retry_after}
                save_error(conn, run_id=run_id, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, error_type="fetch_error", message=sanitize_for_persistence(result.error or "fetch failed"), http_status=result.status, retry_after=result.retry_after, raw_json=safe_error_meta)
                if result.status == 429:
                    save_error(conn, run_id=run_id, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, error_type="rate_limited", message="rate limited", http_status=result.status, retry_after=result.retry_after, raw_json={**safe_error_meta, "error_type": "rate_limited"})
                    if result.retry_after:
                        time.sleep(min(result.retry_after, args.max_retry_after_seconds))
                if consecutive_failures >= args.max_consecutive_failures or rate_limit_count >= args.max_rate_limit_count:
                    break
                continue
            consecutive_failures = 0
            payload = result.data or []
            if not payload:
                warnings += 1
                consecutive_failures += 1
                save_error(conn, run_id=run_id, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, error_type="empty_response", message="response had no history entries", http_status=result.status, raw_json={"error_type": "empty_response", "http_status": result.status})
                if consecutive_failures >= args.max_consecutive_failures:
                    break
                continue
            candles = payload[0].get("history", []) if isinstance(payload, list) else []
            candles = sorted(candles, key=lambda x: x.get("t", 0))
            records = []
            for c in candles:
                try:
                    records.append(record_from_candle(c, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, fetched_at=int(time.time())))
                except ValueError as exc:
                    warnings += 1
                    save_error(conn, run_id=run_id, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, error_type="invalid_candle", message=str(exc), http_status=result.status, raw_json={"error_type": "invalid_candle", "symbol": symbol, "exchange": exchange, "interval": args.interval})
            if not records:
                warnings += 1
                save_error(conn, run_id=run_id, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, error_type="no_valid_records", message="no valid candles to store", http_status=result.status, raw_json=payload)
                continue
            saved = upsert_ohlcv_records(conn, records)
            if saved < 1:
                failed += 1
                consecutive_failures += 1
                save_error(conn, run_id=run_id, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, error_type="storage_error", message="no records were stored", http_status=result.status, raw_json=payload)
                if consecutive_failures >= args.max_consecutive_failures:
                    break
                continue
            ok += 1
            if args.sleep_seconds > 0 and idx < len(symbols):
                time.sleep(args.sleep_seconds)
        status = "success" if failed == 0 and warnings == 0 else ("partial_success" if ok > 0 else "failed")
        finalize_fetch_run(conn, run_id, status=status, succeeded_count=ok, failed_count=failed, warning_count=warnings)
        print(f"run_id={run_id} status={status} ok={ok} failed={failed} warnings={warnings}")
        return 0 if status == "success" or args.allow_partial_success else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
