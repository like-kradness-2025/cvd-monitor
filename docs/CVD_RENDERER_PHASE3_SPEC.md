# CVD Renderer Phase 3 Specification

## 1. Purpose and Scope

| Item | Value / Detail | Note |
|---|---|---|
| Phase | Phase 3 | Matplotlib-based static renderer for derived CVD features |
| Goal | Render a single PNG chart from `cvd_features` with four panels | No GUI, no live streaming |
| Primary package | `cvd_monitor` | Same namespace as existing receiver and calculator |
| Source table | `cvd_features` | Phase 2 output table |
| Config source | `config/universe.generated.yml` | Used for symbol resolution, labels, and market metadata |
| Output | PNG file | Must be written to disk |
| Rendering library | `matplotlib` only | No Plotly, no web framework |
| Theme | Dark theme | Suitable for terminal/dashboard use |
| Default CLI | `python -m cvd_monitor render --interval 5min --window-hours 6 --output out/cvd_monitor.png` | Main rendering entrypoint; if `--symbols` is omitted, render the configured default market set |
| Smoke CLI | `python -m cvd_monitor render --interval 5min --window-hours 6 --symbols BTCUSD.C,BTCUSD.A,BTCUSDT_PERP.A,FDUSDUSD.A,USDTUSD.K --output out/smoke.png` | Validates explicit symbol filtering and multi-panel behavior |
| Design principle | Deterministic, isolated per market, and safe with sparse data | Never mix rows across market keys |

## 2. Functional Requirements

| Item | Value / Detail | Note |
|---|---|---|
| Internal identity | `market_key` | All joins, grouping, and selection must use `market_key` internally |
| External symbol input | `--symbols` is optional | When omitted, render the configured default market set from the universe config |
| External symbol input format | `--symbols` accepts a comma-separated list of Coinalyze symbols | Input examples: `BTCUSD.C`, `BTCUSD.A`, `BTCUSDT_PERP.A` |
| Limit interaction | `--limit` applies globally after symbol resolution or default-set expansion and before per-panel selection | It caps the final resolved render set, does not change resolution semantics, and is enforced before any panel-specific crowding logic |
| Default market set | If `--symbols` is omitted, use all render-eligible markets from the universe config, ordered by config priority | No heuristic discovery from data tables |
| Symbol resolution | Resolve input symbols through the universe config to `market_key` | Do not infer anything from rendered labels or feature-table contents |
| Label source | Use `exchange + display_pair` | Example: `coinbase BTC/USD` or `binance FDUSD/USDT` |
| Label rule | Never derive `display_pair` from `coinalyze_symbol` | Use config field only |
| Data source | Query `cvd_features` joined by `market_key` | Only feature rows are rendered |
| Ordering | Sort each series by `ts` ascending | Deterministic and chronological |
| Timestamp conversion | Convert `ts` to timezone-aware datetime | Use UTC for axis and range text |
| Metric selection | Use `cvd_quote` when available, else `cvd` | Quote-denominated series is preferred when present |
| Missing metrics | If both `cvd_quote` and `cvd` are null for a row, exclude that row from plotted data | Do not invent values |
| Panel count | Exactly four panels | See section 4 |
| Missing markets | Skip markets with no feature rows and report them | Rendering must continue for remaining markets |
| Crowding policy | When too many markets are present, show highest-priority available series first, up to the per-panel maximum series count defined in section 4 | Preserve readability; selection order is priority ascending, then `market_key` alphabetically |
| Priority source | Use universe config priority order | Lower numeric priority means higher importance if config uses ascending sort |
| Market isolation | No market mixing | A series must never combine rows from different `market_key` values |
| Output directory | Create parent directory automatically | Do not require it to exist beforehand |
| GUI requirement | None | Renderer must work headless |
| Save behavior | Write PNG and close the figure | Avoid interactive windows |

## 3. Inputs and Selection Rules

### 3.1 CLI Arguments

| Argument | Required | Type | Description |
|---|---:|---|---|
| `--interval` | Yes | string | Feature interval to render, e.g. `5min` |
| `--window-hours` | Yes | integer | Amount of history to include in the chart |
| `--output` | Yes | path | Target PNG path |
| `--symbols` | No | comma-separated string | Optional filter to selected Coinalyze symbols before resolution |
| `--limit` | No | integer | Optional global cap on resolved markets, applied after symbol resolution or default-set expansion and before per-panel selection |
| `--log-level` | No | string | Standard logging level |

