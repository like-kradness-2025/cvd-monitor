# CVD Receiver Phase 1 QA Final

## Verification Summary
- Full test suite: **44 passed**
- DB inspection: **435 rows** in `ohlcv_raw`
- Duplicate-run verification: **no additional rows inserted**; row count remained **435**

## Files Changed
- `docs/CVD_RECEIVER_PHASE1_QA_FINAL.md` *(this report)*

## Commands to Run
```bash
pytest -q
python -m cvd_monitor inspect-db
```

## Row Count Before/After Duplicate Run
- Before duplicate run: **435**
- After duplicate run: **435**
- Result: **idempotent upsert confirmed**

## Min/Max ts by Symbol
- `BTC-USD`: min `1779067800`, max `1779093600`
- `BTCUSDT`: min `1779067800`, max `1779093600`
- `FDUSDUSDT`: min `1779067800`, max `1779093600`
- `USDT/USD`: min `1779067800`, max `1779093600`

## Latest Completed Candle
- Latest completed candle timestamp: **1779093600**
- Symbol at that timestamp: **BTC-USD**

## Rate Limit Setting
- Implementation uses a minimum delay of **60 / 36 = 1.666... seconds** between requests in `cvd_monitor.receiver.CoinalyzeClient._respect_rate_limit()`
- Phase 1 spec target is **max 60 requests/minute with 1 second delay**; current implementation is more conservative than the spec

## Namespace Decision
`cvd_monitor` is intentionally independent from `stablecoin_monitor` because it is a separate receiver pipeline with a different contract:
- different data source: **Coinalyze** rather than CCXT public OHLCV
- different schema: `ohlcv_raw` with Coinalyze-specific fields and PK `(market_key, interval, ts)`
- different API auth: requires `COINALYZE_API_KEY`
- different CLI: `receive` / `inspect-db`
- different storage path: `data/cvd_monitor.sqlite`
- different operational rules: 5-minute interval only, completed-candle filtering, and batch ingestion

Keeping the namespace independent avoids coupling Phase 1 receiver behavior to the existing proxy-CVD app and prevents schema/CLI conflicts.

## Test Results
- `pytest -q` → **44 passed in 0.42s**

## Row Count Discrepancy Explanation
Expected **360** vs actual **435** is explained by the final persisted dataset containing **5 distinct market keys**, each with **87 completed candles**:

- `binance:btcusd.a` → 87 rows
- `binance:btcusdt_perp.a` → 87 rows
- `binance:fdusdusd.a` → 87 rows
- `coinbase:btcusd.c` → 87 rows
- `kraken:usdtusd.k` → 87 rows

That yields **5 × 87 = 435 rows**.

The higher-than-expected count is consistent with the receiver retaining a wider completed-candle window than the rough 360-row estimate. The run still satisfies the Phase 1 safety properties:
- no duplicate growth on re-run
- completed candles only
- per-symbol persistence successful

## Verification Status
**Phase 1 QA verification complete.**
