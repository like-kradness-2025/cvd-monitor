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

import cvd_monitor.fetcher as fetcher
from cvd_monitor.dashboard import build_dashboard_data, render_dashboard
from cvd_monitor.fetcher import FetchDependencies, RuntimeDependencies, StorageDependencies, run_fetch_job
from cvd_monitor.storage import init_db


class TestIntegrationWorkflow(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "workflow.sqlite3")
        self.symbols_file = str(Path(self.tmpdir.name) / "symbols.json")
        Path(self.symbols_file).write_text(
            '[{"symbol":"BTCUSD.C","exchange_name":"Coinbase","market_type":"spot","interval":"1m"}]',
            encoding="utf-8",
        )
        self.conn = sqlite3.connect(self.db_path)
        init_db(self.conn)
        self.conn.close()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _args(self, **kwargs):
        base = dict(
            symbols_file=self.symbols_file,
            db=self.db_path,
            interval="1m",
            hours=1,
            limit=20,
            overlap_candles=3,
            sleep_seconds=0,
            dry_run=False,
            market_type="all",
            max_retries=0,
            max_retry_after_seconds=120.0,
            min_retry_after_seconds=1.0,
            max_consecutive_failures=3,
            max_rate_limit_count=2,
            allow_partial_success=False,
        )
        base.update(kwargs)
        return SimpleNamespace(**base)

    def _deps(self, *, fetch_result, clock=1_700_000_000, save_error_side_effect=None):
        def fake_fetch_ohlcv_history(*, symbol, interval, from_ts, to_ts, api_key, max_retries, min_retry_after_seconds, max_retry_after_seconds):
            return fetch_result

        def ok_metric(point_key: str):
            return lambda **k: SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 50, point_key: 1}]}], error=None, retry_after=None)

        storage_kwargs = dict(
            db_connect=fetcher.connect_db,
            init_db=fetcher.init_db,
            create_fetch_run=fetcher.create_fetch_run,
            finalize_fetch_run=fetcher.finalize_fetch_run,
            save_error=fetcher.save_error if save_error_side_effect is None else save_error_side_effect,
            load_symbols=fetcher.load_symbols,
            get_last_fetched_timestamp=fetcher.get_last_fetched_timestamp,
            get_last_open_interest_fetched_timestamp=fetcher.get_last_open_interest_fetched_timestamp,
            get_last_funding_rate_fetched_timestamp=fetcher.get_last_funding_rate_fetched_timestamp,
            get_last_liquidation_fetched_timestamp=fetcher.get_last_liquidation_fetched_timestamp,
            get_last_long_short_ratio_fetched_timestamp=fetcher.get_last_long_short_ratio_fetched_timestamp,
            get_cvd_offset=fetcher.get_cvd_offset,
            upsert_ohlcv_records=fetcher.upsert_ohlcv_records,
            upsert_cvd_records=fetcher.upsert_cvd_records,
            upsert_open_interest_records=fetcher.upsert_open_interest_records,
            upsert_funding_rate_records=fetcher.upsert_funding_rate_records,
            upsert_liquidation_records=fetcher.upsert_liquidation_records,
            upsert_long_short_ratio_records=fetcher.upsert_long_short_ratio_records,
            upsert_fetch_state=fetcher.upsert_fetch_state,
            upsert_open_interest_fetch_state=fetcher.upsert_open_interest_fetch_state,
            upsert_funding_rate_fetch_state=fetcher.upsert_funding_rate_fetch_state,
            upsert_liquidation_fetch_state=fetcher.upsert_liquidation_fetch_state,
            upsert_long_short_ratio_fetch_state=fetcher.upsert_long_short_ratio_fetch_state,
        )
        return FetchDependencies(
            runtime=RuntimeDependencies(clock=lambda: clock, sleeper=lambda seconds: None, logger=lambda *a, **k: None),
            storage=StorageDependencies(**storage_kwargs),
            fetch=fetcher.FetchApiDependencies(api_key_loader=lambda: "test-key", fetch_ohlcv_history=fake_fetch_ohlcv_history, fetch_open_interest_history=ok_metric("oi"), fetch_funding_rate_history=ok_metric("r"), fetch_liquidation_history=ok_metric("l"), fetch_long_short_ratio_history=ok_metric("ratio")),
        )

    def test_complete_success_workflow_fetch_store_calculate_display(self) -> None:
        fetch_result = SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 100, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10, "bv": 6, "sv": 4}, {"t": 160, "o": 2, "h": 3, "l": 1.5, "c": 2.5, "v": 12, "bv": 7, "sv": 5}]}], error=None, retry_after=None)
        deps = self._deps(fetch_result=fetch_result)
        rc = run_fetch_job(self._args(), deps=deps)
        self.assertEqual(rc, 0)

        data = build_dashboard_data(self.db_path, symbol="BTCUSD.C", interval="1m")
        self.assertEqual(data["status"], "ok")
        self.assertEqual([row["timestamp"] for row in data["rows"]], [100, 160])
        self.assertEqual([row["timestamp"] for row in data["cvd_rows"]], [100, 160])
        self.assertEqual([row["cumulative_cvd"] for row in data["cvd_rows"]], [2.0, 4.0])
        self.assertEqual(data["rows"][0]["symbol"], data["cvd_rows"][0]["symbol"])
        self.assertEqual(data["rows"][0]["exchange"], data["cvd_rows"][0]["exchange"])
        self.assertEqual(data["rows"][0]["close"], 1.5)
        self.assertEqual(data["cvd_rows"][1]["volume_delta"], 2.0)

        output_path = str(Path(self.tmpdir.name) / "dashboard.png")
        rendered = render_dashboard(self.db_path, output_path, symbol="BTCUSD.C", interval="1m")
        self.assertEqual(rendered["status"], "ok")
        self.assertTrue(Path(output_path).exists())

    def test_api_error_is_recorded_and_dashboard_stays_empty(self) -> None:
        fetch_result = SimpleNamespace(ok=False, status=503, data=None, error="service unavailable", retry_after=None)
        deps = self._deps(fetch_result=fetch_result)
        rc = run_fetch_job(self._args(), deps=deps)
        self.assertEqual(rc, 1)

        conn = sqlite3.connect(self.db_path)
        try:
            errors = conn.execute("SELECT error_type, message, http_status FROM fetch_errors ORDER BY id ASC").fetchall()
            self.assertGreaterEqual(len(errors), 1)
            self.assertEqual(errors[0][0], "fetch_error")
            self.assertEqual(errors[0][2], 503)
        finally:
            conn.close()

        data = build_dashboard_data(self.db_path, symbol="BTCUSD.C", interval="1m")
        self.assertEqual(data["status"], "empty")

    def test_storage_failure_aborts_writes_and_reports_failure(self) -> None:
        deps = self._deps(fetch_result=SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 100, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10, "bv": 6, "sv": 4}]}], error=None, retry_after=None))
        with patch("cvd_monitor.fetcher.upsert_ohlcv_records_in_transaction", side_effect=RuntimeError("disk full")):
            rc = run_fetch_job(self._args(), deps=deps)
        self.assertEqual(rc, 1)

        conn = sqlite3.connect(self.db_path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM ohlcv_history").fetchone()[0]
            self.assertEqual(count, 0)
            errors = conn.execute("SELECT error_type, message FROM fetch_errors ORDER BY id ASC").fetchall()
            self.assertTrue(any(row[0] == "unexpected_exception" for row in errors))
        finally:
            conn.close()

    def test_multi_run_accumulates_cvd_without_duplicates(self) -> None:
        symbols = [{"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"}]
        responses = [
            SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 100, "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 10, "bv": 6, "sv": 4}, {"t": 160, "o": 2, "h": 3, "l": 2, "c": 2.5, "v": 12, "bv": 7, "sv": 5}]}], error=None, retry_after=None),
            SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 160, "o": 2, "h": 3, "l": 2, "c": 2.5, "v": 12, "bv": 7, "sv": 5}, {"t": 220, "o": 3, "h": 4, "l": 2.5, "c": 3.5, "v": 14, "bv": 9, "sv": 5}]}], error=None, retry_after=None),
            SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 220, "o": 3, "h": 4, "l": 2.5, "c": 3.5, "v": 14, "bv": 9, "sv": 5}, {"t": 280, "o": 4, "h": 5, "l": 3.5, "c": 4.5, "v": 16, "bv": 10, "sv": 6}]}], error=None, retry_after=None),
        ]
        fetch_calls: list[tuple[int, int]] = []

        def fake_fetch_ohlcv_history(*, symbol, interval, from_ts, to_ts, api_key, max_retries, min_retry_after_seconds, max_retry_after_seconds):
            fetch_calls.append((from_ts, to_ts))
            return responses.pop(0)

        def ok_metric(point_key: str):
            return lambda **k: SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 50, point_key: 1}]}], error=None, retry_after=None)

        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher._time.time", side_effect=[1000, 1300, 1600]), \
             patch("cvd_monitor.fetcher.fetch_ohlcv_history", side_effect=fake_fetch_ohlcv_history), \
             patch("cvd_monitor.fetcher.fetch_open_interest_history", side_effect=ok_metric("oi")), \
             patch("cvd_monitor.fetcher.fetch_funding_rate_history", side_effect=ok_metric("r")), \
             patch("cvd_monitor.fetcher.fetch_liquidation_history", side_effect=ok_metric("l")), \
             patch("cvd_monitor.fetcher.fetch_long_short_ratio_history", side_effect=ok_metric("ratio")), \
             patch("cvd_monitor.fetcher._fetch_secondary_metrics", return_value=0), \
             patch("cvd_monitor.fetcher.finalize_fetch_run"), \
             patch("cvd_monitor.fetcher.print"):
            for _ in range(3):
                run_fetch_job(self._args(overlap_candles=1, allow_partial_success=True))

        self.assertEqual(fetch_calls, [(0, 1000), (100, 1300), (160, 1600)])

        conn = sqlite3.connect(self.db_path)
        try:
            ohlcv_rows = conn.execute("SELECT timestamp FROM ohlcv_history WHERE symbol = ? ORDER BY timestamp ASC", ("BTCUSD.C",)).fetchall()
            cvd_rows = conn.execute("SELECT timestamp, cumulative_cvd FROM cvd_history WHERE symbol = ? ORDER BY timestamp ASC", ("BTCUSD.C",)).fetchall()
            fetch_state = conn.execute("SELECT last_timestamp FROM ohlcv_fetch_state WHERE symbol = ? AND exchange = ? AND interval = ?", ("BTCUSD.C", "Coinbase", "1m")).fetchone()
        finally:
            conn.close()

        self.assertEqual([row[0] for row in ohlcv_rows], [100, 160, 220, 280])
        self.assertEqual([row[0] for row in cvd_rows], [100, 160, 220, 280])
        self.assertEqual([row[1] for row in cvd_rows], [2.0, 4.0, 6.0, 9.0])
        self.assertEqual(fetch_state[0], 280)

    def test_multi_symbol_isolation_and_cvd_calculation(self) -> None:
        symbols = [
            {"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"},
            {"symbol": "ETHUSD.C", "exchange_name": "Coinbase", "market_type": "spot"},
        ]
        responses = {
            "BTCUSD.C": SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 100, "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 10, "bv": 6, "sv": 4}, {"t": 160, "o": 2, "h": 3, "l": 2, "c": 2.5, "v": 12, "bv": 8, "sv": 4}]}], error=None, retry_after=None),
            "ETHUSD.C": SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 100, "o": 10, "h": 11, "l": 9, "c": 10.5, "v": 30, "bv": 18, "sv": 12}, {"t": 160, "o": 11, "h": 12, "l": 10, "c": 11.5, "v": 36, "bv": 24, "sv": 12}]}], error=None, retry_after=None),
        }
        calls = []

        def fake_fetch_ohlcv_history(*, symbol, interval, from_ts, to_ts, api_key, max_retries, min_retry_after_seconds, max_retry_after_seconds):
            calls.append((symbol, from_ts, to_ts))
            return responses[symbol]

        def ok_metric(point_key: str):
            return lambda **k: SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 50, point_key: 1}]}], error=None, retry_after=None)

        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher._time.time", return_value=1000), \
             patch("cvd_monitor.fetcher.fetch_ohlcv_history", side_effect=fake_fetch_ohlcv_history), \
             patch("cvd_monitor.fetcher.fetch_open_interest_history", side_effect=ok_metric("oi")), \
             patch("cvd_monitor.fetcher.fetch_funding_rate_history", side_effect=ok_metric("r")), \
             patch("cvd_monitor.fetcher.fetch_liquidation_history", side_effect=ok_metric("l")), \
             patch("cvd_monitor.fetcher.fetch_long_short_ratio_history", side_effect=ok_metric("ratio")), \
             patch("cvd_monitor.fetcher._fetch_secondary_metrics", return_value=0), \
             patch("cvd_monitor.fetcher.finalize_fetch_run"), \
             patch("cvd_monitor.fetcher.print"):
            rc = run_fetch_job(self._args(limit=2, overlap_candles=0, allow_partial_success=True))
        self.assertEqual(rc, 0)
        self.assertEqual([call[0] for call in calls], ["BTCUSD.C", "ETHUSD.C"])

        conn = sqlite3.connect(self.db_path)
        try:
            btc_cvd = conn.execute("SELECT timestamp, cumulative_cvd FROM cvd_history WHERE symbol = ? ORDER BY timestamp ASC", ("BTCUSD.C",)).fetchall()
            eth_cvd = conn.execute("SELECT timestamp, cumulative_cvd FROM cvd_history WHERE symbol = ? ORDER BY timestamp ASC", ("ETHUSD.C",)).fetchall()
            btc_ohlcv = conn.execute("SELECT COUNT(*) FROM ohlcv_history WHERE symbol = ?", ("BTCUSD.C",)).fetchone()[0]
            eth_ohlcv = conn.execute("SELECT COUNT(*) FROM ohlcv_history WHERE symbol = ?", ("ETHUSD.C",)).fetchone()[0]
        finally:
            conn.close()

        self.assertEqual([row[1] for row in btc_cvd], [2.0, 6.0])
        self.assertEqual([row[1] for row in eth_cvd], [6.0, 18.0])
        self.assertEqual(btc_ohlcv, 2)
        self.assertEqual(eth_ohlcv, 2)

    def test_partial_overlap_and_duplicate_timestamps_are_deduplicated(self) -> None:
        symbols = [{"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"}]
        first = SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 100, "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 10, "bv": 6, "sv": 4}, {"t": 160, "o": 2, "h": 3, "l": 2, "c": 2.5, "v": 12, "bv": 7, "sv": 5}]}], error=None, retry_after=None)
        second = SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 160, "o": 2, "h": 3, "l": 2, "c": 2.5, "v": 12, "bv": 7, "sv": 5}, {"t": 160, "o": 2, "h": 3, "l": 2, "c": 2.5, "v": 12, "bv": 7, "sv": 5}, {"t": 220, "o": 3, "h": 4, "l": 2.5, "c": 3.5, "v": 14, "bv": 9, "sv": 5}]}], error=None, retry_after=None)
        responses = [first, second]

        def fake_fetch_ohlcv_history(*, symbol, interval, from_ts, to_ts, api_key, max_retries, min_retry_after_seconds, max_retry_after_seconds):
            return responses.pop(0)

        def ok_metric(point_key: str):
            return lambda **k: SimpleNamespace(ok=True, status=200, data=[{"history": [{"t": 50, point_key: 1}]}], error=None, retry_after=None)

        with patch("cvd_monitor.fetcher.load_symbols", return_value=symbols), \
             patch("cvd_monitor.fetcher.load_api_key", return_value="secret"), \
             patch("cvd_monitor.fetcher._time.time", side_effect=[1000, 1300]), \
             patch("cvd_monitor.fetcher.fetch_ohlcv_history", side_effect=fake_fetch_ohlcv_history), \
             patch("cvd_monitor.fetcher.fetch_open_interest_history", side_effect=ok_metric("oi")), \
             patch("cvd_monitor.fetcher.fetch_funding_rate_history", side_effect=ok_metric("r")), \
             patch("cvd_monitor.fetcher.fetch_liquidation_history", side_effect=ok_metric("l")), \
             patch("cvd_monitor.fetcher.fetch_long_short_ratio_history", side_effect=ok_metric("ratio")), \
             patch("cvd_monitor.fetcher._fetch_secondary_metrics", return_value=0), \
             patch("cvd_monitor.fetcher.finalize_fetch_run"), \
             patch("cvd_monitor.fetcher.print"):
            run_fetch_job(self._args(overlap_candles=1, allow_partial_success=True))
            run_fetch_job(self._args(overlap_candles=1, allow_partial_success=True))

        conn = sqlite3.connect(self.db_path)
        try:
            ohlcv_timestamps = [row[0] for row in conn.execute("SELECT timestamp FROM ohlcv_history WHERE symbol = ? ORDER BY timestamp ASC", ("BTCUSD.C",)).fetchall()]
            cvd_rows = conn.execute("SELECT timestamp, cumulative_cvd FROM cvd_history WHERE symbol = ? ORDER BY timestamp ASC", ("BTCUSD.C",)).fetchall()
        finally:
            conn.close()

        self.assertEqual(ohlcv_timestamps, [100, 160, 220])
        self.assertEqual([row[0] for row in cvd_rows], [100, 160, 220])
        self.assertEqual([row[1] for row in cvd_rows], [2.0, 4.0, 7.0])

    def test_empty_and_malformed_responses_are_handled(self) -> None:
        empty_result = SimpleNamespace(ok=True, status=200, data=[{"history": []}], error=None, retry_after=None)
        deps = self._deps(fetch_result=empty_result)
        rc = run_fetch_job(self._args(), deps=deps)
        self.assertEqual(rc, 1)

        conn = sqlite3.connect(self.db_path)
        try:
            errors = conn.execute("SELECT error_type FROM fetch_errors ORDER BY id ASC").fetchall()
            self.assertIn(("no_valid_records",), errors)
        finally:
            conn.close()

        malformed_result = SimpleNamespace(ok=True, status=200, data=[{"history": [{"o": 1, "v": 10}]}], error=None, retry_after=None)
        deps = self._deps(fetch_result=malformed_result)
        rc = run_fetch_job(self._args(), deps=deps)
        self.assertEqual(rc, 1)

        conn = sqlite3.connect(self.db_path)
        try:
            error_types = [row[0] for row in conn.execute("SELECT error_type FROM fetch_errors ORDER BY id ASC").fetchall()]
            self.assertIn("invalid_candle", error_types)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
