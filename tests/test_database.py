from __future__ import annotations

from cvd_monitor.database import CVDRecord, Database


def test_database_save_and_query(tmp_path) -> None:
    db = Database(str(tmp_path / "cvd.sqlite3"))
    db.init_schema()

    record = CVDRecord(symbol="BTCUSDT:spot", timeframe="1h", timestamp=1, price=100.0, spot_cvd=10.0, futures_cvd=0.0)
    db.save_cvd_data(record, payload={"hello": "world"})

    rows = db.query_cvd_data("BTCUSDT:spot", "1h")

    assert rows == [record]


def test_database_query_is_exact_match(tmp_path) -> None:
    db = Database(str(tmp_path / "cvd.sqlite3"))
    db.init_schema()

    record = CVDRecord(symbol="BTCUSDT:spot", timeframe="1h", timestamp=1, price=100.0, spot_cvd=10.0, futures_cvd=0.0)
    other = CVDRecord(symbol="BTCUSDTX:spot", timeframe="1h", timestamp=2, price=101.0, spot_cvd=11.0, futures_cvd=0.0)
    db.save_cvd_data(record)
    db.save_cvd_data(other)

    rows = db.query_cvd_data("BTCUSDT:spot", "1h")

    assert rows == [record]
