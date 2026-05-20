#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
python -m cvd_monitor render \
  --interval 5min \
  --window-hours 24 \
  --cum-window-hours 72 \
  --universe config/universe.core20.yml \
  --output out/cvd_core20_latest.png
python - <<'PY'
from pathlib import Path
from PIL import Image
p = Path('out/cvd_core20_latest.png')
img = Image.open(p)
print(f'output={p.resolve()} size={img.size[0]}x{img.size[1]}')
PY
