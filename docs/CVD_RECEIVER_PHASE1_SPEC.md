# CVD Receiver Phase 1 Specification

## 1. Purpose and Scope
| Item | Value / Detail | Note |
|---|---|---|
| Phase | Phase 1 | Initial Coinalyze OHLCV ingestion only |
| Goal | Fetch 5-minute OHLCV data from Coinalyze and persist raw bars to SQLite | No derived CVD calculation in Phase 1 |
| Primary package | `cvd_monitor` | CLI entry point and receiver implementation |
| Database | `data/cvd_monitor.sqlite` | SQLite file managed locally |
| API key | `COINALYZE_API_KEY` | Plain API key sent in the `api_key` header; never print or log |
| Supported interval | `5min` only | Fixed for Phase 1 |
| Out of scope | Proxy CVD, chart rendering, notifications, advanced scheduling | Reserved for later phases |

## 2. Functional Requirements
| Item | Value / Detail | Note |
|---|---|---|
| OHLCV fetch | Call Coinalyze OHLCV history endpoint | Base URL `https://api.coinalyze.net` |
| Auth | Send `api_key: <COINALYZE_API_KEY>` header | Use the API key value exactly; do not use Bearer auth |
| Endpoint | `/v1/ohlcv-history` | Request multiple symbols via query parameter |
| Query params | `symbols`, `interval`, `from`, `to` | `from` and `to` are epoch timestamps in milliseconds |
| Raw persistence | Save each returned bar to `ohlcv_raw` | Upsert must be idempotent |
| CLI mode | Support one-shot receive and database inspection | See command section |
| Partial failures | Continue processing remaining symbols if one symbol fails | Failures should be reported per symbol |
| Rate limiting | Max 60 requests per minute, with 1 second delay between requests | Retry 3 times with exponential backoff of 1s, 2s, 4s; on 429 wait for `Retry-After` or 30 seconds default |
| Incomplete candles | Exclude the latest incomplete candle | Never store the current unfinished 5m candle |
| Refetch policy | Re-fetch the last 1 hour of data or the last 2 completed candles, whichever is larger | Safe overlap is required on every run |

## 3. Input Data Sources
| Item | Value / Detail | Note |
|---|---|---|
| Market universe | `config/universe.generated.yml` | Source of markets and metadata |
| Symbol list | `coinalyze_symbol` values from enabled markets | Example: `BTCUSD.C` |
| Smoke symbols | `BTCUSD.C`, `BTCUSD.A`, `BTCUSDT_PERP.A`, `FDUSDUSD.A`, `USDTUSD.K` | Must be supported by tests or smoke validation |
| CLI symbol filter | Optional comma-separated list | Limits run to selected symbols |
| CLI limit | Optional cap on number of markets processed | Applied after filtering and enablement checks; max 10 symbols per API request batch |
| Empty symbol list | No symbols remain after filtering | Exit with error code 1 |
| Lookback | Configurable hours | Used to compute `from` boundary |

## 4. Database Schema
| Item | Value / Detail | Note |
|---|---|---|
| Table | `ohlcv_raw` | Single table in Phase 1 |
| Primary key | `(market_key, interval, ts)` | Schema migration must change any existing `(symbol, interval, ts)` primary key to this key |
| Required columns | `market_key, symbol, exchange, symbol_on_exchange, market_type, category, interval, ts, open, high, low, close, volume, buy_volume, tx, buy_tx, fetched_at` | Must all exist in schema |
| Nullable columns | `buy_volume`, `tx`, `buy_tx` | Store `NULL` when missing in API payload |
| Timestamp field | `ts` | Bar timestamp for the candle |
| Fetch timestamp | `fetched_at` | Local ingest time for traceability |
| Uniqueness rule | Re-inserting same PK updates row | Must not create duplicates |

## 5. Data Mapping Rules
| Item | Value / Detail | Note |
|---|---|---|
| API `timestamp` | Map to `ts` | Preserve the bar time as integer |
| API `open` | Map to `open` | Numeric |
| API `high` | Map to `high` | Numeric |
| API `low` | Map to `low` | Numeric |
| API `close` | Map to `close` | Numeric |
| API `volume` | Map to `volume` | Numeric |
| API `bv` | Map to `buy_volume` | If absent, store `NULL` |
| API `btx` | Map to `buy_tx` | If absent, store `NULL` |
| API `tx` | Map to `tx` | If absent, store `NULL` |
| Market metadata | Populate `market_key`, `symbol`, `exchange`, `symbol_on_exchange`, `market_type`, `category` | Taken from universe config |
| Ingest time | Populate `fetched_at` from local clock | Use UTC and integer or epoch-compat format consistently |

## 6. Candle Window Logic
| Item | Value / Detail | Note |
|---|---|---|
| Interval length | 5 minutes | Fixed interval size |
| Lookback input | Hours | CLI argument, converted to fetch window |
| Fetch window | Retrieve enough bars to cover lookback plus overlap | Overlap allows safe refetching |
| Completion rule | A candle is complete if its timestamp (close time) is `<= (current UTC time - 1 minute)` | This 1-minute buffer accounts for API latency and prevents partial candles |
| Ingest rule | Only completed bars are persisted | Applies regardless of symbol |
| Idempotency | Safe to re-run same window repeatedly | Primary key and upsert handle overlap |

