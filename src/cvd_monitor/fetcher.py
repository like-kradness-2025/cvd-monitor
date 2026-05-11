from __future__ import annotations

import sys
import time as _time
from dataclasses import dataclass, field, make_dataclass
from typing import Any, Callable, NamedTuple


class DependencySpec(NamedTuple):
    group: str
    field_name: str
    default_factory: Callable[[], Any]


UNSET = object()


DEPENDENCY_REGISTRY: dict[str, tuple[DependencySpec, ...]] = {
    "runtime": (
        DependencySpec("runtime", "clock", lambda: _time.time),
        DependencySpec("runtime", "sleeper", lambda: _time.sleep),
        DependencySpec("runtime", "logger", lambda: print),
    ),
    "storage": (
        DependencySpec("storage", "db_connect", lambda: connect_db),
        DependencySpec("storage", "init_db", lambda: init_db),
        DependencySpec("storage", "create_fetch_run", lambda: create_fetch_run),
        DependencySpec("storage", "finalize_fetch_run", lambda: finalize_fetch_run),
        DependencySpec("storage", "save_error", lambda: save_error),
        DependencySpec("storage", "load_symbols", lambda: load_symbols),
        DependencySpec("storage", "get_last_fetched_timestamp", lambda: get_last_fetched_timestamp),
        DependencySpec("storage", "get_last_open_interest_fetched_timestamp", lambda: get_last_open_interest_fetched_timestamp),
        DependencySpec("storage", "get_last_funding_rate_fetched_timestamp", lambda: get_last_funding_rate_fetched_timestamp),
        DependencySpec("storage", "get_last_liquidation_fetched_timestamp", lambda: get_last_liquidation_fetched_timestamp),
        DependencySpec("storage", "get_last_long_short_ratio_fetched_timestamp", lambda: get_last_long_short_ratio_fetched_timestamp),
        DependencySpec("storage", "get_cvd_offset", lambda: get_cvd_offset),
        DependencySpec("storage", "upsert_ohlcv_records", lambda: upsert_ohlcv_records),
        DependencySpec("storage", "upsert_cvd_records", lambda: upsert_cvd_records),
        DependencySpec("storage", "upsert_open_interest_records", lambda: upsert_open_interest_records),
        DependencySpec("storage", "upsert_funding_rate_records", lambda: upsert_funding_rate_records),
        DependencySpec("storage", "upsert_liquidation_records", lambda: upsert_liquidation_records),
        DependencySpec("storage", "upsert_long_short_ratio_records", lambda: upsert_long_short_ratio_records),
        DependencySpec("storage", "upsert_fetch_state", lambda: upsert_fetch_state),
        DependencySpec("storage", "upsert_open_interest_fetch_state", lambda: upsert_open_interest_fetch_state),
        DependencySpec("storage", "upsert_funding_rate_fetch_state", lambda: upsert_funding_rate_fetch_state),
        DependencySpec("storage", "upsert_liquidation_fetch_state", lambda: upsert_liquidation_fetch_state),
        DependencySpec("storage", "upsert_long_short_ratio_fetch_state", lambda: upsert_long_short_ratio_fetch_state),
    ),
    "fetch": (
        DependencySpec("fetch", "api_key_loader", lambda: load_api_key),
        DependencySpec("fetch", "fetch_ohlcv_history", lambda: fetch_ohlcv_history),
        DependencySpec("fetch", "fetch_open_interest_history", lambda: fetch_open_interest_history),
        DependencySpec("fetch", "fetch_funding_rate_history", lambda: fetch_funding_rate_history),
        DependencySpec("fetch", "fetch_liquidation_history", lambda: fetch_liquidation_history),
        DependencySpec("fetch", "fetch_long_short_ratio_history", lambda: fetch_long_short_ratio_history),
    ),
}

def _validate_callable(name: str, value: Any) -> None:
    if not callable(value):
        raise TypeError(f"dependency '{name}' must be callable, got {type(value).__name__}")


def _make_dependency_bundle_class(name: str, specs: tuple[DependencySpec, ...]):
    fields = [(spec.field_name, Callable[..., Any] | object, field(default=UNSET)) for spec in specs]
    return make_dataclass(name, fields, frozen=True)


