# Stage 6C All-Series Render Plan

## Goal
Render every eligible Core20 CVD series instead of capping each CVD panel at 3 lines.

## Current validated baseline
- Current Core20 render output is:
  - `selected=20`
  - `with_features=20`
  - `plotted=9`
  - `omitted_crowding=12`
  - `skipped_no_features=0`
  - `skipped_no_cvd=0`
  - `unresolved=0`
- Two independent caps exist in `renderer.py`:
  1. `_select_cvd_series()` truncates with `available[:3]`.
  2. The render loop uses `zip(colors, series)` while `colors` has only 3 entries, so plotting remains capped even if selection is fixed.
- Stage 6C must remove both caps.

## Target all-series metrics for complete Core20 data
- `selected_markets_count = 20`
- `markets_with_feature_rows_count = 20`
- `plotted_series_count = 21` (1 BTC price + 20 CVD series)
- `omitted_for_crowding_count = 0`
- `skipped_no_feature_rows_count = 0`
- `skipped_no_usable_cvd_values_count = 0`
- `unresolved_symbols_count = 0`

## Missing prior artifact handling
- `docs/CORE20_CHART_SELECTION_REVIEW.md` is missing.
- Treat this as a documented baseline gap, not a blocker, because the actual selection logic is directly inspectable in `cvd_monitor/renderer.py` and validated by command evidence.
- Create `docs/CORE20_CHART_SELECTION_REVIEW.md` during Stage 6C to record old cap behavior and new all-series behavior.

## Implementation steps
1. Extend `RenderResult` with:
   - `panel_plot_map: dict[str, list[str]]`
   - `panel_omitted_map: dict[str, list[str]]`
2. Change `_select_cvd_series()` so it returns all available/usable series and never truncates due to panel cap.
   - Remove `available[:3]` behavior.
   - `omitted_for_crowding` should be empty in normal Core20 render.
3. Remove render-loop cap:
   - Replace `for color, market in zip(colors, series):` with `for idx, market in enumerate(series):`.
   - Use a deterministic color cycle from `plt.get_cmap('tab20')` or an equivalent palette so >3 series all get styles.
   - Add linestyle cycling if needed, but never drop a series because the color list is short.
4. Add deterministic BTC price selection helper with required order:
   1. `BTCUSD.C` / `coinbase:btcusd.c`
   2. `BTCUSD.A` / `binance:btcusd.a`
   3. `BTCUSDT_PERP.A` / `binance:btcusdt_perp.a`
   4. any usable BTC spot
   5. any usable BTC future
5. Improve legend readability without dropping lines:
   - larger canvas
   - thinner CVD lines
   - smaller font
   - multi-column legend determined from series count
   - keep all series even if crowded
6. Define omission semantics:
   - `omitted_for_crowding_count` is always 0 in all-series mode unless a future technical omission reason is explicitly added.
   - `panel_omitted_map` must be `{}` for normal Core20 all-series render.
   - If any series is omitted for a real technical reason, record panel name + `market_key (reason)` in `panel_omitted_map` and count it in the matching skip metric, not crowding.
7. Update render CLI output to include:
   - `btc_price_market`
   - `panel_plot_map`
   - `panel_omitted_map`
8. Update `run_once_pipeline` summary to include the same all-series fields.
9. Add/update tests:
   - all eligible CVD series are plotted
   - `plotted_series_count == 21` for complete Core20 data
   - `omitted_for_crowding_count == 0` for normal Core20 path
   - BTC price prefers `coinbase:btcusd.c` when usable
   - `panel_plot_map` contains:
     - BTC Spot/Perp CVD: 15 series
     - Stable/Stable CVD: 2 series
     - Stable/Fiat CVD: 3 series
   - `panel_omitted_map == {}` for complete Core20 data
   - render CLI output includes all-series metrics

## Validation commands
```bash
python -m cvd_monitor receive --once --interval 5min --lookback-hours 6 --universe config/universe.core20.yml
python -m cvd_monitor compute --interval 5min --universe config/universe.core20.yml
python -m cvd_monitor render --interval 5min --window-hours 6 --universe config/universe.core20.yml --output out/cvd_core20_chart_all_6h.png
python -m cvd_monitor render --interval 5min --window-hours 12 --universe config/universe.core20.yml --output out/cvd_core20_chart_all_12h.png
pytest -q
```

## Acceptance
PASS if:
- plan review score >= 90
- implementation review score >= 90
- 6h/12h PNG generated and non-empty
- all eligible CVD series plotted
- BTC price uses `coinbase:btcusd.c` when available
- `plotted_series_count == 21` when all 20 CVD markets are usable
- `omitted_for_crowding_count == 0`
- explicit `panel_plot_map` and `panel_omitted_map`
- pytest passes
- no secrets printed
