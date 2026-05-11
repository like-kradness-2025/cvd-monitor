from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from coinalyze_ohlcv.storage import init_db, record_from_candle, save_error, upsert_ohlcv_records, upsert_cvd_records, CVDRecord, get_cvd_offset, get_last_fetched_timestamp, upsert_fetch_state, OpenInterestRecord, upsert_open_interest_records, get_last_open_interest_fetched_timestamp, upsert_open_interest_fetch_state


class TestOhlcvStorage(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_record_from_candle_computes_sell_volume_and_delta(self) -> None:
        rec = record_from_candle(
            {"t": 100, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10, "bv": 6},
            symbol="BTCUSD.C",
            exchange="Coinbase",
            market_type="spot",
            interval="5min",
        )
        self.assertEqual(rec.sell_volume, 4)
        self.assertEqual(rec.volume_delta, 2)

    def test_save_error_sanitizes_raw_json_and_message(self) -> None:
        save_error(
            self.conn,
            run_id=None,
            symbol="BTCUSD.C",
            exchange="Coinbase",
            market_type="spot",
            interval="5min",
            error_type="fetch_error",
            message="failed api_key=SECRET_VALUE coinalyze_api_key: SECRET_VALUE",
            raw_json={
                "error": "api_key=SECRET_VALUE",
                "nested": ["coinalyze_api_key=SECRET_VALUE"],
                "authorization": "Bearer SECRET_VALUE",
                "cookie": "session=SECRET_VALUE",
                "meta": {"random_api_key": "SECRET_VALUE", "normal": "ok"},
            },
        )
        row = self.conn.execute("SELECT message, raw_json FROM fetch_errors").fetchone()
        self.assertIsNotNone(row)
        self.assertNotIn("SECRET_VALUE", row[0])
        self.assertNotIn("SECRET_VALUE", row[1])
        self.assertIn("[REDACTED]", row[0])
        self.assertIn("[REDACTED]", row[1])
        self.assertIn("normal", row[1])

    def test_history_sort_before_save(self) -> None:
        candles = [
            {"t": 200, "o": 2, "h": 3, "l": 1.5, "c": 2.5, "v": 12, "bv": 7},
            {"t": 100, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10, "bv": 6},
        ]
        records = [
            record_from_candle(c, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="5min")
            for c in sorted(candles, key=lambda x: x["t"])
        ]
        upsert_ohlcv_records(self.conn, records)
        rows = self.conn.execute("SELECT timestamp FROM ohlcv_history ORDER BY timestamp").fetchall()
        self.assertEqual([r[0] for r in rows], [100, 200])

    def test_upsert_overwrites_existing_row_without_duplication(self) -> None:
        first = record_from_candle({"t": 1, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10, "bv": 6}, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="5min")
        second = record_from_candle({"t": 1, "o": 9, "h": 9, "l": 9, "c": 9, "v": 20, "bv": 8}, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="5min")
        self.assertEqual(upsert_ohlcv_records(self.conn, [first]), 1)
        self.assertEqual(upsert_ohlcv_records(self.conn, [second]), 1)
        row = self.conn.execute("SELECT open, high, low, close, volume, buy_volume FROM ohlcv_history WHERE timestamp=1").fetchone()
        self.assertEqual(tuple(row), (9.0, 9.0, 9.0, 9.0, 20.0, 8.0))
        count = self.conn.execute("SELECT COUNT(*) FROM ohlcv_history").fetchone()[0]
        self.assertEqual(count, 1)

    def test_market_type_none_is_normalized_and_unique_per_market_type(self) -> None:
        unknown = record_from_candle({"t": 1, "o": 1, "v": 10, "bv": 6}, symbol="BTCUSD.C", exchange="Coinbase", market_type=None, interval="5min")
        spot = record_from_candle({"t": 1, "o": 2, "v": 12, "bv": 7}, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="5min")
        self.assertEqual(upsert_ohlcv_records(self.conn, [unknown]), 1)
        self.assertEqual(upsert_ohlcv_records(self.conn, [spot]), 1)
        rows = self.conn.execute("SELECT market_type FROM ohlcv_history ORDER BY market_type").fetchall()
        self.assertEqual([r[0] for r in rows], ["spot", "unknown"])

    def test_fetch_state_helpers_round_trip(self) -> None:
        self.assertIsNone(get_last_fetched_timestamp(self.conn, "BTCUSD.C", "Coinbase", "spot", "1min"))
        upsert_fetch_state(self.conn, "BTCUSD.C", "Coinbase", "spot", "1min", 123)
        self.assertEqual(get_last_fetched_timestamp(self.conn, "BTCUSD.C", "Coinbase", "spot", "1min"), 123)
        self.assertIsNone(get_last_open_interest_fetched_timestamp(self.conn, "BTCUSD.C", "Coinbase", "spot", "1min"))
        upsert_open_interest_fetch_state(self.conn, "BTCUSD.C", "Coinbase", "spot", "1min", 456)
        self.assertEqual(get_last_open_interest_fetched_timestamp(self.conn, "BTCUSD.C", "Coinbase", "spot", "1min"), 456)

    def test_open_interest_history_is_separate_and_upserts(self) -> None:
        first = OpenInterestRecord(timestamp=1, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="5min", open_interest=100.5, fetched_at=10)
        second = OpenInterestRecord(timestamp=1, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="5min", open_interest=200.5, fetched_at=20)
        self.assertEqual(upsert_open_interest_records(self.conn, [first]), 1)
        self.assertEqual(upsert_open_interest_records(self.conn, [second]), 1)
        row = self.conn.execute("SELECT open_interest, fetched_at FROM open_interest_history WHERE timestamp=1").fetchone()
        self.assertEqual(tuple(row), (200.5, 20))
        count = self.conn.execute("SELECT COUNT(*) FROM open_interest_history").fetchone()[0]
        self.assertEqual(count, 1)
        ohlcv_count = self.conn.execute("SELECT COUNT(*) FROM ohlcv_history").fetchone()[0]
        self.assertEqual(ohlcv_count, 0)

    def test_open_interest_history_table_exists(self) -> None:
        tables = {row[0] for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        self.assertIn("open_interest_history", tables)
        self.assertIn("open_interest_fetch_state", tables)

    def test_cvd_offset_uses_prior_history_for_continuity(self) -> None:
        records = [
            CVDRecord(timestamp=100, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="1min", buy_volume=6, sell_volume=4, volume_delta=2, cumulative_cvd=2, fetched_at=1),
            CVDRecord(timestamp=160, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="1min", buy_volume=7, sell_volume=5, volume_delta=2, cumulative_cvd=4, fetched_at=1),
        ]
        upsert_cvd_records(self.conn, records)
        self.assertEqual(get_cvd_offset(self.conn, "BTCUSD.C", "Coinbase", "spot", "1min", 160), 2.0)
        self.assertEqual(get_cvd_offset(self.conn, "BTCUSD.C", "Coinbase", "spot", "1min", 101), 2.0)
        self.assertEqual(get_cvd_offset(self.conn, "BTCUSD.C", "Coinbase", "spot", "1min", 100), 0.0)

    def test_record_from_candle_rejects_invalid_numeric_and_missing_volume(self) -> None:
        with self.assertRaises(ValueError):
            record_from_candle({"t": 1, "o": "NaN", "v": 10}, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="5min")
        with self.assertRaises(ValueError):
            record_from_candle({"t": 1, "o": 1, "v": float("inf")}, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="5min")
        with self.assertRaises(ValueError):
            record_from_candle({"t": 1, "o": 1, "v": 10, "bv": 11}, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="5min")
        with self.assertRaises(ValueError):
            record_from_candle({"t": 1, "o": 1}, symbol="BTCUSD.C", exchange="Coinbase", market_type="spot", interval="5min")


if __name__ == "__main__":
    unittest.main()
