from __future__ import annotations

import json
import sys
import time
from typing import Any

from .client import fetch_funding_rate_history, fetch_liquidation_history, fetch_long_short_ratio_history, fetch_ohlcv_history, fetch_open_interest_history, load_api_key, sanitize_for_persistence
from .config import load_symbols, parse_args
from .storage import (
    CVDRecord,
    FundingRateRecord,
    LiquidationRecord,
    LongShortRatioRecord,
    OpenInterestRecord,
    connect_db,
    create_fetch_run,
    finalize_fetch_run,
    get_cvd_offset,
    get_last_fetched_timestamp,
    get_last_funding_rate_fetched_timestamp,
    get_last_liquidation_fetched_timestamp,
    get_last_long_short_ratio_fetched_timestamp,
    get_last_open_interest_fetched_timestamp,
    init_db,
    record_from_candle,
    save_error,
    upsert_cvd_records,
    upsert_fetch_state,
    upsert_funding_rate_fetch_state,
    upsert_funding_rate_records,
    upsert_liquidation_fetch_state,
    upsert_liquidation_records,
    upsert_long_short_ratio_fetch_state,
    upsert_long_short_ratio_records,
    upsert_ohlcv_records,
    upsert_open_interest_fetch_state,
    upsert_open_interest_records,
)


_INTERVAL_SECONDS = {
    "1m": 60,
    "1min": 60,
    "5m": 300,
    "5min": 300,
    "15m": 900,
    "15min": 900,
    "30m": 1800,
    "30min": 1800,
    "1h": 3600,
    "1hour": 3600,
    "2h": 7200,
    "2hour": 7200,
    "4h": 14400,
    "4hour": 14400,
    "6h": 21600,
    "6hour": 21600,
    "12h": 43200,
    "12hour": 43200,
    "1d": 86400,
    "daily": 86400,
}


def _compute_fetch_from_ts(*, last_timestamp: int | None, default_from_ts: int, overlap_candles: int, interval_seconds: int, now: int) -> int:
    """Return the inclusive fetch start timestamp.

    Spec:
    - `last_timestamp` is the last successfully stored OHLCV candle timestamp.
    - `overlap_candles` is subtracted from `last_timestamp` so the next request re-fetches
      the boundary candles and tolerates API gaps / late arrivals.
    - If no previous state exists, `default_from_ts` (lookback window start) is used.
    - The returned timestamp is always clamped to `0 <= from_ts < now`.
    - Failed fetches do not advance fetch state; state is only updated after at least one
      valid record has been written.
    """
    overlap_seconds = max(0, overlap_candles * interval_seconds)
    candidate = (last_timestamp - overlap_seconds) if last_timestamp is not None else default_from_ts
    return max(0, min(candidate, now - 1))


def _interval_seconds(interval: str) -> int:
    try:
        return _INTERVAL_SECONDS[interval]
    except KeyError as exc:
        raise ValueError(f"unsupported interval: {interval}") from exc


def _validate_query_params(*, symbol: str | None, exchange: str | None, interval: str, from_ts: int, to_ts: int) -> None:
    if not symbol or not str(symbol).strip():
        raise ValueError("symbol is required")
    if exchange is None or not str(exchange).strip():
        raise ValueError("exchange is required")
    if from_ts < 0 or to_ts < 0:
        raise ValueError("timestamps must be non-negative")
    if from_ts >= to_ts:
        raise ValueError("from_ts must be earlier than to_ts")
    _interval_seconds(interval)


def _open_interest_value(row: dict[str, Any]) -> float | None:
    for key in ("oi", "open_interest", "openInterest", "value", "v"):
        if key in row and row[key] is not None:
            try:
                return float(row[key])
            except (TypeError, ValueError):
                raise ValueError(f"invalid open interest value: {row[key]!r}")
    raise ValueError("open interest is required")


