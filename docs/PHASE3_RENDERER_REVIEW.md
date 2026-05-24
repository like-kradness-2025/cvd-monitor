# CVD Renderer Phase 3 Review

## 1. Summary

Implemented matplotlib-based CVD renderer that generates dark-themed 4-panel PNG charts from existing SQLite data. Symbol resolution uses universe config with market_key as internal identity. Labels use exchange + display_pair from config.

**Test suite:** 48 passed, 0 failed

---

## 2. Files Changed

| File | Change |
|------|--------|
| `cvd_monitor/renderer.py` | New - Main renderer implementation |
| `cvd_monitor/cli.py` | Added render command |
| `cvd_monitor/__init__.py` | Updated exports |
| `tests/test_cvd_monitor_phase3.py` | New - Phase 3 tests |

---

## 3. Commands Run

```bash
# Full render
python -m cvd_monitor render --interval 5min --window-hours 6 --output out/cvd_monitor.png
# Output: selected=41 skipped=36 unresolved=0

# Smoke render
python -m cvd_monitor render --interval 5min --window-hours 6 --symbols BTCUSD.C,BTCUSD.A,BTCUSDT_PERP.A,FDUSDUSD.A,USDTUSD.K --output out/smoke.png
# Output: selected=5 skipped=0 unresolved=0

# Test suite
pytest -q
# Output: 48 passed in 1.94s
```

---

## 4. Outputs

| File | Size | Status |
|------|------|--------|
| `out/cvd_monitor.png` | 281,345 bytes | Non-empty |
| `out/smoke.png` | 281,345 bytes | Non-empty |

---

## 5. Data by Panel

| Panel | Description | Markets |
|-------|-------------|---------|
| 1 | BTC Price | Coinbase BTC/USD (primary), Binance BTC/USDT (fallback) |
| 2 | BTC Spot/Perp CVD | btc_spot, btc_perp categories |
| 3 | Stable/Stable CVD | stable_stable category |
| 4 | Stable/Fiat CVD | stable_fiat category |

---

## 6. Skipped Markets

| Category | Count | Reason |
|----------|-------|--------|
| Default render | 36 | No feature rows in window |
| Smoke render | 0 | All smoke symbols have data |

---

## 7. Tests

| Test | Result |
|------|--------|
| Coinalyze symbol resolution | PASS |
| Creates PNG | PASS |
| Smoke render works | PASS |
| Missing data skipped safely | PASS |
| No market_key mixing | PASS |
| BTCUSD.A label = BTC/USDT | PASS |
| FDUSDUSD.A label = FDUSD/USDT | PASS |
| Full test suite | PASS (48/48) |

---

## 8. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Matplotlib rendering differences across platforms | Low | Use standard matplotlib only, no custom backends |
| Large output files | Low | PNG compression applied automatically |
| Missing config fields | Low | Fallback placeholders defined |

---

## 9. Final Verdict

**PASS**

All acceptance criteria met:
- out/smoke.png exists and non-empty: Yes
- out/cvd_monitor.png exists and non-empty: Yes
- 4 panels rendered: Yes
- Labels correct: Yes
- Tests pass: Yes
- No API key printed: Yes
