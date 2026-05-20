# CVD Calculator Phase 2 Specification

## 1. Purpose and Scope
|| Item | Value / Detail | Note |
||---|---|---|
|| Phase | Phase 2 | Derived-feature calculator built on Phase 1 raw OHLCV data |
|| Goal | Compute and persist cumulative volume delta features from `ohlcv_raw` into a new feature table | No raw data mutation |
|| Primary package | `cvd_monitor` | Same namespace as Phase 1 receiver |
|| Source table | `ohlcv_raw` | Existing immutable input table |
|| Target table | `cvd_features` | New derived features table |
|| Supported compute interval | User-specified interval, starting with `5min` | CLI must support `--interval 5min` |
|| Out of scope | Raw ingestion changes, chart rendering, alerting, web UI, external APIs | Reserved for later phases |
|| Design principle | Deterministic, idempotent, reproducible | Same raw input must produce same feature rows |

## 2. Functional Requirements
|| Item | Value / Detail | Note |
||---|---|---|
|| Delta formula | `delta = 2 * buy_volume - volume` | Compute only when both inputs are present |
|| Sell volume formula | `sell_volume = volume - buy_volume` | Derived internally for validation/diagnostics; not required as a persisted column |
|| Quote delta formula | `delta_quote = delta * close` | Requires `close` to be present for the row |
|| CVD formula | Cumulative sum of `delta` per `market_key`, ordered by `ts` | Reset at each `market_key` boundary |
|| CVD quote formula | Cumulative sum of `delta_quote` per `market_key`, ordered by `ts` | Reset at each `market_key` boundary |
|| Buy ratio formula | `buy_ratio = buy_volume / volume` | Safe division; only compute when denominator is non-zero |
|| Buy transaction ratio formula | `buy_tx_ratio = buy_tx / tx` | Safe division; only compute when denominator is non-zero and both values are present |
|| Change windows | `cvd_change_15m` and `cvd_change_1h` | Defined relative to prior feature rows in the same series |
|| Null handling | Handle null `buy_volume` safely | Do not crash or coerce nulls into zero implicitly unless explicitly required by formula definition |
|| Row eligibility | Do not compute rows without `volume`, `buy_volume`, `close`, `tx`, or `buy_tx` | Such rows are skipped entirely from `cvd_features` |
|| Ordering rule | Process rows ordered by `ts` within each `market_key` | Deterministic result set |
|| Scope of computation | Compute per `market_key` | Never mix series across markets |
|| Raw immutability | `ohlcv_raw` must never be modified | Read-only input contract |
|| Idempotency | Re-running compute with same inputs must not change row count or create duplicates | Enforced by primary key/upsert logic |

## 3. Input Data Sources
|| Item | Value / Detail | Note |
||---|---|---|
|| Raw source database | `data/cvd_monitor.sqlite` | Same SQLite file used in Phase 1 |
|| Input table | `ohlcv_raw` | Must already exist or be creatable through existing initialization path |
|| Required raw columns | `market_key, symbol, interval, ts, close, volume, buy_volume, buy_tx, tx` | All required fields must be non-null for a row to be computed |
|| Symbol selection | Optional `--symbols` CLI filter | Accept comma-separated Coinalyze symbols such as `BTCUSD.C,BTCUSD.A` |
|| Limit selection | Optional `--limit` CLI filter | Applied after symbol filtering |
|| Interval filter | `--interval` | Feature computation uses rows from the requested interval only |
|| Row completeness | Rows missing any of `volume`, `buy_volume`, `close`, `tx`, or `buy_tx` are skipped | Preserves correctness of delta, ratio, and quote-based formulas |
|| Multi-symbol support | At least 3 symbols must be computable in standard smoke data | Required for acceptance |

## 4. Target Database Schema
|| Item | Value / Detail | Note |
||---|---|---|
|| Table | `cvd_features` | New derived features table |
|| Primary key | `(market_key, interval, ts)` | Guarantees one feature row per candle per market |
|| Columns | `market_key, symbol, interval, ts, delta, delta_quote, cvd, cvd_quote, buy_ratio, buy_tx_ratio, cvd_change_15m, cvd_change_1h, computed_at` | Exact required schema |
|| `symbol` | Text | Copied from raw input row |
|| `computed_at` | Integer epoch time in UTC | Time feature row was written |
|| Numeric columns | All feature metrics | Store as REAL where appropriate; use NULL when formula inputs are insufficient |
|| Uniqueness rule | Re-inserting same primary key must replace the existing row | Upsert semantics required |
|| Table creation | Auto-create on first compute run | No manual migration step should be required |

