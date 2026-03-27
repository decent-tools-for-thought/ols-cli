"""Configuration loading for the OLS CLI."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://www.ebi.ac.uk/ols4"
DEFAULT_TIMEOUT = 20.0


class ConfigError(ValueError):
    """Raised when configuration is invalid."""


@dataclass(frozen=True)
class AppConfig:
    """Resolved application configuration."""

    base_url: str = DEFAULT_BASE_URL
    timeout: float = DEFAULT_TIMEOUT


def default_config_path() -> Path:
    """Return XDG-style config path."""
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / "ols-cli" / "config.json"
    return Path.home() / ".config" / "ols-cli" / "config.json"


def _load_file_config(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"failed to read config file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in config file {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"config file {path} must contain a JSON object")
    return raw


def _normalize_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    if not base_url:
        raise ConfigError("base URL cannot be empty")
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        raise ConfigError("base URL must start with http:// or https://")
    return base_url


def _parse_timeout(value: object) -> float:
    if isinstance(value, int | float):
        timeout = float(value)
    elif isinstance(value, str):
        try:
            timeout = float(value.strip())
        except ValueError as exc:
            raise ConfigError("timeout must be a number") from exc
    else:
        raise ConfigError("timeout must be numeric")

    if timeout <= 0:
        raise ConfigError("timeout must be > 0")
    return timeout


def load_config(
    *,
    base_url: str | None,
    timeout: float | None,
    config_path: Path | None,
) -> AppConfig:
    """Resolve config values from flags, env, and optional file.

    Precedence: CLI flags > environment variables > config file > defaults.
    """
    cfg_path = config_path if config_path is not None else default_config_path()
    file_cfg = _load_file_config(cfg_path)

    env_base = os.environ.get("OLS_BASE_URL")
    env_timeout = os.environ.get("OLS_TIMEOUT")

    resolved_base = base_url or env_base or str(file_cfg.get("base_url", DEFAULT_BASE_URL))

    timeout_source: object
    if timeout is not None:
        timeout_source = timeout
    elif env_timeout is not None:
        timeout_source = env_timeout
    else:
        timeout_source = file_cfg.get("timeout", DEFAULT_TIMEOUT)

    return AppConfig(
        base_url=_normalize_base_url(resolved_base), timeout=_parse_timeout(timeout_source)
    )