def _funding_rate_value(row: dict[str, Any]) -> float | None:
    for key in ("funding_rate", "fundingRate", "fr", "value", "v"):
        if key in row and row[key] is not None:
            return float(row[key])
    return None


def _liquidation_values(row: dict[str, Any]) -> tuple[float | None, float | None]:
    long_value = None
    short_value = None
    for key in ("long_liquidation", "longLiquidation", "long", "buy", "long_volume"):
        if key in row and row[key] is not None:
            long_value = float(row[key])
            break
    for key in ("short_liquidation", "shortLiquidation", "short", "sell", "short_volume"):
        if key in row and row[key] is not None:
            short_value = float(row[key])
            break
    return long_value, short_value


def _long_short_ratio_value(row: dict[str, Any]) -> float | None:
    for key in ("long_short_ratio", "longShortRatio", "ratio", "value", "v"):
        if key in row and row[key] is not None:
            return float(row[key])
    return None


def _history_points(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list) and payload:
        history = payload[0].get("history", []) if isinstance(payload[0], dict) else []
        return sorted(history, key=lambda x: x.get("t", 0)) if isinstance(history, list) else []
    return []


def _fetch_metric_history(conn, *, fetch_fn, get_last_fn, upsert_records_fn, upsert_state_fn, record_builder, symbol: str, exchange: str, market_type: str | None, interval: str, from_ts: int, now: int, api_key: str, args, run_id: int, error_type: str, empty_error_type: str, invalid_error_type: str) -> int:
    """Fetch and persist metric history with the same overlap policy as OHLCV.

    Spec:
    - Metric fetches reuse the last successfully stored timestamp minus
      `args.overlap_candles * interval_seconds` so boundary points are
      re-requested on the next run.
    - If no prior metric state exists, the OHLCV fetch window start (`from_ts`)
      is used as the initial lookback boundary.
    - The computed start timestamp is clamped to the valid request range and
      never allowed to be negative.
    - Fetch state is only advanced after at least one valid record has been
      stored.
    - This keeps open interest, funding rate, liquidation, and long/short
      ratio retrieval aligned with OHLCV behavior without changing the
      storage architecture.
    """
    _validate_query_params(symbol=symbol, exchange=exchange, interval=interval, from_ts=from_ts, to_ts=now)
    last_timestamp = get_last_fn(conn, symbol, exchange, market_type, interval)
    metric_from_ts = _compute_fetch_from_ts(last_timestamp=last_timestamp, default_from_ts=from_ts, overlap_candles=args.overlap_candles, interval_seconds=_interval_seconds(interval), now=now)
    result = fetch_fn(symbol=symbol, interval=interval, from_ts=metric_from_ts, to_ts=now, api_key=api_key, max_retries=args.max_retries, min_retry_after_seconds=args.min_retry_after_seconds, max_retry_after_seconds=args.max_retry_after_seconds)
    warnings = 0
    if not result.ok:
        warnings += 1
        save_error(conn, run_id=run_id, symbol=symbol, exchange=exchange, market_type=market_type, interval=interval, error_type=error_type, message=sanitize_for_persistence(result.error or f"{error_type} failed"), http_status=result.status, retry_after=result.retry_after, raw_json={"error_type": error_type, "http_status": result.status, "retry_after": result.retry_after})
        return warnings
    points = _history_points(result.data)
    records = []
    fetched_at = int(time.time())
    for point in points:
        try:
            records.append(record_builder(point, symbol=symbol, exchange=exchange, market_type=market_type, interval=interval, fetched_at=fetched_at))
        except ValueError as exc:
            warnings += 1
            save_error(conn, run_id=run_id, symbol=symbol, exchange=exchange, market_type=market_type, interval=interval, error_type=invalid_error_type, message=str(exc), http_status=result.status, raw_json={"error_type": invalid_error_type})
    if records:
        upsert_records_fn(conn, records)
        upsert_state_fn(conn, symbol, exchange, market_type, interval, max(r.timestamp for r in records), fetched_at)
    else:
        warnings += 1
        save_error(conn, run_id=run_id, symbol=symbol, exchange=exchange, market_type=market_type, interval=interval, error_type=empty_error_type, message="response had no history entries", http_status=result.status, raw_json={"error_type": empty_error_type})
    return warnings


