from __future__ import annotations

import json

import pytest

from ols_cli.core import (
    CoreError,
    extract_ontology_rows,
    extract_search_rows,
    parse_bool_flag,
    parse_raw_params,
    render_jsonl,
    render_search_text,
)


def test_parse_bool_flag_values() -> None:
    assert parse_bool_flag("true") is True
    assert parse_bool_flag("FALSE") is False
    assert parse_bool_flag(None) is None
    with pytest.raises(CoreError):
        parse_bool_flag("maybe")


def test_parse_raw_params() -> None:
    out = parse_raw_params(["q=heart", "rows=10"])
    assert out == {"q": "heart", "rows": "10"}
    with pytest.raises(CoreError):
        parse_raw_params(["missing-separator"])


def test_extract_search_rows_and_text() -> None:
    payload = {
        "response": {
            "docs": [
                {
                    "label": "diabetes mellitus",
                    "iri": "http://example.org/term1",
                    "ontology_name": "efo",
                    "short_form": "EFO_0000400",
                }
            ]
        }
    }
    rows = extract_search_rows(payload)
    assert len(rows) == 1
    text = render_search_text(rows)
    assert "diabetes mellitus" in text
    assert "http://example.org/term1" in text


def test_extract_ontology_rows_and_jsonl() -> None:
    payload = {
        "_embedded": {
            "ontologies": [
                {"ontologyId": "efo", "loaded": "true", "config": {"title": "EFO"}},
            ]
        }
    }
    rows = extract_ontology_rows(payload)
    assert rows[0]["ontologyId"] == "efo"
    lines = render_jsonl(rows).splitlines()
    assert json.loads(lines[0])["title"] == "EFO"
