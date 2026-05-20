from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cvd_monitor.calc import compute_cvd_features
from cvd_monitor.db import get_db_connection, init_db, save_raw_ohlcv_rows
from cvd_monitor.models import RawOhlcvRow


def _row(market_key: str, symbol: str, ts: int, volume: float, buy_volume: float, close: float, tx: int, buy_tx: int) -> RawOhlcvRow:
    return RawOhlcvRow(market_key, symbol, 'binance', symbol, 'spot', 'other', '5min', ts, None, None, None, close, volume, buy_volume, tx, buy_tx, 1)


def test_compute_cvd_features_idempotent_and_skips_nulls(tmp_path: Path) -> None:
    db_path = tmp_path / 'db.sqlite3'
    init_db(db_path)
    save_raw_ohlcv_rows(db_path, [
        _row('m1', 'BTCUSD.A', 0, 10, 6, 100, 20, 12),
        _row('m1', 'BTCUSD.A', 300, 20, 10, 110, 30, 15),
        RawOhlcvRow('m1', 'BTCUSD.A', 'binance', 'BTCUSD.A', 'spot', 'other', '5min', 600, None, None, None, 120, None, 1, 1, 1, 1),
    ])
    stats = compute_cvd_features(db_path, '5min')
    assert stats['rows_written'] == 2
    assert stats['rows_skipped'] == 1
    assert stats['symbols_processed'] == 1
    with get_db_connection(db_path, read_only=True) as conn:
        rows = conn.execute('SELECT ts, delta, cvd, cvd_change_15m, cvd_change_1h FROM cvd_features ORDER BY ts').fetchall()
    assert [tuple(r) for r in rows] == [(0, 2.0, 2.0, None, None), (300, 0.0, 2.0, None, None)]
    stats2 = compute_cvd_features(db_path, '5min')
    with get_db_connection(db_path, read_only=True) as conn:
        assert conn.execute('SELECT COUNT(*) FROM cvd_features').fetchone()[0] == 2
    assert stats2['rows_written'] == 2
