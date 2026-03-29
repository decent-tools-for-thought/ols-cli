"""Core orchestration and rendering logic."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

JsonValue = dict[str, Any]


class CoreError(ValueError):
    """Raised for user-facing validation and rendering errors."""


@dataclass(frozen=True)
class SearchResult:
    label: str
    iri: str
    ontology: str
    short_form: str | None


def parse_bool_flag(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise CoreError(f"invalid boolean value: {value!r}; expected true/false")


def parse_raw_params(items: list[str]) -> dict[str, object]:
    params: dict[str, object] = {}
    for item in items:
        if "=" not in item:
            raise CoreError(f"invalid --param {item!r}; expected KEY=VALUE")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise CoreError(f"invalid --param {item!r}; empty key")
        params[key] = value
    return params


def parse_operation_params(items: list[str], *, flag_name: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise CoreError(f"invalid {flag_name} value {item!r}; expected KEY=VALUE")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise CoreError(f"invalid {flag_name} value {item!r}; empty key")
        params[key] = value
    return params


def parse_json_input(value: str | None, *, from_file: bool = False) -> object | None:
    if value is None:
        return None
    raw = value
    if from_file:
        from pathlib import Path

        try:
            raw = Path(value).read_text(encoding="utf-8")
        except OSError as exc:
            raise CoreError(f"failed to read JSON file {value}: {exc}") from exc
    try:
        parsed: object = json.loads(raw)
        return parsed
    except json.JSONDecodeError as exc:
        source = "file" if from_file else "--json-body"
        raise CoreError(f"invalid JSON in {source}: {exc}") from exc


def coerce_positive_int(value: int | None, *, name: str) -> int | None:
    if value is None:
        return None
    if value <= 0:
        raise CoreError(f"{name} must be > 0")
    return value


def extract_search_rows(payload: JsonValue) -> list[SearchResult]:
    response = payload.get("response")
    if not isinstance(response, dict):
        return []
    docs = response.get("docs")
    if not isinstance(docs, list):
        return []

    rows: list[SearchResult] = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        label = str(doc.get("label", ""))
        iri = str(doc.get("iri", ""))
        ontology = str(doc.get("ontology_name", doc.get("ontology_prefix", "")))
        short_form_obj = doc.get("short_form")
        short_form = str(short_form_obj) if isinstance(short_form_obj, str | int | float) else None
        rows.append(SearchResult(label=label, iri=iri, ontology=ontology, short_form=short_form))
    return rows


def extract_ontology_rows(payload: JsonValue) -> list[dict[str, str]]:
    embedded = payload.get("_embedded")
    if not isinstance(embedded, dict):
        return []
    ontologies = embedded.get("ontologies")
    if not isinstance(ontologies, list):
        return []

    rows: list[dict[str, str]] = []
    for entry in ontologies:
        if not isinstance(entry, dict):
            continue
        rows.append(
            {
                "ontologyId": str(entry.get("ontologyId", "")),
                "loaded": str(entry.get("loaded", "")),
                "title": str(entry.get("config", {}).get("title", ""))
                if isinstance(entry.get("config"), dict)
                else "",
            }
        )
    return rows


def render_json(payload: JsonValue) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def render_jsonl(rows: Iterable[JsonValue]) -> str:
    return "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)


def render_search_text(rows: list[SearchResult]) -> str:
    if not rows:
        return "No matches."
    lines: list[str] = []
    for row in rows:
        sf = f" [{row.short_form}]" if row.short_form else ""
        lines.append(f"{row.label}{sf}\n  ontology: {row.ontology}\n  iri: {row.iri}")
    return "\n".join(lines)


def render_ontology_text(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "No ontologies found."
    lines = [f"{r['ontologyId']}\t{r['loaded']}\t{r['title']}" for r in rows]
    return "\n".join(lines)


def render_term_text(payload: JsonValue) -> str:
    label = str(payload.get("label", ""))
    iri = str(payload.get("iri", ""))
    short_form = str(payload.get("short_form", ""))
    description_obj = payload.get("description")

    description = ""
    if isinstance(description_obj, list) and description_obj:
        description = str(description_obj[0])
    elif isinstance(description_obj, str):
        description = description_obj

    lines = [f"label: {label}", f"short_form: {short_form}", f"iri: {iri}"]
    if description:
        lines.append(f"description: {description}")
    return "\n".join(lines)
