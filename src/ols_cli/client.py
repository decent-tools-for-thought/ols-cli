"""HTTP transport and OLS API interaction layer."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

JsonDict = dict[str, Any]


class OlsClientError(RuntimeError):
    """Base exception for client failures."""


class OlsApiError(OlsClientError):
    """Raised for non-success HTTP responses from OLS."""

    def __init__(self, status_code: int, message: str, *, details: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class OlsNetworkError(OlsClientError):
    """Raised for network-level failures."""


class OlsDecodeError(OlsClientError):
    """Raised when JSON cannot be decoded."""


@dataclass(frozen=True)
class Paging:
    """Paging controls for list endpoints."""

    size: int | None = None
    page: int | None = None

    def to_params(self) -> dict[str, object]:
        params: dict[str, object] = {}
        if self.size is not None:
            params["size"] = self.size
        if self.page is not None:
            params["page"] = self.page
        return params


class Response(Protocol):
    def read(self) -> bytes: ...

    def __enter__(self) -> Response: ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


Transport = Any


def _default_transport(request: Request, timeout: float) -> Response:
    return cast(Response, urlopen(request, timeout=timeout))


class OlsClient:
    """Client for OLS4 API."""

    def __init__(
        self, *, base_url: str, timeout: float, transport: Transport | None = None
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport: Transport = transport or _default_transport

    def close(self) -> None:
        return

    def __enter__(self) -> OlsClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def _build_url(self, path: str, params: dict[str, object] | None) -> str:
        normalized = path if path.startswith("/") else f"/{path}"
        url = f"{self._base_url}{normalized}"
        if params:
            encoded = urlencode([(k, str(v)) for k, v in params.items() if v is not None])
            return f"{url}?{encoded}"
        return url

    @staticmethod
    def _build_path(path_template: str, path_params: Mapping[str, object] | None) -> str:
        if not path_params:
            return path_template
        path = path_template
        for key, value in path_params.items():
            token = "{" + key + "}"
            if token in path:
                path = path.replace(token, quote(str(value), safe=""))
        return path

    def _decode_json(self, payload: bytes) -> JsonDict:
        try:
            parsed = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OlsDecodeError("response was not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise OlsDecodeError("unexpected JSON shape: expected object")
        return parsed

    @staticmethod
    def _status_to_message(status_code: int) -> str:
        if status_code in {401, 403}:
            return "authentication failed (OLS normally requires no auth; check endpoint/base URL)"
        if status_code == 404:
            return "resource not found"
        if status_code == 429:
            return "rate limited by upstream API; retry later"
        return f"upstream API error ({status_code})"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        json_body: object | None = None,
        raw_body: bytes | None = None,
        content_type: str | None = None,
    ) -> JsonDict:
        request_headers: dict[str, str] = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        data: bytes | None = None
        if json_body is not None and raw_body is not None:
            raise OlsClientError("cannot send both JSON body and raw body")
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        elif raw_body is not None:
            data = raw_body
            if content_type:
                request_headers.setdefault("Content-Type", content_type)

        request = Request(url=self._build_url(path, params), method=method, data=data)
        for key, value in request_headers.items():
            request.add_header(key, value)

        try:
            with self._transport(request, self._timeout) as response:
                payload = response.read()
                return self._decode_json(payload)
        except HTTPError as exc:
            details: str | None = None
            try:
                body = exc.read()
                decoded = self._decode_json(body)
                details_obj = decoded.get("message") or decoded.get("error")
                if details_obj is not None:
                    details = str(details_obj)
            except OlsDecodeError:
                details = None
            raise OlsApiError(exc.code, self._status_to_message(exc.code), details=details) from exc
        except TimeoutError as exc:
            raise OlsNetworkError("request timed out") from exc
        except URLError as exc:
            raise OlsNetworkError(f"network error: {exc}") from exc
        except OSError as exc:
            raise OlsNetworkError(f"network error: {exc}") from exc

    def list_ontologies(self, *, paging: Paging) -> JsonDict:
        return self._request("GET", "/api/ontologies", params=paging.to_params())

    def get_ontology(self, ontology: str) -> JsonDict:
        return self._request("GET", f"/api/ontologies/{quote(ontology, safe='')}")

    def search(
        self,
        *,
        query: str,
        ontology: str | None,
        exact: bool,
        field_list: list[str] | None,
        obsoletes: bool | None,
        local: bool | None,
        paging: Paging,
    ) -> JsonDict:
        params: dict[str, object] = {"q": query, **paging.to_params()}
        if ontology:
            params["ontology"] = ontology
        if exact:
            params["exact"] = "true"
        if field_list:
            params["fieldList"] = ",".join(field_list)
        if obsoletes is not None:
            params["obsoletes"] = str(obsoletes).lower()
        if local is not None:
            params["local"] = str(local).lower()
        return self._request("GET", "/api/search", params=params)

    def suggest(
        self,
        *,
        query: str,
        ontology: str | None,
        field_list: list[str] | None,
    ) -> JsonDict:
        params: dict[str, object] = {"q": query}
        if ontology:
            params["ontology"] = ontology
        if field_list:
            params["fieldList"] = ",".join(field_list)
        return self._request("GET", "/api/suggest", params=params)

    def get_term(
        self,
        *,
        ontology: str,
        iri: str,
        language: str | None,
    ) -> JsonDict:
        encoded_iri = quote(iri, safe="")
        params: dict[str, object] = {}
        if language:
            params["lang"] = language
        return self._request(
            "GET",
            f"/api/ontologies/{quote(ontology, safe='')}/terms/{encoded_iri}",
            params=params,
        )

    def raw_get(self, path: str, *, params: dict[str, object] | None) -> JsonDict:
        normalized = path if path.startswith("/") else f"/{path}"
        return self._request("GET", normalized, params=params)

    def call_operation(
        self,
        *,
        method: str,
        path_template: str,
        path_params: Mapping[str, object] | None,
        query_params: Mapping[str, object] | None,
        header_params: dict[str, str] | None,
        json_body: object | None,
        raw_body: bytes | None,
        content_type: str | None,
    ) -> JsonDict:
        path = self._build_path(path_template, path_params)
        query_as_dict = dict(query_params) if query_params is not None else None
        return self._request(
            method.upper(),
            path,
            params=query_as_dict,
            headers=header_params,
            json_body=json_body,
            raw_body=raw_body,
            content_type=content_type,
        )
