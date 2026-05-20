# Phone portrait output fix

The bundled preview `out/cvd_core20_latest.png` is now the phone portrait layout.

Previous package issue:
- renderer code generated portrait output when run manually
- but the pre-bundled `out/cvd_core20_latest.png` still contained an older landscape chart
- this made the newest ZIP look like the old layout when opening the latest PNG directly

Current expected files:
- `out/cvd_core20_latest.png`: primary output, phone portrait layout
- `out/cvd_core20_latest_phone_portrait.png`: same preview alias for comparison

Verified:
- `python -m cvd_monitor render --interval 5min --window-hours 6 --universe config/universe.core20.yml --output out/cvd_core20_latest.png`
- output size: about 1093 x 2377 px
- `pytest -q`: 13 passed
