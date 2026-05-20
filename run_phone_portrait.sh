#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python -m cvd_monitor render \
  --interval 5min \
  --window-hours 24 \
  --cum-window-hours 72 \
  --universe config/universe.core20.yml \
  --output out/cvd_core20_latest.png
python - <<'PY'
from pathlib import Path
import struct
p = Path('out/cvd_core20_latest.png')
with p.open('rb') as f:
    sig = f.read(24)
if sig[:8] != b'\x89PNG\r\n\x1a\n':
    raise SystemExit(f'{p} is not a PNG')
width, height = struct.unpack('>II', sig[16:24])
print(f'image={p} size={width}x{height} portrait={height > width}')
PY