def _open_interest_record_from_point(point: dict[str, Any], *, symbol: str, exchange: str, market_type: str | None, interval: str, fetched_at: int) -> OpenInterestRecord:
    return OpenInterestRecord(
        timestamp=int(point["t"]),
        symbol=symbol,
        exchange=exchange,
        market_type=market_type,
        interval=interval,
        open_interest=_open_interest_value(point),
        fetched_at=fetched_at,
        raw_json=sanitize_for_persistence(json.dumps(point, ensure_ascii=False)),
    )


def _fetch_open_interest_history(conn, *, symbol: str, exchange: str, market_type: str | None, interval: str, from_ts: int, now: int, api_key: str, args, run_id: int) -> int:
    return _fetch_metric_history(
        conn,
        fetch_fn=fetch_open_interest_history,
        get_last_fn=get_last_open_interest_fetched_timestamp,
        upsert_records_fn=upsert_open_interest_records,
        upsert_state_fn=upsert_open_interest_fetch_state,
        record_builder=_open_interest_record_from_point,
        symbol=symbol,
        exchange=exchange,
        market_type=market_type,
        interval=interval,
        from_ts=from_ts,
        now=now,
        api_key=api_key,
        args=args,
        run_id=run_id,
        error_type="open_interest_fetch_error",
        empty_error_type="empty_open_interest_response",
        invalid_error_type="invalid_open_interest_point",
    )


def _funding_rate_record_from_point(point: dict[str, Any], *, symbol: str, exchange: str, market_type: str | None, interval: str, fetched_at: int):
    return FundingRateRecord(
        timestamp=int(point["t"]),
        symbol=symbol,
        exchange=exchange,
        market_type=market_type,
        interval=interval,
        funding_rate=_funding_rate_value(point),
        fetched_at=fetched_at,
        raw_json=sanitize_for_persistence(json.dumps(point, ensure_ascii=False)),
    )


def _liquidation_record_from_point(point: dict[str, Any], *, symbol: str, exchange: str, market_type: str | None, interval: str, fetched_at: int):
    long_liquidation, short_liquidation = _liquidation_values(point)
    return LiquidationRecord(
        timestamp=int(point["t"]),
        symbol=symbol,
        exchange=exchange,
        market_type=market_type,
        interval=interval,
        long_liquidation=long_liquidation,
        short_liquidation=short_liquidation,
        fetched_at=fetched_at,
        raw_json=sanitize_for_persistence(json.dumps(point, ensure_ascii=False)),
    )


def _long_short_ratio_record_from_point(point: dict[str, Any], *, symbol: str, exchange: str, market_type: str | None, interval: str, fetched_at: int):
    return LongShortRatioRecord(
        timestamp=int(point["t"]),
        symbol=symbol,
        exchange=exchange,
        market_type=market_type,
        interval=interval,
        long_short_ratio=_long_short_ratio_value(point),
        fetched_at=fetched_at,
        raw_json=sanitize_for_persistence(json.dumps(point, ensure_ascii=False)),
    )


def _symbol_exchange(item: dict[str, Any]) -> str:
    exchange = item.get("exchange") or item.get("exchange_name") or item.get("exchange_code") or ""
    return str(exchange).strip()


