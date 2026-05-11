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

from cvd_monitor.fetcher import (
    _compute_fetch_from_ts,
    _fetch_metric_history,
    _funding_rate_record_from_point,
    _liquidation_record_from_point,
    _long_short_ratio_record_from_point,
    run_fetch_job,
)
from cvd_monitor.storage import get_last_fetched_timestamp, get_last_open_interest_fetched_timestamp, init_db


class TestFetcherState(unittest.TestCase):
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
             patch("cvd_monitor.fetcher.time.time", return_value=1000), \
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
             patch("cvd_monitor.fetcher.time.time", return_value=1300), \
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
             patch("cvd_monitor.fetcher.time.time", return_value=1000), \
             patch("cvd_monitor.fetcher.fetch_ohlcv_history", side_effect=fake_fetch_ohlcv_history), \
             patch("cvd_monitor.fetcher.finalize_fetch_run"), \
             patch("cvd_monitor.fetcher.print"):
            run_fetch_job(self._args(interval="1m", overlap_candles=3))
        self.assertEqual(calls[-1], ("1m", 0, 1000))

        calls.clear()
        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher.time.time", return_value=1000), \
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

    def test_state_not_advanced_on_empty_or_failure(self) -> None:
        symbols = [{"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"}]
        empty = SimpleNamespace(ok=True, status=200, data=[{"history": []}], error=None, retry_after=None)
        failure = SimpleNamespace(ok=False, status=503, data=None, error="boom", retry_after=None)

        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher.time.time", return_value=1000), \
             patch("cvd_monitor.fetcher.fetch_ohlcv_history", return_value=empty), \
             patch("cvd_monitor.fetcher.finalize_fetch_run"), \
             patch("cvd_monitor.fetcher.print"):
            run_fetch_job(self._args(allow_partial_success=True))
        self.assertIsNone(get_last_fetched_timestamp(self.conn, "BTCUSD.C", "Coinbase", "spot", "1min"))

        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher.time.time", return_value=1000), \
             patch("cvd_monitor.fetcher.fetch_ohlcv_history", return_value=failure), \
             patch("cvd_monitor.fetcher.finalize_fetch_run"), \
             patch("cvd_monitor.fetcher.print"):
            run_fetch_job(self._args(allow_partial_success=True))
        self.assertIsNone(get_last_fetched_timestamp(self.conn, "BTCUSD.C", "Coinbase", "spot", "1min"))

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
             patch("cvd_monitor.fetcher.time.time", return_value=1000), \
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
             patch("cvd_monitor.fetcher.time.time", return_value=1000), \
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
             patch("cvd_monitor.fetcher.time.time", return_value=1000), \
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
        self.assertEqual(_compute_fetch_from_ts(last_timestamp=50, default_from_ts=10, overlap_candles=0, interval_seconds=60, now=100), 50)
        self.assertEqual(_compute_fetch_from_ts(last_timestamp=50, default_from_ts=10, overlap_candles=-3, interval_seconds=60, now=100), 50)
        self.assertEqual(_compute_fetch_from_ts(last_timestamp=500, default_from_ts=10, overlap_candles=1, interval_seconds=60, now=100), 99)
        self.assertEqual(_compute_fetch_from_ts(last_timestamp=None, default_from_ts=500, overlap_candles=1, interval_seconds=60, now=100), 99)

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

        with patch("cvd_monitor.fetcher.save_error"):
            warnings1 = _fetch_metric_history(conn, fetch_fn=fake_fetch_fn, get_last_fn=lambda *a: None, upsert_records_fn=lambda *a: None, upsert_state_fn=lambda *a: None, record_builder=_funding_rate_record_from_point, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="1m", from_ts=0, now=100, api_key="secret", args=args, run_id=run_id, error_type="funding_rate_fetch_error", empty_error_type="empty_funding_rate_response", invalid_error_type="invalid_funding_rate_point")
        self.assertEqual(warnings1, 1)
        with patch("cvd_monitor.fetcher.save_error"):
            warnings2 = _fetch_metric_history(conn, fetch_fn=fake_fetch_fn, get_last_fn=lambda *a: None, upsert_records_fn=lambda *a: None, upsert_state_fn=lambda *a: None, record_builder=_funding_rate_record_from_point, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="1m", from_ts=0, now=100, api_key="secret", args=args, run_id=run_id, error_type="funding_rate_fetch_error", empty_error_type="empty_funding_rate_response", invalid_error_type="invalid_funding_rate_point")
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
             patch("cvd_monitor.fetcher.time.time", return_value=1000), \
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


if __name__ == "__main__":
    unittest.main()
