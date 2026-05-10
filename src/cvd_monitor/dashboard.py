"""matplotlib dashboard generator."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .database import CVDRecord


def build_dashboard(records: Sequence[CVDRecord], output_path: str = "artifacts/dashboard.png") -> Path | None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not records:
        return None

    timestamps = [record.timestamp for record in records]
    prices = [record.price for record in records]
    spot_cvd = [record.spot_cvd for record in records]
    futures_cvd = [record.futures_cvd for record in records]

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    axes[0].plot(timestamps, prices, color="black")
    axes[0].set_title("BTC Price")
    axes[1].plot(timestamps, spot_cvd, color="tab:blue")
    axes[1].set_title("Spot CVD")
    axes[2].plot(timestamps, futures_cvd, color="tab:orange")
    axes[2].set_title("Futures CVD")
    axes[2].set_xlabel("Timestamp")
    for ax in axes:
        ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