### 3.2 Market Resolution

| Rule | Behavior |
|---|---|
| Input form | Split `--symbols` by comma, trim whitespace, ignore empty tokens |
| Resolution index | Build directly from the universe config entries and their explicit fields; do not route through market registry helpers for resolution |
| Canonical path | Resolve in this order: (1) exact Coinalyze symbol match in the universe config, (2) exact `market_key` match, (3) exact `symbol_on_exchange` match only if the universe entry explicitly exposes it | No other fallback paths are allowed |
| Fallback order | If multiple universe entries match the same external symbol, choose the one with the lowest numeric `priority`; if tied, use deterministic config order |
| Internal handling | After resolution, only `market_key` is used for joins and grouping |
| Duplicate inputs | Duplicate symbols in the CLI must not duplicate plots |
| Unknown symbols | Exclude them from the render set and report them as unresolved |
| Empty result | If no symbols resolve and the default set is empty, exit non-zero with a clear error |

### 3.3 Data Loading Window

| Rule | Behavior |
|---|---|
| Time window | Load feature rows whose timestamps fall within the last `window-hours` relative to the render time |
| End time | Use the latest available feature timestamp for each selected market when possible; otherwise use current UTC time |
| Start time | `end_time - window_hours` |
| Interval scope | Use only rows for the requested `--interval` |
| Column scope | At minimum load `market_key`, `symbol`, `interval`, `ts`, `cvd`, `cvd_quote`, and any price field required for BTC panel rendering |
| Sorting | Sort by `market_key`, then `ts` |

## 4. Panel Specification

The renderer must create a single figure with four stacked panels.

### Panel 1: BTC Price

| Item | Value / Detail | Note |
|---|---|---|
| Purpose | Show BTC price context | Primary trend reference panel |
| Primary series | The highest-priority BTC spot market from the universe config with a non-null `close` value in `ohlcv_raw` joined by `market_key` | Config priority determines which BTC spot market is preferred |
| Fallback series | If no BTC spot market has usable `close`, use the highest-priority BTC perp market with usable `close`; if none exist, use the highest-priority remaining BTC market with usable `close` | Deterministic fallback only |
| Data source | `ohlcv_raw.close` joined by `market_key` for the selected BTC market | No other price field may be used for this panel |
| Visual style | Bright price line with readable contrast | Distinct from CVD panels |
| Selection rule | Use the highest-priority available BTC market from the universe config | No blending of unrelated BTC markets |
| Missing data | If no BTC market has a usable price series, render a placeholder message in-panel and continue | Do not fail the whole render |
| Usable price definition | A BTC market is usable only when at least one `ohlcv_raw.close` row exists in the requested window after joining by `market_key` | Ignore `open`, `high`, `low`, `volume`, and any derived price fields |

### Panel 2: BTC Spot/Perp CVD

| Item | Value / Detail | Note |
|---|---|---|
| Purpose | Compare BTC spot and perp CVD behavior | Core flow comparison |
| Markets | Universe entries where `base == BTC` and `market_type == spot` or `market_type == future` | Use config metadata only |
| Series | One line per `market_key`, with a maximum of 3 plotted series total | No aggregation across markets |
| Label format | `exchange display_pair` | Example: `binance BTC/USDT` |
| Visual style | Distinct but compact line styling | Maintain readability when 2+ series are present |
| Series selection | If more than 3 markets qualify, plot the 3 markets selected by priority ascending, then `market_key` alphabetically, and only among markets with usable data in the window | Drop the rest and report them as omitted due to crowding |

### Panel 3: Stable/Stable CVD

| Item | Value / Detail | Note |
|---|---|---|
| Purpose | Show stablecoin-to-stablecoin flows | Useful for liquidity routing |
| Markets | Universe entries where `category == stable_stable` | Based on config metadata only |
| Series selection | Highest-priority available markets first if crowded, up to 3 series total; select by priority ascending, then `market_key` alphabetically, after excluding markets with no usable data in the window | Limit legend overload |
| Label format | `exchange display_pair` | Use config display pair verbatim |

### Panel 4: Stable/Fiat CVD

