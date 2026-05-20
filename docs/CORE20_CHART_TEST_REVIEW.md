# Core20 Chart Test Review - Corrected Market Key Verification

## Summary
Previous Stage 6A review was too optimistic. The issue was market_key case mixing:

- config/universe.core20.yml used uppercase symbol parts in market_key, e.g. `binance:BTCUSD.A`
- DB tables use lowercase market_key, e.g. `binance:btcusd.a`

This violated the no market_key mixing acceptance criterion and made direct config-key coverage checks report 0/20.

## Fix
Updated only `market_key` fields to lowercase in:

- config/universe.core20.yml
- config/universe.generated.yml

No labels were derived from coinalyze_symbol. Existing label fields remain intact.

## Commands Run
```bash
python -m cvd_monitor receive --once --interval 5min --lookback-hours 6 --universe config/universe.core20.yml
python -m cvd_monitor compute --interval 5min --universe config/universe.core20.yml
python -m cvd_monitor render --interval 5min --window-hours 6 --universe config/universe.core20.yml --output out/cvd_core20_chart_test_6h_fixed.png
python -m cvd_monitor render --interval 5min --window-hours 12 --universe config/universe.core20.yml --output out/cvd_core20_chart_test_12h_fixed.png
pytest -q
```

All commands exited 0.

## Generated Images
| File | Size |
|---|---:|
| out/cvd_core20_chart_test_6h_fixed.png | 289,401 bytes |
| out/cvd_core20_chart_test_12h_fixed.png | 291,709 bytes |

## Render Metrics
Both 6h and 12h:

```text
selected=20
with_features=20
plotted=9
omitted_crowding=12
skipped_no_features=0
skipped_no_cvd=0
unresolved=0
```

## Corrected Data Coverage
Coverage was verified using the exact `market_key` values from `config/universe.core20.yml`.

| Category | Markets | Raw markets | Raw rows | Feature markets | Feature rows |
|---|---:|---:|---:|---:|---:|
| btc_spot | 7 | 7 | 546 | 7 | 539 |
| btc_perp | 8 | 8 | 617 | 8 | 609 |
| stable_stable | 2 | 2 | 156 | 2 | 154 |
| stable_fiat | 3 | 3 | 234 | 3 | 231 |

Missing markets: none.

Latest raw timestamp: 2026-05-19 11:50 UTC  
Latest feature timestamp: 2026-05-19 11:45 UTC

Deribit has fewer rows (71 raw / 70 feature) but is present and usable.

## Interpretation
The chart is not missing data now. The reason only 9 series are visible is renderer crowding control:

- 20 markets selected
- 20 markets have feature rows
- 9 series plotted
- 12 omitted for crowding / panel max-series cap
- 0 skipped for missing feature rows
- 0 skipped for unusable CVD

## Tests
```text
12 passed
```

## Secret Safety
No API key printed. No webhook printed. `.env` was not dumped.

## Verdict
PASS after correction.

Previous ZIP/report should be treated as HOLD because it had market_key mixing. Rebuild package only after this corrected state is accepted.
