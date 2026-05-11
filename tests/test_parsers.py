from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cvd_monitor import parsers
from cvd_monitor.adapters import (
    funding_rate_record_from_point,
    liquidation_record_from_point,
    long_short_ratio_record_from_point,
    ohlcv_parsed_from_point,
    open_interest_record_from_point,
)


class TestParsers(unittest.TestCase):
    def test_interval_normalization_and_validation(self) -> None:
        self.assertEqual(parsers.normalize_interval("1m"), "1m")
        self.assertEqual(parsers.interval_seconds("5min"), 300)
        with self.assertRaises(ValueError):
            parsers.normalize_interval("bogus")

    def test_timestamp_clamping_and_parse(self) -> None:
        self.assertEqual(parsers.parse_timestamp("12"), 12)
        self.assertEqual(parsers.clamp_timestamp(-3), 0)
        self.assertEqual(parsers.clamp_timestamp(10, upper=5), 5)

    def test_history_and_metric_transforms(self) -> None:
        payload = [{"history": [{"t": 2, "v": 2}, {"t": 1, "v": 1}]}]
        self.assertEqual([p["t"] for p in parsers.history_points(payload)], [1, 2])
        self.assertEqual(parsers.transform_open_interest({"oi": "1.5"}), 1.5)
        self.assertEqual(parsers.transform_funding_rate({"v": "0.01"}), 0.01)
        self.assertEqual(parsers.transform_liquidation({"long": 1, "short": 2}), (1.0, 2.0))
        self.assertEqual(parsers.transform_long_short_ratio({"ratio": 3}), 3.0)

    def test_required_field_is_public_and_documented(self) -> None:
        self.assertIn("Return a required field", parsers.required_field.__doc__ or "")
        self.assertEqual(parsers.required_field({"t": 1}, "t", "test point"), 1)

    def test_strict_record_parsing_missing_required_fields_raise_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "OHLCV candle missing required field 't'"):
            parsers.parse_ohlcv_record({}, symbol="BTC", exchange="Coinbase", market_type="spot", interval="1m", fetched_at=1)
        with self.assertRaisesRegex(ValueError, "open interest point missing required field 'oi'"):
            open_interest_record_from_point({}, symbol="BTC", exchange="Coinbase", market_type="spot", interval="1m", fetched_at=1)
        with self.assertRaisesRegex(ValueError, "funding rate point missing required field 't'"):
            funding_rate_record_from_point({}, symbol="BTC", exchange="Coinbase", market_type="spot", interval="1m", fetched_at=1)
        with self.assertRaisesRegex(ValueError, "liquidation point missing required field 't'"):
            liquidation_record_from_point({}, symbol="BTC", exchange="Coinbase", market_type="spot", interval="1m", fetched_at=1)
        with self.assertRaisesRegex(ValueError, "long short ratio point missing required field 't'"):
            long_short_ratio_record_from_point({}, symbol="BTC", exchange="Coinbase", market_type="spot", interval="1m", fetched_at=1)


if __name__ == "__main__":
    unittest.main()