| Item | Value / Detail | Note |
|---|---|---|
| Purpose | Show fiat on/off-ramp style stablecoin flows | Useful for USD-linked flow monitoring |
| Markets | Universe entries where `category == stable_fiat` | Based on config metadata only |
| Series selection | Highest-priority available markets first if crowded, up to 3 series total; select by priority ascending, then `market_key` alphabetically, after excluding markets with no usable data in the window | Favor the most important series |
| Label format | `exchange display_pair` | Example: `binance FDUSD/USDT` |

## 5. Styling and Layout Rules

| Item | Value / Detail | Note |
|---|---|---|
| Figure style | Dark background with light text | Matplotlib theme must be set explicitly |
| Title | Clear global title | Include render interval and panel purpose if helpful |
| Timestamp range | Show rendered UTC time range in the figure header or footer | Must be readable without inspecting axes |
| Grid | Enabled, subtle, and consistent across panels | Avoid visual clutter |
| Legend | Compact and small-font | Legends should not overwhelm plots |
| Labels | Readable axis labels and tick formatting | Especially for crowded markets |
| Tick density | Keep x-axis sparse enough to remain legible | Use concise datetime formatting |
| Spacing | Tight layout or equivalent | Prevent overlap between panels |
| Color usage | Stable, consistent palette by panel/series | Do not reuse identical colors for adjacent series if avoidable |
| Export | Save PNG with sufficient DPI for downstream review | No interactive display |

## 6. Data Handling Rules

| Item | Value / Detail | Note |
|---|---|---|
| Source table | `cvd_features` | No raw OHLCV access required for core CVD panels |
| Join key | `market_key` | Required for correctness |
| Sort key | `ts` ascending | Required before plotting |
| Datetime conversion | `datetime.fromtimestamp(ts, tz=timezone.utc)` or equivalent | Preserve UTC semantics |
| CVD choice | Prefer `cvd_quote` when not null; otherwise use `cvd` | The preferred rendered value may differ by row only if necessary |
| Crowded selection | Limit plotted series per panel when necessary | Keep the highest-priority markets visible, using priority ascending then `market_key` alphabetical ordering after filtering to markets with usable data in the window |
| Maximum series per panel | 3 plotted series maximum for each non-price CVD panel; extra qualifying markets are omitted after priority ordering | This is a hard cap, not a soft guideline |
| No market mixing | Do not merge rows from separate market keys into a single series | This is a hard requirement |
| Missing rows | Drop rows with no usable CVD metric rather than backfilling | Preserve data integrity |
| Sparse markets | If a market has no rows in the requested time window, skip it and report it | Panel can still render with remaining markets |

## 7. Error Handling and Resilience

| Item | Value / Detail | Note |
|---|---|---|
| Missing output directory | Create it automatically | Must not fail due to missing parent dirs |
| Missing universe config | Fail fast with clear error | Renderer cannot resolve labels safely without config |
| Missing feature table | Fail fast with a clear error | The renderer requires `cvd_features`; empty panels are not an acceptable substitute for a missing table |
| Missing market rows | Skip safely and report | Do not abort if some markets are empty |
| Missing BTC fallback | Use the BTC price selection rules in section 4; if no usable BTC price market exists, render a placeholder message in the BTC price panel and continue | Do not cross-wire unrelated markets |
| Bad symbol input | Ignore invalid tokens and report unresolved items | Robust CLI behavior |
| No selected data | Exit non-zero with a clear message | Avoid producing an empty misleading chart |
| Matplotlib backend issues | Force a non-GUI backend if necessary | Headless compatibility is required |

## 8. Output Specification

| Item | Value / Detail | Note |
|---|---|---|
| File type | PNG | Required output format |
| Path | User-specified via `--output` | Absolute or relative path accepted |
| Parent directory | Auto-created | Convenience and robustness |
| Return value | Output path or success code | CLI should print a concise completion summary |
| File existence | Must exist after successful render | Verified in tests |
| File content | Non-empty image bytes | Smoke test should ensure the file is not zero-length |

## 9. Tests Required

