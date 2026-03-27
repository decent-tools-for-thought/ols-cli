"""OpenAPI specification loading and operation lookup."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

OPENAPI_URL = "https://www.ebi.ac.uk/ols4/v3/api-docs"


class OpenApiError(ValueError):
    """Raised for invalid or unreadable OpenAPI specs."""


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    location: str
    required: bool
    schema_type: str | None


@dataclass(frozen=True)
class OperationSpec:
    operation_id: str
    method: str
    path: str
    summary: str
    description: str
    parameters: list[ParameterSpec]
    request_body_required: bool
    request_body_content_types: list[str]


def cli_flag_for_name(name: str) -> str:
    out: list[str] = []
    for ch in name:
        if ch.isalnum():
            out.append(ch.lower())
        else:
            out.append("-")
    flag = "".join(out)
    while "--" in flag:
        flag = flag.replace("--", "-")
    return flag.strip("-") or "arg"


def _load_json_bytes(raw: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpenApiError("invalid OpenAPI JSON") from exc
    if not isinstance(parsed, dict):
        raise OpenApiError("OpenAPI document must be a JSON object")
    return parsed


def load_spec_from_path(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise OpenApiError(f"failed to read OpenAPI file {path}: {exc}") from exc
    return _load_json_bytes(raw)


def fetch_spec(url: str = OPENAPI_URL, timeout: float = 20.0) -> dict[str, Any]:
    req = Request(url, method="GET")
    req.add_header("Accept", "application/json")
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read()
    except OSError as exc:
        raise OpenApiError(f"failed to fetch OpenAPI spec: {exc}") from exc
    return _load_json_bytes(raw)


def _parameter_from_object(obj: dict[str, Any]) -> ParameterSpec:
    name = str(obj.get("name", ""))
    location = str(obj.get("in", ""))
    required = bool(obj.get("required", False))
    schema = obj.get("schema")
    schema_type: str | None = None
    if isinstance(schema, dict):
        st = schema.get("type")
        if isinstance(st, str):
            schema_type = st
    return ParameterSpec(name=name, location=location, required=required, schema_type=schema_type)


def _iter_operations(spec: dict[str, Any]) -> list[OperationSpec]:
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        raise OpenApiError("OpenAPI spec has no valid 'paths' object")

    operations: list[OperationSpec] = []
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue

        path_level_parameters: list[dict[str, Any]] = []
        raw_path_params = path_item.get("parameters")
        if isinstance(raw_path_params, list):
            path_level_parameters = [p for p in raw_path_params if isinstance(p, dict)]

        for method, op_obj in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                continue
            if not isinstance(op_obj, dict):
                continue

            op_id = op_obj.get("operationId")
            if not isinstance(op_id, str) or not op_id.strip():
                op_path = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
                op_id = f"{method.lower()}_{op_path}"

            raw_op_params = op_obj.get("parameters")
            op_parameters: list[dict[str, Any]] = []
            if isinstance(raw_op_params, list):
                op_parameters = [p for p in raw_op_params if isinstance(p, dict)]

            merged = path_level_parameters + op_parameters
            parameters = [_parameter_from_object(p) for p in merged]

            request_body_required = False
            request_body_content_types: list[str] = []
            rb = op_obj.get("requestBody")
            if isinstance(rb, dict):
                request_body_required = bool(rb.get("required", False))
                content = rb.get("content")
                if isinstance(content, dict):
                    request_body_content_types = [k for k in content if isinstance(k, str)]

            operations.append(
                OperationSpec(
                    operation_id=op_id,
                    method=method.upper(),
                    path=path,
                    summary=str(op_obj.get("summary", "")),
                    description=str(op_obj.get("description", "")),
                    parameters=parameters,
                    request_body_required=request_body_required,
                    request_body_content_types=request_body_content_types,
                )
            )

    operations.sort(key=lambda o: (o.path, o.method, o.operation_id))
    return operations


def list_operations(spec: dict[str, Any]) -> list[OperationSpec]:
    return _iter_operations(spec)


def get_operation(spec: dict[str, Any], operation_id: str) -> OperationSpec:
    for op in _iter_operations(spec):
        if op.operation_id == operation_id:
            return op
    raise OpenApiError(f"unknown operation id: {operation_id}")


def operations_by_id(spec: dict[str, Any]) -> dict[str, OperationSpec]:
    return {op.operation_id: op for op in _iter_operations(spec)}


def spec_server_url(spec: dict[str, Any]) -> str | None:
    servers = spec.get("servers")
    if isinstance(servers, list) and servers:
        first = servers[0]
        if isinstance(first, dict):
            url = first.get("url")
            if isinstance(url, str):
                return url
    return None
