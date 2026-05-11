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

from cvd_monitor.storage import OHLCVRecord, get_last_fetched_timestamp, init_db, save_error, upsert_fetch_state, upsert_ohlcv_records


class TestStorage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.tmp.close()
        self.conn = sqlite3.connect(self.tmp.name)
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


if __name__ == "__main__":
    unittest.main()