## 7. CLI Commands
| Item | Value / Detail | Note |
|---|---|---|
| Receive once | `python -m cvd_monitor receive --once --interval 5min --lookback-hours 6` | Default one-shot ingestion |
| Receive subset | `python -m cvd_monitor receive --once --interval 5min --lookback-hours 6 --symbols BTCUSD.C,BTCUSD.A` | Process only selected symbols |
| Receive limit | `python -m cvd_monitor receive --once --interval 5min --lookback-hours 6 --limit 5` | Cap the number of processed symbols |
| Inspect DB | `python -m cvd_monitor inspect-db` | Print database summary in a strict 3-column table |
| CLI behavior | `receive` should initialize DB if needed | Safe on empty database |
| Exit behavior | `receive` should return success even when one symbol fails | Per-symbol errors do not abort the run |

## 8. `inspect-db` Output Requirements
| Item | Value / Detail | Note |
|---|---|---|
| Total rows | Count of rows in `ohlcv_raw` | Always shown |
| Rows by category | Aggregate row counts grouped by category | Useful for coverage checks |
| Rows by symbol | Aggregate row counts grouped by symbol | Shows data distribution |
| Min/max ts | Minimum and maximum candle timestamps in the table | Indicates available history |
| Latest completed candle | Most recent candle timestamp that is complete | Must not report unfinished candle as latest completed |
| DB path | Absolute or configured database path | Always shown |
| Empty database state | Should display zero counts and indicate no candle timestamps | Must not crash |
| Output format | Exactly three columns: `Item`, `Value / Detail`, `Note` | Header row and separator row must match the rest of this spec |

## 9. Error Handling and Resilience
| Item | Value / Detail | Note |
|---|---|---|
| API failure on one symbol | Log/report symbol-specific failure and continue | Do not fail the entire run |
| Missing API key | Fail fast before network calls | Do not attempt unauthenticated requests |
| Invalid symbol mapping | Skip symbol and report issue | Do not break other symbols |
| Rate limit response | Retry up to 3 times with exponential backoff of 1s, 2s, 4s | On HTTP 429, honor `Retry-After` header or wait 30 seconds if absent |
| Empty response | Treat as no data for that symbol | Not an exception by itself |
| Partial payload fields | Store available numeric fields and `NULL` where omitted | Preserve raw record consistency |
| Empty symbol list after filtering | Exit immediately with error code 1 | Do not send API requests when no symbols remain |

## 10. Operational Constraints
| Item | Value / Detail | Note |
|---|---|---|
| Python version | 3.11+ | Required runtime |
| Database path | `data/cvd_monitor.sqlite` | Default local storage |
| Request volume | Maximum 60 RPM | Enforced with 1 second delay between requests |
| Batch size | Maximum 10 symbols per API request batch | Split larger symbol sets into multiple requests |
| DB initialization | Auto-create and migrate `data/cvd_monitor.sqlite` on first run | No manual setup step required |
| Logging | Keep logs concise and non-secret-bearing | Never include API key or secret header values |
| Determinism | Tests should mock API and time | Avoid real network in unit tests |

## 11. Test Plan
| Item | Value / Detail | Note |
|---|---|---|
| Config load test | Verify configuration and universe load successfully | Ensures receiver can resolve markets |
| Subset receive test | Verify symbol filtering works | Only requested symbols are fetched/saved |
| Unfinished candle exclusion test | Confirm current incomplete candle is skipped | Core correctness requirement |
| Idempotent upsert test | Re-run same bars and confirm no duplicates | Must preserve primary key uniqueness |
| Null bv/tx/btx test | Confirm missing `buy_volume`, `tx`, `buy_tx` become `NULL` | Matches schema contract |
| Per-symbol failure continues test | One failing symbol does not abort others | Resilience requirement |
| inspect-db empty/non-empty test | Validate both zero-row and populated outputs | Ensures CLI usability |
| Required columns test | Confirm all required columns are present in `ohlcv_raw` | Schema contract must be enforced |
| CLI coverage test | Confirm all documented CLI commands are supported | Includes `receive` and `inspect-db` |

## 12. Acceptance Criteria
| Item | Value / Detail | Note |
|---|---|---|
| Row count | Greater than 0 after smoke run | Must persist actual data |
| Symbol coverage | At least 3 symbols saved | Confirms multi-symbol ingestion |
| buy_volume | Present where Coinalyze supplies it | Missing values may remain null |
| Duplicates | None in `ohlcv_raw` | Enforced by primary key/upsert |
| Unfinished candles | None stored | Latest incomplete candle excluded |
| Smoke symbols | All 5 smoke symbols present in universe config and successfully fetched during smoke test | `BTCUSD.C`, `BTCUSD.A`, `BTCUSDT_PERP.A`, `FDUSDUSD.A`, `USDTUSD.K` must all pass |
| Tests | All listed tests pass | Required before Phase 1 sign-off |
| DB initialization | First run creates or migrates the SQLite DB automatically | Verified by smoke or startup test |

## 13. Implementation Notes
| Item | Value / Detail | Note |
|---|---|---|
| Receiver class | `CoinalyzeOhlcvReceiver` | Main orchestration class |
| DB helper reuse | Use existing SQLite helpers where possible | Keep schema changes centralized |
| Symbol selection | Default to enabled markets from universe config | CLI filter narrows this set |
| Time handling | Use UTC consistently | Avoid timezone ambiguity |
| Upsert semantics | Write latest data for same `(market_key, interval, ts)` | Supports historical refreshes after PK migration |
| Validation | Reject malformed payload rows individually | A bad record should not block the batch |

## 14. Delivery Definition
| Item | Value / Detail | Note |
|---|---|---|
| Phase 1 complete | CLI works, raw OHLCV stored, inspect-db reports summary, tests pass | Minimum shippable receiver |
| Future phases | Derived metrics, alerts, richer reporting | Explicitly deferred |
| Documentation | This spec should be used as the implementation contract | Keep aligned with tests and code |
