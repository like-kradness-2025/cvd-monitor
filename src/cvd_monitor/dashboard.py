"""matplotlib dashboard generator."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .database import CVDRecord

DEFAULT_DASHBOARD_PATH = "artifacts/dashboard.png"


def build_dashboard(records: Sequence[CVDRecord], output_path: str = DEFAULT_DASHBOARD_PATH) -> Path | None:
    """Render price, spot CVD, futures CVD, and spread into a PNG."""

    if not records:
        return None

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    timestamps = [_format_timestamp(record.timestamp) for record in records]
    prices = [record.price for record in records]
    spot_cvd = [record.spot_cvd for record in records]
    futures_cvd = [record.futures_cvd for record in records]
    spread = [future - spot for spot, future in zip(spot_cvd, futures_cvd, strict=False)]

    fig, axes = plt.subplots(4, 1, figsize=(12, 12), sharex=True)
    axes[0].plot(timestamps, prices)
    axes[0].set_title("BTC Price")
    axes[1].plot(timestamps, spot_cvd)
    axes[1].set_title("Spot Approx CVD")
    axes[2].plot(timestamps, futures_cvd)
    axes[2].set_title("Futures Approx CVD")
    axes[3].plot(timestamps, spread)
    axes[3].set_title("Futures - Spot CVD Spread")
    axes[3].set_xlabel("UTC Time")

    for ax in axes:
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis="x", labelrotation=30)

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _format_timestamp(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%m-%d %H:%M")
