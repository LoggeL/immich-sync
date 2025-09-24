from __future__ import annotations

import httpx
import pytest

from app.immich_client import ImmichClient


class StubResponse:
    def __init__(self, status_code: int, url: str, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.request = httpx.Request("POST", url)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=self.request, response=self)

    def json(self) -> dict:
        return self._payload


class FallbackStubClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.calls: list[str] = []

    def post(self, endpoint: str, json: dict) -> StubResponse:
        self.calls.append(endpoint)
        if len(self.calls) == 1:
            return StubResponse(404, f"{self.base_url}{endpoint}")
        return StubResponse(200, f"{self.base_url}{endpoint}", {"results": ["ok"]})


class Always404StubClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.calls: list[str] = []

    def post(self, endpoint: str, json: dict) -> StubResponse:
        self.calls.append(endpoint)
        return StubResponse(404, f"{self.base_url}{endpoint}")


def test_check_bulk_upload_falls_back_to_singular_endpoint() -> None:
    client = ImmichClient("https://example.com", "key")
    stub = FallbackStubClient(client.base_url)
    client._client = stub  # type: ignore[assignment]

    result = client._check_bulk_upload([{"checksum": "abc"}])

    assert result == {"results": ["ok"]}
    assert stub.calls == ["/api/assets/check", "/api/asset/check"]


def test_check_bulk_upload_raises_when_all_endpoints_fail() -> None:
    client = ImmichClient("https://example.com", "key")
    stub = Always404StubClient(client.base_url)
    client._client = stub  # type: ignore[assignment]

    with pytest.raises(httpx.HTTPStatusError):
        client._check_bulk_upload([{"checksum": "abc"}])

    assert stub.calls == ["/api/assets/check", "/api/asset/check"]
