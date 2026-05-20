from __future__ import annotations

import logging
from pathlib import Path

import requests


def send_discord(webhook_url: str | None, content: str, chart_path: str | Path, timeout_seconds: int = 20) -> bool:
    """Send a chart image to Discord.

    Returns True when a notification was posted, False when skipped because the
    webhook is missing/empty.
    """

    webhook_url = (webhook_url or '').strip()
    if not webhook_url:
        return False

    path = Path(chart_path)
    with path.open('rb') as fh:
        response = requests.post(
            webhook_url,
            data={'content': content},
            files={'file': (path.name, fh, 'image/png')},
            timeout=timeout_seconds,
        )
    response.raise_for_status()
    logging.info('Discord notification sent.')
    return True