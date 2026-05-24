from __future__ import annotations

import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cvd_monitor.notifier import send_discord


class DummyResponse:
    def raise_for_status(self) -> None:
        return None


def test_send_discord_posts_png(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chart_path = tmp_path / 'chart.png'
    chart_path.write_bytes(b'png-bytes')
    captured: dict[str, object] = {}

    def fake_post(url, *, data, files, timeout):
        captured['url'] = url
        captured['data'] = data
        captured['timeout'] = timeout
        captured['file_name'] = files['file'][0]
        captured['file_mime'] = files['file'][2]
        captured['file_bytes'] = files['file'][1].read()
        return DummyResponse()

    monkeypatch.setattr('cvd_monitor.notifier.requests.post', fake_post)

    assert send_discord('https://example.invalid/webhook', 'hello', chart_path, timeout_seconds=12) is True
    assert captured == {
        'url': 'https://example.invalid/webhook',
        'data': {'content': 'hello'},
        'timeout': 12,
        'file_name': 'chart.png',
        'file_mime': 'image/png',
        'file_bytes': b'png-bytes',
    }


def test_send_discord_skips_missing_webhook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chart_path = tmp_path / 'chart.png'
    chart_path.write_bytes(b'png-bytes')
    called = False

    def fake_post(*args, **kwargs):
        nonlocal called
        called = True
        return DummyResponse()

    monkeypatch.setattr('cvd_monitor.notifier.requests.post', fake_post)

    assert send_discord('', 'hello', chart_path, timeout_seconds=12) is False
    assert called is False


def test_send_discord_returns_false_on_webhook_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chart_path = tmp_path / 'chart.png'
    chart_path.write_bytes(b'png-bytes')

    def fake_post(*args, **kwargs):
        raise requests.RequestException('boom')

    monkeypatch.setattr('cvd_monitor.notifier.requests.post', fake_post)

    with pytest.raises(requests.RequestException):
        send_discord('https://example.invalid/webhook', 'hello', chart_path, timeout_seconds=12)