RuntimeDependencies = _make_dependency_bundle_class("RuntimeDependencies", DEPENDENCY_REGISTRY["runtime"])
StorageDependencies = _make_dependency_bundle_class("StorageDependencies", DEPENDENCY_REGISTRY["storage"])
FetchApiDependencies = _make_dependency_bundle_class("FetchApiDependencies", DEPENDENCY_REGISTRY["fetch"])


def _build_group_dependencies(group: str, provided: Any | None, legacy_kwargs: dict[str, Any]) -> Any:
    bundle_cls = {
        "runtime": RuntimeDependencies,
        "storage": StorageDependencies,
        "fetch": FetchApiDependencies,
    }[group]
    values: dict[str, Any] = {}
    if provided is not None:
        if not isinstance(provided, bundle_cls):
            raise TypeError(f"{group} dependency bundle must be a {bundle_cls.__name__} instance, got {type(provided).__name__}")
        for spec in DEPENDENCY_REGISTRY[group]:
            provided_value = getattr(provided, spec.field_name)
            if provided_value is not UNSET:
                if spec.field_name in legacy_kwargs:
                    raise TypeError(f"conflicting dependency kwargs for {group}.{spec.field_name}: provided via {group} bundle and legacy kwarg")
                values[spec.field_name] = provided_value
                continue
            if spec.field_name in legacy_kwargs:
                values[spec.field_name] = legacy_kwargs.pop(spec.field_name)
                continue
            values[spec.field_name] = spec.default_factory()
    else:
        for spec in DEPENDENCY_REGISTRY[group]:
            if spec.field_name in legacy_kwargs:
                values[spec.field_name] = legacy_kwargs.pop(spec.field_name)
            else:
                values[spec.field_name] = spec.default_factory()
    for spec in DEPENDENCY_REGISTRY[group]:
        _validate_callable(spec.field_name, values[spec.field_name])
    return bundle_cls(**values)


@dataclass(frozen=True, init=False)
class FetchDependencies:
    runtime: RuntimeDependencies = field(default_factory=RuntimeDependencies)
    storage: StorageDependencies = field(default_factory=StorageDependencies)
    fetch: FetchApiDependencies = field(default_factory=FetchApiDependencies)

    def __init__(self, runtime: RuntimeDependencies | None = None, storage: StorageDependencies | None = None, fetch: FetchApiDependencies | None = None, **legacy_kwargs: Any) -> None:
        """Construct dependency bundles.

        Merge rule:
        - subgroup objects take precedence for explicitly supplied values;
        - legacy flat kwargs fill missing values;
        - defaults fill anything still unspecified.
        """
        runtime = _build_group_dependencies("runtime", runtime, legacy_kwargs)
        storage = _build_group_dependencies("storage", storage, legacy_kwargs)
        fetch = _build_group_dependencies("fetch", fetch, legacy_kwargs)
        if legacy_kwargs:
            raise TypeError(f"unexpected dependency kwargs: {', '.join(sorted(legacy_kwargs))}")
        object.__setattr__(self, "runtime", runtime)
        object.__setattr__(self, "storage", storage)
        object.__setattr__(self, "fetch", fetch)

from .adapters import (
    cvd_db_record_from_parsed,
    funding_rate_record_from_point,
    liquidation_record_from_point,
    long_short_ratio_record_from_point,
    ohlcv_db_record_from_parsed,
    ohlcv_parsed_from_point,
    open_interest_record_from_point,
)
from .client import (
    fetch_funding_rate_history,
    fetch_liquidation_history,
    fetch_long_short_ratio_history,
    fetch_ohlcv_history,
    fetch_open_interest_history,
    load_api_key,
)
from .config import load_symbols, parse_args
from .db import transaction
from .parsers import FetchPlan, compute_fetch_from_ts, history_points, interval_seconds as _interval_seconds, validate_query_params as _validate_query_params
from .storage import CVDRecord, connect_db, create_fetch_run, finalize_fetch_run, get_cvd_offset, get_last_fetched_timestamp, get_last_funding_rate_fetched_timestamp, get_last_liquidation_fetched_timestamp, get_last_long_short_ratio_fetched_timestamp, get_last_open_interest_fetched_timestamp, init_db, save_error, upsert_cvd_records, upsert_cvd_records_in_transaction, upsert_fetch_state, upsert_fetch_state_in_transaction, upsert_funding_rate_fetch_state, upsert_funding_rate_records, upsert_liquidation_fetch_state, upsert_liquidation_records, upsert_long_short_ratio_fetch_state, upsert_long_short_ratio_records, upsert_ohlcv_records, upsert_ohlcv_records_in_transaction, upsert_open_interest_fetch_state, upsert_open_interest_records