| Test | Expected Result | Note |
|---|---|---|
| Coinalyze symbol resolution | CLI resolves symbols to the correct `market_key` entries | Must use universe config, not string heuristics |
| Creates PNG | Render command writes a PNG to disk | Core output contract |
| Smoke render works | Example command with multiple symbols succeeds | Validates end-to-end flow |
| Missing data skipped safely | Markets with no feature rows are skipped and reported | No crash |
| No market_key mixing | Each plotted series uses one `market_key` only | Prevent contamination |
| BTCUSD.A label | Renders as `binance BTC/USDT` or the config-defined exchange/display pair for that market | Must not derive from `coinalyze_symbol` |
| FDUSDUSD.A label | Renders as `binance FDUSD/USDT` or the config-defined exchange/display pair for that market | Must use universe display_pair |
| Priority ordering | In crowded panels, higher-priority markets appear before lower-priority ones | Readability requirement |
| Dark theme | Figure background and axes use dark styling | Visual regression guard |

## 10. Reporting Requirement

A review document may be created at `docs/PHASE3_RENDERER_REVIEW.md` as a deliverable artifact.

### Report Content Expectations

| Section | What to include |
|---|---|
| Summary | Short description of what Phase 3 delivered |
| Files changed | List renderer code, tests, and docs updates |
| Commands run | Exact CLI commands used to verify the renderer |
| Outputs | PNG path(s) and whether they were generated successfully |
| Data by panel | Which markets/series appear in each of the four panels |
| Skipped markets | Markets omitted due to missing rows or resolution problems |
| Tests | Pass/fail summary for each required test |
| Risks | Any remaining caveats such as sparse data or crowding limits |
| Verdict | Clear completion status for Phase 3 |

## 11. Implementation Notes

| Item | Value / Detail | Note |
|---|---|---|
| Module location | Prefer a new `cvd_monitor/render.py` or similar renderer module | Keep CLI thin |
| CLI integration | Add a new `render` subcommand to `python -m cvd_monitor` | Match the required command form |
| Shared config | Reuse existing universe config loading and explicit field access; do not depend on market registry helpers for symbol resolution | Avoid duplicating resolution logic |
| Data access | Reuse SQLite helpers from `cvd_monitor.db` | Keep query logic centralized |
| Backend setup | Set Matplotlib backend for headless execution before importing pyplot if needed | Avoid GUI dependencies |
| Figure closing | Always close figures after save | Prevent resource leaks in batch use |
| Logging | Concise and informative | Report selected markets, skipped markets, and output path |
| Determinism | Sort series and panels consistently | Render output should be stable across runs with identical input |

## 12. Acceptance Criteria

| Item | Value / Detail | Note |
|---|---|---|
| CLI available | `python -m cvd_monitor render ...` works | Required entrypoint |
| PNG output | Output file is created successfully | Must be on disk |
| Smoke command | Multi-symbol render command succeeds | Covers the requested smoke path |
| Label correctness | Labels use exchange + display_pair | No derived labels from Coinalyze symbols |
| Missing rows | Skipped safely and reported | Robustness requirement |
| Market isolation | No market_key mixing anywhere in plotting logic | Hard correctness requirement |
| Styling | Dark theme, readable labels, grid, compact legend | Visual spec satisfied |
| BTC price source | BTC price panel uses `ohlcv_raw.close` joined by `market_key` only | No alternative price field may be substituted |
| Crowd cap | Each non-price CVD panel renders no more than 3 series | Hard selection limit |
| Config fallback | Missing universe metadata fields fall back to explicit "unknown"-style placeholders and category-based inclusion rules must ignore missing fields rather than assume completeness | Renderer must not crash on partial config |
| Report artifact | If created, `docs/PHASE3_RENDERER_REVIEW.md` should summarize verification and outcomes | Documentation deliverable, not a runtime dependency |
| Tests | Required tests pass | Phase 3 not complete otherwise |

## 13. Delivery Definition

Phase 3 is complete when all of the following are true:

- The `render` CLI exists and generates a PNG with the required four-panel layout.
- Symbol resolution uses the universe configuration directly and internal `market_key` identity.
- Markets with no feature rows are skipped safely and reported.
- The renderer uses `cvd_quote` when available, otherwise `cvd`.
- The chart uses a dark matplotlib theme, writes output directories automatically, and runs headless.
- The required tests pass.
- The review artifact `docs/PHASE3_RENDERER_REVIEW.md` may be produced as delivery documentation, but it is not a runtime requirement.
