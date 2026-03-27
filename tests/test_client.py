from __future__ import annotations

import io
import json
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from ols_cli.client import OlsApiError, OlsClient, OlsDecodeError, OlsNetworkError, Paging


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


def test_client_success_list_ontologies() -> None:
    def transport(request: Request, timeout: float) -> FakeResponse:
        assert request.full_url.startswith("https://example.org/api/ontologies")
        assert timeout == 5.0
        return FakeResponse(json.dumps({"_embedded": {"ontologies": []}}).encode("utf-8"))

    client = OlsClient(base_url="https://example.org", timeout=5.0, transport=transport)
    payload = client.list_ontologies(paging=Paging(size=5, page=0))
    assert "_embedded" in payload


def test_client_http_error_raises_api_error() -> None:
    def transport(request: Request, timeout: float) -> FakeResponse:
        raise HTTPError(
            request.full_url,
            404,
            "Not Found",
            hdrs=Message(),
            fp=io.BytesIO(json.dumps({"message": "not found"}).encode("utf-8")),
        )

    client = OlsClient(base_url="https://example.org", timeout=5.0, transport=transport)
    with pytest.raises(OlsApiError) as exc:
        client.get_ontology("efo")
    assert exc.value.status_code == 404


def test_client_decode_error() -> None:
    def transport(request: Request, timeout: float) -> FakeResponse:
        return FakeResponse(b"not-json")

    client = OlsClient(base_url="https://example.org", timeout=5.0, transport=transport)
    with pytest.raises(OlsDecodeError):
        client.get_ontology("efo")


def test_client_network_error() -> None:
    def transport(request: Request, timeout: float) -> FakeResponse:
        raise URLError("boom")

    client = OlsClient(base_url="https://example.org", timeout=5.0, transport=transport)
    with pytest.raises(OlsNetworkError):
        client.get_ontology("efo")


def test_call_operation_replaces_path_and_query_and_body() -> None:
    seen: dict[str, object] = {}

    def transport(request: Request, timeout: float) -> FakeResponse:
        seen["url"] = request.full_url
        seen["content_type"] = request.headers.get("Content-type")
        seen["method"] = request.get_method()
        body_data = request.data
        if isinstance(body_data, bytes):
            seen["body"] = body_data.decode("utf-8")
        else:
            seen["body"] = ""
        return FakeResponse(json.dumps({"ok": True}).encode("utf-8"))

    client = OlsClient(base_url="https://example.org", timeout=5.0, transport=transport)
    payload = client.call_operation(
        method="POST",
        path_template="/api/v2/ontologies/{onto}/classes/{class}",
        path_params={"onto": "efo", "class": "http://example.org/C_1"},
        query_params={"page": "0"},
        header_params={"X-Test": "1"},
        json_body={"x": 1},
        raw_body=None,
        content_type=None,
    )
    assert payload["ok"] is True
    assert seen["method"] == "POST"
    assert "%3A%2F%2Fexample.org%2FC_1" in str(seen["url"])
    assert "page=0" in str(seen["url"])
    assert seen["content_type"] == "application/json"
    assert seen["body"] == '{"x": 1}'
