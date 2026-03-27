<div align="center">

# ols-cli

![Python](https://img.shields.io/badge/python-3.11%2B-eab308)
![License](https://img.shields.io/badge/license-0BSD-ca8a04)

OpenAPI-driven command-line client for searching, browsing, and invoking the full EMBL-EBI OLS4 ontology API from the shell.

</div>

## Map
- [Install](#install)
- [Functionality](#functionality)
- [Configuration](#configuration)
- [Quick Start](#quick-start)
- [Credits](#credits)

## Install

```bash
uv tool install .    # install the CLI
ols --help           # inspect the command surface
```

For local development:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Functionality

### Ontology Search
- `ols search`: search terms/entities with optional ontology restriction, exact mode, field selection, paging, and `text`/`json`/`jsonl` output.
- `ols suggest`: autocomplete-like lookup for partial queries.
- `ols term`: fetch one ontology term by ontology id and full IRI.

### Ontology Browse
- `ols ontologies`: list ontology metadata with paging and output format controls.
- `ols ontology`: fetch one ontology by ontology id.

### Full OpenAPI Coverage
- `ols ops`: list all operations from `https://www.ebi.ac.uk/ols4/v3/api-docs` with filtering by method/path.
- `ols call`: generic operation executor by `operationId` (`--path-param`, `--query-param`, `--header`, `--json-body`).
- `ols api`: dedicated bespoke command per `operationId` with generated operation-specific flags.
- `ols raw`: direct GET escape hatch for path/query access.

### Output and Exit Behavior
- Output formats: `json` everywhere, plus `text`/`jsonl` on curated list/search commands.
- Exit codes:
  - `0`: success
  - `2`: usage/config/validation errors
  - `1`: runtime/network/upstream failures

## Configuration

Auth model: none (public OLS API).

Config precedence (highest to lowest):

1. CLI flags: `--base-url`, `--timeout`, `--openapi-spec`
2. environment: `OLS_BASE_URL`, `OLS_TIMEOUT`
3. config file: `$XDG_CONFIG_HOME/ols-cli/config.json` or `~/.config/ols-cli/config.json`
4. defaults

Example config file:

```json
{
  "base_url": "https://www.ebi.ac.uk/ols4",
  "timeout": 20
}
```

## Quick Start

```bash
# Curated commands
ols ontologies --size 5
ols search diabetes --ontology efo --size 3 --format jsonl
ols term efo "http://www.ebi.ac.uk/efo/EFO_0000408"

# Enumerate full API operation surface
ols ops --format jsonl

# Generic operation call by operationId
ols call getOntology_1 --path-param onto=efo
ols call search --query-param q=diabetes --query-param ontology=efo --query-param rows=1

# Dedicated per-operation command UX (generated flags)
ols api getOntology_1 -- --onto efo
ols api search -- --q diabetes --ontology efo --rows 1

# Request body endpoint
ols api tagText -- --content-type application/json --body '{"text":"diabetes and insulin"}'
```

## Credits

This client is built for the EMBL-EBI Ontology Lookup Service (OLS4) API and is not affiliated with EMBL-EBI.

Credit goes to EMBL-EBI and ontology maintainers for the ontology data, API, and documentation this tool depends on.
