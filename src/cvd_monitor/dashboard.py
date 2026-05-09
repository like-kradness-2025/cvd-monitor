"""matplotlib dashboard generator placeholder."""

from pathlib import Path


def build_dashboard(output_path: str = 'artifacts/dashboard.png') -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'')
    return path
