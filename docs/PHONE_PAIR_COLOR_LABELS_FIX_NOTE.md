# PHONE_PAIR_COLOR_LABELS_FIX_NOTE

## Change
- CVD line colors now use an exchange-agnostic pair key: `BASE/QUOTE`.
- The key ignores `market_type`, so spot and futures/perp lines share the same color when they represent the same target pair.
  - Example: `BTC/USDT` spot and `BTC/USDT` perp use the same color.
  - Example: `USDT/USD` on Kraken and Bitfinex use the same color.
- Exchange separability is preserved with subtle line styles while keeping the color identity common.

## Layout version
`phone_portrait_wide_pair_color_labels_cum_delta_v8`
