from __future__ import annotations

import argparse
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from ols_cli import cli
from ols_cli.core import CoreError, parse_raw_params


def test_bare_invocation_prints_help_and_exits_zero() -> None:
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        code = cli.main([])
    assert code == 0
    assert "usage: ols" in stdout.getvalue()


def test_top_level_help_works() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0


def test_parser_subcommand_help() -> None:
    parser = cli.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["search", "--help"])
    assert exc.value.code == 0


def test_validation_error_returns_usage_code() -> None:
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        code = cli.main(["search", "cancer", "--size", "0"])
    assert code == 2
    assert "size must be > 0" in stderr.getvalue()


def test_successful_search_jsonl(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyClient:
        def __init__(self, **_: object) -> None:
            pass

        def __enter__(self) -> DummyClient:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def search(self, **_: object) -> dict[str, object]:
            return {
                "response": {
                    "docs": [
                        {
                            "label": "cancer",
                            "iri": "http://example/cancer",
                            "ontology_name": "efo",
                            "short_form": "EFO_1",
                        }
                    ]
                }
            }

    monkeypatch.setattr(cli, "OlsClient", DummyClient)
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        code = cli.main(["search", "cancer", "--format", "jsonl"])
    assert code == 0
    out = stdout.getvalue().strip()
    assert '"label": "cancer"' in out


def test_raw_param_validation_error() -> None:
    ns = argparse.Namespace(param=["badparam"])
    with pytest.raises(CoreError):
        _ = parse_raw_params(ns.param)


def test_ops_command_with_spec_file(tmp_path: Path) -> None:
    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/api/search": {
                "get": {
                    "operationId": "search",
                    "summary": "Search",
                    "parameters": [{"name": "q", "in": "query", "required": True}],
                }
            }
        },
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        code = cli.main(["--openapi-spec", str(spec_path), "ops", "--format", "jsonl"])
    assert code == 0
    assert '"operationId": "search"' in stdout.getvalue()


def test_call_command_dispatches_operation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/api/items/{id}": {
                "post": {
                    "operationId": "createItem",
                    "parameters": [{"name": "id", "in": "path", "required": True}],
                    "requestBody": {"required": True, "content": {"application/json": {}}},
                }
            }
        },
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    called: dict[str, object] = {}

    class DummyClient:
        def __init__(self, **_: object) -> None:
            pass

        def __enter__(self) -> DummyClient:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def call_operation(self, **kwargs: object) -> dict[str, object]:
            called.update(kwargs)
            return {"ok": True}

    monkeypatch.setattr(cli, "OlsClient", DummyClient)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        code = cli.main(
            [
                "--openapi-spec",
                str(spec_path),
                "call",
                "createItem",
                "--path-param",
                "id=42",
                "--json-body",
                '{"a":1}',
            ]
        )
    assert code == 0
    assert called["method"] == "POST"
    assert called["path_template"] == "/api/items/{id}"
    assert called["path_params"] == {"id": "42"}
    assert called["json_body"] == {"a": 1}
    assert called["raw_body"] is None
    assert '"ok": true' in stdout.getvalue().lower()


def test_api_command_generates_operation_flags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/api/items/{id}": {
                "get": {
                    "operationId": "getItem",
                    "parameters": [
                        {"name": "id", "in": "path", "required": True},
                        {"name": "lang", "in": "query", "required": False},
                    ],
                }
            }
        },
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    called: dict[str, object] = {}

    class DummyClient:
        def __init__(self, **_: object) -> None:
            pass

        def __enter__(self) -> DummyClient:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def call_operation(self, **kwargs: object) -> dict[str, object]:
            called.update(kwargs)
            return {"ok": True}

    monkeypatch.setattr(cli, "OlsClient", DummyClient)

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        code = cli.main(
            [
                "--openapi-spec",
                str(spec_path),
                "api",
                "getItem",
                "--",
                "--id",
                "42",
                "--lang",
                "en",
            ]
        )
    assert code == 0
    assert called["method"] == "GET"
    assert called["path_template"] == "/api/items/{id}"
    assert called["path_params"] == {"id": "42"}
    assert called["query_params"] == {"lang": "en"}
