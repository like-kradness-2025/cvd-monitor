# Core20 Chart Selection Review

## Baseline before Stage 6C
The previous renderer selected all 20 Core20 markets, but did not plot all eligible CVD series.

Observed baseline:

```text
selected=20
with_features=20
plotted=9
omitted_crowding=12
skipped_no_features=0
skipped_no_cvd=0
unresolved=0
```

Root causes in `cvd_monitor/renderer.py`:

1. `_select_cvd_series()` used `available[:3]`, truncating each panel to 3 eligible series.
2. The render loop used `zip(colors, series)` while `colors` contained only 3 colors, which would still cap plotting even if selection returned more series.

## Stage 6C selection policy
All eligible CVD series are plotted.

```text
If a market belongs to the panel and has usable feature rows, plot it.
Do not omit it only because of panel cap.
```

## Stage 6C result
Observed all-series render:

```text
selected=20
with_features=20
plotted=21
omitted_crowding=0
skipped_no_features=0
skipped_no_cvd=0
unresolved=0
btc_price_market=coinbase:btcusd.c
```

`plotted=21` means:
- 1 BTC price series
- 20 CVD market series

## Panel maps

BTC Spot/Perp CVD:

```text
BTCFDUSD.A
BTCUSD.A
BTCUSD_PERP.A
BTCUSDC.A
BTCUSDC_PERP.A
BTCUSDT_PERP.A
BTCUSD.F
BTCUSDT.6
BTCUSD.C
BTC-PERPETUAL.2
BTC.H
BTCUSD.K
BTCUSDT.K
BTCUSD_PERP.3
BTCUSDT_PERP.3
```

Stable/Stable CVD:

```text
FDUSDUSD.A
USDCUSD.A
```

Stable/Fiat CVD:

```text
USDTUSD.F
USDCUSD.K
USDTUSD.K
```

Panel omitted map:

```text
{}
```

## Verdict
PASS. Stage 6C removes the small panel cap and renders all eligible Core20 CVD series.
