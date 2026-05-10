from __future__ import annotations

from pathlib import Path

import pytest
import requests

from cvd_monitor.discord_sender import DiscordSenderError, send_chart


class DummyResponse:
    def __init__(self, status_code: int = 200, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_send_chart_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = tmp_path / "chart.png"
    image.write_bytes(b"data")
    called = {}

    def fake_post(url: str, files, timeout: int):  # type: ignore[no-untyped-def]
        called["url"] = url
        called["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr("cvd_monitor.discord_sender.requests.post", fake_post)
    assert send_chart("https://example.test/webhook", str(image)) is True
    assert called["url"] == "https://example.test/webhook"


def test_send_chart_fails_after_retries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = tmp_path / "chart.png"
    image.write_bytes(b"data")
    attempts = 0

    def fake_post(url: str, files, timeout: int):  # type: ignore[no-untyped-def]
        nonlocal attempts
        attempts += 1
        return DummyResponse(status_code=500)

    sleeps: list[float] = []
    monkeypatch.setattr("cvd_monitor.discord_sender.requests.post", fake_post)
    monkeypatch.setattr("cvd_monitor.discord_sender.time.sleep", lambda seconds: sleeps.append(seconds))

    with pytest.raises(DiscordSenderError):
        send_chart("https://example.test/webhook", str(image), max_retries=1)
    assert attempts == 2
    assert sleeps == [1]


def test_send_chart_retries_429_with_retry_after(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = tmp_path / "chart.png"
    image.write_bytes(b"data")
    calls: list[DummyResponse] = [DummyResponse(status_code=429, headers={"Retry-After": "3"}), DummyResponse()]
    sleeps: list[float] = []

    def fake_post(url: str, files, timeout: int):  # type: ignore[no-untyped-def]
        return calls.pop(0)

    monkeypatch.setattr("cvd_monitor.discord_sender.requests.post", fake_post)
    monkeypatch.setattr("cvd_monitor.discord_sender.time.sleep", lambda seconds: sleeps.append(seconds))

    assert send_chart("https://example.test/webhook", str(image), max_retries=1) is True
    assert sleeps == [3.0]
