# cvd-monitor

Selected20 Coinalyze OHLCV storage test utilities.

## Configuration input format
The symbols file must contain a JSON array of objects. Each object must include:
- `symbol` (string)
- `market_type` (string: `spot` or `future`)
- `interval` (string)
- one exchange identifier: `exchange`, `exchange_name`, or `exchange_code`

The loader normalizes the exchange field into all three keys for runtime use:
- `exchange`
- `exchange_name`
- `exchange_code`

Example:
```json
[
  {
    "symbol": "BTCUSDT",
    "exchange_name": "binance",
    "market_type": "spot",
    "interval": "1m"
  }
]
```

## Notes
- The API key is sent in a request header by default to avoid leaking credentials in URLs.
- Set `COINALYZE_API_KEY_TRANSPORT=query` only if you must use legacy query-string transport.
- Set `COINALYZE_API_KEY_HEADER` to override the header name used for the API key.
- Logs, exceptions, and DB error rows are sanitized to avoid leaking the full URL or key.
- Empty responses, invalid candles, and 429s are recorded as fetch errors. A run is only considered successful when at least one record is stored.
