from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cvd_monitor.db import get_schema_version, migrate
from cvd_monitor.schemas import SCHEMA_VERSION, OHLCVRecord
from cvd_monitor.storage import StorageDependencies, StorageNotFoundError, get_last_fetched_timestamp, init_db, save_error, upsert_fetch_state, upsert_ohlcv_records


class TestStorage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.tmp.close()
        self.conn = sqlite3.connect(self.tmp.name)
        init_db(self.conn)

    def test_schema_version_is_initialized(self) -> None:
        self.assertEqual(get_schema_version(self.conn), SCHEMA_VERSION)
        self.assertEqual(migrate(self.conn), SCHEMA_VERSION)

    def test_dependency_injection_defaults_work(self) -> None:
        deps = StorageDependencies(db_path=self.tmp.name)
        self.assertEqual(deps.db_path, self.tmp.name)
        init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_upsert_deduplicates_by_primary_key(self) -> None:
        records = [
            OHLCVRecord(timestamp=1, symbol=" BTCUSD.C ", exchange="Coinbase", market_type="SPOT", interval="1M", open=1, high=2, low=1, close=2, volume=3, buy_volume=2, sell_volume=1, volume_delta=1),
            OHLCVRecord(timestamp=1, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="1m", open=10, high=20, low=10, close=20, volume=30, buy_volume=20, sell_volume=10, volume_delta=10),
        ]
        inserted = upsert_ohlcv_records(self.conn, records)
        self.assertEqual(inserted, 2)
        rows = self.conn.execute("SELECT open, market_type, interval FROM ohlcv_history WHERE symbol = ?", ("BTCUSD.C",)).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 10)
        self.assertEqual(rows[0][1], "spot")
        self.assertEqual(rows[0][2], "1m")

    def test_upsert_updates_existing_row_in_place(self) -> None:
        original = OHLCVRecord(timestamp=1, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="1m", open=1, high=2, low=1, close=2, volume=3, buy_volume=2, sell_volume=1, volume_delta=1)
        updated = OHLCVRecord(timestamp=1, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="1m", open=10, high=20, low=10, close=20, volume=30, buy_volume=20, sell_volume=10, volume_delta=10)
        self.assertEqual(upsert_ohlcv_records(self.conn, [original]), 1)
        before = self.conn.execute("SELECT open, high, close, volume_delta FROM ohlcv_history WHERE symbol = ?", ("BTCUSD.C",)).fetchone()
        self.assertEqual(tuple(before), (1.0, 2.0, 2.0, 1.0))
        self.assertEqual(upsert_ohlcv_records(self.conn, [updated]), 1)
        after = self.conn.execute("SELECT open, high, close, volume_delta FROM ohlcv_history WHERE symbol = ?", ("BTCUSD.C",)).fetchone()
        self.assertEqual(tuple(after), (10.0, 20.0, 20.0, 10.0))

    def test_save_error_masks_secret_like_values(self) -> None:
        save_error(self.conn, run_id=None, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="1m", error_type="fetch_error", message="api_key=SECRET_VALUE token=SECRET_VALUE", raw_json={"authorization": "Bearer SECRET_VALUE", "nested": {"password": "SECRET_VALUE"}})
        row = self.conn.execute("SELECT message, raw_json FROM fetch_errors ORDER BY id DESC LIMIT 1").fetchone()
        self.assertNotIn("SECRET_VALUE", row[0])
        self.assertNotIn("SECRET_VALUE", row[1])
        self.assertIn("[REDACTED]", row[0])

    def test_save_error_commits_inserted_row(self) -> None:
        save_error(self.conn, run_id=None, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="1m", error_type="fetch_error", message="boom", raw_json={"detail": "boom"})
        self.conn.close()
        self.conn = sqlite3.connect(self.tmp.name)
        row = self.conn.execute("SELECT message, raw_json FROM fetch_errors ORDER BY id DESC LIMIT 1").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "boom")
        self.assertIn("boom", row[1])

    def test_finalize_fetch_run_returns_true_and_updates_exactly_one_row(self) -> None:
        run_id = self.conn.execute("INSERT INTO fetch_runs (started_at, symbols_file, db_path, interval, hours, limit_symbols, sleep_seconds, market_type, dry_run, status, requested_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (1, "symbols.json", self.tmp.name, "1m", 1, 1, 0.0, "spot", 0, "running", 1)).lastrowid
        self.conn.commit()
        from cvd_monitor.storage import finalize_fetch_run
        self.assertTrue(finalize_fetch_run(self.conn, int(run_id), status="success", succeeded_count=1, failed_count=0, warning_count=0))
        row = self.conn.execute("SELECT status, succeeded_count, failed_count, warning_count FROM fetch_runs WHERE id = ?", (run_id,)).fetchone()
        self.assertEqual(tuple(row), ("success", 1, 0, 0))

    def test_finalize_fetch_run_raises_for_missing_run_id(self) -> None:
        from cvd_monitor.storage import finalize_fetch_run
        with self.assertRaises(StorageNotFoundError):
            finalize_fetch_run(self.conn, 999999, status="success", succeeded_count=1, failed_count=0, warning_count=0)

    def test_finalize_fetch_run_rejects_active_transaction(self) -> None:
        from cvd_monitor.storage import finalize_fetch_run

        self.conn.execute("BEGIN")
        self.assertTrue(self.conn.in_transaction)
        with self.assertRaisesRegex(RuntimeError, r"must be called in autocommit mode.*caller-managed transaction"):
            finalize_fetch_run(self.conn, 999999, status="success", succeeded_count=1, failed_count=0, warning_count=0)
        self.assertTrue(self.conn.in_transaction)
        self.conn.rollback()

    def test_finalize_fetch_run_rejects_implicit_transaction_from_prior_write(self) -> None:
        from cvd_monitor.storage import finalize_fetch_run

        self.conn.execute("INSERT INTO fetch_errors (run_id, symbol, exchange, market_type, interval, error_type, message, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (None, None, None, None, None, "test_error", "boom", 1))
        self.assertTrue(self.conn.in_transaction)
        with self.assertRaisesRegex(RuntimeError, r"must be called in autocommit mode.*caller-managed transaction"):
            finalize_fetch_run(self.conn, 999999, status="success", succeeded_count=1, failed_count=0, warning_count=0)
        self.conn.rollback()

    def test_finalize_fetch_run_rejects_savepoint_context(self) -> None:
        from cvd_monitor.storage import finalize_fetch_run

        self.conn.execute("SAVEPOINT sp1")
        self.assertTrue(self.conn.in_transaction)
        with self.assertRaisesRegex(RuntimeError, r"must be called in autocommit mode.*caller-managed transaction"):
            finalize_fetch_run(self.conn, 999999, status="success", succeeded_count=1, failed_count=0, warning_count=0)
        self.conn.execute("ROLLBACK TO sp1")
        self.conn.execute("RELEASE sp1")

    def test_finalize_fetch_run_leaves_connection_usable_after_missing_run_id(self) -> None:
        from cvd_monitor.storage import finalize_fetch_run

        self.assertFalse(self.conn.in_transaction)
        with self.assertRaises(StorageNotFoundError):
            finalize_fetch_run(self.conn, 999999, status="success", succeeded_count=1, failed_count=0, warning_count=0)
        self.assertFalse(self.conn.in_transaction)

        # The same connection should still support subsequent writes and reads.
        run_id = self.conn.execute("INSERT INTO fetch_runs (started_at, symbols_file, db_path, interval, hours, limit_symbols, sleep_seconds, market_type, dry_run, status, requested_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (2, "symbols.json", self.tmp.name, "1m", 1, 1, 0.0, "spot", 0, "running", 1)).lastrowid
        self.conn.commit()
        self.assertTrue(finalize_fetch_run(self.conn, int(run_id), status="success", succeeded_count=2, failed_count=0, warning_count=0))
        row = self.conn.execute("SELECT status, succeeded_count, failed_count, warning_count FROM fetch_runs WHERE id = ?", (run_id,)).fetchone()
        self.assertEqual(tuple(row), ("success", 2, 0, 0))
        self.assertFalse(self.conn.in_transaction)


if __name__ == "__main__":
    unittest.main()
