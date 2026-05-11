from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import test_ohlcv_selected20 as script


class TestScript(unittest.TestCase):
    def test_main_fails_when_no_valid_records(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            symbols_file = Path(td) / "symbols.json"
            db_path = Path(td) / "db.sqlite3"
            symbols_file.write_text(json.dumps([{"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"}]), encoding="utf-8")
            with patch.object(script, "load_api_key", return_value="k"), patch.object(script, "fetch_ohlcv_history", return_value=type("R", (), {"ok": True, "data": [{"history": [{"t": 1, "v": 10, "bv": 11}]}], "status": 200, "error": None, "retry_after": None})()), patch.object(script, "upsert_ohlcv_records", return_value=0):
                with patch.object(sys, "argv", ["x", "--symbols-file", str(symbols_file), "--db", str(db_path), "--limit", "1", "--sleep-seconds", "0"]):
                    rc = script.main()
        self.assertEqual(rc, 1)

    def test_main_success_when_one_record_saved(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            symbols_file = Path(td) / "symbols.json"
            db_path = Path(td) / "db.sqlite3"
            symbols_file.write_text(json.dumps([{"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"}]), encoding="utf-8")
            response = type("R", (), {"ok": True, "data": [{"history": [{"t": 1, "v": 10, "bv": 6}]}], "status": 200, "error": None, "retry_after": None})()
            with patch.object(script, "load_api_key", return_value="k"), patch.object(script, "fetch_ohlcv_history", return_value=response):
                with patch.object(sys, "argv", ["x", "--symbols-file", str(symbols_file), "--db", str(db_path), "--limit", "1", "--sleep-seconds", "0"]):
                    rc = script.main()
        self.assertEqual(rc, 0)

    def test_main_returns_nonzero_on_partial_success_without_allow_flag(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            symbols_file = Path(td) / "symbols.json"
            db_path = Path(td) / "db.sqlite3"
            symbols_file.write_text(
                json.dumps([
                    {"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"},
                    {"symbol": "ETHUSD.C", "exchange_name": "Coinbase", "market_type": "spot"},
                ]),
                encoding="utf-8",
            )
            responses = [
                type("R", (), {"ok": True, "data": [{"history": [{"t": 1, "v": 10, "bv": 6}]}], "status": 200, "error": None, "retry_after": None})(),
                type("R", (), {"ok": False, "data": {"error": "rate limit"}, "status": 429, "error": "HTTP 429", "retry_after": 120})(),
            ]
            with patch.object(script, "load_api_key", return_value="k"), patch.object(script, "fetch_ohlcv_history", side_effect=responses), patch.object(script.time, "sleep"):
                with patch.object(sys, "argv", ["x", "--symbols-file", str(symbols_file), "--db", str(db_path), "--limit", "2", "--sleep-seconds", "0"]):
                    rc = script.main()
        self.assertEqual(rc, 1)

    def test_main_allows_partial_success_with_flag(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            symbols_file = Path(td) / "symbols.json"
            db_path = Path(td) / "db.sqlite3"
            symbols_file.write_text(
                json.dumps([
                    {"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"},
                    {"symbol": "ETHUSD.C", "exchange_name": "Coinbase", "market_type": "spot"},
                ]),
                encoding="utf-8",
            )
            responses = [
                type("R", (), {"ok": True, "data": [{"history": [{"t": 1, "v": 10, "bv": 6}]}], "status": 200, "error": None, "retry_after": None})(),
                type("R", (), {"ok": False, "data": {"error": "rate limit"}, "status": 429, "error": "HTTP 429", "retry_after": 120})(),
            ]
            with patch.object(script, "load_api_key", return_value="k"), patch.object(script, "fetch_ohlcv_history", side_effect=responses), patch.object(script.time, "sleep"):
                with patch.object(sys, "argv", ["x", "--symbols-file", str(symbols_file), "--db", str(db_path), "--limit", "2", "--sleep-seconds", "0", "--allow-partial-success"]):
                    rc = script.main()
        self.assertEqual(rc, 0)

    def test_main_stops_after_rate_limit_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            symbols_file = Path(td) / "symbols.json"
            db_path = Path(td) / "db.sqlite3"
            symbols_file.write_text(
                json.dumps([
                    {"symbol": "BTCUSD.C", "exchange_name": "Coinbase", "market_type": "spot"},
                    {"symbol": "ETHUSD.C", "exchange_name": "Coinbase", "market_type": "spot"},
                    {"symbol": "SOLUSD.C", "exchange_name": "Coinbase", "market_type": "spot"},
                ]),
                encoding="utf-8",
            )
            failure = type("R", (), {"ok": False, "data": {"error": "rate limit"}, "status": 429, "error": "HTTP 429", "retry_after": 120})()
            fetch_mock = patch.object(script, "fetch_ohlcv_history", return_value=failure)
            save_error_calls = []
            with patch.object(script, "load_api_key", return_value="DUMMY_SECRET"), fetch_mock, patch.object(script.time, "sleep"), patch.object(script, "save_error", side_effect=lambda *a, **k: save_error_calls.append((a, k))), patch.object(sys, "argv", ["x", "--symbols-file", str(symbols_file), "--db", str(db_path), "--limit", "3", "--sleep-seconds", "0", "--max-consecutive-failures", "10", "--max-rate-limit-count", "2"]):
                rc = script.main()
        self.assertEqual(rc, 1)
        self.assertEqual(len(save_error_calls), 4)
        for _, kwargs in save_error_calls:
            raw_json = kwargs.get("raw_json")
            self.assertIsInstance(raw_json, dict)
            self.assertNotIn("DUMMY_SECRET", json.dumps(raw_json, ensure_ascii=False))
            self.assertNotIn("headers", json.dumps(raw_json, ensure_ascii=False).lower())


if __name__ == "__main__":
    unittest.main()
