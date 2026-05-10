# cvd-monitor

Selected20 Coinalyze OHLCV storage test utilities.

## Notes
- API key is only used in request parameters for Coinalyze compatibility; logs, exceptions, and DB error rows are sanitized to avoid leaking the full URL or key.
- Empty responses, invalid candles, and 429s are recorded as fetch errors. A run is only considered successful when at least one record is stored.
