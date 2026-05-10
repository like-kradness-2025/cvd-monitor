from __future__ import annotations

from typing import Any

import pytest
import requests

from cvd_monitor.coinalyze import CoinAlYZeClient, CoinAlYZeError


class DummyResponse:
    def __init__(self, payload: Any, status_code: int = 200, headers: dict[str, str] | None = None) -> None:
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class DummySession:
    def __init__(self, responses: list[DummyResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, str], dict[str, Any] | None, float]] = []

    def get(self, url: str, headers: dict[str, str], params: dict[str, Any] | None, timeout: float) -> DummyResponse:
        self.calls.append((url, headers, params, timeout))
        return self.responses.pop(0)


def test_coinalyze_client_adds_auth_and_parses_data() -> None:
    session = DummySession([DummyResponse({"data": [{"id": 1}]})])
    client = CoinAlYZeClient(api_key="secret", base_url="https://example.test", session=session)

    data = client.exchanges()

    assert data == [{"id": 1}]
    assert session.calls[0][0] == "https://example.test/exchanges"
    assert session.calls[0][1]["Authorization"] == "Bearer secret"


def test_coinalyze_client_retries_429_and_uses_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    session = DummySession([
        DummyResponse({}, status_code=429, headers={"Retry-After": "2"}),
        DummyResponse({"data": ["ok"]}),
    ])
    sleeps: list[float] = []
    monkeypatch.setattr("cvd_monitor.coinalyze.time.sleep", lambda seconds: sleeps.append(seconds))
    client = CoinAlYZeClient(base_url="https://example.test", session=session, max_retries=1)

    assert client.exchanges() == ["ok"]
    assert sleeps == [2.0]


def test_coinalyze_client_retries_503(monkeypatch: pytest.MonkeyPatch) -> None:
    session = DummySession([
        DummyResponse({}, status_code=503),
        DummyResponse({"data": ["ok"]}),
    ])
    sleeps: list[float] = []
    monkeypatch.setattr("cvd_monitor.coinalyze.time.sleep", lambda seconds: sleeps.append(seconds))
    client = CoinAlYZeClient(base_url="https://example.test", session=session, max_retries=1)

    assert client.exchanges() == ["ok"]
    assert sleeps == [1]


def test_coinalyze_client_fails_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    session = DummySession([DummyResponse(ValueError("bad json"))])
    monkeypatch.setattr("cvd_monitor.coinalyze.time.sleep", lambda seconds: None)
    client = CoinAlYZeClient(base_url="https://example.test", session=session, max_retries=0)

    with pytest.raises(CoinAlYZeError):
        client.exchanges()
