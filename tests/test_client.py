from __future__ import annotations

import json
import sys
import urllib.error
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from coinalyze_ohlcv.client import _clamp_retry_after, fetch_ohlcv_history, sanitize_for_persistence


class TestClient(unittest.TestCase):
    def test_clamp_retry_after_bounds(self) -> None:
        self.assertEqual(_clamp_retry_after(0.2, min_seconds=1, max_seconds=120), 1)
        self.assertEqual(_clamp_retry_after(999, min_seconds=1, max_seconds=120), 120)
        self.assertIsNone(_clamp_retry_after(None, min_seconds=1, max_seconds=120))

    def test_sanitize_for_persistence_masks_secret_like_values(self) -> None:
        payload = {
            "message": "api_key=SECRET_VALUE coinalyze_api_key: SECRET_VALUE token: SECRET_VALUE password=SECRET_VALUE secret=SECRET_VALUE authorization: Bearer SECRET_VALUE",
            "nested": [
                "url?api_key=SECRET_VALUE",
                "https://example.com/path?foo_token=SECRET_VALUE&normal=ok",
                "Bearer SECRET_VALUE",
                "https://hooks.example.com/webhook/SECRET_VALUE",
            ],
            "authorization": "Bearer SECRET_VALUE",
            "cookie": "session=SECRET_VALUE",
            "details": {
                "random_api_key": "SECRET_VALUE",
                "serviceToken": "SECRET_VALUE",
                "password": "SECRET_VALUE",
                "normal": "ok",
            },
        }
        sanitized = sanitize_for_persistence(payload)
        text = json.dumps(sanitized, ensure_ascii=False)
        self.assertNotIn("SECRET_VALUE", text)
        self.assertIn("[REDACTED]", text)
        self.assertIn("[REDACTED_WEBHOOK_URL]", text)
        self.assertIn('"normal": "ok"', text)
        self.assertNotIn("foo_token=SECRET_VALUE", text)
        self.assertNotIn("Bearer SECRET_VALUE", text)

    def test_retry_after_clamp_used_for_429(self) -> None:
        calls = []

        def fake_request(url: str, timeout: int = 30):
            calls.append(url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(
                    url=url,
                    code=429,
                    msg="Too Many Requests",
                    hdrs={"Retry-After": "999"},
                    fp=None,
                )
            return 200, b'[{"history": []}]', {}

        with patch("coinalyze_ohlcv.client._request", side_effect=fake_request), patch("coinalyze_ohlcv.client.time.sleep") as sleep:
            result = fetch_ohlcv_history(symbol="BTCUSD.C", interval="5min", from_ts=1, to_ts=2, api_key="secret", max_retries=1, min_retry_after_seconds=1, max_retry_after_seconds=120)
        self.assertTrue(result.ok)
        sleep.assert_called_with(120)

    def test_http_503_failure_returns_error(self) -> None:
        def fake_request(url: str, timeout: int = 30):
            raise urllib.error.HTTPError(
                url=url,
                code=503,
                msg="Service Unavailable",
                hdrs={},
                fp=None,
            )

        with patch("coinalyze_ohlcv.client._request", side_effect=fake_request):
            result = fetch_ohlcv_history(symbol="BTCUSD.C", interval="5min", from_ts=1, to_ts=2, api_key="secret")
        self.assertFalse(result.ok)
        self.assertEqual(result.status, 503)
        self.assertIsNotNone(result.error)

    def test_invalid_json_response_fails_cleanly(self) -> None:
        with patch("coinalyze_ohlcv.client._request", return_value=(200, b"not-json", {})):
            result = fetch_ohlcv_history(symbol="BTCUSD.C", interval="5min", from_ts=1, to_ts=2, api_key="secret")
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)


if __name__ == "__main__":
    unittest.main()
