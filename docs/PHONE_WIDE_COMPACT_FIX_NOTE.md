# Phone wide compact portrait fix

- Layout version: `phone_portrait_wide_compact_cum_delta_v4`
- Target canvas: `1280 x 1920 px` via `figsize=(7.11112, 10.666667), dpi=180`.
- Height is kept from v3, width is increased to reduce horizontal compression on smartphone previews.
- `bbox_inches='tight'` is intentionally not used, so the saved PNG size remains deterministic.
