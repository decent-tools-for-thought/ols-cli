from __future__ import annotations

import json
from pathlib import Path

import pytest

from ols_cli.config import ConfigError, load_config


def test_load_config_defaults() -> None:
    cfg = load_config(base_url=None, timeout=None, config_path=Path("/nonexistent-config.json"))
    assert cfg.base_url == "https://www.ebi.ac.uk/ols4"
    assert cfg.timeout == 20.0


def test_load_config_env_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps({"base_url": "https://example.org", "timeout": 1}), encoding="utf-8"
    )
    monkeypatch.setenv("OLS_BASE_URL", "https://env.example")
    monkeypatch.setenv("OLS_TIMEOUT", "9")

    cfg = load_config(base_url=None, timeout=None, config_path=cfg_path)
    assert cfg.base_url == "https://env.example"
    assert cfg.timeout == 9.0


def test_load_config_cli_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLS_BASE_URL", "https://env.example")
    monkeypatch.setenv("OLS_TIMEOUT", "3")

    cfg = load_config(base_url="https://flag.example", timeout=15.0, config_path=Path("/nope.json"))
    assert cfg.base_url == "https://flag.example"
    assert cfg.timeout == 15.0


def test_load_config_invalid_timeout(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"timeout": "x"}), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(base_url=None, timeout=None, config_path=cfg_path)
