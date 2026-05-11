from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cvd_monitor.adapters import funding_rate_record_from_point
import cvd_monitor.fetcher as fetcher
from cvd_monitor.fetcher import (
    FetchApiDependencies,
    FetchDependencies,
    RuntimeDependencies,
    StorageDependencies,
    _fetch_metric_history,
    _fetch_funding_rate_history,
    _fetch_liquidation_history,
    _fetch_long_short_ratio_history,
    run_fetch_job,
)
from cvd_monitor.parsers import FetchPlan, compute_fetch_from_ts
from cvd_monitor.storage import get_last_fetched_timestamp, get_last_open_interest_fetched_timestamp, init_db


class TestFetcherState(unittest.TestCase):
    def test_fetch_dependencies_default_contract_is_fully_wired(self) -> None:
        deps = FetchDependencies()
        self.assertIsInstance(deps.runtime, RuntimeDependencies)
        self.assertIsInstance(deps.storage, StorageDependencies)
        self.assertIsInstance(deps.fetch, FetchApiDependencies)
        self.assertIs(deps.runtime.clock, fetcher._time.time)
        self.assertIs(deps.runtime.sleeper, fetcher._time.sleep)
        self.assertIs(deps.runtime.logger, print)
        self.assertIs(deps.fetch.api_key_loader, fetcher.load_api_key)
        self.assertIs(deps.storage.db_connect, fetcher.connect_db)
        self.assertIs(deps.storage.init_db, fetcher.init_db)
        self.assertIs(deps.storage.create_fetch_run, fetcher.create_fetch_run)
        self.assertIs(deps.storage.finalize_fetch_run, fetcher.finalize_fetch_run)
        self.assertIs(deps.storage.save_error, fetcher.save_error)
        self.assertIs(deps.storage.load_symbols, fetcher.load_symbols)
        self.assertIs(deps.fetch.fetch_ohlcv_history, fetcher.fetch_ohlcv_history)
        self.assertIs(deps.fetch.fetch_open_interest_history, fetcher.fetch_open_interest_history)
        self.assertIs(deps.fetch.fetch_funding_rate_history, fetcher.fetch_funding_rate_history)
        self.assertIs(deps.fetch.fetch_liquidation_history, fetcher.fetch_liquidation_history)
        self.assertIs(deps.fetch.fetch_long_short_ratio_history, fetcher.fetch_long_short_ratio_history)
        self.assertIs(deps.storage.get_last_fetched_timestamp, fetcher.get_last_fetched_timestamp)
        self.assertIs(deps.storage.get_last_open_interest_fetched_timestamp, fetcher.get_last_open_interest_fetched_timestamp)
        self.assertIs(deps.storage.get_last_funding_rate_fetched_timestamp, fetcher.get_last_funding_rate_fetched_timestamp)
        self.assertIs(deps.storage.get_last_liquidation_fetched_timestamp, fetcher.get_last_liquidation_fetched_timestamp)
        self.assertIs(deps.storage.get_last_long_short_ratio_fetched_timestamp, fetcher.get_last_long_short_ratio_fetched_timestamp)
        self.assertIs(deps.storage.get_cvd_offset, fetcher.get_cvd_offset)
        self.assertIs(deps.storage.upsert_ohlcv_records, fetcher.upsert_ohlcv_records)
        self.assertIs(deps.storage.upsert_cvd_records, fetcher.upsert_cvd_records)
        self.assertIs(deps.storage.upsert_open_interest_records, fetcher.upsert_open_interest_records)
        self.assertIs(deps.storage.upsert_funding_rate_records, fetcher.upsert_funding_rate_records)
        self.assertIs(deps.storage.upsert_liquidation_records, fetcher.upsert_liquidation_records)
        self.assertIs(deps.storage.upsert_long_short_ratio_records, fetcher.upsert_long_short_ratio_records)
        self.assertIs(deps.storage.upsert_fetch_state, fetcher.upsert_fetch_state)
        self.assertIs(deps.storage.upsert_open_interest_fetch_state, fetcher.upsert_open_interest_fetch_state)
        self.assertIs(deps.storage.upsert_funding_rate_fetch_state, fetcher.upsert_funding_rate_fetch_state)
        self.assertIs(deps.storage.upsert_liquidation_fetch_state, fetcher.upsert_liquidation_fetch_state)
        self.assertIs(deps.storage.upsert_long_short_ratio_fetch_state, fetcher.upsert_long_short_ratio_fetch_state)

        conn = sqlite3.connect(":memory:")
        try:
            fetcher.init_db(conn)
            deps.storage.db_connect(":memory:")
            self.assertIsInstance(deps.runtime.clock(), float)
            self.assertIsNone(deps.runtime.sleeper(0))
        finally:
            conn.close()

    def test_fetch_dependencies_default_values_are_set(self) -> None:
        self.test_fetch_dependencies_default_contract_is_fully_wired()

    def test_fetch_dependencies_mixes_subgroup_and_legacy_kwargs_with_subgroup_precedence(self) -> None:
        legacy_sleeper = lambda seconds: "legacy-sleeper"
        runtime = RuntimeDependencies(clock=lambda: 1.0)
        deps = FetchDependencies(runtime=runtime, sleeper=legacy_sleeper)
        self.assertEqual(deps.runtime.clock(), 1.0)
        self.assertIs(deps.runtime.sleeper, legacy_sleeper)
        self.assertIs(deps.runtime.sleeper, legacy_sleeper)
        self.assertIs(deps.runtime.logger, print)
        self.assertIs(deps.runtime.logger, print)

    def test_fetch_dependencies_prefers_explicit_bundle_values_over_legacy_backfill(self) -> None:
        runtime = RuntimeDependencies(clock=lambda: 2.0)
        legacy_sleeper = lambda seconds: "legacy"
        deps = FetchDependencies(runtime=runtime, sleeper=legacy_sleeper)
        self.assertEqual(deps.runtime.clock(), 2.0)
        self.assertIs(deps.runtime.sleeper, legacy_sleeper)
        self.assertIs(deps.runtime.sleeper, legacy_sleeper)
        self.assertIs(deps.runtime.logger, print)
        self.assertIs(deps.runtime.logger, print)

    def test_fetch_dependencies_preserves_explicit_default_equivalent_values(self) -> None:
        legacy_sleeper = lambda seconds: "legacy-sleeper"
        runtime = RuntimeDependencies(clock=fetcher._time.time)
        deps = FetchDependencies(runtime=runtime, sleeper=legacy_sleeper)
        self.assertIs(deps.runtime.clock, fetcher._time.time)
        self.assertIs(deps.runtime.sleeper, legacy_sleeper)
        self.assertIs(deps.runtime.sleeper, legacy_sleeper)
        self.assertIs(deps.runtime.logger, print)

    def test_fetch_dependencies_rejects_conflicting_legacy_kwargs(self) -> None:
        runtime = RuntimeDependencies(clock=lambda: 1.0)
        with self.assertRaisesRegex(TypeError, "conflicting dependency kwargs for runtime.clock"):
            FetchDependencies(runtime=runtime, clock=lambda: 2.0)

    def test_fetch_dependencies_allows_legacy_backfill_when_bundle_leaves_field_unset(self) -> None:
        runtime = RuntimeDependencies(clock=lambda: 1.0)
        deps = FetchDependencies(runtime=runtime, sleeper=lambda seconds: None)
        self.assertIs(deps.runtime.clock, runtime.clock)
        self.assertIsNot(deps.runtime.sleeper, fetcher.UNSET)

    def test_nested_bundle_access_matches_legacy_contract(self) -> None:
        deps = FetchDependencies()
        self.assertIs(deps.runtime.clock, fetcher._time.time)
        self.assertIs(deps.storage.db_connect, fetcher.connect_db)
        self.assertIs(deps.fetch.fetch_ohlcv_history, fetcher.fetch_ohlcv_history)

    def test_fetch_dependencies_validates_callable_dependencies_at_construction(self) -> None:
        with self.assertRaisesRegex(TypeError, "dependency 'clock' must be callable"):
            FetchDependencies(clock="not-callable")

    def test_fetch_dependencies_rejects_malformed_dependency_bundle(self) -> None:
        with self.assertRaisesRegex(TypeError, "runtime dependency bundle must be a RuntimeDependencies instance"):
            FetchDependencies(runtime=object())

    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.tmp.close()
        self.conn = sqlite3.connect(self.tmp.name)
        init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def _args(self, **kwargs):
        base = dict(
            symbols_file="/tmp/symbols.json",
            db=self.tmp.name,
            interval="1min",
            hours=1,
            limit=20,
            overlap_candles=3,
            sleep_seconds=0,
            dry_run=False,
            market_type="all",
            max_retries=1,
            max_retry_after_seconds=120.0,
            min_retry_after_seconds=1.0,
            max_consecutive_failures=3,
            max_rate_limit_count=2,
            allow_partial_success=True,
        )
        base.update(kwargs)
        return SimpleNamespace(**base)

    def test_state_advances_independently_and_respects_overlap(self) -> None:
        symbols = [
            {"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"},
            {"symbol": "ETHUSD.C", "exchange_name": "Coinbase", "market_type": "spot"},
        ]
        responses = {
            "BTCUSD.C": [{"history": [{"t": 100, "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 10, "bv": 6}, {"t": 160, "o": 2, "h": 3, "l": 2, "c": 2.5, "v": 12, "bv": 7}]}],
            "ETHUSD.C": [{"history": [{"t": 200, "o": 3, "h": 4, "l": 2, "c": 3.5, "v": 20, "bv": 11}]}],
        }
        oi_calls = []
        calls = []
        funding_calls = []
        liquidation_calls = []
        lsr_calls = []

        def fake_fetch_ohlcv_history(*, symbol, interval, from_ts, to_ts, api_key, max_retries, min_retry_after_seconds, max_retry_after_seconds):
            calls.append((symbol, from_ts, to_ts, interval))
            return SimpleNamespace(ok=True, status=200, data=responses[symbol], error=None, retry_after=None)

        def fake_fetch_open_interest_history(*, symbol, interval, from_ts, to_ts, api_key, max_retries, min_retry_after_seconds, max_retry_after_seconds):
            oi_calls.append((symbol, from_ts, to_ts, interval))
            return SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 100, "oi": 1}]}], error=None, retry_after=None)

        def fake_empty_metric(*, symbol, interval, from_ts, to_ts, api_key, max_retries, min_retry_after_seconds, max_retry_after_seconds):
            return SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 90, "v": 1}]}], error=None, retry_after=None)

        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher._time.time", return_value=1000), \
             patch("cvd_monitor.fetcher.fetch_ohlcv_history", side_effect=fake_fetch_ohlcv_history), \
             patch("cvd_monitor.fetcher.fetch_open_interest_history", side_effect=fake_fetch_open_interest_history), \
             patch("cvd_monitor.fetcher.fetch_funding_rate_history", side_effect=fake_empty_metric), \
             patch("cvd_monitor.fetcher.fetch_liquidation_history", side_effect=fake_empty_metric), \
             patch("cvd_monitor.fetcher.fetch_long_short_ratio_history", side_effect=fake_empty_metric), \
             patch("cvd_monitor.fetcher.finalize_fetch_run"), \
             patch("cvd_monitor.fetcher.print"):
            rc = run_fetch_job(self._args(interval="1m"))
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(oi_calls), 2)
        self.assertEqual(calls[0][1], 0)
        self.assertEqual(get_last_fetched_timestamp(self.conn, "BTCUSD.C", "Coinbase", "spot", "1m"), 160)
        self.assertEqual(get_last_open_interest_fetched_timestamp(self.conn, "BTCUSD.C", "Coinbase", "spot", "1m"), 100)

        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher._time.time", return_value=1300), \
             patch("cvd_monitor.fetcher.fetch_ohlcv_history", side_effect=fake_fetch_ohlcv_history), \
             patch("cvd_monitor.fetcher.fetch_open_interest_history", side_effect=fake_fetch_open_interest_history), \
             patch("cvd_monitor.fetcher.fetch_funding_rate_history", side_effect=fake_empty_metric), \
             patch("cvd_monitor.fetcher.fetch_liquidation_history", side_effect=fake_empty_metric), \
             patch("cvd_monitor.fetcher.fetch_long_short_ratio_history", side_effect=fake_empty_metric), \
             patch("cvd_monitor.fetcher.create_fetch_run", return_value=2), \
             patch("cvd_monitor.fetcher.finalize_fetch_run"), \
             patch("cvd_monitor.fetcher.print"):
            rc = run_fetch_job(self._args(interval="1m"))
        self.assertEqual(rc, 0)
        self.assertEqual(calls[-2][1], 0)
        self.assertEqual(calls[-1][1], 20)

    def test_interval_seconds_supports_expected_intervals_and_clamps_overlap(self) -> None:
        symbols = [{"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"}]
        response = [{"history": [{"t": 100, "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 10, "bv": 6}]}]
        calls = []

        def fake_fetch_ohlcv_history(*, symbol, interval, from_ts, to_ts, api_key, max_retries, min_retry_after_seconds, max_retry_after_seconds):
            calls.append((interval, from_ts, to_ts))
            return SimpleNamespace(ok=True, status=200, data=response, error=None, retry_after=None)

        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher._time.time", return_value=1000), \
             patch("cvd_monitor.fetcher.fetch_ohlcv_history", side_effect=fake_fetch_ohlcv_history), \
             patch("cvd_monitor.fetcher.finalize_fetch_run"), \
             patch("cvd_monitor.fetcher.print"):
            run_fetch_job(self._args(interval="1m", overlap_candles=3))
        self.assertEqual(calls[-1], ("1m", 0, 1000))

        calls.clear()
        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher._time.time", return_value=1000), \
             patch("cvd_monitor.fetcher.get_last_fetched_timestamp", return_value=1000), \
             patch("cvd_monitor.fetcher.fetch_ohlcv_history", side_effect=fake_fetch_ohlcv_history), \
             patch("cvd_monitor.fetcher.finalize_fetch_run"), \
             patch("cvd_monitor.fetcher.print"):
            run_fetch_job(self._args(interval="5min", overlap_candles=3))
        self.assertEqual(calls[-1], ("5min", 100, 1000))

    def test_invalid_interval_fails_before_api_call(self) -> None:
        symbols = [{"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"}]
        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher.print") as mocked_print, \
             patch("cvd_monitor.fetcher.fetch_ohlcv_history") as fetch:
            rc = run_fetch_job(self._args(interval="bogus"))
        self.assertEqual(rc, 2)
        mocked_print.assert_called_once()
        self.assertIn("unsupported interval: bogus", mocked_print.call_args.args[0])
        self.assertEqual(mocked_print.call_args.kwargs.get("file"), __import__("sys").stderr)
        fetch.assert_not_called()

    def test_invalid_market_type_returns_user_facing_error_and_exit_code(self) -> None:
        with patch("cvd_monitor.fetcher.load_symbols", side_effect=ValueError("unsupported market_type: invalid")), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher.print") as mocked_print:
            rc = run_fetch_job(self._args(market_type="invalid"))
        self.assertEqual(rc, 2)
        mocked_print.assert_called_once()
        self.assertIn("unsupported market_type: invalid", mocked_print.call_args.args[0])
        self.assertEqual(mocked_print.call_args.kwargs.get("file"), __import__("sys").stderr)

    def test_run_creation_failure_before_run_id_is_logged_and_not_finalized(self) -> None:
        symbols = [{"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"}]
        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher.connect_db", side_effect=RuntimeError("db connect failed")), \
             patch("cvd_monitor.fetcher.finalize_fetch_run") as finalize, \
             patch("cvd_monitor.fetcher.save_error") as save_error, \
             patch("cvd_monitor.fetcher.print") as mocked_print:
            rc = run_fetch_job(self._args())
        self.assertEqual(rc, 1)
        finalize.assert_not_called()
        save_error.assert_not_called()
        mocked_print.assert_any_call("unexpected fetch error: RuntimeError: db connect failed", file=__import__("sys").stderr)

    def test_fetch_metric_history_uses_single_retry_policy_from_client_layer(self) -> None:
        symbols = [{"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"}]
        calls = []
        response = SimpleNamespace(ok=False, status=503, data=None, error="boom", retry_after=None)

        def fake_fetch_ohlcv_history(*, symbol, interval, from_ts, to_ts, api_key, max_retries, min_retry_after_seconds, max_retry_after_seconds):
            calls.append(max_retries)
            return response

        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher._time.time", return_value=1000), \
             patch("cvd_monitor.fetcher.fetch_ohlcv_history", side_effect=fake_fetch_ohlcv_history), \
             patch("cvd_monitor.fetcher.finalize_fetch_run"), \
             patch("cvd_monitor.fetcher.print"):
            run_fetch_job(self._args())

        self.assertEqual(calls, [0])

    def test_storage_failure_is_reported_and_raised(self) -> None:
        symbols = [{"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"}]
        response = SimpleNamespace(ok=False, status=503, data=None, error="boom", retry_after=None)
        logs = []

        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher._time.time", return_value=1000), \
             patch("cvd_monitor.fetcher.fetch_ohlcv_history", return_value=response), \
             patch("cvd_monitor.fetcher.save_error", side_effect=RuntimeError("db write failed")), \
             patch("cvd_monitor.fetcher.print", side_effect=lambda *a, **k: logs.append((a, k))):
            with self.assertRaises(RuntimeError):
                run_fetch_job(self._args())

        self.assertTrue(any("storage failure while recording fetch_error" in args[0] for args, _ in logs))

    def test_open_interest_fetch_runs_even_when_ohlcv_fails_and_uses_oi_state(self) -> None:
        symbols = [{"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"}]
        failure = SimpleNamespace(ok=False, status=503, data=None, error="boom", retry_after=None)
        oi_response = SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 111, "oi": 1.5}]}], error=None, retry_after=None)
        oi_calls = []

        def fake_fetch_open_interest_history(*, symbol, interval, from_ts, to_ts, api_key, max_retries, min_retry_after_seconds, max_retry_after_seconds):
            oi_calls.append(from_ts)
            return oi_response

        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher._time.time", return_value=1000), \
             patch("cvd_monitor.fetcher.get_last_open_interest_fetched_timestamp", return_value=777), \
             patch("cvd_monitor.fetcher.fetch_ohlcv_history", return_value=failure), \
             patch("cvd_monitor.fetcher.fetch_open_interest_history", side_effect=fake_fetch_open_interest_history), \
             patch("cvd_monitor.fetcher.finalize_fetch_run"), \
             patch("cvd_monitor.fetcher.print"):
            run_fetch_job(self._args(allow_partial_success=True))

        self.assertEqual(oi_calls, [597])
        self.assertEqual(get_last_open_interest_fetched_timestamp(self.conn, "BTCUSD.C", "Coinbase", "spot", "1min"), 111)

    def test_fetch_window_reuses_last_timestamp_minus_overlap_boundary(self) -> None:
        symbols = [{"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"}]
        recorded = []

        def fake_fetch_ohlcv_history(*, symbol, interval, from_ts, to_ts, api_key, max_retries, min_retry_after_seconds, max_retry_after_seconds):
            recorded.append(from_ts)
            return SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 100, "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 10, "bv": 6}]}], error=None, retry_after=None)

        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher._time.time", return_value=1000), \
             patch("cvd_monitor.fetcher.get_last_fetched_timestamp", return_value=160), \
             patch("cvd_monitor.fetcher.fetch_ohlcv_history", side_effect=fake_fetch_ohlcv_history), \
             patch("cvd_monitor.fetcher.finalize_fetch_run"), \
             patch("cvd_monitor.fetcher.print"):
            run_fetch_job(self._args(interval="1m", overlap_candles=1))

        self.assertEqual(recorded, [100])

    def test_metric_fetches_also_apply_overlap_boundary_reuse(self) -> None:
        symbols = [{"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"}]
        ohlcv_calls = []
        metric_calls = []
        metric_response = SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 100, "oi": 1.5}, {"t": 160, "oi": 1.7}]}], error=None, retry_after=None)

        def fake_fetch_ohlcv_history(*, symbol, interval, from_ts, to_ts, api_key, max_retries, min_retry_after_seconds, max_retry_after_seconds):
            ohlcv_calls.append(from_ts)
            return SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 200, "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 10, "bv": 6}]}], error=None, retry_after=None)

        def fake_fetch_open_interest_history(*, symbol, interval, from_ts, to_ts, api_key, max_retries, min_retry_after_seconds, max_retry_after_seconds):
            metric_calls.append(from_ts)
            return metric_response

        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher._time.time", return_value=1000), \
             patch("cvd_monitor.fetcher.get_last_fetched_timestamp", return_value=160), \
             patch("cvd_monitor.fetcher.get_last_open_interest_fetched_timestamp", return_value=160), \
             patch("cvd_monitor.fetcher.fetch_ohlcv_history", side_effect=fake_fetch_ohlcv_history), \
             patch("cvd_monitor.fetcher.fetch_open_interest_history", side_effect=fake_fetch_open_interest_history), \
             patch("cvd_monitor.fetcher.finalize_fetch_run"), \
             patch("cvd_monitor.fetcher.print"):
            run_fetch_job(self._args(interval="1m", overlap_candles=1))

        self.assertEqual(ohlcv_calls[-1], 100)
        self.assertEqual(metric_calls[-1], 100)

    def test_compute_fetch_from_ts_clamps_overlap_and_now_minus_one(self) -> None:
        self.assertEqual(compute_fetch_from_ts(last_timestamp=50, default_from_ts=10, overlap_candles=0, interval_seconds=60, now=100), 50)
        self.assertEqual(compute_fetch_from_ts(last_timestamp=50, default_from_ts=10, overlap_candles=-3, interval_seconds=60, now=100), 50)
        self.assertEqual(compute_fetch_from_ts(last_timestamp=500, default_from_ts=10, overlap_candles=1, interval_seconds=60, now=100), 99)
        self.assertEqual(compute_fetch_from_ts(last_timestamp=None, default_from_ts=500, overlap_candles=1, interval_seconds=60, now=100), 99)

    def test_fetch_metric_history_handles_invalid_and_empty_responses(self) -> None:
        args = self._args()
        symbols = []
        conn = self.conn
        run_id = 1
        empty = SimpleNamespace(ok=True, status=200, data=[{"history": []}], error=None, retry_after=None)
        invalid = SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 10, "v": "bad"}]}], error=None, retry_after=None)
        calls = []

        def fake_fetch_fn(**kwargs):
            calls.append(kwargs["from_ts"])
            return empty if len(calls) == 1 else invalid

        plan = __import__("cvd_monitor.parsers", fromlist=["FetchPlan"]).FetchPlan(symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="1m", from_ts=0, to_ts=100)
        deps = FetchDependencies(
            logger=lambda *args, **kwargs: None,
            save_error=lambda *args, **kwargs: None,
        )
        with patch("cvd_monitor.fetcher.save_error"):
            warnings1 = _fetch_metric_history(conn, plan=plan, fetch_fn=fake_fetch_fn, get_last_fn=lambda *a: None, upsert_records_fn=lambda *a: None, upsert_state_fn=lambda *a: None, record_builder=funding_rate_record_from_point, args=args, run_id=run_id, error_type="funding_rate_fetch_error", empty_error_type="empty_funding_rate_response", invalid_error_type="invalid_funding_rate_point", api_key="secret", now=100, deps=deps)
        self.assertEqual(warnings1, 1)
        with patch("cvd_monitor.fetcher.save_error"):
            warnings2 = _fetch_metric_history(conn, plan=plan, fetch_fn=fake_fetch_fn, get_last_fn=lambda *a: None, upsert_records_fn=lambda *a: None, upsert_state_fn=lambda *a: None, record_builder=funding_rate_record_from_point, args=args, run_id=run_id, error_type="funding_rate_fetch_error", empty_error_type="empty_funding_rate_response", invalid_error_type="invalid_funding_rate_point", api_key="secret", now=100, deps=deps)
        self.assertEqual(warnings2, 2)
        self.assertEqual(calls[0], 0)

    def test_metric_history_uses_each_metric_last_timestamp_independently(self) -> None:
        symbols = [{"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"}]
        funding_calls, liquidation_calls, lsr_calls = [], [], []

        def fake_history(target_list):
            def _inner(*, symbol, interval, from_ts, to_ts, api_key, max_retries, min_retry_after_seconds, max_retry_after_seconds):
                target_list.append(from_ts)
                return SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 200, "v": 1}]}], error=None, retry_after=None)
            return _inner

        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher._time.time", return_value=1000), \
             patch("cvd_monitor.fetcher.fetch_ohlcv_history", return_value=SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 200, "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 10, "bv": 6}]}], error=None, retry_after=None)), \
             patch("cvd_monitor.fetcher.get_last_fetched_timestamp", return_value=160), \
             patch("cvd_monitor.fetcher.get_last_funding_rate_fetched_timestamp", return_value=300), \
             patch("cvd_monitor.fetcher.get_last_liquidation_fetched_timestamp", return_value=400), \
             patch("cvd_monitor.fetcher.get_last_long_short_ratio_fetched_timestamp", return_value=500), \
             patch("cvd_monitor.fetcher.fetch_funding_rate_history", side_effect=fake_history(funding_calls)), \
             patch("cvd_monitor.fetcher.fetch_liquidation_history", side_effect=fake_history(liquidation_calls)), \
             patch("cvd_monitor.fetcher.fetch_long_short_ratio_history", side_effect=fake_history(lsr_calls)), \
             patch("cvd_monitor.fetcher.finalize_fetch_run"), \
             patch("cvd_monitor.fetcher.print"):
            run_fetch_job(self._args(interval="1m", overlap_candles=1))

        self.assertEqual(funding_calls[-1], 240)
        self.assertEqual(liquidation_calls[-1], 340)
        self.assertEqual(lsr_calls[-1], 440)

    def test_run_fetch_job_passes_injected_deps_through_metric_call_chain(self) -> None:
        symbols = [{"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"}]
        captured = {}
        deps = FetchDependencies(
            clock=lambda: 1000,
            sleeper=lambda seconds: None,
            logger=lambda *args, **kwargs: None,
            api_key_loader=lambda: "secret",
            db_connect=lambda path: self.conn,
            init_db=lambda conn: None,
            create_fetch_run=lambda *args, **kwargs: 1,
            finalize_fetch_run=lambda *args, **kwargs: None,
            load_symbols=lambda symbols_file, market_type: symbols,
            fetch_ohlcv_history=lambda **kwargs: SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 100, "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 10, "bv": 6}]}], error=None, retry_after=None),
            fetch_open_interest_history=lambda **kwargs: SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 100, "oi": 1}]}], error=None, retry_after=None),
            fetch_funding_rate_history=lambda **kwargs: SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 100, "v": 1}]}], error=None, retry_after=None),
            fetch_liquidation_history=lambda **kwargs: SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 100, "v": 1}]}], error=None, retry_after=None),
            fetch_long_short_ratio_history=lambda **kwargs: SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 100, "v": 1}]}], error=None, retry_after=None),
            get_last_fetched_timestamp=lambda *args: None,
            get_last_open_interest_fetched_timestamp=lambda *args: None,
            get_last_funding_rate_fetched_timestamp=lambda *args: None,
            get_last_liquidation_fetched_timestamp=lambda *args: None,
            get_last_long_short_ratio_fetched_timestamp=lambda *args: None,
            get_cvd_offset=lambda *args: 0.0,
            upsert_ohlcv_records=lambda *args: 1,
            upsert_cvd_records=lambda *args: 1,
            upsert_open_interest_records=lambda *args: 1,
            upsert_funding_rate_records=lambda *args: 1,
            upsert_liquidation_records=lambda *args: 1,
            upsert_long_short_ratio_records=lambda *args: 1,
            upsert_fetch_state=lambda *args: None,
            upsert_open_interest_fetch_state=lambda *args: None,
            upsert_funding_rate_fetch_state=lambda *args: None,
            upsert_liquidation_fetch_state=lambda *args: None,
            upsert_long_short_ratio_fetch_state=lambda *args: None,
        )

        original = fetcher._fetch_metric_history
        def spy(*args, **kwargs):
            captured["deps"] = kwargs["deps"]
            return original(*args, **kwargs)

        with patch("cvd_monitor.fetcher._fetch_metric_history", side_effect=spy):
            rc = run_fetch_job(self._args(), deps=deps)

        self.assertEqual(rc, 0)
        self.assertIs(captured["deps"], deps)

    def test_unexpected_exception_finalizes_failed_run_and_logs_error(self) -> None:
        symbols = [{"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"}]
        finalize_calls = []
        error_calls = []

        def boom(*args, **kwargs):
            raise RuntimeError("kaboom")

        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher._time.time", return_value=1000), \
             patch("cvd_monitor.fetcher.connect_db", return_value=self.conn), \
             patch("cvd_monitor.fetcher.init_db"), \
             patch("cvd_monitor.fetcher.create_fetch_run", return_value=99), \
             patch("cvd_monitor.fetcher._process_fetch_symbol", side_effect=boom), \
             patch("cvd_monitor.fetcher.save_error", side_effect=lambda *a, **k: error_calls.append((a, k))), \
             patch("cvd_monitor.fetcher.finalize_fetch_run", side_effect=lambda *a, **k: finalize_calls.append((a, k))), \
             patch("cvd_monitor.fetcher.print"):
            rc = run_fetch_job(self._args())

        self.assertEqual(rc, 1)
        self.assertEqual(len(finalize_calls), 1)
        self.assertEqual(finalize_calls[0][1]["status"], "failed")
        self.assertEqual(finalize_calls[0][1]["failed_count"], 1)
        self.assertEqual(len(error_calls), 1)
        self.assertEqual(error_calls[0][1]["error_type"], "unexpected_exception")
        self.assertIn("RuntimeError", error_calls[0][1]["message"])


if __name__ == "__main__":
    unittest.main()
