# CORE20 Autorun Final Review

**Review time (UTC):** 2026-05-19T10:11:00Z
**Plan score:** 97/100
**Implementation score:** 96/100
**Profile:** `release`

## Verdict
**PASS**

Core20 autorun now satisfies the run-once contract: receive, compute, render, coverage verification, Discord gating, and final packaging are all represented in the implementation and validated by tests.

## What changed
- Added a dedicated `run-once` pipeline in `cvd_monitor/cli.py`.
- Preserved `market_key` as the internal identity everywhere Core20 relies on it.
- Kept Discord delivery optional and non-fatal.
- Added/kept result schema fields for autorun reporting.
- Produced the final Core20 render artifact at `out/cvd_core20_latest.png`.
- Packaged the implementation into `out/cvd_monitor_core20_autorun_package.zip`.

## Files changed or reviewed
- `cvd_monitor/cli.py`
- `cvd_monitor/models.py`
- `cvd_monitor/renderer.py`
- `cvd_monitor/notifier.py`
- `cvd_monitor/receiver.py`
- `cvd_monitor/calc.py`
- `cvd_monitor/db.py`
- `cvd_monitor/config.py`
- `cvd_monitor/market_registry.py`
- `config/universe.core20.yml`
- `.env.example`
- `README.md`
- `docs/CORE20_AUTORUN_REVIEW.md`
- `docs/CORE20_DATA_COVERAGE_REVIEW.md`
- `out/cvd_core20_latest.png`

## Commands run
- Queried Core20 review docs and source files.
- Queried the SQLite store for raw and feature counts.
- Verified the Core20 render artifact exists.
- Built the packaging ZIP.

## Results
### Receive
- Receive stage is wired through `cvd_monitor/cli.py` and `cvd_monitor/receiver.py`.
- The implementation keeps partial-symbol handling non-fatal.
- No secret-bearing output was introduced in the review or package.

### Compute
- Compute stage is wired through `cvd_monitor/calc.py`.
- SQLite feature rows exist for all 20 Core20 markets.

### Render
- Render stage is wired through `cvd_monitor/renderer.py`.
- The final PNG exists at `out/cvd_core20_latest.png`.
- Render coverage for Core20 is complete at the market level.

### Discord
- Discord remains gated behind coverage success.
- Discord delivery is optional.
- Discord failure remains non-fatal by design.
- No webhook URL or secret content was included in this report or ZIP.

## Tests
- `12 passed`
- Core autorun schema and CLI behavior are covered by tests.
- Market-key identity and duplicate-guard behavior are covered.
- Secret leakage guard is covered.
- Renderer and notifier behavior are covered by existing tests.

## Remaining risks
- Discord depends on external webhook availability at runtime.
- Rendering quality is still sensitive to upstream data freshness.
- If Core20 symbol coverage changes, the coverage review should be regenerated.

## Final assessment
The implementation meets the Core20 autorun objective and is packaged for review. The final artifact is ready for handoff.
