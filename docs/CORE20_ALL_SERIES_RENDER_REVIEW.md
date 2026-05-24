# Core20 All-Series Render Review (Stage 6C)

## 1. Summary
Stage 6C changed the renderer to plot all eligible Core20 CVD series. The previous chart looked sparse because each CVD panel was capped to 3 plotted lines. That cap has been removed.

Final verdict: **PASS**

## 2. Stage 6C plan
Plan file: `docs/STAGE6C_ALL_SERIES_RENDER_PLAN.md`

Plan review score: **93/100 PASS**

## 3. Plan review score
```text
Score: 93/100
Verdict: PASS
```

## 4. Files changed
```text
cvd_monitor/renderer.py
cvd_monitor/cli.py
tests/test_cvd_monitor/test_cvd_monitor_phase3.py
docs/STAGE6C_ALL_SERIES_RENDER_PLAN.md
docs/CORE20_CHART_SELECTION_REVIEW.md
docs/CORE20_ALL_SERIES_RENDER_REVIEW.md
```

No Discord posting was performed. No final ZIP was rebuilt.

## 5. Commands run
```bash
pytest tests/test_cvd_monitor/test_cvd_monitor_phase3.py -q
pytest -q
python -m cvd_monitor receive --once --interval 5min --lookback-hours 6 --universe config/universe.core20.yml
python -m cvd_monitor compute --interval 5min --universe config/universe.core20.yml
python -m cvd_monitor render --interval 5min --window-hours 6 --universe config/universe.core20.yml --output out/cvd_core20_chart_all_6h.png
python -m cvd_monitor render --interval 5min --window-hours 12 --universe config/universe.core20.yml --output out/cvd_core20_chart_all_12h.png
pytest -q
```

Command evidence:

```text
receive: exit 0
compute: rows_read=1633 rows_skipped=0 rows_written=1633 symbols_processed=20
render 6h: exit 0
render 12h: exit 0
pytest: 13 passed
secret_leak=False
```

## 6. Generated images
| Image | Size |
|---|---:|
| `out/cvd_core20_chart_all_6h.png` | 357,132 bytes |
| `out/cvd_core20_chart_all_12h.png` | 365,213 bytes |

## 7. Data coverage
| Category | Markets | Raw markets | Raw rows | Feature markets | Feature rows |
|---|---:|---:|---:|---:|---:|
| btc_spot | 7 | 7 | 581 | 7 | 574 |
| btc_perp | 8 | 8 | 657 | 8 | 649 |
| stable_stable | 2 | 2 | 166 | 2 | 164 |
| stable_fiat | 3 | 3 | 249 | 3 | 246 |

All 20 Core20 markets have raw rows and feature rows.

## 8. Render metrics
Both 6h and 12h render commands reported:

```text
selected_markets_count=20
markets_with_feature_rows_count=20
plotted_series_count=21
omitted_for_crowding_count=0
skipped_no_feature_rows_count=0
skipped_no_usable_cvd_values_count=0
unresolved_symbols_count=0
btc_price_market=coinbase:btcusd.c
```

`plotted_series_count=21` means:
- 1 BTC price series
- 20 CVD market series

## 9. panel_plot_map
```text
BTC Spot/Perp CVD:
- BTCFDUSD.A
- BTCUSD.A
- BTCUSD_PERP.A
- BTCUSDC.A
- BTCUSDC_PERP.A
- BTCUSDT_PERP.A
- BTCUSD.F
- BTCUSDT.6
- BTCUSD.C
- BTC-PERPETUAL.2
- BTC.H
- BTCUSD.K
- BTCUSDT.K
- BTCUSD_PERP.3
- BTCUSDT_PERP.3

Stable/Stable CVD:
- FDUSDUSD.A
- USDCUSD.A

Stable/Fiat CVD:
- USDTUSD.F
- USDCUSD.K
- USDTUSD.K
```

## 10. panel_omitted_map
```text
{}
```

No eligible series were omitted for crowding.

## 11. Visual interpretation
Visual checks confirmed:
- BTC Price uses Coinbase BTC/USD.
- BTC Spot/Perp panel shows many BTC spot/perp series.
- Stable/Stable panel shows 2 series.
- Stable/Fiat panel shows 3 series.
- No important series are silently dropped because of panel cap.
- The BTC panel legend is crowded, but that is expected under the all-series requirement. Lines are kept instead of being dropped.

## 12. Issues found
- Previous cap existed in two places:
  - `_select_cvd_series(): available[:3]`
  - render loop: `zip(colors, series)` with only 3 colors
- Both caps were removed.
- No remaining blockers.

## 13. Tests
```text
pytest tests/test_cvd_monitor/test_cvd_monitor_phase3.py -q: 4 passed
pytest -q: 13 passed
```

Added/updated tests cover:
- all eligible Core20 CVD series are plotted
- `plotted_series_count == 21`
- `omitted_for_crowding_count == 0`
- BTC price source prefers `coinbase:btcusd.c`
- `panel_plot_map` includes all expected Core20 panel series
- `panel_omitted_map == {}`
- CLI output includes all-series metrics

## 14. Implementation review score
```text
Score: 96/100
Verdict: PASS
```

## 15. Final verdict
**PASS**

Acceptance criteria met:
- plan review score >= 90
- implementation review score >= 90
- 6h image generated and non-empty
- 12h image generated and non-empty
- all eligible series are plotted
- BTC Price uses BTCUSD.C / Coinbase BTC/USD when available
- plotted_series_count is explicit
- panel_plot_map is explicit
- panel_omitted_map is explicit
- omitted_for_crowding_count = 0
- pytest passes
- no secrets printed
