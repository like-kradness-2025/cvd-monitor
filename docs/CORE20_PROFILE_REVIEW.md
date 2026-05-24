# CORE20 Profile Review

## Summary
Core20 profile was verified end-to-end with the requested 20 enabled markets. The existing 41-market universe remains intact, and the `--universe` path works for receive / compute / render without changing core logic.

## Files changed
- `config/universe.core20.yml`
- `cvd_monitor/cli.py`
- `cvd_monitor/config.py`
- `stablecoin_monitor.py`
- `tests/test_config.py`
- `tests/test_market_registry.py`
- `tests/test_cvd_monitor_phase3.py`
- `docs/CORE20_PROFILE_REVIEW.md`

## Commands run
- `python -m cvd_monitor receive --once --interval 5min --lookback-hours 6 --universe config/universe.core20.yml`
- `python -m cvd_monitor compute --interval 5min --universe config/universe.core20.yml`
- `python -m cvd_monitor render --interval 5min --window-hours 6 --universe config/universe.core20.yml --output out/cvd_core20.png`
- `python -m cvd_monitor inspect-features --interval 5min --universe config/universe.core20.yml`
- `pytest -q`

## Core20 list
Enabled symbols:
- BTCUSD.C
- BTCUSD.A
- BTCFDUSD.A
- BTCUSDC.A
- BTCUSD.K
- BTCUSDT.K
- BTCUSD.F
- BTCUSDT_PERP.A
- BTCUSDC_PERP.A
- BTCUSD_PERP.A
- BTCUSDT_PERP.3
- BTCUSD_PERP.3
- BTCUSDT.6
- BTC.H
- BTC-PERPETUAL.2
- FDUSDUSD.A
- USDCUSD.A
- USDTUSD.K
- USDCUSD.K
- USDTUSD.F

## Row counts
Category totals from `inspect-features` at `5min`:
- btc_spot: 675 rows
- btc_perp: 759 rows
- stable_stable: 255 rows
- stable_fiat: 339 rows
- total: 2028 rows

Per-market summary:
- BTCUSD.C: 171 raw / 171 eligible / 171 feature / 0 skipped
- BTCUSD.A: 171 / 171 / 171 / 0
- BTCFDUSD.A: 84 / 84 / 84 / 0
- BTCUSDC.A: 84 / 84 / 84 / 0
- BTCUSD.K: 84 / 84 / 84 / 0
- BTCUSDT.K: 84 / 84 / 84 / 0
- BTCUSD.F: 84 / 84 / 84 / 0
- BTCUSDT_PERP.A: 171 / 171 / 171 / 0
- BTCUSDC_PERP.A: 84 / 84 / 84 / 0
- BTCUSD_PERP.A: 84 / 84 / 84 / 0
- BTCUSDT_PERP.3: 84 / 84 / 84 / 0
- BTCUSD_PERP.3: 84 / 84 / 84 / 0
- BTCUSDT.6: 84 / 84 / 84 / 0
- BTC.H: 84 / 84 / 84 / 0
- BTC-PERPETUAL.2: 84 / 84 / 84 / 0
- FDUSDUSD.A: 171 / 171 / 171 / 0
- USDCUSD.A: 84 / 84 / 84 / 0
- USDTUSD.K: 171 / 171 / 171 / 0
- USDCUSD.K: 84 / 84 / 84 / 0
- USDTUSD.F: 84 / 84 / 84 / 0

## Render result
- Output: `out/cvd_core20.png`
- Exists: yes
- Size: 278953 bytes
- Rendered count: 20
- Skipped count: 0
- Skip reason: none
- Unresolved symbols: 0

## Tests
- `pytest -q` → `50 passed`

## Risks
- Core20 is currently verified against the local database state available in this workspace.
- The render command selected 20 markets and produced no skips, but ongoing data freshness still depends on the live receiver schedule.
- No API key text was printed during verification.

## Verdict
PASS
