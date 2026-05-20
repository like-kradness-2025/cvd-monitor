from pathlib import Path
import cvd_monitor
from cvd_monitor import renderer
print('cvd_monitor_file=', Path(cvd_monitor.__file__).resolve())
print('renderer_file=', Path(renderer.__file__).resolve())
print('layout=', renderer.LAYOUT_VERSION)
