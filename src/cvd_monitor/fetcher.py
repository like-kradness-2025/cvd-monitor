from __future__ import annotations

import json
import sys
import time
from typing import Any

from .client import fetch_ohlcv_history, load_api_key, sanitize_for_persistence
from .config import load_symbols, parse_args
from .storage import (
    connect_db,
    create_fetch_run,
    finalize_fetch_run,
    init_db,
    record_from_candle,
    save_error,
    upsert_ohlcv_records,
)


def run_fetch_job(args) -> int:
    symbols = load_symbols(args.symbols_file, args.market_type)[: args.limit]
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
    run_id = create_fetch_run(
        conn,
        symbols_file=args.symbols_file,
        db_path=args.db,
        interval=args.interval,
        hours=args.hours,
        limit_symbols=args.limit,
        sleep_seconds=args.sleep_seconds,
        market_type=args.market_type,
        dry_run=False,
        requested_count=len(symbols),
    )
    ok = failed = warnings = consecutive_failures = rate_limit_count = 0
    try:
        for idx, item in enumerate(symbols, 1):
            symbol = item.get("symbol")
            exchange = item.get("exchange_name") or item.get("exchange_code") or ""
            market_type = item.get("market_type")
            print(f"[{idx}/{len(symbols)}] fetch {symbol} @ {exchange}")
            result = fetch_ohlcv_history(
                symbol=symbol,
                interval=args.interval,
                from_ts=from_ts,
                to_ts=now,
                api_key=api_key,
                max_retries=args.max_retries,
                min_retry_after_seconds=args.min_retry_after_seconds,
                max_retry_after_seconds=args.max_retry_after_seconds,
            )
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


def main() -> int:
    return run_fetch_job(parse_args())