## 5. Formula and Calculation Rules
|| Item | Value / Detail | Note |
||---|---|---|
|| Delta | `2 * buy_volume - volume` | Core signed volume feature |
|| Sell volume | `volume - buy_volume` | Used as a conceptual mirror of delta; not persisted unless later needed |
|| Delta quote | `delta * close` | Uses candle close price as quote conversion |
|| CVD | Running sum of `delta` ordered by `ts` per `market_key` | Must include all eligible rows in order |
|| CVD quote | Running sum of `delta_quote` ordered by `ts` per `market_key` | Must include all eligible rows in order |
|| Buy ratio | `buy_volume / volume` | Safe divide; should be between 0 and 1 when inputs are valid |
|| Buy tx ratio | `buy_tx / tx` | Safe divide; should be between 0 and 1 when inputs are valid |
|| 15m change | Difference between current `cvd` and the `cvd` value 15 minutes earlier within same market series | Exact lag lookup only; if the exact prior row is not found, use NULL |
|| 1h change | Difference between current `cvd` and the `cvd` value 1 hour earlier within same market series | Exact lag lookup only; if the exact prior row is not found, use NULL |
|| Calculation basis | Ordered by `ts` ascending | Stable results require chronological ordering |
|| Skipped rows | Non-eligible raw rows are excluded from cumulative sums | Do not allow missing-input rows to silently distort the series |

## 6. Change Window Semantics
|| Item | Value / Detail | Note |
||---|---|---|
|| `cvd_change_15m` definition | `cvd(ts) - cvd(ts_minus_15m)` | For `5min` intervals, look up exactly 3 candles prior; if not found, use NULL |
|| `cvd_change_1h` definition | `cvd(ts) - cvd(ts_minus_1h)` | For `5min` intervals, look up exactly 12 candles prior; if not found, use NULL |
|| Exact timestamp match | Required | Change-window lookup must use the exact prior timestamp, not a nearest-neighbor fallback |
|| Fallback behavior | If exact lag timestamp is absent, return NULL | No alternative lag lookup behavior is permitted |
|| Interval note | For non-5min intervals, the candle count is calculated as `(target_duration / interval_duration)`. For `15m` change with `5min` interval: `15/5 = 3` candles. For `1h` change with `5min` interval: `60/5 = 12` candles. If the calculated candle count is not an integer, round down to the nearest whole candle. | Use wall-clock duration mapped to whole candles |
|| Insufficient history | Return NULL for change fields until enough history exists | First rows in a series will often have NULL change values |
|| Interval awareness | Change windows are measured in wall-clock time, not row count | Required because raw series may have gaps |

## 7. Compute Pipeline
|| Item | Value / Detail | Note |
||---|---|---|
|| Step 1 | Read eligible raw rows from `ohlcv_raw` | Filter by interval and optional symbol/limit selectors |
|| Step 2 | Group rows by `market_key` | Isolate each market series |
|| Step 3 | Sort each group by `ts` ascending | Ensure deterministic cumulative calculations |
|| Step 4 | Skip rows missing any required field (`volume`, `buy_volume`, `close`, `tx`, `buy_tx`) | Do not write incomplete feature rows |
|| Step 5 | Compute per-row formulas | Delta, ratios, quote delta |
|| Step 6 | Compute cumulative series | `cvd` and `cvd_quote` per market |
|| Step 7 | Compute window changes | `cvd_change_15m` and `cvd_change_1h` |
|| Step 8 | Upsert into `cvd_features` | Use primary key `(market_key, interval, ts)` |
|| Step 9 | Commit transaction | Must be atomic per compute batch when feasible |
|| Step 10 | Report summary | Rows read, rows skipped, rows written, symbols processed |

## 8. CLI Commands
|| Item | Value / Detail | Note |
||---|---|---|
|| Compute features | `python -m cvd_monitor compute --interval 5min` | Main Phase 2 command |
|| Compute subset | `python -m cvd_monitor compute --interval 5min --symbols BTCUSD.C,BTCUSD.A` | Restrict computation to selected symbols |
|| Compute with limit | `python -m cvd_monitor compute --interval 5min --limit 5` | Cap the number of processed symbols |
|| Inspect features | `python -m cvd_monitor inspect-features` | Summarize the feature table |
|| CLI command list | `python -m cvd_monitor compute --interval 5min`, `python -m cvd_monitor compute --interval 5min --symbols BTCUSD.C,BTCUSD.A`, `python -m cvd_monitor compute --interval 5min --limit 5`, `python -m cvd_monitor inspect-features` | These are the explicitly supported Phase 2 CLI commands |
|| CLI behavior | `compute` must not modify `ohlcv_raw` | Read-only on source table |
|| Empty selection | If no symbols remain after filtering, exit with error code 1 | Do not write features for an empty selection |
|| Default interval | No default required beyond explicit `--interval` support, but `5min` must be documented and tested | Keep behavior consistent with Phase 1 raw data |

## 9. `inspect-features` Output Requirements
|| Item | Value / Detail | Note |
||---|---|---|
|| Total rows | Count of rows in `cvd_features` | Always shown |
|| Rows by symbol | Aggregate counts grouped by symbol | Useful for coverage checks |
|| Rows by market_key | Aggregate counts grouped by market_key | Confirms per-series computation |
|| Min/max ts | Minimum and maximum feature timestamps | Indicates range of computed features |
|| Latest computed_at | Most recent `computed_at` value | Confirms compute freshness |
|| Empty database state | Show zero counts and no timestamp range | Must not crash |
|| Output format | Exactly three columns: `Item`, `Value / Detail`, `Note` | Must follow the repo’s strict 3-column layout requirement |

