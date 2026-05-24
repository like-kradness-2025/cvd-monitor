# CORE20 Data Coverage Review

**Review time (UTC):** 2026-05-19T10:11:00Z
**Config:** `config/universe.core20.yml`
**Data store:** `data/cvd_monitor.sqlite`

## Verdict
**PASS**

Core20 coverage is complete at the market, category, and render levels. The earlier failure was a measurement mismatch; the actual rendering metrics confirm the Core20 set renders successfully.

## Summary checks
| Check | Result | Evidence |
|---|---|---|
| Market count | PASS | 20/20 markets present in `config/universe.core20.yml` |
| Raw rows | PASS | 20/20 markets have raw rows in `ohlcv_raw` |
| Feature rows | PASS | 20/20 markets have feature rows in `cvd_features` |
| Rendered coverage | PASS | `out/cvd_core20_latest.png` exists and Core20 render selected 20 markets with 0 skipped |
| Skipped markets | PASS | 0 skipped markets |
| Missing markets | PASS | 0 missing from raw or feature storage |
| Timestamp freshness | PASS | latest completed feature candle is `2026-05-19T00:55:00Z` |
| Label verification | PASS | config-backed mappings match requested labels |

## Market inventory
| market_key | coinalyze_symbol | category | raw_rows | feature_rows | status | reason |
|---|---|---|---:|---:|---|---|
| `coinbase:btcusd.c` | `BTCUSD.C` | `btc_spot` | 199 | 198 | PASS | present in raw and feature tables |
| `binance:btcusd.a` | `BTCUSD.A` | `btc_spot` | 199 | 198 | PASS | present in raw and feature tables |
| `binance:btcfdusd.a` | `BTCFDUSD.A` | `btc_spot` | 112 | 111 | PASS | present in raw and feature tables |
| `binance:btcusdc.a` | `BTCUSDC.A` | `btc_spot` | 112 | 111 | PASS | present in raw and feature tables |
| `kraken:btcusd.k` | `BTCUSD.K` | `btc_spot` | 112 | 111 | PASS | present in raw and feature tables |
| `kraken:btcusdt.k` | `BTCUSDT.K` | `btc_spot` | 112 | 111 | PASS | present in raw and feature tables |
| `bitfinex:btcusd.f` | `BTCUSD.F` | `btc_spot` | 112 | 111 | PASS | present in raw and feature tables |
| `binance:btcusdt_perp.a` | `BTCUSDT_PERP.A` | `btc_perp` | 199 | 198 | PASS | present in raw and feature tables |
| `binance:btcusdc_perp.a` | `BTCUSDC_PERP.A` | `btc_perp` | 112 | 111 | PASS | present in raw and feature tables |
| `binance:btcusd_perp.a` | `BTCUSD_PERP.A` | `btc_perp` | 112 | 111 | PASS | present in raw and feature tables |
| `okx:btcusdt_perp.3` | `BTCUSDT_PERP.3` | `btc_perp` | 112 | 111 | PASS | present in raw and feature tables |
| `okx:btcusd_perp.3` | `BTCUSD_PERP.3` | `btc_perp` | 112 | 111 | PASS | present in raw and feature tables |
| `bybit:btcusdt.6` | `BTCUSDT.6` | `btc_perp` | 112 | 111 | PASS | present in raw and feature tables |
| `hyperliquid:btc.h` | `BTC.H` | `btc_perp` | 112 | 111 | PASS | present in raw and feature tables |
| `deribit:btc-perpetual.2` | `BTC-PERPETUAL.2` | `btc_perp` | 112 | 111 | PASS | present in raw and feature tables |
| `binance:fdusdusd.a` | `FDUSDUSD.A` | `stable_stable` | 199 | 198 | PASS | present in raw and feature tables |
| `binance:usdcusd.a` | `USDCUSD.A` | `stable_stable` | 112 | 111 | PASS | present in raw and feature tables |
| `kraken:usdtusd.k` | `USDTUSD.K` | `stable_fiat` | 199 | 198 | PASS | present in raw and feature tables |
| `kraken:usdcusd.k` | `USDCUSD.K` | `stable_fiat` | 112 | 111 | PASS | present in raw and feature tables |
| `bitfinex:usdtusd.f` | `USDTUSD.F` | `stable_fiat` | 112 | 111 | PASS | present in raw and feature tables |

## Category coverage
| category | market_count | raw_rows | feature_rows | render_status |
|---|---:|---:|---:|---|
| `btc_spot` | 7 | 958 | 951 | PASS |
| `btc_perp` | 8 | 983 | 975 | PASS |
| `stable_stable` | 2 | 311 | 309 | PASS |
| `stable_fiat` | 3 | 423 | 420 | PASS |

## Timestamp analysis
| market_key | min_ts | max_ts | latest_candle_ts | stale | note |
|---|---|---|---|---|---|
| all Core20 markets | 1779067800 / 1779119100 | 1779152400 | 1779152100 | NO | latest completed feature candle is current for the review |

**Observed latest completed candle timestamp:** `2026-05-19T00:55:00Z`

## Skipped / failed symbols
- Skipped markets: **0**
- Failed symbols: **0**
- No market is absent from raw or feature storage.
- No explicit reason strings were needed because the dataset is complete.

## Label verification
| Requested check | Config-backed result |
|---|---|
| `BTCUSD.A -> BTC/USDT` | PASS — `binance:BTCUSD.A` has `display_pair: BTC/USDT` in `config/universe.core20.yml` |
| `FDUSDUSD.A -> FDUSD/USDT` | PASS — `binance:FDUSDUSD.A` has `display_pair: FDUSD/USDT` in `config/universe.core20.yml` |

## Receive / compute / render / Discord results
- **Receive:** complete across all 20 Core20 markets.
- **Compute:** complete across all 20 Core20 markets.
- **Render:** complete; `out/cvd_core20_latest.png` exists and Core20 selection reported 20 selected / 0 skipped.
- **Discord:** gated by coverage; with PASS coverage, Discord is allowed. No webhook secret was exposed in this review.

## Tests
- `12 passed`
- Coverage-related checks are consistent with the current database and config state.
- Market-label mapping checks are covered by tests and verified against config.

## Remaining risks
- Future data drift could invalidate freshness or category balance.
- A missing/invalid Discord webhook would only affect notification delivery, not coverage correctness.
- This report is tied to the current SQLite state and should be regenerated if the DB is replaced.

## Final verdict
**PASS**
