"""Discord webhook sender."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests

DEFAULT_DISCORD_TIMEOUT_SECONDS = 30.0


class DiscordSenderError(RuntimeError):
    """Raised when a Discord webhook request fails."""


def send_chart(webhook_url: str | None, image_path: str, max_retries: int = 3) -> bool:
    """Send a chart image to Discord.

    Returns False when no webhook URL is configured. Raises for invalid local
    files or exhausted request retries.
    """

    if not webhook_url:
        return False

    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")

    last_error: Exception | None = None
    for attempt in range(max(0, max_retries) + 1):
        try:
            with path.open("rb") as fh:
                response = requests.post(
                    webhook_url,
                    files={"file": (path.name, fh, "image/png")},
                    timeout=DEFAULT_DISCORD_TIMEOUT_SECONDS,
                )

            if response.status_code == 429:
                if attempt < max_retries:
                    time.sleep(_retry_after_seconds(response.headers.get("Retry-After")))
                    continue
                raise DiscordSenderError("Discord rate limited")

            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            time.sleep(_backoff_seconds(attempt))

    raise DiscordSenderError(f"Failed to send Discord chart: {last_error}") from last_error


def _retry_after_seconds(value: str | None) -> float:
    if value is None:
        return 1.0
    try:
        return min(max(float(value), 0.0), 120.0)
    except ValueError:
        return 1.0


def _backoff_seconds(attempt: int) -> float:
    return min(2.0**attempt, 30.0)