## 10. Error Handling and Resilience
|| Item | Value / Detail | Note |
||---|---|---|
|| Missing raw table | Fail fast with clear error | Compute requires Phase 1 data to exist |
|| Missing required columns | Fail fast or surface schema mismatch | Avoid partial or incorrect derived output |
|| Null `buy_volume` | Skip row entirely | Required by user rule |
|| Null `volume` | Skip row entirely | Required by user rule |
|| Zero denominator for ratios | Return NULL for the affected ratio | Prevent divide-by-zero errors |
|| Unexpected null `close` | Skip row entirely | Rows with null `close` are not partially computed |
|| Duplicate compute run | Replace rows for same primary key without increasing row count | Idempotent upsert contract |
|| Partial symbol failure | Continue with remaining symbols where possible | Prefer robust batch behavior |

## 11. Operational Constraints
|| Item | Value / Detail | Note |
||---|---|---|
|| Python version | 3.11+ | Match existing project runtime |
|| Database engine | SQLite | Same local file as Phase 1 |
|| Transaction strategy | Prefer batched transactions | Minimizes partial writes and improves consistency |
|| Compute determinism | Sort by `ts`, group by `market_key` | No dependence on Python hash order |
|| Raw immutability | No updates, deletes, or replaces against `ohlcv_raw` | Feature job is strictly read-only on source table |
|| Logging | Concise and non-secret-bearing | Should describe counts, not secrets |
|| Testability | Use local DB fixtures and deterministic timestamps in tests | Avoid real-time dependency where possible |

## 12. Test Plan
|| Item | Value / Detail | Note |
||---|---|---|
|| Delta formula correctness | Verify `delta = 2 * buy_volume - volume` on known rows | Core math requirement |
|| CVD cumulative per symbol | Verify running sum resets per `market_key` and follows `ts` order | Prevent cross-series contamination |
|| Null buy_volume handling | Verify rows with null `buy_volume` are skipped | Required safety rule |
|| Idempotent compute | Run compute twice and confirm row count does not change | Must not create duplicates |
|| 15m/1h change calculation | Verify `cvd_change_15m` and `cvd_change_1h` against expected history | Windowed feature requirement |
|| Raw table unchanged after compute | Snapshot `ohlcv_raw` before and after compute and confirm equality | Validates immutability |
|| Symbol filtering | Verify `--symbols` limits computation to requested symbols | CLI contract |
|| Limit filtering | Verify `--limit` caps processed symbols | CLI contract |
|| Inspect command | Verify `inspect-features` returns counts and range data | Operational visibility |
|| No duplicate rows | Confirm unique primary key prevents duplicate inserts | Schema contract |

## 13. Acceptance Criteria
|| Item | Value / Detail | Note |
||---|---|---|
|| Feature rows | Greater than 0 | Calculator produces output |
|| Symbol coverage | 3+ symbols have computed features | Minimum smoke coverage |
|| Formula correctness | All required formulas match expected values | Must hold in tests and smoke validation |
|| No duplicates | Zero duplicate rows in `cvd_features` | Primary key/upsert enforced |
|| Idempotency | Re-running compute does not change row count | Required for scheduled jobs |
|| Raw immutability | `ohlcv_raw` remains unchanged after compute | Hard requirement |
|| Tests | All required tests pass | Phase 2 not complete until test suite passes |
|| CLI support | `compute` and `inspect-features` are available | Must match documented commands |

## 14. Implementation Notes
|| Item | Value / Detail | Note |
||---|---|---|
|| Feature service | New calculator module or extension within `cvd_monitor` | Should mirror the structure of the Phase 1 receiver where practical |
|| DB helper reuse | Extend existing SQLite helper layer | Keep schema and upsert logic centralized |
|| Schema migrations | Add `cvd_features` creation without affecting `ohlcv_raw` | Raw table must remain immutable |
|| Symbol resolution | Reuse universe/config filtering from Phase 1 | Keeps CLI semantics consistent |
|| Time handling | Use UTC epoch integers consistently | Avoid timezone ambiguity |
|| Upsert semantics | `INSERT OR REPLACE` or equivalent on `(market_key, interval, ts)` | Must not create duplicates |
|| Upsert delete/insert behavior | `INSERT OR REPLACE` is used for idempotent upserts; it will delete and re-insert rows on update | Acceptable for Phase 2 because there are no foreign key dependencies on `cvd_features` |
|| Series continuity | Cumulative values must be computed from the ordered eligible rows only | No hidden state across runs |
|| Documentation | This file is the implementation contract for Phase 2 | Keep aligned with tests and CLI output |

## 15. Delivery Definition
|| Item | Value / Detail | Note |
||---|---|---|
|| Phase 2 complete | `compute` populates `cvd_features`, `inspect-features` works, tests pass, and raw data remains unchanged | Minimum shippable calculator |
|| Future phases | Alerting, rendering, export, and richer analytics | Explicitly deferred |
|| Verification expectation | Smoke-run the calculator on existing SQLite data and confirm multi-symbol output | Must demonstrate real computed rows |