def _build_default_fetch_dependencies() -> FetchDependencies:
    return FetchDependencies()


def _symbol_exchange(item: dict[str, Any]) -> str:
    exchange = item.get("exchange") or item.get("exchange_name") or item.get("exchange_code") or ""
    return str(exchange).strip()


def _record_storage_failure(deps: FetchDependencies, *, conn, run_id: int, error_type: str, message: str, symbol: str | None, exchange: str | None, market_type: str | None, interval: str | None, http_status: int | None = None, retry_after: float | None = None, raw_json: Any = None) -> None:
    try:
        deps.storage.save_error(conn, run_id=run_id, symbol=symbol, exchange=exchange, market_type=market_type, interval=interval, error_type=error_type, message=message, http_status=http_status, retry_after=retry_after, raw_json=raw_json)
    except Exception as exc:
        deps.runtime.logger(f"storage failure while recording {error_type} for {symbol or 'unknown'} {exchange or 'unknown'} {interval or 'unknown'}: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise


def _fetch_metric_history(conn, *, plan: FetchPlan, fetch_fn, get_last_fn, upsert_records_fn, upsert_state_fn, record_builder, args, run_id: int, error_type: str, empty_error_type: str, invalid_error_type: str, api_key: str, now: int, deps: FetchDependencies) -> int:
    _validate_query_params(symbol=plan.symbol, exchange=plan.exchange, interval=plan.interval, from_ts=plan.from_ts, to_ts=plan.to_ts)
    last_timestamp = get_last_fn(conn, plan.symbol, plan.exchange, plan.market_type, plan.interval)
    metric_from_ts = compute_fetch_from_ts(last_timestamp=last_timestamp, default_from_ts=plan.from_ts, overlap_candles=args.overlap_candles, interval_seconds=_interval_seconds(plan.interval), now=now)
    result = fetch_fn(symbol=plan.symbol, interval=plan.interval, from_ts=metric_from_ts, to_ts=now, api_key=api_key, max_retries=0, min_retry_after_seconds=args.min_retry_after_seconds, max_retry_after_seconds=args.max_retry_after_seconds)
    warnings = 0
    if not result.ok:
        warnings += 1
        _record_storage_failure(deps, conn=conn, run_id=run_id, error_type=error_type, message=(result.error or f"{error_type} failed after {int(now) - int(metric_from_ts)}s window from {metric_from_ts} to {now} (limit={args.limit}, url={plan.symbol}@{plan.exchange})"), symbol=plan.symbol, exchange=plan.exchange, market_type=plan.market_type, interval=plan.interval, http_status=result.status, retry_after=result.retry_after, raw_json={"error_type": error_type, "http_status": result.status, "retry_after": result.retry_after, "from_ts": metric_from_ts, "to_ts": now, "limit": args.limit})
        return warnings
    points = history_points(result.data)
    records = []
    fetched_at = int(now)
    for point in points:
        try:
            records.append(record_builder(point, symbol=plan.symbol, exchange=plan.exchange, market_type=plan.market_type, interval=plan.interval, fetched_at=fetched_at))
        except ValueError as exc:
            warnings += 1
            deps.storage.save_error(conn, run_id=run_id, symbol=plan.symbol, exchange=plan.exchange, market_type=plan.market_type, interval=plan.interval, error_type=invalid_error_type, message=str(exc), http_status=result.status, raw_json={"error_type": invalid_error_type})
    if records:
        upsert_records_fn(conn, records)
        upsert_state_fn(conn, plan.symbol, plan.exchange, plan.market_type, plan.interval, max(r.timestamp for r in records), fetched_at)
    else:
        warnings += 1
        deps.storage.save_error(conn, run_id=run_id, symbol=plan.symbol, exchange=plan.exchange, market_type=plan.market_type, interval=plan.interval, error_type=empty_error_type, message="response had no history entries", http_status=result.status, raw_json={"error_type": empty_error_type})
    return warnings


def _fetch_open_interest_history(conn, *, plan: FetchPlan, args, run_id: int, api_key: str, now: int, deps: FetchDependencies) -> int:
    return _fetch_metric_history(conn, plan=plan, fetch_fn=deps.fetch.fetch_open_interest_history, get_last_fn=deps.storage.get_last_open_interest_fetched_timestamp, upsert_records_fn=deps.storage.upsert_open_interest_records, upsert_state_fn=deps.storage.upsert_open_interest_fetch_state, record_builder=open_interest_record_from_point, args=args, run_id=run_id, error_type="open_interest_fetch_error", empty_error_type="empty_open_interest_response", invalid_error_type="invalid_open_interest_point", api_key=api_key, now=now, deps=deps)


def _fetch_funding_rate_history(conn, *, plan: FetchPlan, args, run_id: int, api_key: str, now: int, deps: FetchDependencies) -> int:
    return _fetch_metric_history(conn, plan=plan, fetch_fn=deps.fetch.fetch_funding_rate_history, get_last_fn=deps.storage.get_last_funding_rate_fetched_timestamp, upsert_records_fn=deps.storage.upsert_funding_rate_records, upsert_state_fn=deps.storage.upsert_funding_rate_fetch_state, record_builder=funding_rate_record_from_point, args=args, run_id=run_id, error_type="funding_rate_fetch_error", empty_error_type="empty_funding_rate_response", invalid_error_type="invalid_funding_rate_point", api_key=api_key, now=now, deps=deps)


def _fetch_liquidation_history(conn, *, plan: FetchPlan, args, run_id: int, api_key: str, now: int, deps: FetchDependencies) -> int:
    return _fetch_metric_history(conn, plan=plan, fetch_fn=deps.fetch.fetch_liquidation_history, get_last_fn=deps.storage.get_last_liquidation_fetched_timestamp, upsert_records_fn=deps.storage.upsert_liquidation_records, upsert_state_fn=deps.storage.upsert_liquidation_fetch_state, record_builder=liquidation_record_from_point, args=args, run_id=run_id, error_type="liquidation_fetch_error", empty_error_type="empty_liquidation_response", invalid_error_type="invalid_liquidation_point", api_key=api_key, now=now, deps=deps)


def _fetch_long_short_ratio_history(conn, *, plan: FetchPlan, args, run_id: int, api_key: str, now: int, deps: FetchDependencies) -> int:
    return _fetch_metric_history(conn, plan=plan, fetch_fn=deps.fetch.fetch_long_short_ratio_history, get_last_fn=deps.storage.get_last_long_short_ratio_fetched_timestamp, upsert_records_fn=deps.storage.upsert_long_short_ratio_records, upsert_state_fn=deps.storage.upsert_long_short_ratio_fetch_state, record_builder=long_short_ratio_record_from_point, args=args, run_id=run_id, error_type="long_short_ratio_fetch_error", empty_error_type="empty_long_short_ratio_response", invalid_error_type="invalid_long_short_ratio_point", api_key=api_key, now=now, deps=deps)


def _fetch_secondary_metrics(conn, *, plan: FetchPlan, args, run_id: int, api_key: str, now: int, deps: FetchDependencies) -> int:
    warnings = 0
    warnings += _fetch_open_interest_history(conn, plan=plan, args=args, run_id=run_id, api_key=api_key, now=now, deps=deps)
    warnings += _fetch_funding_rate_history(conn, plan=plan, args=args, run_id=run_id, api_key=api_key, now=now, deps=deps)
    warnings += _fetch_liquidation_history(conn, plan=plan, args=args, run_id=run_id, api_key=api_key, now=now, deps=deps)
    warnings += _fetch_long_short_ratio_history(conn, plan=plan, args=args, run_id=run_id, api_key=api_key, now=now, deps=deps)
    return warnings


def _process_fetch_symbol(conn, *, idx: int, total: int, item: dict[str, Any], args, now: int, interval_seconds: int, api_key: str, run_id: int, ok: int, failed: int, warnings: int, consecutive_failures: int, rate_limit_count: int, deps: FetchDependencies):
    symbol = item.get("symbol")
    exchange = _symbol_exchange(item)
    market_type = item.get("market_type")
    _validate_query_params(symbol=symbol, exchange=exchange, interval=args.interval, from_ts=0, to_ts=1)
    last_timestamp = deps.storage.get_last_fetched_timestamp(conn, symbol, exchange, market_type, args.interval)
    from_ts = compute_fetch_from_ts(last_timestamp=last_timestamp, default_from_ts=now - args.hours * 3600, overlap_candles=args.overlap_candles, interval_seconds=interval_seconds, now=now)
    if from_ts >= now:
        warnings += 1
        deps.storage.save_error(conn, run_id=run_id, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, error_type="skipped_window", message="from_ts is not earlier than to_ts", http_status=None, raw_json={"error_type": "skipped_window", "from_ts": from_ts, "to_ts": now})
        return ok, failed, warnings, consecutive_failures, rate_limit_count, False

    deps.runtime.logger(f"[{idx}/{total}] fetch {symbol} @ {exchange} from={from_ts} to={now}")
    plan = FetchPlan(symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, from_ts=from_ts, to_ts=now)
    result = deps.fetch.fetch_ohlcv_history(symbol=plan.symbol, interval=plan.interval, from_ts=plan.from_ts, to_ts=plan.to_ts, api_key=api_key, max_retries=0, min_retry_after_seconds=args.min_retry_after_seconds, max_retry_after_seconds=args.max_retry_after_seconds)
    if not result.ok:
        failed += 1
        consecutive_failures += 1
        if result.status == 429:
            rate_limit_count += 1
        safe_error_meta = {"error_type": "fetch_error", "http_status": result.status, "retry_after": result.retry_after, "from_ts": plan.from_ts, "to_ts": plan.to_ts, "limit": args.limit, "url": f"{symbol}@{exchange}"}
        _record_storage_failure(deps, conn=conn, run_id=run_id, error_type="fetch_error", message=(result.error or f"fetch failed after {int(now) - int(plan.from_ts)}s from {plan.from_ts} to {plan.to_ts} (limit={args.limit}, url={symbol}@{exchange})"), symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, http_status=result.status, retry_after=result.retry_after, raw_json=safe_error_meta)
        if result.status == 429:
            _record_storage_failure(deps, conn=conn, run_id=run_id, error_type="rate_limited", message=f"rate limited for {symbol}@{exchange} {args.interval}; retry_after={result.retry_after or 'n/a'}s", symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, http_status=result.status, retry_after=result.retry_after, raw_json={**safe_error_meta, "error_type": "rate_limited"})
        if consecutive_failures >= args.max_consecutive_failures or rate_limit_count >= args.max_rate_limit_count:
            return ok, failed, warnings, consecutive_failures, rate_limit_count, True
        warnings += _fetch_secondary_metrics(conn, plan=plan, args=args, run_id=run_id, api_key=api_key, now=now, deps=deps)
        return ok, failed, warnings, consecutive_failures, rate_limit_count, False

    consecutive_failures = 0
    payload = result.data or []
    warnings += _fetch_secondary_metrics(conn, plan=plan, args=args, run_id=run_id, api_key=api_key, now=now, deps=deps)
    candles = history_points(payload)
    records = []
    cvd_records = []
    cumulative_cvd = deps.storage.get_cvd_offset(conn, symbol, exchange, market_type, args.interval, from_ts)
    fetched_at = int(deps.runtime.clock())
    for c in candles:
        try:
            parsed = ohlcv_parsed_from_point(c, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, fetched_at=fetched_at)
            records.append(ohlcv_db_record_from_parsed(parsed))
            if parsed.volume_delta is not None:
                cumulative_cvd += parsed.volume_delta
            cvd_records.append(cvd_db_record_from_parsed(parsed, cumulative_cvd=cumulative_cvd))
        except ValueError as exc:
            warnings += 1
            deps.storage.save_error(conn, run_id=run_id, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, error_type="invalid_candle", message=str(exc), http_status=result.status, raw_json={"error_type": "invalid_candle", "symbol": symbol, "exchange": exchange, "interval": args.interval})
    if not records:
        warnings += 1
        deps.storage.save_error(conn, run_id=run_id, symbol=symbol, exchange=exchange, market_type=market_type, interval=args.interval, error_type="no_valid_records", message="no valid candles to store", http_status=result.status, raw_json=payload)
        return ok, failed, warnings, consecutive_failures, rate_limit_count, False
    with transaction(conn):
        saved = upsert_ohlcv_records_in_transaction(conn, records)
        upsert_cvd_records_in_transaction(conn, cvd_records)
        if saved < 1:
            raise RuntimeError("no records were stored")
        upsert_fetch_state_in_transaction(conn, symbol, exchange, market_type, args.interval, max(r.timestamp for r in records), fetched_at)
    ok += 1
    return ok, failed, warnings, consecutive_failures, rate_limit_count, False


def run_fetch_job(args, deps: FetchDependencies | None = None) -> int:
    """Run a fetch job and finalize the run whenever a run record exists.

    The run finalization guarantee applies to every path after deps.create_fetch_run()
    succeeds. If setup fails before a run exists, the error is logged and no
    finalization is attempted because there is no database run to update.
    """
    deps = deps or _build_default_fetch_dependencies()
    conn = None
    run_id = None
    run_created = False
    ok = failed = warnings = consecutive_failures = rate_limit_count = 0
    run_exception: Exception | None = None
    try:
        interval_seconds = _interval_seconds(args.interval)
        symbols = deps.storage.load_symbols(args.symbols_file, args.market_type)[: args.limit]
    except ValueError as exc:
        deps.runtime.logger(f"invalid fetch job arguments: {exc}", file=sys.stderr)
        return 2
    try:
        now = int(deps.runtime.clock())
        deps.runtime.logger(f"db={args.db}")
        deps.runtime.logger(f"symbols_file={args.symbols_file}")
        deps.runtime.logger(f"interval={args.interval} now={now}")
        deps.runtime.logger(f"selected_symbols={len(symbols)} limit={args.limit} market_type={args.market_type}")
        if args.dry_run:
            deps.runtime.logger("dry-run: no API call")
            return 0
        api_key = deps.fetch.api_key_loader()
        if not api_key:
            deps.runtime.logger("COINALYZE_API_KEY is missing", file=sys.stderr)
            return 2
        conn = deps.storage.db_connect(args.db)
        deps.storage.init_db(conn)
        run_id = deps.storage.create_fetch_run(conn, symbols_file=args.symbols_file, db_path=args.db, interval=args.interval, hours=args.hours, limit_symbols=args.limit, sleep_seconds=args.sleep_seconds, market_type=args.market_type, dry_run=False, requested_count=len(symbols))
        run_created = True
        for idx, item in enumerate(symbols, 1):
            ok, failed, warnings, consecutive_failures, rate_limit_count, should_break = _process_fetch_symbol(conn, idx=idx, total=len(symbols), item=item, args=args, now=now, interval_seconds=interval_seconds, api_key=api_key, run_id=run_id, ok=ok, failed=failed, warnings=warnings, consecutive_failures=consecutive_failures, rate_limit_count=rate_limit_count, deps=deps)
            if should_break:
                break
            if args.sleep_seconds > 0 and idx < len(symbols):
                deps.runtime.sleeper(args.sleep_seconds)
        status = "success" if failed == 0 and warnings == 0 else ("partial_success" if ok > 0 else "failed")
        deps.runtime.logger(f"run_id={run_id} status={status} ok={ok} failed={failed} warnings={warnings}")
        return 0 if status == "success" or args.allow_partial_success else 1
    except Exception as exc:
        run_exception = exc
        if conn is not None and run_created and run_id is not None:
            deps.storage.save_error(conn, run_id=run_id, symbol=None, exchange=None, market_type=getattr(args, "market_type", None), interval=getattr(args, "interval", None), error_type="unexpected_exception", message=f"{type(exc).__name__}: {exc}", raw_json={"exception_type": type(exc).__name__, "exception_message": str(exc)})
        deps.runtime.logger(f"unexpected fetch error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            try:
                if run_created and run_id is not None:
                    if run_exception is not None:
                        deps.storage.finalize_fetch_run(conn, run_id, status="failed", succeeded_count=ok, failed_count=failed + 1, warning_count=warnings, notes=f"unexpected_exception: {type(run_exception).__name__}: {run_exception}")
                    else:
                        status = "success" if failed == 0 and warnings == 0 else ("partial_success" if ok > 0 else "failed")
                        deps.storage.finalize_fetch_run(conn, run_id, status=status, succeeded_count=ok, failed_count=failed, warning_count=warnings)
                elif run_exception is not None:
                    deps.runtime.logger(f"fetch run setup failed before run creation: {type(run_exception).__name__}: {run_exception}", file=sys.stderr)
            except Exception as finalize_exc:
                deps.runtime.logger(f"failed to finalize fetch run {run_id}: {type(finalize_exc).__name__}: {finalize_exc}", file=sys.stderr)
            finally:
                conn.close()


def main() -> int:
    return run_fetch_job(parse_args())
