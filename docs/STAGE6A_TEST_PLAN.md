# Stage 6A Chart Generation Test Plan

## 1. Test Objectives
- Validate Core20 chart generation for 6h and 12h windows
- Verify data coverage and render metrics
- Confirm label correctness (BTCUSD.A=BTC/USDT, FDUSDUSD.A=FDUSD/USDT)
- Ensure no secret leakage
- Classify any sparse chart causes

## 2. Test Steps
1. Run receive step to fetch fresh OHLCV data
2. Run compute step to calculate CVD features
3. Run render for 6h window, capture CLI output
4. Run render for 12h window, capture CLI output
5. Verify generated PNG files exist and are non-empty (> 100KB)
6. Extract render metrics from CLI output (selected, plotted, omitted, skipped)
7. Verify Core20 count (20 total, 7 spot, 8 perp, 5 stable)
8. Verify BTCUSD.A and FDUSDUSD.A labels in universe config
9. Check stdout/stderr for secret leakage (API key, webhook URL)
10. Run pytest to ensure no regressions
11. If chart appears sparse, classify cause (missing raw rows, missing feature rows, omitted_for_crowding, stale timestamps, no usable cvd values, renderer bug)

## 3. Expected Results
- Both PNG files generated, > 100KB each
- selected_markets_count = 20
- markets_with_feature_rows_count = 20
- plotted_series_count >= 1
- omitted_for_crowding_count >= 0
- skipped_no_feature_rows_count = 0
- skipped_no_usable_cvd_values_count = 0
- unresolved_symbols_count = 0
- No secrets in output
- pytest 12 passed

## 4. Sparse Chart Interpretation
If chart appears sparse, classify as one or more of:
- missing raw rows: no OHLCV data received for market
- missing feature rows: OHLCV exists but no CVD features computed
- omitted_for_crowding: market excluded due to panel capacity (max 3 series per panel)
- stale timestamps: data older than window period
- no usable cvd values: buy_volume = sell_volume for all candles
- renderer bug: data exists but not plotted

If cause cannot be determined, verdict = HOLD.

## 5. Secret Safety Checks
- Verify COINALYZE_API_KEY not printed in stdout/stderr
- Verify DISCORD_WEBHOOK_URL not printed in stdout/stderr
- Verify .env file not dumped in output
- Verify no credentials in generated PNG metadata

## 6. Acceptance Criteria
PASS if:
- All commands execute successfully (exit 0)
- Both PNG files exist and are non-empty (> 100KB)
- All metrics are explicitly reported from CLI output
- BTCUSD.A label = BTC/USDT, FDUSDUSD.A label = FDUSD/USDT
- No secrets leaked
- Tests pass (12 passed)
- Any sparse chart causes are classified

HOLD if:
- COINALYZE_API_KEY unavailable and no live receive was run
- Metrics are ambiguous
- Chart sparsity is unexplained
- Any Core20 category has no data
- Tests were not run

FAIL if:
- Commands fail with exit != 0
- PNG files missing or empty
- Metrics not reported
- Labels incorrect
- Secrets leaked
- Tests fail
