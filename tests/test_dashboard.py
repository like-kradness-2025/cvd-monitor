from __future__ import annotations

from cvd_monitor.dashboard import build_dashboard
from cvd_monitor.database import CVDRecord


def test_build_dashboard_creates_image(tmp_path) -> None:
    output = tmp_path / "dashboard.png"
    records = [
        CVDRecord(symbol="BTCUSDT:spot", timeframe="1h", timestamp=1, price=100.0, spot_cvd=10.0, futures_cvd=0.0),
        CVDRecord(symbol="BTCUSDT:spot", timeframe="1h", timestamp=2, price=101.0, spot_cvd=12.0, futures_cvd=0.0),
    ]

    result = build_dashboard(records, str(output))

    assert result == output
    assert output.exists()


def test_build_dashboard_returns_none_for_empty_records(tmp_path) -> None:
    output = tmp_path / "dashboard.png"

    result = build_dashboard([], str(output))

    assert result is None
