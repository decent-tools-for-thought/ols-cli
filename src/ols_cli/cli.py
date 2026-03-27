"""Command-line interface for OLS4."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .client import OlsApiError, OlsClient, OlsClientError, OlsDecodeError, Paging
from .config import AppConfig, ConfigError, load_config
from .core import (
    CoreError,
    coerce_positive_int,
    extract_ontology_rows,
    extract_search_rows,
    parse_bool_flag,
    parse_json_input,
    parse_operation_params,
    parse_raw_params,
    render_json,
    render_jsonl,
    render_ontology_text,
    render_search_text,
    render_term_text,
)
from .openapi import (
    OpenApiError,
    cli_flag_for_name,
    fetch_spec,
    get_operation,
    list_operations,
    load_spec_from_path,
)

ExitCode = int
USAGE_ERROR: ExitCode = 2
RUNTIME_ERROR: ExitCode = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ols",
        description="Command-line interface for EMBL-EBI OLS4 ontology search and lookup.",
    )
    parser.add_argument(
        "--base-url", help="Override OLS base URL (default: https://www.ebi.ac.uk/ols4)"
    )
    parser.add_argument("--timeout", type=float, help="HTTP timeout in seconds (default: 20)")
    parser.add_argument("--config", type=Path, help="Path to config JSON file")
    parser.add_argument(
        "--openapi-spec",
        type=Path,
        help="Path to OpenAPI JSON (default: fetch from official OLS4 endpoint)",
    )

    subparsers = parser.add_subparsers(dest="command")

    ops = subparsers.add_parser("ops", help="List all operations from OpenAPI spec")
    ops.add_argument("--format", choices=["text", "json", "jsonl"], default="text")
    ops.add_argument(
        "--method", choices=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
    )
    ops.add_argument("--path-prefix", help="Filter by path prefix")

    call = subparsers.add_parser("call", help="Call any OpenAPI operation by operation id")
    call.add_argument("operation_id", help="OpenAPI operationId")
    call.add_argument("--path-param", action="append", default=[], help="Path param KEY=VALUE")
    call.add_argument("--query-param", action="append", default=[], help="Query param KEY=VALUE")
    call.add_argument("--header", action="append", default=[], help="Header KEY=VALUE")
    call.add_argument("--json-body", help="Inline JSON body string")
    call.add_argument("--json-body-file", help="Path to JSON body file")
    call.add_argument("--format", choices=["json"], default="json")

    api = subparsers.add_parser("api", help="Dedicated OpenAPI operation command")
    api.add_argument("operation_id", help="OpenAPI operationId")
    api.add_argument("operation_args", nargs=argparse.REMAINDER, help="Operation-specific options")

    ontologies = subparsers.add_parser("ontologies", help="List ontology metadata")
    ontologies.add_argument("--size", type=int, help="Page size")
    ontologies.add_argument("--page", type=int, help="Page number (0-based)")
    ontologies.add_argument("--format", choices=["text", "json", "jsonl"], default="text")

    ontology_get = subparsers.add_parser("ontology", help="Get one ontology by ontology id")
    ontology_get.add_argument("ontology", help="Ontology id (example: efo)")
    ontology_get.add_argument("--format", choices=["text", "json"], default="text")

    search = subparsers.add_parser("search", help="Search terms/entities")
    search.add_argument("query", help="Search query string")
    search.add_argument("--ontology", help="Restrict to ontology id")
    search.add_argument("--exact", action="store_true", help="Exact matching")
    search.add_argument(
        "--field", action="append", default=[], help="Requested field list (repeatable)"
    )
    search.add_argument("--obsoletes", choices=["true", "false"], help="Include obsolete terms")
    search.add_argument("--local", choices=["true", "false"], help="Use local ontology settings")
    search.add_argument("--size", type=int, help="Page size")
    search.add_argument("--page", type=int, help="Page number (0-based)")
    search.add_argument("--format", choices=["text", "json", "jsonl"], default="text")

    suggest = subparsers.add_parser("suggest", help="Autocomplete-like term suggestions")
    suggest.add_argument("query", help="Suggestion query string")
    suggest.add_argument("--ontology", help="Restrict to ontology id")
    suggest.add_argument(
        "--field", action="append", default=[], help="Requested field list (repeatable)"
    )
    suggest.add_argument("--format", choices=["text", "json", "jsonl"], default="text")

    term = subparsers.add_parser("term", help="Get one ontology term by IRI")
    term.add_argument("ontology", help="Ontology id (example: efo)")
    term.add_argument("iri", help="Full term IRI")
    term.add_argument("--lang", help="Language code")
    term.add_argument("--format", choices=["text", "json"], default="text")

    raw = subparsers.add_parser("raw", help="Generic GET request escape hatch")
    raw.add_argument("path", help="API path, for example /api/select")
    raw.add_argument(
        "--param", action="append", default=[], help="Query param KEY=VALUE (repeatable)"
    )
    raw.add_argument("--format", choices=["json"], default="json")

    return parser


def _create_config(namespace: argparse.Namespace) -> AppConfig:
    return load_config(
        base_url=namespace.base_url, timeout=namespace.timeout, config_path=namespace.config
    )


def _emit(text: str) -> None:
    sys.stdout.write(text)
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")


def _render_ontology_obj_text(payload: dict[str, object]) -> str:
    ontology_id = str(payload.get("ontologyId", ""))
    loaded = str(payload.get("loaded", ""))
    config = payload.get("config")
    title = ""
    if isinstance(config, dict):
        title = str(config.get("title", ""))
    return f"ontologyId: {ontology_id}\nloaded: {loaded}\ntitle: {title}"


def _load_openapi(namespace: argparse.Namespace, timeout: float) -> dict[str, object]:
    if namespace.openapi_spec:
        return load_spec_from_path(namespace.openapi_spec)
    return fetch_spec(timeout=timeout)


def _run_ops(namespace: argparse.Namespace, timeout: float) -> int:
    spec = _load_openapi(namespace, timeout)
    operations = list_operations(spec)

    if namespace.method:
        operations = [op for op in operations if op.method == namespace.method]
    if namespace.path_prefix:
        operations = [op for op in operations if op.path.startswith(namespace.path_prefix)]

    if namespace.format == "json":
        _emit(
            render_json(
                {
                    "operations": [
                        {
                            "operationId": op.operation_id,
                            "method": op.method,
                            "path": op.path,
                            "summary": op.summary,
                            "description": op.description,
                            "parameters": [
                                {
                                    "name": p.name,
                                    "in": p.location,
                                    "required": p.required,
                                    "type": p.schema_type,
                                }
                                for p in op.parameters
                            ],
                            "requestBodyRequired": op.request_body_required,
                            "requestBodyContentTypes": op.request_body_content_types,
                        }
                        for op in operations
                    ]
                }
            )
        )
        return 0

    if namespace.format == "jsonl":
        _emit(
            render_jsonl(
                {
                    "operationId": op.operation_id,
                    "method": op.method,
                    "path": op.path,
                    "summary": op.summary,
                }
                for op in operations
            )
        )
        return 0

    lines = [f"{op.operation_id}\t{op.method}\t{op.path}\t{op.summary}" for op in operations]
    _emit("\n".join(lines) if lines else "No operations matched.")
    return 0


def _run_call(namespace: argparse.Namespace, cfg: AppConfig) -> int:
    spec = _load_openapi(namespace, cfg.timeout)
    op = get_operation(spec, namespace.operation_id)

    path_params = parse_operation_params(namespace.path_param, flag_name="--path-param")
    query_params = parse_operation_params(namespace.query_param, flag_name="--query-param")
    header_params = parse_operation_params(namespace.header, flag_name="--header")

    json_inline = parse_json_input(namespace.json_body, from_file=False)
    json_file = parse_json_input(namespace.json_body_file, from_file=True)

    if json_inline is not None and json_file is not None:
        raise CoreError("use either --json-body or --json-body-file, not both")
    json_body = json_inline if json_inline is not None else json_file

    required_path = [p.name for p in op.parameters if p.location == "path" and p.required]
    missing = [name for name in required_path if name not in path_params]
    if missing:
        raise CoreError(f"missing required path params for {op.operation_id}: {', '.join(missing)}")

    required_query = [p.name for p in op.parameters if p.location == "query" and p.required]
    missing_query = [name for name in required_query if name not in query_params]
    if missing_query:
        raise CoreError(
            f"missing required query params for {op.operation_id}: {', '.join(missing_query)}"
        )

    if op.request_body_required and json_body is None:
        raise CoreError(f"operation {op.operation_id} requires a request body")

    with OlsClient(base_url=cfg.base_url, timeout=cfg.timeout) as client:
        payload = client.call_operation(
            method=op.method,
            path_template=op.path,
            path_params=path_params,
            query_params=query_params,
            header_params=header_params,
            json_body=json_body,
            raw_body=None,
            content_type=None,
        )
    _emit(render_json(payload))
    return 0


def _build_operation_parser(op_id: str, spec: object) -> argparse.ArgumentParser:
    from .openapi import get_operation

    if not isinstance(spec, dict):
        raise OpenApiError("invalid OpenAPI spec loaded")
    op = get_operation(spec, op_id)

    parser = argparse.ArgumentParser(
        prog=f"ols api {op_id}",
        description=f"{op.method} {op.path} - {op.summary or op.description or op.operation_id}",
    )

    parser.add_argument("--format", choices=["json"], default="json")
    reserved_flags = {"--format", "--body", "--body-file", "--content-type"}

    def param_dest(location: str, name: str) -> str:
        return f"param__{location}__{name}"

    for param in op.parameters:
        base = cli_flag_for_name(param.name)
        flag = f"--{base}"
        if flag in reserved_flags:
            flag = f"--{param.location}-{base}"
        reserved_flags.add(flag)
        required = param.required and param.location in {"path", "query"}
        help_text = f"{param.location} parameter '{param.name}'"
        parser.add_argument(
            flag,
            dest=param_dest(param.location, param.name),
            required=required,
            help=help_text,
        )

    if op.request_body_content_types:
        parser.add_argument("--body", help="Inline request body text (JSON or raw)")
        parser.add_argument("--body-file", help="Path to request body file")
        parser.add_argument(
            "--content-type",
            choices=op.request_body_content_types,
            default=op.request_body_content_types[0],
            help="Request content type",
        )

    return parser


def _run_api(namespace: argparse.Namespace, cfg: AppConfig) -> int:
    spec = _load_openapi(namespace, cfg.timeout)
    op_parser = _build_operation_parser(namespace.operation_id, spec)
    op_args = namespace.operation_args
    if op_args and op_args[0] == "--":
        op_args = op_args[1:]
    op_ns = op_parser.parse_args(op_args)

    op = get_operation(spec, namespace.operation_id)

    def param_dest(location: str, name: str) -> str:
        return f"param__{location}__{name}"

    path_params: dict[str, object] = {}
    query_params: dict[str, object] = {}
    header_params: dict[str, str] = {}
    for param in op.parameters:
        value = getattr(op_ns, param_dest(param.location, param.name), None)
        if value is None:
            continue
        if param.location == "path":
            path_params[param.name] = value
        elif param.location == "query":
            query_params[param.name] = value
        elif param.location == "header":
            header_params[param.name] = str(value)

    json_body: object | None = None
    raw_body: bytes | None = None
    content_type: str | None = None
    if op.request_body_content_types:
        body_inline = getattr(op_ns, "body", None)
        body_file = getattr(op_ns, "body_file", None)
        if body_inline and body_file:
            raise CoreError("use either --body or --body-file, not both")
        if op.request_body_required and not body_inline and not body_file:
            raise CoreError(f"operation {op.operation_id} requires a request body")
        content_type = getattr(op_ns, "content_type", None)
        body_text: str | None = None
        if body_file:
            try:
                body_text = Path(body_file).read_text(encoding="utf-8")
            except OSError as exc:
                raise CoreError(f"failed to read body file {body_file}: {exc}") from exc
        elif body_inline:
            body_text = body_inline

        if body_text is not None:
            if content_type == "application/json":
                json_body = parse_json_input(body_text, from_file=False)
            else:
                raw_body = body_text.encode("utf-8")

    with OlsClient(base_url=cfg.base_url, timeout=cfg.timeout) as client:
        payload = client.call_operation(
            method=op.method,
            path_template=op.path,
            path_params=path_params,
            query_params=query_params,
            header_params=header_params or None,
            json_body=json_body,
            raw_body=raw_body,
            content_type=content_type,
        )
    _emit(render_json(payload))
    return 0


def run_command(namespace: argparse.Namespace) -> int:
    if not namespace.command:
        parser = build_parser()
        parser.print_help()
        return 0

    cfg = _create_config(namespace)

    if namespace.command == "ops":
        return _run_ops(namespace, cfg.timeout)
    if namespace.command == "call":
        return _run_call(namespace, cfg)
    if namespace.command == "api":
        return _run_api(namespace, cfg)

    size = coerce_positive_int(getattr(namespace, "size", None), name="size")
    page = getattr(namespace, "page", None)
    if page is not None and page < 0:
        raise CoreError("page must be >= 0")

    with OlsClient(base_url=cfg.base_url, timeout=cfg.timeout) as client:
        if namespace.command == "ontologies":
            payload = client.list_ontologies(paging=Paging(size=size, page=page))
            rows = extract_ontology_rows(payload)
            if namespace.format == "json":
                _emit(render_json(payload))
            elif namespace.format == "jsonl":
                _emit(render_jsonl(rows))
            else:
                _emit(render_ontology_text(rows))
            return 0

        if namespace.command == "ontology":
            payload = client.get_ontology(namespace.ontology)
            if namespace.format == "json":
                _emit(render_json(payload))
            else:
                _emit(_render_ontology_obj_text(payload))
            return 0

        if namespace.command == "search":
            payload = client.search(
                query=namespace.query,
                ontology=namespace.ontology,
                exact=namespace.exact,
                field_list=namespace.field,
                obsoletes=parse_bool_flag(namespace.obsoletes),
                local=parse_bool_flag(namespace.local),
                paging=Paging(size=size, page=page),
            )
            search_rows = extract_search_rows(payload)
            if namespace.format == "json":
                _emit(render_json(payload))
            elif namespace.format == "jsonl":
                _emit(
                    render_jsonl(
                        {
                            "label": row.label,
                            "iri": row.iri,
                            "ontology": row.ontology,
                            "short_form": row.short_form,
                        }
                        for row in search_rows
                    )
                )
            else:
                _emit(render_search_text(search_rows))
            return 0

        if namespace.command == "suggest":
            payload = client.suggest(
                query=namespace.query,
                ontology=namespace.ontology,
                field_list=namespace.field,
            )
            suggest_rows = extract_search_rows(payload)
            if namespace.format == "json":
                _emit(render_json(payload))
            elif namespace.format == "jsonl":
                _emit(
                    render_jsonl(
                        {
                            "label": row.label,
                            "iri": row.iri,
                            "ontology": row.ontology,
                            "short_form": row.short_form,
                        }
                        for row in suggest_rows
                    )
                )
            else:
                _emit(render_search_text(suggest_rows))
            return 0

        if namespace.command == "term":
            payload = client.get_term(
                ontology=namespace.ontology, iri=namespace.iri, language=namespace.lang
            )
            if namespace.format == "json":
                _emit(render_json(payload))
            else:
                _emit(render_term_text(payload))
            return 0

        if namespace.command == "raw":
            params = parse_raw_params(namespace.param)
            payload = client.raw_get(namespace.path, params=params)
            _emit(render_json(payload))
            return 0

    raise CoreError(f"unknown command: {namespace.command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return run_command(args)
    except (ConfigError, CoreError, OpenApiError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return USAGE_ERROR
    except OlsApiError as exc:
        details = f": {exc.details}" if exc.details else ""
        print(f"API error ({exc.status_code}): {exc}{details}", file=sys.stderr)
        return RUNTIME_ERROR
    except (OlsClientError, OlsDecodeError) as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return RUNTIME_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
