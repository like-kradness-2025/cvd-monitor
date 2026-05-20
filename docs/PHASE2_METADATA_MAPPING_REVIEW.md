# Phase 2 Metadata Mapping Review

## 1. Summary

The metadata source of truth is `config/universe.generated.yml`. The earlier bad display came from the CLI using the wrong default markets config path. That is fixed now, so `inspect-features` reads the universe config and displays the correct human-facing metadata.

**Test suite:** 45 passed, 0 failed

---

## 2. Exact YAML entry

```yaml
- market_key: binance:BTCUSD.A
  exchange: binance
  coinalyze_symbol: BTCUSD.A
  symbol_on_exchange: BTCUSDT
  market_type: spot
  base: BTC
  quote: USDT
  display_pair: BTC/USDT
  category: btc_spot
  priority: 100
  enabled: true
  has_buy_sell_data: true
  has_ohlcv_data: null
  notes: v0.1 btc_spot curated
```

---

## 3. Root cause

- `config/universe.generated.yml` was correct.
- `inspect-features` was using the wrong default config path, so it could not reliably resolve the universe metadata.
- The fix is to make the universe config the default source of truth and derive display fields from it.
- `display_pair` is not derived from `coinalyze_symbol`.

---

## 4. Files changed

| File | Change |
|------|--------|
| `cvd_monitor/config.py` | Default markets config path changed to `config/universe.generated.yml` |
| `docs/PHASE2_METADATA_MAPPING_REVIEW.md` | Updated review record and acceptance status |

---

## 5. Verification

| Check | Result |
|------|--------|
| `BTCUSD.A` display | `BTC/USDT` |
| `FDUSDUSD.A` display | `FDUSD/USDT` |
| `BTCUSDT_PERP.A` display | `BTC/USDT` |
| `USDTUSD.K` display | `USDT/USD` |
| `BTCUSD.C` display | `BTC/USD` |
| `compute --symbols` | PASS |
| feature rows | 435 |
| `pytest -q` | PASS |

Command output:

```text
python -m cvd_monitor compute --interval 5min --symbols BTCUSD.C,BTCUSD.A,BTCUSDT_PERP.A,FDUSDUSD.A,USDTUSD.K
rows_read=435 rows_skipped=0 rows_written=435 symbols_processed=5
```

---

## 6. Final verdict

**PASS**

Acceptance criteria met:
- `BTCUSD.A` displays `BTC/USDT`, not `BTC/USD`
- `compute --symbols` still works
- feature rows remain 435
- `pytest -q` passes
