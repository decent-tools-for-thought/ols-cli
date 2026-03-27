from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def clean_ols_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key in ["OLS_BASE_URL", "OLS_TIMEOUT", "XDG_CONFIG_HOME"]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
