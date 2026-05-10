"""Discord webhook sender."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests


class DiscordSenderError(RuntimeError):
    pass


def send_chart(webhook_url: str | None, image_path: str, max_retries: int = 3) -> bool:
    if not webhook_url:
        return False

    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            with path.open("rb") as fh:
                files: dict[str, tuple[str, Any, str]] = {"file": (path.name, fh, "image/png")}
                response = requests.post(webhook_url, files=files, timeout=30)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    sleep_seconds = min(max(float(retry_after) if retry_after else 1.0, 0.0), 120.0)
                    if attempt < max_retries:
                        time.sleep(sleep_seconds)
                        continue
                    raise DiscordSenderError("Discord rate limited")
                response.raise_for_status()
            return True
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            time.sleep(min(2**attempt, 30.0))
    raise DiscordSenderError(f"Failed to send Discord chart: {last_error}") from last_error
