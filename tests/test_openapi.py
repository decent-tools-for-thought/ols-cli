from __future__ import annotations

import json
from pathlib import Path

import pytest

from ols_cli.openapi import OpenApiError, get_operation, list_operations, load_spec_from_path


def test_load_spec_and_list_operations(tmp_path: Path) -> None:
    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/api/search": {
                "get": {
                    "operationId": "search",
                    "summary": "Search",
                    "parameters": [
                        {"name": "q", "in": "query", "required": True, "schema": {"type": "string"}}
                    ],
                }
            }
        },
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")

    loaded = load_spec_from_path(path)
    ops = list_operations(loaded)
    assert len(ops) == 1
    assert ops[0].operation_id == "search"
    assert ops[0].parameters[0].name == "q"


def test_get_operation_unknown_raises() -> None:
    spec = {"openapi": "3.1.0", "paths": {}}
    with pytest.raises(OpenApiError):
        get_operation(spec, "missing")