def _process_fetch_symbol(conn, *, idx: int, total: int, item: dict[str, Any], args, now: int, interval_seconds: int, api_key: str, run_id: int, ok: int, failed: int, warnings: int, consecutive_failures: int, rate_limit_count: int):
    symbol = item.get("symbol")
    exchange = _symbol_exchange(item)
    market_type = item.get("market_type")
    _validate_query_params(symbol=symbol, exchange=exchange, interval=args.interval, from_ts=0, to_ts=1)
    last_timestamp = get_last_fetched_timestamp(conn, symbol, exchange, market_type, args.interval)
    from_ts = _compute_fetch_from_ts(last_timestamp=last_timestamp, default_from_ts=now - args.hours * 3600, overlap_candles=args.overlap_candles, interval_seconds=interval_seconds, now=now)
    if from_ts >= now:
        warnings += 1
        save_error(conn, run_id=run_id, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, error_type="skipped_window", message="from_ts is not earlier than to_ts", http_status=None, raw_json={"error_type": "skipped_window", "from_ts": from_ts, "to_ts": now})
        return ok, failed, warnings, consecutive_failures, rate_limit_count, False

    print(f"[{idx}/{total}] fetch {symbol} @ {exchange} from={from_ts} to={now}")
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
            return ok, failed, warnings, consecutive_failures, rate_limit_count, True
        warnings += _fetch_open_interest_history(conn, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, from_ts=from_ts, now=now, api_key=api_key, args=args, run_id=run_id)
        warnings += _fetch_metric_history(conn, fetch_fn=fetch_funding_rate_history, get_last_fn=get_last_funding_rate_fetched_timestamp, upsert_records_fn=upsert_funding_rate_records, upsert_state_fn=upsert_funding_rate_fetch_state, record_builder=_funding_rate_record_from_point, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, from_ts=from_ts, now=now, api_key=api_key, args=args, run_id=run_id, error_type="funding_rate_fetch_error", empty_error_type="empty_funding_rate_response", invalid_error_type="invalid_funding_rate_point")
        warnings += _fetch_metric_history(conn, fetch_fn=fetch_liquidation_history, get_last_fn=get_last_liquidation_fetched_timestamp, upsert_records_fn=upsert_liquidation_records, upsert_state_fn=upsert_liquidation_fetch_state, record_builder=_liquidation_record_from_point, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, from_ts=from_ts, now=now, api_key=api_key, args=args, run_id=run_id, error_type="liquidation_fetch_error", empty_error_type="empty_liquidation_response", invalid_error_type="invalid_liquidation_point")
        warnings += _fetch_metric_history(conn, fetch_fn=fetch_long_short_ratio_history, get_last_fn=get_last_long_short_ratio_fetched_timestamp, upsert_records_fn=upsert_long_short_ratio_records, upsert_state_fn=upsert_long_short_ratio_fetch_state, record_builder=_long_short_ratio_record_from_point, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, from_ts=from_ts, now=now, api_key=api_key, args=args, run_id=run_id, error_type="long_short_ratio_fetch_error", empty_error_type="empty_long_short_ratio_response", invalid_error_type="invalid_long_short_ratio_point")
        return ok, failed, warnings, consecutive_failures, rate_limit_count, False

    consecutive_failures = 0
    payload = result.data or []
    warnings += _fetch_open_interest_history(conn, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, from_ts=from_ts, now=now, api_key=api_key, args=args, run_id=run_id)
    warnings += _fetch_metric_history(conn, fetch_fn=fetch_funding_rate_history, get_last_fn=get_last_funding_rate_fetched_timestamp, upsert_records_fn=upsert_funding_rate_records, upsert_state_fn=upsert_funding_rate_fetch_state, record_builder=_funding_rate_record_from_point, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, from_ts=from_ts, now=now, api_key=api_key, args=args, run_id=run_id, error_type="funding_rate_fetch_error", empty_error_type="empty_funding_rate_response", invalid_error_type="invalid_funding_rate_point")
    warnings += _fetch_metric_history(conn, fetch_fn=fetch_liquidation_history, get_last_fn=get_last_liquidation_fetched_timestamp, upsert_records_fn=upsert_liquidation_records, upsert_state_fn=upsert_liquidation_fetch_state, record_builder=_liquidation_record_from_point, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, from_ts=from_ts, now=now, api_key=api_key, args=args, run_id=run_id, error_type="liquidation_fetch_error", empty_error_type="empty_liquidation_response", invalid_error_type="invalid_liquidation_point")
    warnings += _fetch_metric_history(conn, fetch_fn=fetch_long_short_ratio_history, get_last_fn=get_last_long_short_ratio_fetched_timestamp, upsert_records_fn=upsert_long_short_ratio_records, upsert_state_fn=upsert_long_short_ratio_fetch_state, record_builder=_long_short_ratio_record_from_point, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, from_ts=from_ts, now=now, api_key=api_key, args=args, run_id=run_id, error_type="long_short_ratio_fetch_error", empty_error_type="empty_long_short_ratio_response", invalid_error_type="invalid_long_short_ratio_point")
    candles = payload[0].get("history", []) if isinstance(payload, list) and payload and isinstance(payload[0], dict) else []
    candles = sorted(candles, key=lambda x: x.get("t", 0))
    records = []
    cvd_records = []
    cumulative_cvd = get_cvd_offset(conn, symbol, exchange, market_type, args.interval, from_ts)
    fetched_at = int(time.time())
    for c in candles:
        try:
            rec = record_from_candle(c, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, fetched_at=fetched_at)
            records.append(rec)
            if rec.volume_delta is not None:
                cumulative_cvd += rec.volume_delta
            cvd_records.append(CVDRecord(timestamp=rec.timestamp, symbol=rec.symbol, exchange=rec.exchange, market_type=rec.market_type, interval=rec.interval, buy_volume=rec.buy_volume, sell_volume=rec.sell_volume, volume_delta=rec.volume_delta, cumulative_cvd=cumulative_cvd, fetched_at=fetched_at, raw_json=rec.raw_json))
        except ValueError as exc:
            warnings += 1
            save_error(conn, run_id=run_id, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, error_type="invalid_candle", message=str(exc), http_status=result.status, raw_json={"error_type": "invalid_candle", "symbol": symbol, "exchange": exchange, "interval": args.interval})
    if not records:
        warnings += 1
        save_error(conn, run_id=run_id, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, error_type="no_valid_records", message="no valid candles to store", http_status=result.status, raw_json=payload)
        return ok, failed, warnings, consecutive_failures, rate_limit_count, False
    saved = upsert_ohlcv_records(conn, records)
    upsert_cvd_records(conn, cvd_records)
    if saved < 1:
        failed += 1
        consecutive_failures += 1
        save_error(conn, run_id=run_id, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, error_type="storage_error", message="no records were stored", http_status=result.status, raw_json=payload)
        if consecutive_failures >= args.max_consecutive_failures:
            return ok, failed, warnings, consecutive_failures, rate_limit_count, True
        return ok, failed, warnings, consecutive_failures, rate_limit_count, False
    ok += 1
    upsert_fetch_state(conn, symbol, exchange, market_type, args.interval, max(r.timestamp for r in records), fetched_at)
    return ok, failed, warnings, consecutive_failures, rate_limit_count, False


def run_fetch_job(args) -> int:
    try:
        interval_seconds = _interval_seconds(args.interval)
        symbols = load_symbols(args.symbols_file, args.market_type)[: args.limit]
    except ValueError as exc:
        print(f"invalid fetch job arguments: {exc}", file=sys.stderr)
        return 2
    now = int(time.time())
    print(f"db={args.db}")
    print(f"symbols_file={args.symbols_file}")
    print(f"interval={args.interval} now={now}")
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
            ok, failed, warnings, consecutive_failures, rate_limit_count, should_break = _process_fetch_symbol(conn, idx=idx, total=len(symbols), item=item, args=args, now=now, interval_seconds=interval_seconds, api_key=api_key, run_id=run_id, ok=ok, failed=failed, warnings=warnings, consecutive_failures=consecutive_failures, rate_limit_count=rate_limit_count)
            if should_break:
                break
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
