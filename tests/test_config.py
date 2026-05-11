from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cvd_monitor.config import _parse_bool, load_symbols, parse_args
from cvd_monitor.env import load_env


class TestConfig(unittest.TestCase):
    def test_parse_bool_accepts_common_truthy_and_falsy_values(self) -> None:
        self.assertTrue(_parse_bool("true"))
        self.assertTrue(_parse_bool("1"))
        self.assertFalse(_parse_bool("false"))
        self.assertFalse(_parse_bool("0"))
        self.assertFalse(_parse_bool(None))
        with self.assertRaises(ValueError):
            _parse_bool("maybe")

    def test_load_symbols_validates_json_structure_required_keys_and_types(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            valid_path = base / "valid.json"
            valid_path.write_text(
                json.dumps([
                    {"symbol": "BTCUSDT", "exchange_name": "binance", "market_type": "spot", "interval": "1m"},
                    {"symbol": "ETHUSDT", "exchange_code": "binance", "market_type": "future", "interval": "1m"},
                ]),
                encoding="utf-8",
            )
            loaded = load_symbols(str(valid_path), "all")
            self.assertEqual(len(loaded), 2)
            self.assertEqual(len(load_symbols(str(valid_path), "spot")), 1)
            self.assertEqual(loaded[0]["exchange"], "binance")
            self.assertEqual(loaded[0]["exchange_code"], "binance")
            self.assertEqual(loaded[1]["exchange_name"], "binance")

            invalid_json_path = base / "invalid.json"
            invalid_json_path.write_text("{not-json", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"invalid JSON in symbols file:"):
                load_symbols(str(invalid_json_path), "all")

            array_path = base / "array.json"
            array_path.write_text(json.dumps({"symbol": "BTCUSDT"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "symbols file must contain a JSON array"):
                load_symbols(str(array_path), "all")

            empty_array_path = base / "empty_array.json"
            empty_array_path.write_text(json.dumps([]), encoding="utf-8")
            self.assertEqual(load_symbols(str(empty_array_path), "all"), [])

            missing_exchange_path = base / "missing_exchange.json"
            missing_exchange_path.write_text(
                json.dumps([{"symbol": "BTCUSDT", "market_type": "spot", "interval": "1m"}]),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, r"symbols\[0\]: missing required key 'exchange' \(or exchange_name/exchange_code\)"):
                load_symbols(str(missing_exchange_path), "all")

            wrong_exchange_type_path = base / "wrong_exchange_type.json"
            wrong_exchange_type_path.write_text(
                json.dumps([{"symbol": "BTCUSDT", "exchange": 123, "market_type": "spot", "interval": "1m"}]),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, r"symbols\[0\]: missing required key 'exchange' \(or exchange_name/exchange_code\)"):
                load_symbols(str(wrong_exchange_type_path), "all")

            wrong_type_path = base / "wrong_type.json"
            wrong_type_path.write_text(
                json.dumps([{"symbol": "BTCUSDT", "exchange": "binance", "market_type": "spot", "interval": 1}]),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, r"symbols\[0\]\.interval must be of type str"):
                load_symbols(str(wrong_type_path), "all")

            empty_string_path = base / "empty_string.json"
            empty_string_path.write_text(
                json.dumps([{"symbol": "", "exchange": "binance", "market_type": "spot", "interval": "1m"}]),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, r"symbols\[0\]\.symbol must not be empty"):
                load_symbols(str(empty_string_path), "all")

            non_dict_path = base / "non_dict.json"
            non_dict_path.write_text(json.dumps(["BTCUSDT"]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"symbols\[0\] must be an object"):
                load_symbols(str(non_dict_path), "all")

    def test_load_symbols_rejects_invalid_market_type(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "symbols.json"
            path.write_text(json.dumps([]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"unsupported market_type: invalid"):
                load_symbols(str(path), "invalid")

    def test_parse_args_loads_env_defaults_from_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env_dir = Path(td)
            dotenv = env_dir / ".env"
            dotenv.write_text("CVD_MONITOR_LIMIT=7\nCVD_MONITOR_ALLOW_PARTIAL_SUCCESS=1\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True), patch("cvd_monitor.env.Path.cwd", return_value=env_dir):
                load_env()
                with patch.object(sys, "argv", ["x"]):
                    args = parse_args()
        self.assertEqual(args.limit, 7)
        self.assertTrue(args.allow_partial_success)


if __name__ == "__main__":
    unittest.main()
