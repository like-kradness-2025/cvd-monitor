from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cvd_monitor.fetcher import _validate_query_params


class TestFetcherValidation(unittest.TestCase):
    def test_validate_query_params_rejects_missing_or_invalid_values(self) -> None:
        with self.assertRaises(ValueError):
            _validate_query_params(symbol="", exchange="Coinbase", interval="1m", from_ts=0, to_ts=1)
        with self.assertRaises(ValueError):
            _validate_query_params(symbol="BTCUSD.C", exchange="", interval="1m", from_ts=0, to_ts=1)
        with self.assertRaises(ValueError):
            _validate_query_params(symbol="BTCUSD.C", exchange="Coinbase", interval="bogus", from_ts=0, to_ts=1)
        with self.assertRaises(ValueError):
            _validate_query_params(symbol="BTCUSD.C", exchange="Coinbase", interval="1m", from_ts=1, to_ts=1)


if __name__ == "__main__":
    unittest.main()
